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
    """Create all tables (idempotent)."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency: yields a DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
