# IMAP Service – checks bounces and replies via Hostinger IMAP
# Replaces Gmail API bounce checking for outbound emails sent via Hostinger SMTP.
# Gmail API is still used for checking replies to martin.foerster@gmail.com (Reply-To).
from __future__ import annotations

import email
import imaplib
import logging
import re
import ssl
from datetime import datetime, timedelta
from email.header import decode_header
from typing import Optional

logger = logging.getLogger("harpo.imap")


def _decode_header_value(raw: str) -> str:
    """Decode MIME-encoded header values."""
    if not raw:
        return ""
    parts = decode_header(raw)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _imap_login(host: str, port: int, user: str, password: str) -> imaplib.IMAP4_SSL:
    """Login to IMAP server, handling non-ASCII passwords via AUTHENTICATE PLAIN."""
    ctx = ssl.create_default_context()
    conn = imaplib.IMAP4_SSL(host, port, ssl_context=ctx)
    try:
        # Try standard login first
        conn.login(user, password)
    except imaplib.IMAP4.error:
        # Fall back to AUTHENTICATE PLAIN for non-ASCII passwords
        logger.info("Using AUTHENTICATE PLAIN for non-ASCII password")

        def auth_plain(response):
            return f"\0{user}\0{password}".encode("utf-8")

        conn.authenticate("PLAIN", auth_plain)
    return conn


def check_bounces(
    host: str,
    port: int,
    user: str,
    password: str,
    sent_emails: list[dict],
    days_back: int = 30,
) -> list[dict]:
    """Check Hostinger IMAP for bounce-back messages.

    sent_emails: [{"to": "recipient@example.com", "subject": "...", "lead_id": "..."}]
    Returns: [{"to": "...", "lead_id": "...", "bounce_type": "...", "details": "...", "date": "..."}]
    """
    bounces = []
    try:
        conn = _imap_login(host, port, user, password)
    except Exception as e:
        logger.error(f"IMAP login failed: {e}")
        return []

    try:
        conn.select("INBOX")

        # Search for bounce-like messages
        since_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%d-%b-%Y")
        search_queries = [
            f'(FROM "mailer-daemon" SINCE {since_date})',
            f'(FROM "postmaster" SINCE {since_date})',
            f'(SUBJECT "Delivery Status" SINCE {since_date})',
            f'(SUBJECT "Undeliverable" SINCE {since_date})',
            f'(SUBJECT "Mail Delivery Failed" SINCE {since_date})',
            f'(SUBJECT "Delivery Failure" SINCE {since_date})',
            f'(SUBJECT "Returned mail" SINCE {since_date})',
        ]

        seen_ids: set[str] = set()
        bounce_messages = []

        for query in search_queries:
            try:
                status, data = conn.search(None, query)
                if status != "OK" or not data[0]:
                    continue
                for msg_id in data[0].split():
                    msg_id_str = msg_id.decode()
                    if msg_id_str in seen_ids:
                        continue
                    seen_ids.add(msg_id_str)
                    status, msg_data = conn.fetch(msg_id, "(RFC822)")
                    if status != "OK":
                        continue
                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)
                    bounce_messages.append(msg)
            except Exception as e:
                logger.warning(f"IMAP search failed for query '{query}': {e}")
                continue

        # Build a lookup of sent emails
        sent_lookup = {}
        for sent in sent_emails:
            sent_lookup[sent["to"].lower()] = sent

        # Parse bounces and match to sent emails
        email_pattern = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

        for msg in bounce_messages:
            subject = _decode_header_value(msg.get("Subject", ""))
            date_str = msg.get("Date", "")

            # Extract body text
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    ct = part.get_content_type()
                    if ct in ("text/plain", "message/delivery-status"):
                        try:
                            body += part.get_payload(decode=True).decode("utf-8", errors="replace")
                        except Exception:
                            pass
            else:
                try:
                    body = msg.get_payload(decode=True).decode("utf-8", errors="replace")
                except Exception:
                    body = str(msg.get_payload())

            combined = (subject + " " + body).lower()

            # Determine bounce type
            bounce_type = "unknown"
            if any(kw in combined for kw in ["user unknown", "no such user", "does not exist", " 550 ", "550-"]):
                bounce_type = "hard_bounce_user_unknown"
            elif any(kw in combined for kw in ["mailbox full", "quota exceeded", "over quota"]):
                bounce_type = "soft_bounce_mailbox_full"
            elif any(kw in combined for kw in ["connection refused", "host not found", "domain not found", "no mx"]):
                bounce_type = "hard_bounce_domain_error"
            elif any(kw in combined for kw in ["spam", "rejected", "blocked", "blacklist"]):
                bounce_type = "soft_bounce_rejected"
            elif any(kw in combined for kw in ["delivery status", "undeliverable", "failed", "failure"]):
                bounce_type = "hard_bounce_undeliverable"

            # Match to a sent email
            found_emails = email_pattern.findall(body)
            matched_email = ""
            matched_lead_id = ""

            for found in found_emails:
                found_lower = found.lower()
                if found_lower in sent_lookup:
                    matched_email = found_lower
                    matched_lead_id = sent_lookup[found_lower].get("lead_id", "")
                    break

            if matched_email:
                bounces.append({
                    "to": matched_email,
                    "lead_id": matched_lead_id,
                    "bounce_type": bounce_type,
                    "details": subject[:200],
                    "date": date_str,
                })

    except Exception as e:
        logger.error(f"IMAP bounce check failed: {e}")
    finally:
        try:
            conn.logout()
        except Exception:
            pass

    logger.info(f"IMAP bounce check: found {len(bounces)} bounces out of {len(seen_ids)} bounce-like messages")
    return bounces


