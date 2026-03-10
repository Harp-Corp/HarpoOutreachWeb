"""
Phase 1-5 DB Models: Email Warmup, Inbox Rotation, Tracking, Multi-User, A/B Testing
"""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Index, Integer, String, Text
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from .db import Base


# ─── Phase 1: Email Warmup ────────────────────────────────────────

class WarmupAccountDB(Base):
    """Tracks warmup state for each sender address."""
    __tablename__ = "warmup_accounts"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    email = Column(String, nullable=False, unique=True)
    smtp_host = Column(String, nullable=False, default="smtp.hostinger.com")
    smtp_port = Column(Integer, nullable=False, default=465)
    smtp_user = Column(String, nullable=False, default="")
    smtp_password_encrypted = Column(String, nullable=False, default="")
    daily_limit = Column(Integer, nullable=False, default=5)
    max_daily_limit = Column(Integer, nullable=False, default=50)
    warmup_started_at = Column(DateTime, nullable=True)
    warmup_day = Column(Integer, nullable=False, default=0)
    warmup_complete = Column(Boolean, nullable=False, default=False)
    emails_sent_today = Column(Integer, nullable=False, default=0)
    last_send_date = Column(String, nullable=False, default="")
    reputation_score = Column(Float, nullable=False, default=50.0)
    is_active = Column(Boolean, nullable=False, default=True)
    is_primary = Column(Boolean, nullable=False, default=False)
    reply_to_email = Column(String, nullable=False, default="")
    display_name = Column(String, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (Index("idx_warmup_email", "email"),)


class WarmupLogDB(Base):
    """Logs each warmup email sent for tracking."""
    __tablename__ = "warmup_log"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id = Column(PG_UUID(as_uuid=True), nullable=False)
    direction = Column(String, nullable=False, default="sent")
    to_email = Column(String, nullable=False, default="")
    subject = Column(String, nullable=False, default="")
    status = Column(String, nullable=False, default="sent")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


# ─── Phase 2: Sender Pool / Inbox Rotation ───────────────────────

class SenderPoolDB(Base):
    """Pool of sender accounts for rotation."""
    __tablename__ = "sender_pool"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    email = Column(String, nullable=False, unique=True)
    display_name = Column(String, nullable=False, default="Martin Foerster")
    smtp_host = Column(String, nullable=False, default="smtp.hostinger.com")
    smtp_port = Column(Integer, nullable=False, default=465)
    smtp_user = Column(String, nullable=False, default="")
    smtp_password_encrypted = Column(String, nullable=False, default="")
    reply_to = Column(String, nullable=False, default="martin.foerster@gmail.com")
    daily_limit = Column(Integer, nullable=False, default=30)
    emails_sent_today = Column(Integer, nullable=False, default=0)
    last_send_date = Column(String, nullable=False, default="")
    is_active = Column(Boolean, nullable=False, default=True)
    health_status = Column(String, nullable=False, default="healthy")
    bounce_rate = Column(Float, nullable=False, default=0.0)
    total_sent = Column(Integer, nullable=False, default=0)
    total_bounced = Column(Integer, nullable=False, default=0)
    rotation_weight = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─── Phase 3: Open/Click Tracking ────────────────────────────────

class EmailTrackingDB(Base):
    """Tracks opens and clicks per sent email."""
    __tablename__ = "email_tracking"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    lead_id = Column(PG_UUID(as_uuid=True), nullable=False)
    email_type = Column(String, nullable=False, default="initial")
    msg_id = Column(String, nullable=False, default="")
    sender_email = Column(String, nullable=False, default="")
    recipient_email = Column(String, nullable=False, default="")
    subject = Column(String, nullable=False, default="")
    sent_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    opens = Column(Integer, nullable=False, default=0)
    first_opened_at = Column(DateTime, nullable=True)
    last_opened_at = Column(DateTime, nullable=True)
    clicks = Column(Integer, nullable=False, default=0)
    first_clicked_at = Column(DateTime, nullable=True)
    clicked_links_json = Column(Text, nullable=False, default="[]")
    delivery_status = Column(String, nullable=False, default="sent")
    bounced_at = Column(DateTime, nullable=True)
    bounce_reason = Column(String, nullable=False, default="")
    ab_variant = Column(String, nullable=True)

    __table_args__ = (
        Index("idx_tracking_lead", "lead_id"),
        Index("idx_tracking_msgid", "msg_id"),
    )


# ─── Phase 4: Multi-User ─────────────────────────────────────────

class UserDB(Base):
    """Multi-user support (max 10)."""
    __tablename__ = "users"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    email = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False, default="")
    role = Column(String, nullable=False, default="user")
    google_id = Column(String, nullable=True)
    avatar_url = Column(String, nullable=False, default="")
    is_active = Column(Boolean, nullable=False, default=True)
    sender_email = Column(String, nullable=False, default="")
    sender_name = Column(String, nullable=False, default="")
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (Index("idx_users_email", "email"),)


