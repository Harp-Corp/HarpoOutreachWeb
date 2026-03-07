# Database helper functions – wraps SQLAlchemy ORM operations
# Ported from DatabaseService.swift
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.db import (
    AddressBookDB,
    BlocklistDB,
    CampaignTemplateDB,
    CompanyDB,
    LeadDB,
    SettingsDB,
    SocialPostDB,
)
from ..models.schemas import (
    CompanyResponse,
    DeliveryStatus,
    LeadResponse,
    LeadStatus,
    OutboundEmail,
    SocialPostResponse,
)


# ─── Companies ────────────────────────────────────────────────────

def save_company(db: Session, data: dict) -> CompanyDB:
    company_id = data.get("id", uuid4())
    existing = db.get(CompanyDB, company_id)
    if existing:
        for k, v in data.items():
            if k != "id" and hasattr(existing, k):
                setattr(existing, k, v)
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing
    else:
        obj = CompanyDB(id=company_id, **{k: v for k, v in data.items() if k != "id"})
        obj.updated_at = datetime.utcnow()
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj


def save_companies(db: Session, companies: list[dict]) -> int:
    count = 0
    for c in companies:
        save_company(db, c)
        count += 1
    return count


def load_companies(db: Session) -> list[CompanyDB]:
    return db.query(CompanyDB).order_by(CompanyDB.name).all()


def delete_company(db: Session, company_id: UUID):
    obj = db.get(CompanyDB, company_id)
    if obj:
        db.delete(obj)
        db.commit()


def company_exists(db: Session, name: str) -> bool:
    return db.query(CompanyDB).filter(func.lower(CompanyDB.name) == name.lower()).count() > 0


def get_company_by_name(db: Session, name: str) -> Optional[CompanyDB]:
    # Try exact match first (case-insensitive)
    exact = db.query(CompanyDB).filter(func.lower(CompanyDB.name) == name.lower()).first()
    if exact:
        return exact
    # Try fuzzy match: search term contained in company name or vice versa
    like_match = db.query(CompanyDB).filter(
        func.lower(CompanyDB.name).contains(name.lower())
    ).first()
    if like_match:
        return like_match
    # Try reverse: company name contained in search term
    all_companies = db.query(CompanyDB).all()
    for c in all_companies:
        if c.name.lower() in name.lower():
            return c
    return None


# ─── Leads ────────────────────────────────────────────────────────

def _lead_to_db(lead_id: UUID, data: dict) -> dict:
    """Map Pydantic/dict fields to DB column names."""
    result = {"id": lead_id}
    field_map = {
        "name": "name",
        "title": "title",
        "company": "company",
        "email": "email",
        "email_verified": "email_verified",
        "linkedin_url": "linkedin_url",
        "phone": "phone",
        "responsibility": "responsibility",
        "status": "status",
        "source": "source",
        "verification_notes": "verification_notes",
        "date_identified": "date_identified",
        "date_email_sent": "date_email_sent",
        "date_follow_up_sent": "date_follow_up_sent",
        "reply_received": "reply_received",
        "is_manually_created": "is_manually_created",
        "scheduled_send_date": "scheduled_send_date",
        "opted_out": "opted_out",
        "opt_out_date": "opt_out_date",
        "delivery_status": "delivery_status",
        # New: email verification fields
        "email_risk_level": "email_risk_level",
        "email_smtp_verified": "email_smtp_verified",
        "email_is_catch_all": "email_is_catch_all",
        "email_mx_host": "email_mx_host",
        # New: campaign fields
        "campaign_sequence_json": "campaign_sequence_json",
        "campaign_current_step": "campaign_current_step",
        "campaign_paused": "campaign_paused",
        "last_reply_check": "last_reply_check",
    }
    for src, dst in field_map.items():
        if src in data:
            val = data[src]
            if src == "status" and isinstance(val, LeadStatus):
                val = val.value
            elif src == "delivery_status" and isinstance(val, DeliveryStatus):
                val = val.value
            result[dst] = val

    # JSON-encoded email drafts
    if "drafted_email" in data and data["drafted_email"]:
        de = data["drafted_email"]
        if isinstance(de, OutboundEmail):
            result["drafted_email_json"] = de.model_dump_json()
        elif isinstance(de, dict):
            result["drafted_email_json"] = json.dumps(de)
    if "follow_up_email" in data and data["follow_up_email"]:
        fu = data["follow_up_email"]
        if isinstance(fu, OutboundEmail):
            result["follow_up_email_json"] = fu.model_dump_json()
        elif isinstance(fu, dict):
            result["follow_up_email_json"] = json.dumps(fu)

    return result


