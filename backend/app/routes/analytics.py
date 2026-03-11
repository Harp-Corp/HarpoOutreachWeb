# Analytics routes – email tracking, reply detection, campaign analytics, funnel metrics
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..models.db import LeadDB, get_db
from ..models.db_phase2 import ActivityLogDB, EmailTrackingDB, SenderPoolDB
from ..services import database_service as db_svc
from ..services import gmail_service as gmail
from ..services import tracking_service as tracking_svc
from .email_pipeline import _get_access_token, _refresh_google_token
from ..services.auth_service import get_current_user

logger = logging.getLogger("harpo.analytics")

router = APIRouter(prefix="/analytics", tags=["Analytics"])


# ─── Sent Emails Overview ────────────────────────────────────────

@router.get("/sent-emails")
async def list_sent_emails(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
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
async def check_replies(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
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
async def analytics_summary(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
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

    # ── Email Tracking (Open/Click) from email_tracking table ──
    tracking_stats = tracking_svc.get_tracking_stats(db)
    tracking_daily = defaultdict(lambda: {"sent": 0, "opened": 0, "clicked": 0})
    for e in tracking_stats.get("entries", []):
        if e["sent_at"]:
            day = e["sent_at"][:10]
            tracking_daily[day]["sent"] += 1
            if e["opens"] > 0:
                tracking_daily[day]["opened"] += 1
            if e["clicks"] > 0:
                tracking_daily[day]["clicked"] += 1

    # ── Sender Pool status ──
    pool_senders = db.query(SenderPoolDB).filter(SenderPoolDB.is_active == True).all()
    pool_capacity = sum(s.daily_limit for s in pool_senders)
    pool_sent_today = sum(s.emails_sent_today for s in pool_senders)

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
            # Email Tracking (Open/Click)
            "tracking_open_rate": tracking_stats.get("open_rate", 0),
            "tracking_click_rate": tracking_stats.get("click_rate", 0),
            "tracking_total_tracked": tracking_stats.get("total_sent", 0),
            "tracking_total_opened": tracking_stats.get("total_opened", 0),
            "tracking_total_clicked": tracking_stats.get("total_clicked", 0),
            "tracking_daily": dict(sorted(tracking_daily.items(), reverse=True)[:14]),
            # Sender Pool
            "pool_active_senders": len(pool_senders),
            "pool_daily_capacity": pool_capacity,
            "pool_sent_today": pool_sent_today,
        }
    }


# ─── Activity Log (accessible from Analytics) ────────────────

@router.get("/activity-log")
async def analytics_activity_log(limit: int = Query(50, ge=1, le=200), user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get recent activity log entries for the analytics dashboard."""
    entries = db.query(ActivityLogDB).order_by(ActivityLogDB.created_at.desc()).limit(limit).all()
    return {"data": [
        {
            "id": str(e.id),
            "user_email": e.user_email,
            "action": e.action,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "details": e.details,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in entries
    ]}


# ─── Funnel View (Detailed Pipeline) ────────────────────────────

@router.get("/funnel")
async def analytics_funnel(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
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


# ─── LinkedIn Post Analytics ────────────────────────────────────

@router.get("/linkedin-posts")
async def linkedin_post_analytics(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get analytics for published LinkedIn posts.
    Fetches engagement data (clicks, likes, comments, impressions, shares)
    from LinkedIn organizationalEntityShareStatistics API."""
    from ..models.db import SocialPostDB

    # Get all published posts with linkedin_post_id
    posts = db.query(SocialPostDB).filter(
        SocialPostDB.is_published == True
    ).order_by(SocialPostDB.published_at.desc()).all()

    if not posts:
        return {"data": [], "summary": {"total_posts": 0}}

    org_id = db_svc.get_setting(db, "linkedin_org_id", "42109305")

    # Try to get LinkedIn access token for API calls
    # First check if we have a Pipedream-managed token in settings
    li_token = db_svc.get_setting(db, "linkedin_access_token")

    results = []
    total_impressions = 0
    total_clicks = 0
    total_likes = 0
    total_comments = 0
    total_shares = 0

    for post in posts:
        post_data = {
            "id": str(post.id),
            "content": post.content[:150] + ("..." if len(post.content) > 150 else ""),
            "published_at": post.published_at.isoformat() if post.published_at else None,
            "linkedin_post_id": post.linkedin_post_id,
            "stats": None,
        }

        # If we have a token AND a linkedin_post_id, fetch stats
        if li_token and post.linkedin_post_id:
            try:
                stats = await _fetch_post_stats(org_id, post.linkedin_post_id, li_token)
                if stats:
                    post_data["stats"] = stats
                    total_impressions += stats.get("impressionCount", 0)
                    total_clicks += stats.get("clickCount", 0)
                    total_likes += stats.get("likeCount", 0)
                    total_comments += stats.get("commentCount", 0)
                    total_shares += stats.get("shareCount", 0)
            except Exception as e:
                logger.warning(f"Failed to fetch LinkedIn stats for post {post.id}: {e}")

        results.append(post_data)

    return {
        "data": results,
        "summary": {
            "total_posts": len(posts),
            "posts_with_stats": sum(1 for r in results if r["stats"]),
            "total_impressions": total_impressions,
            "total_clicks": total_clicks,
            "total_likes": total_likes,
            "total_comments": total_comments,
            "total_shares": total_shares,
            "has_token": bool(li_token),
        }
    }


async def _fetch_post_stats(org_id: str, linkedin_post_id: str, access_token: str) -> dict | None:
    """Fetch statistics for a single LinkedIn post via organizationalEntityShareStatistics API."""
    import httpx
    import urllib.parse

    org_urn = f"urn:li:organization:{org_id}"

    # Determine if it's a share or ugcPost based on the URN format
    if "ugcPost" in linkedin_post_id:
        params = f"q=organizationalEntity&organizationalEntity={urllib.parse.quote(org_urn)}&ugcPosts[0]={urllib.parse.quote(linkedin_post_id)}"
    elif "share" in linkedin_post_id:
        params = f"q=organizationalEntity&organizationalEntity={urllib.parse.quote(org_urn)}&shares[0]={urllib.parse.quote(linkedin_post_id)}"
    else:
        # Try as share URN
        share_urn = f"urn:li:share:{linkedin_post_id}" if not linkedin_post_id.startswith("urn:") else linkedin_post_id
        params = f"q=organizationalEntity&organizationalEntity={urllib.parse.quote(org_urn)}&shares[0]={urllib.parse.quote(share_urn)}"

    url = f"https://api.linkedin.com/rest/organizationalEntityShareStatistics?{params}"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers={
            "Authorization": f"Bearer {access_token}",
            "LinkedIn-Version": "202602",
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        })

    if resp.status_code != 200:
        logger.warning(f"LinkedIn stats API returned {resp.status_code}: {resp.text[:200]}")
        return None

    data = resp.json()
    elements = data.get("elements", [])
    if not elements:
        return None

    stats = elements[0].get("totalShareStatistics", {})
    return {
        "clickCount": stats.get("clickCount", 0),
        "likeCount": stats.get("likeCount", 0),
        "commentCount": stats.get("commentCount", 0),
        "shareCount": stats.get("shareCount", 0),
        "impressionCount": stats.get("impressionCount", 0),
        "engagement": stats.get("engagement", 0),
        "uniqueImpressionsCount": stats.get("uniqueImpressionsCount", 0),
    }


@router.get("/linkedin-page")
async def linkedin_page_analytics(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get LinkedIn organization page statistics (views, visitors)."""
    import httpx
    import urllib.parse

    org_id = db_svc.get_setting(db, "linkedin_org_id", "42109305")
    li_token = db_svc.get_setting(db, "linkedin_access_token")

    if not li_token:
        return {"data": None, "error": "Kein LinkedIn-Token vorhanden. Bitte in den Einstellungen verbinden."}

    org_urn = f"urn:li:organization:{org_id}"
    url = f"https://api.linkedin.com/rest/organizationPageStatistics?q=organization&organization={urllib.parse.quote(org_urn)}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers={
                "Authorization": f"Bearer {li_token}",
                "LinkedIn-Version": "202602",
                "X-Restli-Protocol-Version": "2.0.0",
                "Content-Type": "application/json",
            })

        if resp.status_code != 200:
            return {"data": None, "error": f"LinkedIn API Fehler: {resp.status_code}"}

        data = resp.json()
        elements = data.get("elements", [])
        if not elements:
            return {"data": None, "error": "Keine Seitenstatistiken verfügbar."}

        page_stats = elements[0].get("totalPageStatistics", {})
        views = page_stats.get("views", {})

        return {
            "data": {
                "total_page_views": views.get("allPageViews", {}).get("pageViews", 0),
                "desktop_views": views.get("allDesktopPageViews", {}).get("pageViews", 0),
                "mobile_views": views.get("allMobilePageViews", {}).get("pageViews", 0),
                "overview_views": views.get("overviewPageViews", {}).get("pageViews", 0),
            }
        }
    except Exception as e:
        logger.error(f"LinkedIn page stats error: {e}")
        return {"data": None, "error": str(e)}
