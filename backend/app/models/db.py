# SQLAlchemy ORM models + async database engine
from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from ..config import settings


class Base(DeclarativeBase):
    pass


# ─── Companies ────────────────────────────────────────────────────

class CompanyDB(Base):
    __tablename__ = "companies"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, nullable=False, default="")
    industry = Column(String, nullable=False, default="")
    region = Column(String, nullable=False, default="")
    website = Column(String, nullable=False, default="")
    linkedin_url = Column(String, nullable=False, default="")
    description = Column(Text, nullable=False, default="")
    size = Column(String, nullable=False, default="")
    country = Column(String, nullable=False, default="")
    nace_code = Column(String, nullable=False, default="")
    employee_count = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_companies_name", "name"),
    )


# ─── Leads ────────────────────────────────────────────────────────

class LeadDB(Base):
    __tablename__ = "leads"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, nullable=False, default="")
    title = Column(String, nullable=False, default="")
    company = Column(String, nullable=False, default="")
    email = Column(String, nullable=False, default="")
    email_verified = Column(Boolean, nullable=False, default=False)
    linkedin_url = Column(String, nullable=False, default="")
    phone = Column(String, nullable=False, default="")
    responsibility = Column(String, nullable=False, default="")
    status = Column(String, nullable=False, default="Identified")
    source = Column(String, nullable=False, default="")
    verification_notes = Column(Text, nullable=False, default="")
    drafted_email_json = Column(Text, nullable=True)
    follow_up_email_json = Column(Text, nullable=True)
    date_identified = Column(DateTime, nullable=False, default=datetime.utcnow)
    date_email_sent = Column(DateTime, nullable=True)
    date_follow_up_sent = Column(DateTime, nullable=True)
    reply_received = Column(Text, nullable=False, default="")
    is_manually_created = Column(Boolean, nullable=False, default=False)
    scheduled_send_date = Column(DateTime, nullable=True)
    opted_out = Column(Boolean, nullable=False, default=False)
    opt_out_date = Column(DateTime, nullable=True)
    delivery_status = Column(String, nullable=False, default="Pending")
    gmail_thread_id = Column(String, nullable=True)  # Gmail thread ID for reply tracking
    # ── New: Technical email verification ──
    email_risk_level = Column(String, nullable=False, default="unknown")  # low/medium/high/invalid/unknown
    email_smtp_verified = Column(Boolean, nullable=False, default=False)
    email_is_catch_all = Column(Boolean, nullable=False, default=False)
    email_mx_host = Column(String, nullable=False, default="")
    # ── New: Campaign sequence tracking ──
    campaign_sequence_json = Column(Text, nullable=True)  # JSON: [{step, type, subject, body, status, scheduled_at, sent_at}]
    campaign_current_step = Column(Integer, nullable=False, default=0)  # 0 = not started
    campaign_paused = Column(Boolean, nullable=False, default=False)
    last_reply_check = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_leads_email", "email"),
        Index("idx_leads_company", "company"),
        Index("idx_leads_status", "status"),
    )


# ─── Address Book (persistent verified contacts) ─────────────────

class AddressBookDB(Base):
    __tablename__ = "address_book"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, nullable=False, default="")
    title = Column(String, nullable=False, default="")
    company = Column(String, nullable=False, default="")
    email = Column(String, nullable=False, default="")
    email_verified = Column(Boolean, nullable=False, default=False)
    linkedin_url = Column(String, nullable=False, default="")
    phone = Column(String, nullable=False, default="")
    notes = Column(Text, nullable=False, default="")
    source = Column(String, nullable=False, default="")  # "verified" or "manual"
    contact_status = Column(String, nullable=False, default="active")  # "active" | "blocked"
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_addressbook_email", "email"),
        Index("idx_addressbook_company", "company"),
        Index("idx_addressbook_status", "contact_status"),
    )


# ─── Social Posts ─────────────────────────────────────────────────

class SocialPostDB(Base):
    __tablename__ = "social_posts"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    platform = Column(String, nullable=False, default="LinkedIn")
    content = Column(Text, nullable=False, default="")
    hashtags_json = Column(Text, nullable=False, default="[]")
    created_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    is_published = Column(Boolean, nullable=False, default=False)
    is_copied = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─── Campaign Sequences (templates) ──────────────────────────────