class ActivityLogDB(Base):
    """Activity log per user."""
    __tablename__ = "activity_log"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(PG_UUID(as_uuid=True), nullable=True)
    user_email = Column(String, nullable=False, default="system")
    action = Column(String, nullable=False, default="")
    entity_type = Column(String, nullable=False, default="")
    entity_id = Column(String, nullable=False, default="")
    details = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_activity_user", "user_id"),
        Index("idx_activity_created", "created_at"),
    )


# ─── Phase 5: A/B Testing ────────────────────────────────────────

class ABTestDB(Base):
    """A/B test configuration and results."""
    __tablename__ = "ab_tests"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, nullable=False, default="")
    test_type = Column(String, nullable=False, default="subject")
    status = Column(String, nullable=False, default="draft")
    variant_a_subject = Column(String, nullable=False, default="")
    variant_a_body = Column(Text, nullable=False, default="")
    variant_a_sent = Column(Integer, nullable=False, default=0)
    variant_a_opens = Column(Integer, nullable=False, default=0)
    variant_a_clicks = Column(Integer, nullable=False, default=0)
    variant_a_replies = Column(Integer, nullable=False, default=0)
    variant_b_subject = Column(String, nullable=False, default="")
    variant_b_body = Column(Text, nullable=False, default="")
    variant_b_sent = Column(Integer, nullable=False, default=0)
    variant_b_opens = Column(Integer, nullable=False, default=0)
    variant_b_clicks = Column(Integer, nullable=False, default=0)
    variant_b_replies = Column(Integer, nullable=False, default=0)
    split_ratio = Column(Float, nullable=False, default=0.5)
    sample_size = Column(Integer, nullable=False, default=0)
    winner = Column(String, nullable=True)
    winning_metric = Column(String, nullable=False, default="opens")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


# ─── Phase 5: Enhanced Sequences ─────────────────────────────────

class SequenceDB(Base):
    """Multi-step email sequences with conditions."""
    __tablename__ = "sequences"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, nullable=False, default="")
    description = Column(Text, nullable=False, default="")
    steps_json = Column(Text, nullable=False, default="[]")
    is_active = Column(Boolean, nullable=False, default=True)
    total_enrolled = Column(Integer, nullable=False, default=0)
    total_completed = Column(Integer, nullable=False, default=0)
    total_replied = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SequenceEnrollmentDB(Base):
    """Tracks which lead is at which step in a sequence."""
    __tablename__ = "sequence_enrollments"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    sequence_id = Column(PG_UUID(as_uuid=True), nullable=False)
    lead_id = Column(PG_UUID(as_uuid=True), nullable=False)
    current_step = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False, default="active")
    next_send_at = Column(DateTime, nullable=True)
    enrolled_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_enrollment_sequence", "sequence_id"),
        Index("idx_enrollment_lead", "lead_id"),
        Index("idx_enrollment_status", "status"),
    )
