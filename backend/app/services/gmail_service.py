# GmailService – ported from Swift GmailService.swift
# Sends emails via Gmail API using OAuth2 access tokens.
from __future__ import annotations

import base64
import logging
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
from uuid import uuid4

import httpx

logger = logging.getLogger("harpo.gmail")

GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


def _build_mime_email(to: str, from_addr: str, subject: str, body: str) -> str:
    """Build a multipart/alternative MIME email with plain text + HTML (professional signature).
    Uses Python's email library for correct RFC 2045 encoding (proper base64 line wrapping).
    Includes X-Harpo-Campaign header for campaign tracking."""

    # Unsubscribe footer
    unsub_url = f"mailto:unsubscribe@harpocrates-corp.com?subject=Unsubscribe&body=Please%20remove%20{to}"
    body_with_opt_out = body + f"\n\n---\nTo unsubscribe from future emails, reply with 'Unsubscribe' or click: {unsub_url}"

    # HTML body: convert paragraphs (double newline) and line breaks (single newline)
    html_paragraphs = "\n".join(
        f'<p style="margin:0 0 14px 0;line-height:1.7;color:#2d3748;font-size:14px;font-family:Arial,Helvetica,sans-serif;">'
        f'{"<br>".join(p.split(chr(10)))}</p>'
        for p in body.split("\n\n")
    )
    logo_url = "https://new.harpocrates-corp.com/harpocrates-logo.png"
    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background-color:#f7f7f7;">
<div style="max-width:600px;margin:0 auto;padding:24px;background-color:#ffffff;">
{html_paragraphs}
<!-- Signature -->
<table cellpadding="0" cellspacing="0" border="0" style="margin-top:32px;border-top:3px solid #1a365d;padding-top:20px;width:100%;font-family:Arial,Helvetica,sans-serif;">
<tr>
<td style="vertical-align:top;padding-right:18px;width:60px;">
<img src="{logo_url}" alt="Harpocrates" width="52" height="52" style="display:block;border:0;border-radius:6px;">
</td>
<td style="vertical-align:top;">
<p style="margin:0 0 2px 0;font-size:16px;font-weight:bold;color:#1a365d;letter-spacing:0.3px;font-family:Arial,Helvetica,sans-serif;">Martin F\u00f6rster</p>
<p style="margin:0 0 10px 0;font-size:12px;color:#4a5568;text-transform:uppercase;letter-spacing:0.8px;font-family:Arial,Helvetica,sans-serif;">CEO &amp; Founder</p>
<p style="margin:0 0 3px 0;font-size:13px;font-weight:600;color:#2d3748;font-family:Arial,Helvetica,sans-serif;">Harpocrates Solutions GmbH</p>
<table cellpadding="0" cellspacing="0" border="0" style="margin-top:6px;">
<tr><td style="padding:2px 8px 2px 0;font-size:12px;color:#718096;font-family:Arial,Helvetica,sans-serif;">Tel</td><td style="padding:2px 0;font-size:12px;color:#2d3748;font-family:Arial,Helvetica,sans-serif;"><a href="tel:+491726348377" style="color:#2d3748;text-decoration:none;">+49 172 6348377</a></td></tr>
<tr><td style="padding:2px 8px 2px 0;font-size:12px;color:#718096;font-family:Arial,Helvetica,sans-serif;">Mail</td><td style="padding:2px 0;font-size:12px;font-family:Arial,Helvetica,sans-serif;"><a href="mailto:mf@harpocrates-corp.com" style="color:#2b6cb0;text-decoration:none;">mf@harpocrates-corp.com</a></td></tr>
<tr><td style="padding:2px 8px 2px 0;font-size:12px;color:#718096;font-family:Arial,Helvetica,sans-serif;">Web</td><td style="padding:2px 0;font-size:12px;font-family:Arial,Helvetica,sans-serif;"><a href="https://www.harpocrates-corp.com" style="color:#2b6cb0;text-decoration:none;">www.harpocrates-corp.com</a></td></tr>
</table>
<p style="margin:6px 0 0 0;font-size:11px;color:#a0aec0;font-family:Arial,Helvetica,sans-serif;">Berlin, Germany</p>
</td>
</tr>
</table>
</div>
<div style="max-width:600px;margin:0 auto;padding:12px 24px;">
<p style="margin:0;font-size:10px;color:#a0aec0;font-family:Arial,Helvetica,sans-serif;">
<a href="{unsub_url}" style="color:#a0aec0;text-decoration:underline;">Abmelden / Unsubscribe</a>
</p>
</div>
</body>
</html>"""

    # Build MIME message using Python email library (handles RFC 2045 base64 line wrapping)
    msg = MIMEMultipart("alternative")
    msg["From"] = f"Martin Foerster <{from_addr}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg["X-Harpo-Campaign"] = "comply-reg"
    msg["List-Unsubscribe"] = f"<mailto:unsubscribe@harpocrates-corp.com?subject=Unsubscribe>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

    # Plain text part
    part_plain = MIMEText(body_with_opt_out, "plain", "utf-8")
    msg.attach(part_plain)

    # HTML part
    part_html = MIMEText(html, "html", "utf-8")
    msg.attach(part_html)

    return msg.as_string()


async def _gmail_api_send(json_data: dict, access_token: str) -> dict:
    """POST to Gmail messages/send. Returns response dict with id and threadId, or raises."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{GMAIL_BASE}/messages/send",
            json=json_data,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
        )
    if resp.status_code == 200:
        return resp.json()
    elif resp.status_code == 401:
        raise PermissionError("Gmail token expired (401)")
    elif resp.status_code == 403:
        raise PermissionError("No Gmail permission. Check API scopes.")
    elif resp.status_code == 429:
        raise Exception("Gmail rate limit reached.")
    else:
        raise Exception(f"Gmail HTTP {resp.status_code}: {resp.text[:200]}")