def save_lead(db: Session, data: dict) -> LeadDB:
    lead_id = data.get("id", uuid4())
    existing = db.get(LeadDB, lead_id)
    mapped = _lead_to_db(lead_id, data)

    if existing:
        for k, v in mapped.items():
            if k != "id" and hasattr(existing, k):
                setattr(existing, k, v)
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing
    else:
        obj = LeadDB(**{k: v for k, v in mapped.items()})
        obj.updated_at = datetime.utcnow()
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj


def load_leads(db: Session) -> list[LeadDB]:
    return db.query(LeadDB).order_by(LeadDB.date_identified.desc()).all()


def get_lead(db: Session, lead_id: UUID) -> Optional[LeadDB]:
    return db.get(LeadDB, lead_id)


def delete_lead(db: Session, lead_id: UUID):
    obj = db.get(LeadDB, lead_id)
    if obj:
        db.delete(obj)
        db.commit()


def lead_exists(db: Session, name: str, company: str) -> bool:
    return (
        db.query(LeadDB)
        .filter(func.lower(LeadDB.name) == name.lower(), func.lower(LeadDB.company) == company.lower())
        .count()
        > 0
    )


def lead_exists_by_email(db: Session, email: str) -> bool:
    norm = email.lower().strip()
    return db.query(LeadDB).filter(func.lower(LeadDB.email) == norm).count() > 0


def lead_db_to_response(lead: LeadDB) -> dict:
    """Convert LeadDB ORM object to a response dict."""
    drafted = None
    if lead.drafted_email_json:
        try:
            drafted = json.loads(lead.drafted_email_json)
        except Exception:
            pass
    follow_up = None
    if lead.follow_up_email_json:
        try:
            follow_up = json.loads(lead.follow_up_email_json)
        except Exception:
            pass

    # Parse campaign sequence
    campaign_sequence = None
    if getattr(lead, "campaign_sequence_json", None):
        try:
            campaign_sequence = json.loads(lead.campaign_sequence_json)
        except Exception:
            pass

    return {
        "id": str(lead.id),
        "name": lead.name,
        "title": lead.title,
        "company": lead.company,
        "email": lead.email,
        "email_verified": lead.email_verified,
        "linkedin_url": lead.linkedin_url,
        "phone": lead.phone,
        "responsibility": lead.responsibility,
        "status": lead.status,
        "source": lead.source,
        "verification_notes": lead.verification_notes,
        "drafted_email": drafted,
        "follow_up_email": follow_up,
        "date_identified": lead.date_identified.isoformat() if lead.date_identified else None,
        "date_email_sent": lead.date_email_sent.isoformat() if lead.date_email_sent else None,
        "date_follow_up_sent": lead.date_follow_up_sent.isoformat() if lead.date_follow_up_sent else None,
        "reply_received": lead.reply_received,
        "is_manually_created": lead.is_manually_created,
        "scheduled_send_date": lead.scheduled_send_date.isoformat() if lead.scheduled_send_date else None,
        "opted_out": lead.opted_out,
        "opt_out_date": lead.opt_out_date.isoformat() if lead.opt_out_date else None,
        "delivery_status": lead.delivery_status,
        # New: technical email verification
        "email_risk_level": getattr(lead, "email_risk_level", "unknown") or "unknown",
        "email_smtp_verified": getattr(lead, "email_smtp_verified", False),
        "email_is_catch_all": getattr(lead, "email_is_catch_all", False),
        "email_mx_host": getattr(lead, "email_mx_host", ""),
        # New: campaign sequences
        "campaign_sequence": campaign_sequence,
        "campaign_current_step": getattr(lead, "campaign_current_step", 0),
        "campaign_paused": getattr(lead, "campaign_paused", False),
        "last_reply_check": lead.last_reply_check.isoformat() if getattr(lead, "last_reply_check", None) else None,
    }


