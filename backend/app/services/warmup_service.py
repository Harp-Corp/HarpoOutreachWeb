"""
Email Warmup Service — Phase 1
Gradually increases sending volume for new sender accounts.
Warmup schedule:
  Day 1-3: 5 emails/day
  Day 4-7: 10/day
  Day 8-14: 20/day
  Day 15-21: 35/day
  Day 22+: full limit (50/day)
"""
from __future__ import annotations

import logging
from datetime import datetime, date

from sqlalchemy.orm import Session

from ..models.db_phase2 import WarmupAccountDB, WarmupLogDB

logger = logging.getLogger("harpo.warmup")

WARMUP_SCHEDULE = [
    (3, 5),
    (7, 10),
    (14, 20),
    (21, 35),
]


def get_warmup_limit(warmup_day: int, max_limit: int) -> int:
    """Calculate daily limit based on warmup day."""
    for threshold, limit in WARMUP_SCHEDULE:
        if warmup_day <= threshold:
            return min(limit, max_limit)
    return max_limit


def check_and_reset_daily(db: Session, account: WarmupAccountDB) -> None:
    """Reset daily counter if new day."""
    today = date.today().isoformat()
    if account.last_send_date != today:
        account.emails_sent_today = 0
        account.last_send_date = today
        if account.warmup_started_at:
            delta = (datetime.utcnow() - account.warmup_started_at).days
            account.warmup_day = delta
            account.daily_limit = get_warmup_limit(delta, account.max_daily_limit)
            if delta >= 22 and not account.warmup_complete:
                account.warmup_complete = True
                logger.info(f"Warmup complete for {account.email}")
        db.commit()


def can_send(db: Session, account: WarmupAccountDB) -> bool:
    """Check if account can send another email today."""
    check_and_reset_daily(db, account)
    return account.emails_sent_today < account.daily_limit and account.is_active


def record_send(db: Session, account: WarmupAccountDB, to_email: str, subject: str) -> None:
    """Record a sent email for warmup tracking."""
    account.emails_sent_today += 1
    log = WarmupLogDB(
        account_id=account.id,
        direction="sent",
        to_email=to_email,
        subject=subject,
        status="sent",
    )
    db.add(log)
    db.commit()


def start_warmup(db: Session, account: WarmupAccountDB) -> None:
    """Start warmup process for an account."""
    account.warmup_started_at = datetime.utcnow()
    account.warmup_day = 0
    account.warmup_complete = False
    account.daily_limit = WARMUP_SCHEDULE[0][1]
    db.commit()
    logger.info(f"Warmup started for {account.email}, initial limit: {account.daily_limit}/day")


def get_warmup_status(db: Session, account_id) -> dict:
    """Get warmup status for an account."""
    account = db.query(WarmupAccountDB).filter(WarmupAccountDB.id == account_id).first()
    if not account:
        return {"error": "Account not found"}

    check_and_reset_daily(db, account)

    return {
        "email": account.email,
        "warmup_day": account.warmup_day,
        "warmup_complete": account.warmup_complete,
        "daily_limit": account.daily_limit,
        "max_daily_limit": account.max_daily_limit,
        "emails_sent_today": account.emails_sent_today,
        "remaining_today": max(0, account.daily_limit - account.emails_sent_today),
        "reputation_score": account.reputation_score,
        "is_active": account.is_active,
        "schedule": [
            {"days": f"1-{WARMUP_SCHEDULE[0][0]}", "limit": WARMUP_SCHEDULE[0][1], "active": account.warmup_day <= WARMUP_SCHEDULE[0][0]},
            {"days": f"{WARMUP_SCHEDULE[0][0]+1}-{WARMUP_SCHEDULE[1][0]}", "limit": WARMUP_SCHEDULE[1][1], "active": WARMUP_SCHEDULE[0][0] < account.warmup_day <= WARMUP_SCHEDULE[1][0]},
            {"days": f"{WARMUP_SCHEDULE[1][0]+1}-{WARMUP_SCHEDULE[2][0]}", "limit": WARMUP_SCHEDULE[2][1], "active": WARMUP_SCHEDULE[1][0] < account.warmup_day <= WARMUP_SCHEDULE[2][0]},
            {"days": f"{WARMUP_SCHEDULE[2][0]+1}-{WARMUP_SCHEDULE[3][0]}", "limit": WARMUP_SCHEDULE[3][1], "active": WARMUP_SCHEDULE[2][0] < account.warmup_day <= WARMUP_SCHEDULE[3][0]},
            {"days": f"{WARMUP_SCHEDULE[3][0]+1}+", "limit": account.max_daily_limit, "active": account.warmup_day > WARMUP_SCHEDULE[3][0]},
        ]
    }


def list_accounts(db: Session) -> list[dict]:
    """List all warmup accounts with status."""
    accounts = db.query(WarmupAccountDB).order_by(WarmupAccountDB.created_at).all()
    result = []
    for a in accounts:
        check_and_reset_daily(db, a)
        result.append({
            "id": str(a.id),
            "email": a.email,
            "display_name": a.display_name,
            "daily_limit": a.daily_limit,
            "max_daily_limit": a.max_daily_limit,
            "emails_sent_today": a.emails_sent_today,
            "remaining_today": max(0, a.daily_limit - a.emails_sent_today),
            "warmup_day": a.warmup_day,
            "warmup_complete": a.warmup_complete,
            "reputation_score": a.reputation_score,
            "is_active": a.is_active,
            "is_primary": a.is_primary,
            "reply_to_email": a.reply_to_email,
        })
    return result
