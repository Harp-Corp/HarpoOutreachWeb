"""
Phase 1-5 API Routes: Warmup, Inbox Rotation, Tracking, Multi-User, A/B Testing
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..models.db import get_db
from ..models.db_phase2 import (
    ABTestDB,
    ActivityLogDB,
    EmailTrackingDB,
    SenderPoolDB,
    SequenceDB,
    SequenceEnrollmentDB,
    UserDB,
    WarmupAccountDB,
)
from ..services import rotation_service as rotation
from ..services import tracking_service as tracking
from ..services import warmup_service as warmup

logger = logging.getLogger("harpo.phase2")

router = APIRouter(tags=["Phase 2: Advanced Features"])


# ═══════════════════════════════════════════════════════════════════
# Phase 1: Email Warmup
# ═══════════════════════════════════════════════════════════════════

class AddWarmupAccountBody(BaseModel):
    email: str
    smtp_host: str = "smtp.hostinger.com"
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    max_daily_limit: int = 50
    display_name: str = "Martin Foerster"
    reply_to_email: str = "martin.foerster@gmail.com"
    is_primary: bool = False


@router.get("/warmup/accounts")
async def list_warmup_accounts(db: Session = Depends(get_db)):
    """List all warmup accounts with status."""
    accounts = warmup.list_accounts(db)
    return {"success": True, "data": accounts}


@router.post("/warmup/accounts")
async def add_warmup_account(body: AddWarmupAccountBody, db: Session = Depends(get_db)):
    """Add a new sender account for warmup."""
    existing = db.query(WarmupAccountDB).filter(WarmupAccountDB.email == body.email).first()
    if existing:
        raise HTTPException(400, f"Account {body.email} existiert bereits.")

    account = WarmupAccountDB(
        id=uuid4(),
        email=body.email,
        smtp_host=body.smtp_host,
        smtp_port=body.smtp_port,
        smtp_user=body.smtp_user or body.email,
        smtp_password_encrypted=body.smtp_password,
        max_daily_limit=body.max_daily_limit,
        display_name=body.display_name,
        reply_to_email=body.reply_to_email,
        is_primary=body.is_primary,
    )
    db.add(account)
    db.commit()
    warmup.start_warmup(db, account)
    return {"success": True, "data": {"id": str(account.id), "email": account.email, "daily_limit": account.daily_limit}}


@router.post("/warmup/accounts/{account_id}/start")
async def start_warmup_account(account_id: UUID, db: Session = Depends(get_db)):
    """Start/restart warmup for an account."""
    account = db.query(WarmupAccountDB).filter(WarmupAccountDB.id == account_id).first()
    if not account:
        raise HTTPException(404, "Account nicht gefunden.")
    warmup.start_warmup(db, account)
    return {"success": True, "message": f"Warmup gestartet fuer {account.email}"}


@router.get("/warmup/accounts/{account_id}/status")
async def warmup_status(account_id: UUID, db: Session = Depends(get_db)):
    """Get detailed warmup status."""
    status = warmup.get_warmup_status(db, account_id)
    return {"success": True, "data": status}


@router.delete("/warmup/accounts/{account_id}")
async def delete_warmup_account(account_id: UUID, db: Session = Depends(get_db)):
    """Remove a warmup account."""
    account = db.query(WarmupAccountDB).filter(WarmupAccountDB.id == account_id).first()
    if not account:
        raise HTTPException(404, "Account nicht gefunden.")
    db.delete(account)
    db.commit()
    return {"success": True, "message": f"Account {account.email} entfernt."}


@router.patch("/warmup/accounts/{account_id}")
async def update_warmup_account(account_id: UUID, body: dict, db: Session = Depends(get_db)):
    """Update warmup account settings."""
    account = db.query(WarmupAccountDB).filter(WarmupAccountDB.id == account_id).first()
    if not account:
        raise HTTPException(404, "Account nicht gefunden.")
    for key in ["is_active", "max_daily_limit", "display_name", "reply_to_email", "is_primary"]:
        if key in body:
            setattr(account, key, body[key])
    db.commit()
    return {"success": True}


# ═══════════════════════════════════════════════════════════════════
# Phase 2: Inbox Rotation / Sender Pool
# ═══════════════════════════════════════════════════════════════════

class AddSenderBody(BaseModel):
    email: str
    display_name: str = "Martin Foerster"
    smtp_host: str = "smtp.hostinger.com"
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    reply_to: str = "martin.foerster@gmail.com"
    daily_limit: int = 30
    rotation_weight: int = 1


@router.get("/sender-pool")
async def list_sender_pool(db: Session = Depends(get_db)):
    """List all senders in the rotation pool."""
    pool = rotation.get_pool_status(db)
    capacity = rotation.get_total_daily_capacity(db)
    return {"success": True, "data": {"senders": pool, "capacity": capacity}}


@router.post("/sender-pool")
async def add_sender_to_pool(body: AddSenderBody, db: Session = Depends(get_db)):
    """Add a sender to the rotation pool."""
    existing = db.query(SenderPoolDB).filter(SenderPoolDB.email == body.email).first()
    if existing:
        raise HTTPException(400, f"Sender {body.email} ist bereits im Pool.")
    sender = SenderPoolDB(
        id=uuid4(),
        email=body.email,
        display_name=body.display_name,
        smtp_host=body.smtp_host,
        smtp_port=body.smtp_port,
        smtp_user=body.smtp_user or body.email,
        smtp_password_encrypted=body.smtp_password,
        reply_to=body.reply_to,
        daily_limit=body.daily_limit,
        rotation_weight=body.rotation_weight,
    )
    db.add(sender)
    db.commit()
    return {"success": True, "data": {"id": str(sender.id), "email": sender.email}}


@router.delete("/sender-pool/{sender_id}")
async def remove_sender(sender_id: UUID, db: Session = Depends(get_db)):
    """Remove a sender from the pool."""
    sender = db.query(SenderPoolDB).filter(SenderPoolDB.id == sender_id).first()
    if not sender:
        raise HTTPException(404, "Sender nicht gefunden.")
    db.delete(sender)
    db.commit()
    return {"success": True}


@router.patch("/sender-pool/{sender_id}")
async def update_sender(sender_id: UUID, body: dict, db: Session = Depends(get_db)):
    """Update sender pool settings."""
    sender = db.query(SenderPoolDB).filter(SenderPoolDB.id == sender_id).first()
    if not sender:
        raise HTTPException(404, "Sender nicht gefunden.")
    for key in ["is_active", "daily_limit", "rotation_weight", "display_name", "health_status"]:
        if key in body:
            setattr(sender, key, body[key])
    db.commit()
    return {"success": True}


# ═══════════════════════════════════════════════════════════════════
# Phase 3: Open/Click Tracking
# ═══════════════════════════════════════════════════════════════════

@router.get("/tracking/pixel/{tracking_id}.png")
async def tracking_pixel(tracking_id: str, db: Session = Depends(get_db)):
    """1x1 transparent pixel for email open tracking."""
    tracking.record_open(db, tracking_id)
    pixel = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return Response(content=pixel, media_type="image/png", headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    })


@router.get("/tracking/click/{tracking_id}")
async def tracking_click(tracking_id: str, url: str = Query(...), db: Session = Depends(get_db)):
    """Click tracking redirect."""
    tracking.record_click(db, tracking_id, url)
    return RedirectResponse(url=url, status_code=302)


@router.get("/tracking/stats")
async def tracking_stats(lead_id: str | None = None, db: Session = Depends(get_db)):
    """Get email tracking statistics."""
    stats = tracking.get_tracking_stats(db, lead_id)
    return {"success": True, "data": stats}


@router.get("/tracking/dashboard")
async def tracking_dashboard(db: Session = Depends(get_db)):
    """Get tracking dashboard data."""
    all_stats = tracking.get_tracking_stats(db)
    daily = defaultdict(lambda: {"sent": 0, "opened": 0, "clicked": 0})
    for e in all_stats.get("entries", []):
        if e["sent_at"]:
            day = e["sent_at"][:10]
            daily[day]["sent"] += 1
            if e["opens"] > 0:
                daily[day]["opened"] += 1
            if e["clicks"] > 0:
                daily[day]["clicked"] += 1

    return {
        "success": True,
        "data": {
            "overview": {
                "total_sent": all_stats["total_sent"],
                "open_rate": all_stats["open_rate"],
                "click_rate": all_stats["click_rate"],
                "bounce_rate": all_stats.get("bounce_rate", 0),
            },
            "daily": dict(sorted(daily.items(), reverse=True)[:30]),
        },
    }


# ═══════════════════════════════════════════════════════════════════
# Phase 4: Multi-User — Moved to auth.py with admin-protected endpoints
# User management is now at /api/auth/users/* (requires authentication)
# ═══════════════════════════════════════════════════════════════════


@router.get("/activity-log")
async def get_activity_log(limit: int = 50, db: Session = Depends(get_db)):
    """Get recent activity log entries."""
    entries = db.query(ActivityLogDB).order_by(ActivityLogDB.created_at.desc()).limit(limit).all()
    return {"success": True, "data": [
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


def _log_activity(db: Session, user_id, user_email: str, action: str, entity_type: str, entity_id: str, details: str):
    """Helper to log an activity."""
    entry = ActivityLogDB(
        user_id=user_id,
        user_email=user_email,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )
    db.add(entry)
    db.commit()


# ═══════════════════════════════════════════════════════════════════
# Phase 5: A/B Testing
# ═══════════════════════════════════════════════════════════════════

class CreateABTestBody(BaseModel):
    name: str
    test_type: str = "subject"
    variant_a_subject: str = ""
    variant_a_body: str = ""
    variant_b_subject: str = ""
    variant_b_body: str = ""
    split_ratio: float = 0.5
    winning_metric: str = "opens"


@router.get("/ab-tests")
async def list_ab_tests(db: Session = Depends(get_db)):
    """List all A/B tests."""
    tests = db.query(ABTestDB).order_by(ABTestDB.created_at.desc()).all()
    return {"success": True, "data": [
        {
            "id": str(t.id),
            "name": t.name,
            "test_type": t.test_type,
            "status": t.status,
            "variant_a": {
                "subject": t.variant_a_subject,
                "sent": t.variant_a_sent,
                "opens": t.variant_a_opens,
                "clicks": t.variant_a_clicks,
                "replies": t.variant_a_replies,
                "open_rate": round(t.variant_a_opens / t.variant_a_sent * 100, 1) if t.variant_a_sent else 0,
            },
            "variant_b": {
                "subject": t.variant_b_subject,
                "sent": t.variant_b_sent,
                "opens": t.variant_b_opens,
                "clicks": t.variant_b_clicks,
                "replies": t.variant_b_replies,
                "open_rate": round(t.variant_b_opens / t.variant_b_sent * 100, 1) if t.variant_b_sent else 0,
            },
            "winner": t.winner,
            "winning_metric": t.winning_metric,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tests
    ]}


@router.post("/ab-tests")
async def create_ab_test(body: CreateABTestBody, db: Session = Depends(get_db)):
    """Create a new A/B test."""
    test = ABTestDB(
        id=uuid4(),
        name=body.name,
        test_type=body.test_type,
        variant_a_subject=body.variant_a_subject,
        variant_a_body=body.variant_a_body,
        variant_b_subject=body.variant_b_subject,
        variant_b_body=body.variant_b_body,
        split_ratio=body.split_ratio,
        winning_metric=body.winning_metric,
    )
    db.add(test)
    db.commit()
    return {"success": True, "data": {"id": str(test.id), "name": test.name}}


@router.post("/ab-tests/{test_id}/start")
async def start_ab_test(test_id: UUID, db: Session = Depends(get_db)):
    """Start an A/B test."""
    test = db.query(ABTestDB).filter(ABTestDB.id == test_id).first()
    if not test:
        raise HTTPException(404, "A/B-Test nicht gefunden.")
    test.status = "running"
    test.started_at = datetime.utcnow()
    db.commit()
    return {"success": True}


@router.post("/ab-tests/{test_id}/complete")
async def complete_ab_test(test_id: UUID, db: Session = Depends(get_db)):
    """Complete an A/B test and determine winner."""
    test = db.query(ABTestDB).filter(ABTestDB.id == test_id).first()
    if not test:
        raise HTTPException(404, "A/B-Test nicht gefunden.")
    metric = test.winning_metric
    a_score = getattr(test, f"variant_a_{metric}", 0)
    b_score = getattr(test, f"variant_b_{metric}", 0)
    test.winner = "A" if a_score >= b_score else "B"
    test.status = "completed"
    test.completed_at = datetime.utcnow()
    db.commit()
    return {"success": True, "data": {"winner": test.winner, "metric": metric, "a_score": a_score, "b_score": b_score}}


@router.delete("/ab-tests/{test_id}")
async def delete_ab_test(test_id: UUID, db: Session = Depends(get_db)):
    """Delete an A/B test."""
    test = db.query(ABTestDB).filter(ABTestDB.id == test_id).first()
    if not test:
        raise HTTPException(404, "A/B-Test nicht gefunden.")
    db.delete(test)
    db.commit()
    return {"success": True}


# ═══════════════════════════════════════════════════════════════════
# Phase 5: Enhanced Sequences
# ═══════════════════════════════════════════════════════════════════

class CreateSequenceBody(BaseModel):
    name: str
    description: str = ""
    steps: list[dict] = []


@router.get("/sequences")
async def list_sequences(db: Session = Depends(get_db)):
    """List all email sequences."""
    seqs = db.query(SequenceDB).order_by(SequenceDB.created_at.desc()).all()
    return {"success": True, "data": [
        {
            "id": str(s.id),
            "name": s.name,
            "description": s.description,
            "steps": json.loads(s.steps_json) if s.steps_json else [],
            "is_active": s.is_active,
            "total_enrolled": s.total_enrolled,
            "total_completed": s.total_completed,
            "total_replied": s.total_replied,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in seqs
    ]}


@router.post("/sequences")
async def create_sequence(body: CreateSequenceBody, db: Session = Depends(get_db)):
    """Create a new email sequence."""
    seq = SequenceDB(
        id=uuid4(),
        name=body.name,
        description=body.description,
        steps_json=json.dumps(body.steps),
    )
    db.add(seq)
    db.commit()
    return {"success": True, "data": {"id": str(seq.id), "name": seq.name}}


@router.get("/sequences/{seq_id}/enrollments")
async def list_enrollments(seq_id: UUID, db: Session = Depends(get_db)):
    """List all enrollments in a sequence."""
    enrollments = db.query(SequenceEnrollmentDB).filter(
        SequenceEnrollmentDB.sequence_id == seq_id
    ).order_by(SequenceEnrollmentDB.enrolled_at.desc()).all()
    return {"success": True, "data": [
        {
            "id": str(e.id),
            "lead_id": str(e.lead_id),
            "current_step": e.current_step,
            "status": e.status,
            "next_send_at": e.next_send_at.isoformat() if e.next_send_at else None,
            "enrolled_at": e.enrolled_at.isoformat() if e.enrolled_at else None,
        }
        for e in enrollments
    ]}


@router.delete("/sequences/{seq_id}")
async def delete_sequence(seq_id: UUID, db: Session = Depends(get_db)):
    """Delete a sequence and its enrollments."""
    seq = db.query(SequenceDB).filter(SequenceDB.id == seq_id).first()
    if not seq:
        raise HTTPException(404, "Sequenz nicht gefunden.")
    db.query(SequenceEnrollmentDB).filter(SequenceEnrollmentDB.sequence_id == seq_id).delete()
    db.delete(seq)
    db.commit()
    return {"success": True}
