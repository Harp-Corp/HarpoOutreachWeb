# Analytics routes – email tracking, reply detection, campaign analytics
from __future__ import annotations

import json
import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..models.db import LeadDB, get_db
from ..services import database_service as db_svc
from ..services import gmail_service as gmail
from .email_pipeline import _get_access_token, _refresh_google_token, SUBJECT_TAG

logger = logging.getLogger("harpo.analytics")

router = APIRouter(prefix="/analytics", tags=["Analytics"])


# ─── Sent Emails Overview ────────────────────────────────────────

@router.get("/sent-emails")
async def list_sent_emails(db: Session = Depends(get_db)):
    """Return all leads where an email was sent, with full email content and status."""
    leads = db_svc.load_leads(db)
    sent = []
    for lead in leads:
        if not lead.date_email_sent:
            continue
        # Parse drafted email
        email_data = {}
        if lead.drafted_email_json:
            try:
                email_data = json.loads(lead.drafted_email_json)
            except Exception:
                pass
        # Parse follow-up email
        follow_up_data = {}
        if lead.follow_up_email_json:
            try:
                follow_up_data = json.loads(lead.follow_up_email_json)
            except Exception:
                pass

        sent.append({
            "id": str(lead.id),
            "name": lead.name,
            "title": lead.title,
            "company": lead.company,
            "email": lead.email,
            "status": lead.status,
            "delivery_status": lead.delivery_status,
            "date_email_sent": lead.date_email_sent.isoformat() if lead.date_email_sent else None,
            "date_follow_up_sent": lead.date_follow_up_sent.isoformat() if lead.date_follow_up_sent else None,
            "subject": email_data.get("subject", ""),
            "body": email_data.get("body", ""),
            "follow_up_subject": follow_up_data.get("subject", ""),
            "follow_up_body": follow_up_data.get("body", ""),
            "reply_received": lead.reply_received or "",
            "opted_out": lead.opted_out,
        })

    # Sort by sent date descending
    sent.sort(key=lambda x: x["date_email_sent"] or "", reverse=True)
    return {"data": sent, "total": len(sent)}


# ─── Check Replies via Gmail ────────────────────────────────────

@router.post("/check-replies")
async def check_replies(db: Session = Depends(get_db)):
    """Check Gmail for replies to sent outreach emails.
    Updates lead records with reply content and status."""
    access_token = _get_access_token(db)
    leads = db_svc.load_leads(db)
    sent_leads = [l for l in leads if l.date_email_sent]

    if not sent_leads:
        return {"success": True, "message": "Keine gesendeten E-Mails.", "replies": 0, "unsubscribes": 0}

    # Collect subjects and emails for search
    subjects = []
    lead_emails = []
    for lead in sent_leads:
        if lead.drafted_email_json:
            try:
                draft = json.loads(lead.drafted_email_json)
                subj = draft.get("subject", "")
                if subj:
                    subjects.append(subj)
            except Exception:
                pass
        if lead.email:
            lead_emails.append(lead.email)

    # Search Gmail for replies
    replies_found = 0
    unsubscribes_found = 0
    bounces_found = 0
    results = []

    try:
        # Check replies
        reply_msgs = await gmail.check_replies(subjects, lead_emails, access_token, subject_tag=SUBJECT_TAG)

        for msg in reply_msgs:
            from_addr = msg.get("from", "").lower()
            msg_body = (msg.get("body", "") + " " + msg.get("snippet", "")).lower()
            msg_subject = msg.get("subject", "")

            # Match to a lead
            matched_lead = None
            for lead in sent_leads:
                if lead.email and lead.email.lower() in from_addr:
                    matched_lead = lead
                    break

            if not matched_lead:
                continue

            # Detect unsubscribe
            is_unsub = any(kw in msg_body for kw in [
                "unsubscribe", "abmelden", "opt out", "opt-out",
                "remove me", "no more", "stop", "abbestellen",
            ])

            if is_unsub:
                matched_lead.status = "Do Not Contact"
                matched_lead.opted_out = True
                matched_lead.opt_out_date = datetime.utcnow()
                matched_lead.reply_received = f"[UNSUBSCRIBE] {msg.get('snippet', '')[:200]}"
                unsubscribes_found += 1
                # Add to blocklist
                db_svc.add_to_blocklist(db, matched_lead.email, reason="Unsubscribe-Antwort")
            else:
                if not matched_lead.reply_received:
                    matched_lead.status = "Replied"
                matched_lead.reply_received = msg.get("body", msg.get("snippet", ""))[:1000]
                replies_found += 1

            matched_lead.updated_at = datetime.utcnow()
            results.append({
                "lead_id": str(matched_lead.id),
                "name": matched_lead.name,
                "email": matched_lead.email,
                "type": "unsubscribe" if is_unsub else "reply",
                "subject": msg_subject,
                "snippet": msg.get("snippet", "")[:200],
                "date": msg.get("date", ""),
            })

        # Check bounces
        sent_email_list = [{"to": l.email, "subject": ""} for l in sent_leads if l.email]
        try:
            bounces = await gmail.check_bounces(sent_email_list, access_token)
            for bounce in bounces:
                bounce_email = bounce.get("email", "").lower()
                for lead in sent_leads:
                    if lead.email and lead.email.lower() == bounce_email:
                        lead.delivery_status = "Bounced"
                        lead.updated_at = datetime.utcnow()
                        bounces_found += 1
                        results.append({
                            "lead_id": str(lead.id),
                            "name": lead.name,
                            "email": lead.email,
                            "type": "bounce",
                            "subject": "",
                            "snippet": bounce.get("bounce_type", "unknown"),
                            "date": "",
                        })
                        break
        except Exception as e:
            logger.warning(f"Bounce check failed: {e}")

        db.commit()

    except PermissionError as e:
        raise HTTPException(401, str(e))
    except Exception as e:
        logger.error(f"Reply check failed: {e}")
        raise HTTPException(500, f"Fehler beim Prüfen der Antworten: {str(e)}")

    return {
        "success": True,
        "replies": replies_found,
        "unsubscribes": unsubscribes_found,
        "bounces": bounces_found,
        "details": results,
    }


# ─── Campaign Summary Stats ─────────────────────────────────────

@router.get("/summary")
async def analytics_summary(db: Session = Depends(get_db)):
    """Get aggregated analytics: sent, delivered, bounced, replied, unsubscribed."""
    leads = db_svc.load_leads(db)

    total_sent = 0
    total_delivered = 0
    total_bounced = 0
    total_replied = 0
    total_unsubscribed = 0
    total_follow_ups = 0

    for lead in leads:
        if lead.date_email_sent:
            total_sent += 1
            if lead.delivery_status == "Delivered":
                total_delivered += 1
            elif lead.delivery_status == "Bounced":
                total_bounced += 1
            if lead.reply_received and not lead.reply_received.startswith("[UNSUBSCRIBE]"):
                total_replied += 1
            if lead.opted_out:
                total_unsubscribed += 1
            if lead.date_follow_up_sent:
                total_follow_ups += 1

    reply_rate = round((total_replied / total_sent * 100), 1) if total_sent > 0 else 0.0
    bounce_rate = round((total_bounced / total_sent * 100), 1) if total_sent > 0 else 0.0

    return {
        "data": {
            "total_sent": total_sent,
            "total_delivered": total_delivered,
            "total_bounced": total_bounced,
            "total_replied": total_replied,
            "total_unsubscribed": total_unsubscribed,
            "total_follow_ups": total_follow_ups,
            "reply_rate": reply_rate,
            "bounce_rate": bounce_rate,
        }
    }
