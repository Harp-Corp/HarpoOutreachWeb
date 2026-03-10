# SMTP Email Service – sends emails via Hostinger SMTP (replaces Gmail API sending)
# Keeps Gmail API for reading replies/bounces only.
# v2.0: Added tracking pixel injection + click wrapping
from __future__ import annotations

import base64
import logging
import re
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
from uuid import uuid4

logger = logging.getLogger("harpo.smtp")


def _inject_tracking(html: str, tracking_id: str | None, backend_url: str = "") -> str:
    """Inject tracking pixel and wrap links for click tracking."""
    if not tracking_id or not backend_url:
        return html

    # 1. Inject open-tracking pixel before </body>
    pixel_url = f"{backend_url}/api/tracking/pixel/{tracking_id}.png"
    pixel_tag = f'<img src="{pixel_url}" width="1" height="1" style="display:none;width:1px;height:1px;" alt="" />'
    if "</body>" in html:
        html = html.replace("</body>", f"{pixel_tag}\n</body>")
    else:
        html += pixel_tag

    # 2. Wrap links for click tracking (skip mailto:, tel:, unsubscribe, and tracking URLs)
    def wrap_link(match):
        url = match.group(1)
        # Don't wrap mailto, tel, unsubscribe links, or our own tracking URLs
        if any(skip in url.lower() for skip in ["mailto:", "tel:", "unsubscribe", "/tracking/", backend_url]):
            return match.group(0)
        tracked_url = f"{backend_url}/api/tracking/click/{tracking_id}?url={url}"
        return f'href="{tracked_url}"'

    html = re.sub(r'href="(https?://[^"]+)"', wrap_link, html)

    return html


def _build_mime_email(
    to: str,
    from_addr: str,
    subject: str,
    body: str,
    reply_to: str | None = None,
    tracking_id: str | None = None,
    backend_url: str = "",
) -> MIMEMultipart:
    """Build a multipart/alternative MIME email with plain text + HTML (professional signature).
    Includes X-Harpo-Campaign header for campaign tracking.
    reply_to: if set, adds Reply-To header so replies go to a specific inbox.
    tracking_id: if set, injects open-tracking pixel and click-tracking links.
    backend_url: backend base URL for tracking endpoints."""

    # Unsubscribe footer – uses the sender domain's info address
    from_domain = from_addr.split("@")[1] if "@" in from_addr else "harpocrates-corp.com"
    unsub_email = f"info@{from_domain}"
    unsub_url = f"mailto:{unsub_email}?subject=Unsubscribe&body=Please%20remove%20{to}"
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
<tr><td style="padding:2px 8px 2px 0;font-size:12px;color:#718096;font-family:Arial,Helvetica,sans-serif;">Mail</td><td style="padding:2px 0;font-size:12px;font-family:Arial,Helvetica,sans-serif;"><a href="mailto:{from_addr}" style="color:#2b6cb0;text-decoration:none;">{from_addr}</a></td></tr>
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

    # Inject tracking if available
    if tracking_id and backend_url:
        html = _inject_tracking(html, tracking_id, backend_url)

    # Build MIME message
    msg = MIMEMultipart("alternative")
    msg["From"] = f"Martin Foerster <{from_addr}>"
    msg["To"] = to
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["X-Harpo-Campaign"] = "comply-reg"
    msg["List-Unsubscribe"] = f"<mailto:{unsub_email}?subject=Unsubscribe>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

    # Plain text part
    part_plain = MIMEText(body_with_opt_out, "plain", "utf-8")
    msg.attach(part_plain)

    # HTML part
    part_html = MIMEText(html, "html", "utf-8")
    msg.attach(part_html)

    return msg


def send_email(
    to: str,
    from_addr: str,
    subject: str,
    body: str,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    reply_to: str | None = None,
    tracking_id: str | None = None,
    backend_url: str = "",
) -> dict:
    """Send an email via SMTP (Hostinger). Returns dict with 'msg_id'.

    This is synchronous — smtplib is blocking. Called from async routes
    via asyncio.to_thread() or run_in_executor().
    tracking_id: if provided, injects open/click tracking into the HTML.
    backend_url: base URL of backend for tracking pixel/click endpoints.
    """
    msg = _build_mime_email(
        to, from_addr, subject, body,
        reply_to=reply_to,
        tracking_id=tracking_id,
        backend_url=backend_url,
    )

    # Generate a unique message ID for tracking
    msg_id = f"harpo-{uuid4().hex[:12]}@{from_addr.split('@')[1]}"
    msg["Message-ID"] = f"<{msg_id}>"

    context = ssl.create_default_context()

    try:
        if smtp_port == 465:
            # SSL connection
            with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=30) as smtp:
                smtp.ehlo()
                _smtp_login(smtp, smtp_user, smtp_password)
                smtp.sendmail(from_addr, [to], msg.as_string())
                logger.info(f"Email sent via SMTP to {to}, msg_id={msg_id}, tracking={tracking_id or 'none'}")
        elif smtp_port == 587:
            # STARTTLS connection
            with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
                _smtp_login(smtp, smtp_user, smtp_password)
                smtp.sendmail(from_addr, [to], msg.as_string())
                logger.info(f"Email sent via SMTP to {to}, msg_id={msg_id}, tracking={tracking_id or 'none'}")
        else:
            raise ValueError(f"Unsupported SMTP port: {smtp_port}. Use 465 (SSL) or 587 (STARTTLS).")
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP auth failed: {e}")
        raise PermissionError(f"SMTP-Authentifizierung fehlgeschlagen: {e}")
    except smtplib.SMTPRecipientsRefused as e:
        logger.error(f"Recipient refused {to}: {e}")
        raise Exception(f"Empfaenger abgelehnt: {to}")
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error sending to {to}: {e}")
        raise Exception(f"SMTP-Fehler: {e}")

    return {"msg_id": msg_id, "thread_id": ""}


def _smtp_login(smtp: smtplib.SMTP, user: str, password: str) -> None:
    """Login to SMTP server, handling non-ASCII passwords via AUTH LOGIN with base64."""
    try:
        # Try standard login first
        smtp.login(user, password)
    except UnicodeEncodeError:
        # Non-ASCII password — use AUTH LOGIN with base64 encoding
        logger.info("Using AUTH LOGIN for non-ASCII password")
        smtp.docmd("AUTH", "LOGIN")
        smtp.docmd(base64.b64encode(user.encode("utf-8")).decode("ascii"))
        code, msg = smtp.docmd(base64.b64encode(password.encode("utf-8")).decode("ascii"))
        if code != 235:
            raise smtplib.SMTPAuthenticationError(code, msg)
