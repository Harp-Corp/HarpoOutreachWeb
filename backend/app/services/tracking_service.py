"""
Email Tracking Service — Phase 3
Open tracking via 1x1 pixel, click tracking via redirect links.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from ..models.db_phase2 import EmailTrackingDB

logger = logging.getLogger("harpo.tracking")


def create_tracking_entry(
    db: Session,
    lead_id: str,
    msg_id: str,
    sender_email: str,
    recipient_email: str,
    subject: str,
    email_type: str = "initial",
    ab_variant: str | None = None,
) -> str:
    """Create a tracking entry when an email is sent. Returns tracking_id."""
    entry = EmailTrackingDB(
        id=uuid4(),
        lead_id=lead_id,
        msg_id=msg_id,
        sender_email=sender_email,
        recipient_email=recipient_email,
        subject=subject,
        email_type=email_type,
        ab_variant=ab_variant,
        sent_at=datetime.utcnow(),
    )
    db.add(entry)
    db.commit()
    return str(entry.id)


def record_open(db: Session, tracking_id: str) -> bool:
    """Record an email open event."""
    entry = db.query(EmailTrackingDB).filter(EmailTrackingDB.id == tracking_id).first()
    if not entry:
        return False
    now = datetime.utcnow()
    entry.opens += 1
    if not entry.first_opened_at:
        entry.first_opened_at = now
    entry.last_opened_at = now
    db.commit()
    logger.info(f"Open recorded for tracking {tracking_id}, total opens: {entry.opens}")
    return True


def record_click(db: Session, tracking_id: str, url: str) -> bool:
    """Record a link click event."""
    entry = db.query(EmailTrackingDB).filter(EmailTrackingDB.id == tracking_id).first()
    if not entry:
        return False
    now = datetime.utcnow()
    entry.clicks += 1
    if not entry.first_clicked_at:
        entry.first_clicked_at = now
    try:
        links = json.loads(entry.clicked_links_json)
    except Exception:
        links = []
    links.append({"url": url, "clicked_at": now.isoformat()})
    entry.clicked_links_json = json.dumps(links)
    db.commit()
    logger.info(f"Click recorded for tracking {tracking_id}: {url}")
    return True


def get_tracking_stats(db: Session, lead_id: str | None = None) -> dict:
    """Get aggregated tracking statistics."""
    query = db.query(EmailTrackingDB)
    if lead_id:
        query = query.filter(EmailTrackingDB.lead_id == lead_id)

    entries = query.all()
    total = len(entries)
    if total == 0:
        return {"total_sent": 0, "open_rate": 0, "click_rate": 0, "bounce_rate": 0, "entries": []}

    opened = sum(1 for e in entries if e.opens > 0)
    clicked = sum(1 for e in entries if e.clicks > 0)
    bounced = sum(1 for e in entries if e.delivery_status == "bounced")

    entries_list = []
    for e in entries:
        entries_list.append({
            "id": str(e.id),
            "lead_id": str(e.lead_id),
            "recipient": e.recipient_email,
            "subject": e.subject,
            "email_type": e.email_type,
            "sent_at": e.sent_at.isoformat() if e.sent_at else None,
            "opens": e.opens,
            "first_opened_at": e.first_opened_at.isoformat() if e.first_opened_at else None,
            "clicks": e.clicks,
            "first_clicked_at": e.first_clicked_at.isoformat() if e.first_clicked_at else None,
            "delivery_status": e.delivery_status,
            "ab_variant": e.ab_variant,
        })

    return {
        "total_sent": total,
        "total_opened": opened,
        "total_clicked": clicked,
        "total_bounced": bounced,
        "open_rate": round(opened / total * 100, 1) if total else 0,
        "click_rate": round(clicked / total * 100, 1) if total else 0,
        "bounce_rate": round(bounced / total * 100, 1) if total else 0,
        "entries": sorted(entries_list, key=lambda x: x["sent_at"] or "", reverse=True),
    }