async def send_email(
    to: str,
    from_addr: str,
    subject: str,
    body: str,
    access_token: str,
) -> dict:
    """Send an email via Gmail API. Returns dict with 'msg_id' and 'thread_id'."""
    raw_mime = _build_mime_email(to, from_addr, subject, body)
    # URL-safe base64
    encoded = (
        base64.urlsafe_b64encode(raw_mime.encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )
    payload = {"raw": encoded}
    result = await _gmail_api_send(payload, access_token)
    msg_id = result.get("id", "sent")
    thread_id = result.get("threadId", "")
    logger.info(f"Email sent to {to}, ID: {msg_id}, threadId: {thread_id}")
    return {"msg_id": msg_id, "thread_id": thread_id}


# ─── Check Replies ───────────────────────────────────────────────

async def search_gmail(
    query: str,
    access_token: str,
    max_results: int = 10,
) -> list[dict]:
    """Search Gmail and return message details."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{GMAIL_BASE}/messages",
            params={"q": query, "maxResults": str(max_results)},
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code != 200:
        logger.warning(f"Gmail search failed: {resp.text[:200]}")
        return []

    data = resp.json()
    messages = data.get("messages", [])
    results = []
    for msg_stub in messages:
        msg_id = msg_stub.get("id")
        if msg_id:
            detail = await _fetch_message(msg_id, access_token)
            if detail:
                results.append(detail)
    return results


async def _fetch_message(msg_id: str, access_token: str) -> Optional[dict]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{GMAIL_BASE}/messages/{msg_id}?format=full",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code != 200:
        return None

    data = resp.json()
    payload = data.get("payload", {})
    headers = payload.get("headers", [])

    from_addr = ""
    subject = ""
    date = ""
    for h in headers:
        name = (h.get("name") or "").lower()
        if name == "from":
            from_addr = h.get("value", "")
        elif name == "subject":
            subject = h.get("value", "")
        elif name == "date":
            date = h.get("value", "")

    snippet = data.get("snippet", "")
    body = snippet

    parts = payload.get("parts", [])
    if parts:
        for part in parts:
            if part.get("mimeType") == "text/plain":
                b64 = part.get("body", {}).get("data", "")
                if b64:
                    padded = b64.replace("-", "+").replace("_", "/")
                    try:
                        body = base64.b64decode(padded).decode("utf-8")
                    except Exception:
                        pass
    else:
        b64 = payload.get("body", {}).get("data", "")
        if b64:
            padded = b64.replace("-", "+").replace("_", "/")
            try:
                body = base64.b64decode(padded).decode("utf-8")
            except Exception:
                pass

    return {
        "id": msg_id,
        "from": from_addr,
        "subject": subject,
        "date": date,
        "snippet": snippet,
        "body": body,
    }


async def check_replies(
    sent_subjects: list[str],
    lead_emails: list[str],
    access_token: str,
    subject_tag: str = "",
    thread_ids: list[str] | None = None,
) -> list[dict]:
    """Check for replies to sent emails.
    Primary method: search by Gmail thread IDs (most accurate).
    Fallback: search by lead email addresses."""
    all_replies = []
    seen_ids: set[str] = set()

    # Primary: Thread-based search (most reliable)
    if thread_ids:
        for tid in thread_ids:
            if not tid:
                continue
            try:
                thread_msgs = await _fetch_thread_replies(tid, access_token)
                for msg in thread_msgs:
                    if msg["id"] in seen_ids:
                        continue
                    seen_ids.add(msg["id"])
                    # Skip our own sent messages
                    if "mf@harpocrates-corp.com" in msg["from"].lower():
                        continue
                    all_replies.append(msg)
            except Exception as e:
                logger.warning(f"Thread fetch failed for {tid}: {e}")

    # Fallback: search by lead email addresses
    if not thread_ids:
        for email in lead_emails:
            email_clean = email.lower().strip()
            if not email_clean:
                continue
            query = f"from:{email_clean} newer_than:90d"
            msgs = await search_gmail(query, access_token, max_results=5)
            for msg in msgs:
                if msg["id"] in seen_ids:
                    continue
                seen_ids.add(msg["id"])
                if "mf@harpocrates-corp.com" in msg["from"].lower():
                    continue
                all_replies.append(msg)

    return all_replies


async def _fetch_thread_replies(thread_id: str, access_token: str) -> list[dict]:
    """Fetch all messages in a Gmail thread and return non-first messages (replies)."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{GMAIL_BASE}/threads/{thread_id}?format=full",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code != 200:
        logger.warning(f"Thread fetch {thread_id} failed: {resp.status_code}")
        return []

    data = resp.json()
    messages = data.get("messages", [])

    # Skip the first message (our sent email), only return replies
    if len(messages) <= 1:
        return []

    results = []
    for msg_data in messages[1:]:  # skip first (our outbound)
        payload = msg_data.get("payload", {})
        headers = payload.get("headers", [])

        from_addr = ""
        subject = ""
        date = ""
        for h in headers:
            name = (h.get("name") or "").lower()
            if name == "from":
                from_addr = h.get("value", "")
            elif name == "subject":
                subject = h.get("value", "")
            elif name == "date":
                date = h.get("value", "")

        snippet = msg_data.get("snippet", "")
        body = snippet

        parts = payload.get("parts", [])
        if parts:
            for part in parts:
                if part.get("mimeType") == "text/plain":
                    b64 = part.get("body", {}).get("data", "")
                    if b64:
                        padded = b64.replace("-", "+").replace("_", "/")
                        try:
                            body = base64.b64decode(padded).decode("utf-8")
                        except Exception:
                            pass
        else:
            b64 = payload.get("body", {}).get("data", "")
            if b64:
                padded = b64.replace("-", "+").replace("_", "/")
                try:
                    body = base64.b64decode(padded).decode("utf-8")
                except Exception:
                    pass

        results.append({
            "id": msg_data.get("id", ""),
            "from": from_addr,
            "subject": subject,
            "date": date,
            "snippet": snippet,
            "body": body,
        })

    return results


# ─── Bounce Detection ────────────────────────────────────────────

async def check_bounces(
    sent_emails: list[dict],
    access_token: str,
) -> list[dict]:
    """Check for bounce-back messages. sent_emails: [{to, subject}]."""
    bounces = []
    seen_ids: set[str] = set()

    bounce_queries = [
        'subject:"Delivery Status Notification" newer_than:30d',
        'subject:"Undeliverable" newer_than:30d',
        'subject:"Mail Delivery Failed" newer_than:30d',
        'subject:"Delivery Failure" newer_than:30d',
        'subject:"Returned mail" newer_than:30d',
        "from:mailer-daemon newer_than:30d",
        "from:postmaster newer_than:30d",
    ]

    for query in bounce_queries:
        msgs = await search_gmail(query, access_token, max_results=20)
        for msg in msgs:
            if msg["id"] in seen_ids:
                continue
            seen_ids.add(msg["id"])
            combined = (msg.get("subject", "") + " " + msg.get("body", "") + " " + msg.get("snippet", "")).lower()

            bounce_type = "unknown"
            if "user unknown" in combined or "no such user" in combined or "does not exist" in combined or "550" in combined:
                bounce_type = "hard_bounce_user_unknown"
            elif "mailbox full" in combined or "quota exceeded" in combined:
                bounce_type = "soft_bounce_mailbox_full"
            elif "connection refused" in combined or "host not found" in combined or "domain not found" in combined:
                bounce_type = "hard_bounce_domain_error"
            elif "spam" in combined or "rejected" in combined or "blocked" in combined:
                bounce_type = "soft_bounce_rejected"
            elif "delivery status" in combined or "undeliverable" in combined or "failed" in combined:
                bounce_type = "hard_bounce_undeliverable"

            matched_email = ""
            for sent in sent_emails:
                if sent["to"].lower() in combined:
                    matched_email = sent["to"]
                    break

            if not matched_email:
                # Try regex extraction
                pattern = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
                match = re.search(pattern, msg.get("body", ""))
                if match:
                    extracted = match.group().lower()
                    if "harpocrates-corp.com" not in extracted:
                        matched_email = extracted

            if matched_email and not any(b["email"].lower() == matched_email.lower() for b in bounces):
                bounces.append({"email": matched_email, "bounce_type": bounce_type})

    return bounces
