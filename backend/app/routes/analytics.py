# Analytics routes – email tracking, reply detection, campaign analytics, funnel metrics
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
from .email_pipeline import _get_access_token, _refresh_google_token

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
            # New: technical verification data
            "email_risk_level": getattr(lead, "email_risk_level", "unknown"),
            "email_smtp_verified": getattr(lead, "email_smtp_verified", False),
            # New: campaign sequence info
            "campaign_current_step": getattr(lead, "campaign_current_step", 0),
            "campaign_paused": getattr(lead, "campaign_paused", False),
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

    # Collect subjects, emails, and thread IDs for search
    subjects = []
    lead_emails = []
    thread_ids = []
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
        if hasattr(lead, 'gmail_thread_id') and lead.gmail_thread_id:
            thread_ids.append(lead.gmail_thread_id)

    # Search Gmail for replies
    replies_found = 0
    unsubscribes_found = 0
    bounces_found = 0
    results = []

    try:
        # Check replies
        reply_msgs = await gmail.check_replies(subjects, lead_emails, access_token, thread_ids=thread_ids or None)

        for msg in reply_msgs:
            from_addr = msg.get("from", "").lower()
            full_body = (msg.get("body", "") + " " + msg.get("snippet", ""))
            msg_subject = msg.get("subject", "")

            # Extract only the reply portion (before quoted original)
            # Common quote markers: "On ... wrote:", "Am ... schrieb:", "> ", "------"
            reply_only = full_body
            for marker in ["\nOn ", "\nAm ", "\n>", "\n------", "\n______"]:
                idx = full_body.find(marker)
                if idx > 0:
                    reply_only = full_body[:idx]
                    break
            reply_lower = reply_only.lower().strip()
            full_lower = full_body.lower()

            # Match to a lead
            matched_lead = None
            for lead in sent_leads:
                if lead.email and lead.email.lower() in from_addr:
                    matched_lead = lead
                    break

            if not matched_lead:
                continue

            # Detect unsubscribe — check ONLY the reply portion (not quoted original)
            # to avoid false positives from our own unsubscribe footer
            unsub_keywords = [
                "unsubscribe", "abmelden", "opt out", "opt-out",
                "remove me", "abbestellen", "please remove",
                "nicht mehr kontaktieren", "kein interesse",
            ]
            is_unsub = any(kw in reply_lower for kw in unsub_keywords)

            if is_unsub:
                matched_lead.status = "Do Not Contact"
                matched_lead.opted_out = True
                matched_lead.opt_out_date = datetime.utcnow()
                matched_lead.reply_received = f"[UNSUBSCRIBE] {msg.get('snippet', '')[:200]}"
                unsubscribes_found += 1
                # Add to blocklist
                db_svc.add_to_blocklist(db, matched_lead.email, reason="Unsubscribe-Antwort")
                # Auto-pause campaign if active
                if getattr(matched_lead, 'campaign_sequence_json', None):
                    matched_lead.campaign_paused = True
            else:
                if not matched_lead.reply_received:
                    matched_lead.status = "Replied"
                matched_lead.reply_received = msg.get("body", msg.get("snippet", ""))[:1000]
                replies_found += 1
                # Auto-pause campaign if active (reply received)
                if getattr(matched_lead, 'campaign_sequence_json', None):
                    matched_lead.campaign_paused = True

            matched_lead.last_reply_check = datetime.utcnow()
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


# ─── Campaign Summary Stats (Enhanced Funnel) ───────────────────