class CampaignTemplateDB(Base):
    __tablename__ = "campaign_templates"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, nullable=False, default="Standard-Sequenz")
    description = Column(Text, nullable=False, default="")
    steps_json = Column(Text, nullable=False, default="[]")
    # steps_json format: [{"step": 1, "type": "initial"|"follow_up"|"breakup", "delay_days": 0, "subject_template": "", "body_template": ""}]
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─── Blocklist ────────────────────────────────────────────────────

class BlocklistDB(Base):
    __tablename__ = "blocklist"

    email = Column(String, primary_key=True, nullable=False)
    reason = Column(String, nullable=False, default="")
    opted_out_at = Column(DateTime, nullable=False, default=datetime.utcnow)


# ─── Settings ─────────────────────────────────────────────────────

class SettingsDB(Base):
    __tablename__ = "app_settings"

    key = Column(String, primary_key=True, nullable=False)
    value_json = Column(Text, nullable=False, default="null")


# ─── Engine & Session ─────────────────────────────────────────────

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db():
    """Create all tables (idempotent) + run lightweight column migrations."""
    Base.metadata.create_all(bind=engine)
    # ── Column migrations (ALTER TABLE for columns added after initial create) ──
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if "address_book" in insp.get_table_names():
        cols = [c["name"] for c in insp.get_columns("address_book")]
        if "contact_status" not in cols:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE address_book ADD COLUMN contact_status VARCHAR NOT NULL DEFAULT 'active'"
                ))
    if "social_posts" in insp.get_table_names():
        cols = [c["name"] for c in insp.get_columns("social_posts")]
        if "is_copied" not in cols:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE social_posts ADD COLUMN is_copied BOOLEAN NOT NULL DEFAULT false"
                ))
    # Analytics-related columns on leads
    if "leads" in insp.get_table_names():
        lead_cols = [c["name"] for c in insp.get_columns("leads")]
        migrations = [
            ("delivery_status", "ALTER TABLE leads ADD COLUMN delivery_status VARCHAR NOT NULL DEFAULT 'Pending'"),
            ("reply_received", "ALTER TABLE leads ADD COLUMN reply_received TEXT NOT NULL DEFAULT ''"),
            ("opted_out", "ALTER TABLE leads ADD COLUMN opted_out BOOLEAN NOT NULL DEFAULT false"),
            ("opt_out_date", "ALTER TABLE leads ADD COLUMN opt_out_date TIMESTAMP"),
            ("follow_up_email_json", "ALTER TABLE leads ADD COLUMN follow_up_email_json TEXT"),
            ("date_follow_up_sent", "ALTER TABLE leads ADD COLUMN date_follow_up_sent TIMESTAMP"),
            ("gmail_thread_id", "ALTER TABLE leads ADD COLUMN gmail_thread_id VARCHAR"),
            # New: email verification columns
            ("email_risk_level", "ALTER TABLE leads ADD COLUMN email_risk_level VARCHAR NOT NULL DEFAULT 'unknown'"),
            ("email_smtp_verified", "ALTER TABLE leads ADD COLUMN email_smtp_verified BOOLEAN NOT NULL DEFAULT false"),
            ("email_is_catch_all", "ALTER TABLE leads ADD COLUMN email_is_catch_all BOOLEAN NOT NULL DEFAULT false"),
            ("email_mx_host", "ALTER TABLE leads ADD COLUMN email_mx_host VARCHAR NOT NULL DEFAULT ''"),
            # New: campaign sequence columns
            ("campaign_sequence_json", "ALTER TABLE leads ADD COLUMN campaign_sequence_json TEXT"),
            ("campaign_current_step", "ALTER TABLE leads ADD COLUMN campaign_current_step INTEGER NOT NULL DEFAULT 0"),
            ("campaign_paused", "ALTER TABLE leads ADD COLUMN campaign_paused BOOLEAN NOT NULL DEFAULT false"),
            ("last_reply_check", "ALTER TABLE leads ADD COLUMN last_reply_check TIMESTAMP"),
        ]
        for col_name, sql in migrations:
            if col_name not in lead_cols:
                with engine.begin() as conn:
                    conn.execute(text(sql))


def get_db():
    """FastAPI dependency: yields a DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