def check_replies_imap(
    host: str,
    port: int,
    user: str,
    password: str,
    sent_emails: list[dict],
    days_back: int = 30,
) -> list[dict]:
    """Check Hostinger IMAP for reply messages to mf@harpocrates-corp.com.

    This is a fallback — primary reply checking uses Gmail API (since Reply-To = gmail).
    But some recipients may reply to the From address directly.

    sent_emails: [{"to": "...", "subject": "...", "lead_id": "..."}]
    Returns: [{"from": "...", "lead_id": "...", "subject": "...", "body": "...", "date": "..."}]
    """
    replies = []
    try:
        conn = _imap_login(host, port, user, password)
    except Exception as e:
        logger.error(f"IMAP login failed for reply check: {e}")
        return []

    try:
        conn.select("INBOX")
        since_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%d-%b-%Y")

        # Build set of sender emails to look for
        sender_emails = {s["to"].lower() for s in sent_emails if s.get("to")}
        sent_lookup = {s["to"].lower(): s for s in sent_emails}

        for sender_email in sender_emails:
            try:
                query = f'(FROM "{sender_email}" SINCE {since_date})'
                status, data = conn.search(None, query)
                if status != "OK" or not data[0]:
                    continue
                for msg_id in data[0].split()[:5]:  # max 5 per sender
                    status, msg_data = conn.fetch(msg_id, "(RFC822)")
                    if status != "OK":
                        continue
                    raw = msg_data[0][1]
                    msg = email.message_from_bytes(raw)

                    from_addr = _decode_header_value(msg.get("From", ""))
                    subject = _decode_header_value(msg.get("Subject", ""))
                    date_str = msg.get("Date", "")

                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                try:
                                    body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                                except Exception:
                                    pass
                                break
                    else:
                        try:
                            body = msg.get_payload(decode=True).decode("utf-8", errors="replace")
                        except Exception:
                            pass

                    sent_info = sent_lookup.get(sender_email, {})
                    replies.append({
                        "from": from_addr,
                        "lead_id": sent_info.get("lead_id", ""),
                        "subject": subject,
                        "body": body[:2000],
                        "date": date_str,
                    })
            except Exception as e:
                logger.warning(f"Reply search failed for {sender_email}: {e}")
                continue

    except Exception as e:
        logger.error(f"IMAP reply check failed: {e}")
    finally:
        try:
            conn.logout()
        except Exception:
            pass

    logger.info(f"IMAP reply check: found {len(replies)} replies")
    return replies