@router.get("/summary")
async def analytics_summary(db: Session = Depends(get_db)):
    """Get aggregated analytics: full funnel view with sent/replied/bounced ratios."""
    leads = db_svc.load_leads(db)

    total_leads = len(leads)
    total_sent = 0
    total_delivered = 0
    total_bounced = 0
    total_replied = 0
    total_unsubscribed = 0
    total_follow_ups = 0
    total_verified = 0
    total_smtp_verified = 0

    # Campaign sequence stats
    total_in_campaign = 0
    total_campaign_steps_sent = 0
    total_campaign_steps_pending = 0
    total_campaign_paused = 0

    # By status distribution
    by_status = {}
    by_risk_level = {"low": 0, "medium": 0, "high": 0, "invalid": 0, "unknown": 0}

    for lead in leads:
        # Status distribution
        by_status[lead.status] = by_status.get(lead.status, 0) + 1

        # Verification stats
        if lead.email_verified:
            total_verified += 1
        if getattr(lead, "email_smtp_verified", False):
            total_smtp_verified += 1
        risk = getattr(lead, "email_risk_level", "unknown") or "unknown"
        if risk in by_risk_level:
            by_risk_level[risk] += 1

        # Sent / delivery stats
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

        # Campaign stats
        if getattr(lead, "campaign_sequence_json", None):
            total_in_campaign += 1
            if getattr(lead, "campaign_paused", False):
                total_campaign_paused += 1
            try:
                seq = json.loads(lead.campaign_sequence_json)
                for s in seq:
                    if s.get("status") == "sent":
                        total_campaign_steps_sent += 1
                    elif s.get("status") in ("pending", "drafted", "approved"):
                        total_campaign_steps_pending += 1
            except Exception:
                pass

    # Calculated rates
    reply_rate = round((total_replied / total_sent * 100), 1) if total_sent > 0 else 0.0
    bounce_rate = round((total_bounced / total_sent * 100), 1) if total_sent > 0 else 0.0
    unsub_rate = round((total_unsubscribed / total_sent * 100), 1) if total_sent > 0 else 0.0
    delivery_rate = round((total_delivered / total_sent * 100), 1) if total_sent > 0 else 0.0
    # Effective rate: replies / (sent - bounced)
    effective_base = total_sent - total_bounced
    effective_reply_rate = round((total_replied / effective_base * 100), 1) if effective_base > 0 else 0.0

    return {
        "data": {
            # Core funnel
            "total_leads": total_leads,
            "total_sent": total_sent,
            "total_delivered": total_delivered,
            "total_bounced": total_bounced,
            "total_replied": total_replied,
            "total_unsubscribed": total_unsubscribed,
            "total_follow_ups": total_follow_ups,
            # Rates
            "reply_rate": reply_rate,
            "bounce_rate": bounce_rate,
            "unsub_rate": unsub_rate,
            "delivery_rate": delivery_rate,
            "effective_reply_rate": effective_reply_rate,
            # Verification
            "total_verified": total_verified,
            "total_smtp_verified": total_smtp_verified,
            "by_risk_level": by_risk_level,
            # Campaign sequences
            "total_in_campaign": total_in_campaign,
            "total_campaign_steps_sent": total_campaign_steps_sent,
            "total_campaign_steps_pending": total_campaign_steps_pending,
            "total_campaign_paused": total_campaign_paused,
            # Status distribution
            "by_status": by_status,
        }
    }


# ─── Funnel View (Detailed Pipeline) ────────────────────────────

@router.get("/funnel")
async def analytics_funnel(db: Session = Depends(get_db)):
    """Detailed funnel view: leads → verified → contacted → replied → converted."""
    leads = db_svc.load_leads(db)

    stages = {
        "identified": 0,      # all leads
        "verified": 0,        # email verified
        "smtp_verified": 0,   # SMTP-level verified
        "email_drafted": 0,   # email drafted
        "email_sent": 0,      # email sent
        "follow_up_sent": 0,  # follow-up sent
        "replied": 0,         # got a reply
        "opted_out": 0,       # unsubscribed
        "bounced": 0,         # bounced
    }

    for lead in leads:
        stages["identified"] += 1
        if lead.email_verified:
            stages["verified"] += 1
        if getattr(lead, "email_smtp_verified", False):
            stages["smtp_verified"] += 1
        if lead.drafted_email_json:
            stages["email_drafted"] += 1
        if lead.date_email_sent:
            stages["email_sent"] += 1
        if lead.date_follow_up_sent:
            stages["follow_up_sent"] += 1
        if lead.reply_received and not lead.reply_received.startswith("[UNSUBSCRIBE]"):
            stages["replied"] += 1
        if lead.opted_out:
            stages["opted_out"] += 1
        if lead.delivery_status == "Bounced":
            stages["bounced"] += 1

    # Conversion rates between stages
    conversions = {}
    if stages["identified"] > 0:
        conversions["identified_to_verified"] = round(stages["verified"] / stages["identified"] * 100, 1)
    if stages["verified"] > 0:
        conversions["verified_to_sent"] = round(stages["email_sent"] / stages["verified"] * 100, 1)
    if stages["email_sent"] > 0:
        conversions["sent_to_replied"] = round(stages["replied"] / stages["email_sent"] * 100, 1)

    return {
        "data": {
            "stages": stages,
            "conversions": conversions,
        }
    }
