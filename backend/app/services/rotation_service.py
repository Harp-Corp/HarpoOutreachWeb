"""
Inbox Rotation Service — Phase 2
Distributes email sends across multiple sender accounts.
Strategy: weighted round-robin based on health and remaining daily quota.
"""
from __future__ import annotations

import logging
import random
from datetime import date

from sqlalchemy.orm import Session

from ..models.db_phase2 import SenderPoolDB

logger = logging.getLogger("harpo.rotation")


def check_and_reset_daily(db: Session, sender: SenderPoolDB) -> None:
    """Reset daily counter if new day."""
    today = date.today().isoformat()
    if sender.last_send_date != today:
        sender.emails_sent_today = 0
        sender.last_send_date = today
        db.commit()


def get_next_sender(db: Session) -> SenderPoolDB | None:
    """Pick the best sender for the next email.
    Among active healthy senders with remaining quota,
    pick weighted by remaining capacity."""
    senders = db.query(SenderPoolDB).filter(
        SenderPoolDB.is_active == True,
        SenderPoolDB.health_status.in_(["healthy", "throttled"]),
    ).all()

    if not senders:
        return None

    candidates = []
    for s in senders:
        check_and_reset_daily(db, s)
        remaining = s.daily_limit - s.emails_sent_today
        if remaining > 0:
            candidates.append((s, remaining))

    if not candidates:
        logger.warning("All senders have reached their daily limit")
        return None

    candidates.sort(key=lambda x: x[1], reverse=True)
    top_n = min(3, len(candidates))
    weights = [c[1] * c[0].rotation_weight for c in candidates[:top_n]]
    total = sum(weights)
    if total == 0:
        return candidates[0][0]

    chosen = random.choices(candidates[:top_n], weights=weights, k=1)[0]
    return chosen[0]


def record_send(db: Session, sender: SenderPoolDB) -> None:
    """Record a send against the sender pool entry."""
    sender.emails_sent_today += 1
    sender.total_sent += 1
    db.commit()


def record_bounce(db: Session, sender: SenderPoolDB) -> None:
    """Record a bounce and update health."""
    sender.total_bounced += 1
    if sender.total_sent > 0:
        sender.bounce_rate = sender.total_bounced / sender.total_sent
    if sender.bounce_rate > 0.05 and sender.total_sent >= 20:
        sender.health_status = "bouncing"
        sender.is_active = False
        logger.warning(f"Sender {sender.email} auto-paused: bounce rate {sender.bounce_rate:.1%}")
    db.commit()


def get_pool_status(db: Session) -> list[dict]:
    """Get status of all senders in pool."""
    senders = db.query(SenderPoolDB).order_by(SenderPoolDB.created_at).all()
    result = []
    for s in senders:
        check_and_reset_daily(db, s)
        result.append({
            "id": str(s.id),
            "email": s.email,
            "display_name": s.display_name,
            "daily_limit": s.daily_limit,
            "emails_sent_today": s.emails_sent_today,
            "remaining_today": max(0, s.daily_limit - s.emails_sent_today),
            "is_active": s.is_active,
            "health_status": s.health_status,
            "bounce_rate": round(s.bounce_rate * 100, 1),
            "total_sent": s.total_sent,
            "total_bounced": s.total_bounced,
            "rotation_weight": s.rotation_weight,
            "reply_to": s.reply_to,
        })
    return result


def get_total_daily_capacity(db: Session) -> dict:
    """Get total capacity across all active senders."""
    senders = db.query(SenderPoolDB).filter(
        SenderPoolDB.is_active == True,
        SenderPoolDB.health_status == "healthy",
    ).all()

    total_limit = sum(s.daily_limit for s in senders)
    total_sent = 0
    for s in senders:
        check_and_reset_daily(db, s)
        total_sent += s.emails_sent_today

    return {
        "active_senders": len(senders),
        "total_daily_limit": total_limit,
        "total_sent_today": total_sent,
        "remaining_today": total_limit - total_sent,
    }