def company_db_to_response(company: CompanyDB) -> dict:
    return {
        "id": str(company.id),
        "name": company.name,
        "industry": company.industry,
        "region": company.region,
        "website": company.website,
        "linkedin_url": company.linkedin_url,
        "description": company.description,
        "size": company.size,
        "country": company.country,
        "nace_code": company.nace_code,
        "employee_count": company.employee_count,
    }


# ─── Address Book ─────────────────────────────────────────────────

def save_address_book_entry(db: Session, data: dict) -> AddressBookDB:
    entry_id = data.get("id", uuid4())
    existing = db.get(AddressBookDB, entry_id)
    if existing:
        for k, v in data.items():
            if k != "id" and hasattr(existing, k):
                setattr(existing, k, v)
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing
    else:
        obj = AddressBookDB(
            id=entry_id,
            name=data.get("name", ""),
            title=data.get("title", ""),
            company=data.get("company", ""),
            email=data.get("email", ""),
            email_verified=data.get("email_verified", False),
            linkedin_url=data.get("linkedin_url", ""),
            phone=data.get("phone", ""),
            notes=data.get("notes", ""),
            source=data.get("source", "manual"),
            contact_status=data.get("contact_status", "active"),
            created_at=data.get("created_at", datetime.utcnow()),
            updated_at=datetime.utcnow(),
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj


def load_address_book(db: Session) -> list[AddressBookDB]:
    return db.query(AddressBookDB).order_by(AddressBookDB.name).all()


def get_address_book_entry(db: Session, entry_id: UUID) -> Optional[AddressBookDB]:
    return db.get(AddressBookDB, entry_id)


def delete_address_book_entry(db: Session, entry_id: UUID):
    obj = db.get(AddressBookDB, entry_id)
    if obj:
        db.delete(obj)
        db.commit()


def address_book_exists(db: Session, email: str) -> bool:
    norm = email.lower().strip()
    return db.query(AddressBookDB).filter(func.lower(AddressBookDB.email) == norm).count() > 0


def address_book_to_response(entry: AddressBookDB) -> dict:
    return {
        "id": str(entry.id),
        "name": entry.name,
        "title": entry.title,
        "company": entry.company,
        "email": entry.email,
        "email_verified": entry.email_verified,
        "linkedin_url": entry.linkedin_url,
        "phone": entry.phone,
        "notes": entry.notes,
        "source": entry.source,
        "contact_status": getattr(entry, "contact_status", "active") or "active",
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


# ─── Social Posts ─────────────────────────────────────────────────

def save_social_post(db: Session, data: dict) -> SocialPostDB:
    post_id = data.get("id", uuid4())
    existing = db.get(SocialPostDB, post_id)
    if existing:
        for k in ("platform", "content", "is_published", "is_copied"):
            if k in data:
                setattr(existing, k, data[k])
        if "hashtags" in data:
            existing.hashtags_json = json.dumps(data["hashtags"])
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing
    else:
        obj = SocialPostDB(
            id=post_id,
            platform=data.get("platform", "LinkedIn"),
            content=data.get("content", ""),
            hashtags_json=json.dumps(data.get("hashtags", [])),
            created_date=data.get("created_date", datetime.utcnow()),
            is_published=data.get("is_published", False),
            is_copied=data.get("is_copied", False),
            updated_at=datetime.utcnow(),
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj


def load_social_posts(db: Session) -> list[SocialPostDB]:
    return db.query(SocialPostDB).order_by(SocialPostDB.created_date.desc()).all()


def delete_social_post(db: Session, post_id: UUID):
    obj = db.get(SocialPostDB, post_id)
    if obj:
        db.delete(obj)
        db.commit()


def social_post_to_response(post: SocialPostDB) -> dict:
    hashtags = []
    try:
        hashtags = json.loads(post.hashtags_json)
    except Exception:
        pass
    return {
        "id": str(post.id),
        "platform": post.platform,
        "content": post.content,
        "hashtags": hashtags,
        "created_date": post.created_date.isoformat() if post.created_date else None,
        "is_published": post.is_published,
        "is_copied": getattr(post, "is_copied", False) or False,
    }


# ─── Blocklist ────────────────────────────────────────────────────

def add_to_blocklist(db: Session, email: str, reason: str = ""):
    norm = email.lower().strip()
    obj = BlocklistDB(email=norm, reason=reason, opted_out_at=datetime.utcnow())
    db.merge(obj)
    db.commit()


def is_blocked(db: Session, email: str) -> bool:
    norm = email.lower().strip()
    return db.query(BlocklistDB).filter(BlocklistDB.email == norm).count() > 0


def load_blocklist(db: Session) -> list[BlocklistDB]:
    return db.query(BlocklistDB).order_by(BlocklistDB.opted_out_at.desc()).all()


def remove_from_blocklist(db: Session, email: str):
    norm = email.lower().strip()
    obj = db.query(BlocklistDB).filter(BlocklistDB.email == norm).first()
    if obj:
        db.delete(obj)
        db.commit()


# ─── Settings ─────────────────────────────────────────────────────

def get_setting(db: Session, key: str, default: str = "") -> str:
    obj = db.get(SettingsDB, key)
    if obj:
        try:
            return json.loads(obj.value_json)
        except Exception:
            return obj.value_json
    return default


def set_setting(db: Session, key: str, value):
    obj = SettingsDB(key=key, value_json=json.dumps(value))
    db.merge(obj)
    db.commit()


def get_all_settings(db: Session) -> dict:
    rows = db.query(SettingsDB).all()
    result = {}
    for r in rows:
        try:
            result[r.key] = json.loads(r.value_json)
        except Exception:
            result[r.key] = r.value_json
    return result


# ─── Campaign Templates ─────────────────────────────────────────

def load_campaign_templates(db: Session) -> list[CampaignTemplateDB]:
    return db.query(CampaignTemplateDB).order_by(CampaignTemplateDB.created_at).all()


def get_campaign_template(db: Session, template_id: UUID) -> Optional[CampaignTemplateDB]:
    return db.get(CampaignTemplateDB, template_id)


# ─── Dashboard Stats ─────────────────────────────────────────────

def get_dashboard_stats(db: Session) -> dict:
    leads = db.query(LeadDB).all()
    total = len(leads)
    sent = sum(1 for l in leads if l.date_email_sent is not None)
    replied = sum(1 for l in leads if l.reply_received and l.reply_received.strip())
    rate = (replied / sent * 100) if sent > 0 else 0.0

    by_status: dict[str, int] = {}
    by_industry: dict[str, int] = {}
    for l in leads:
        by_status[l.status] = by_status.get(l.status, 0) + 1

    companies = db.query(CompanyDB).all()
    company_industry = {c.name.lower(): c.industry for c in companies}
    for l in leads:
        ind = company_industry.get(l.company.lower(), "Unknown")
        by_industry[ind] = by_industry.get(ind, 0) + 1

    # Address book count
    ab_count = db.query(AddressBookDB).count()

    # Campaign counts
    in_campaign = sum(1 for l in leads if getattr(l, "campaign_sequence_json", None))

    return {
        "total_leads": total,
        "emails_sent": sent,
        "replies_received": replied,
        "conversion_rate": round(rate, 1),
        "leads_by_status": by_status,
        "leads_by_industry": by_industry,
        "address_book_count": ab_count,
        "in_campaign": in_campaign,
    }
