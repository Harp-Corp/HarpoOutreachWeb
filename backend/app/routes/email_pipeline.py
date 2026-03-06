# Email Pipeline routes – draft, approve, send emails
from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..models.db import CompanyDB, get_db
from ..models.schemas import OutboundEmail
from ..services import database_service as db_svc
from ..services import gmail_service as gmail
from ..services import google_auth_service as gauth
from ..services import perplexity_service as pplx

router = APIRouter(prefix="/email", tags=["Email Pipeline"])


def _get_access_token(db: Session) -> str:
    """Get a valid Google access token (refresh if needed)."""
    token = db_svc.get_setting(db, "google_access_token")
    if not token:
        raise HTTPException(401, "Nicht mit Google authentifiziert.")
    # TODO: check expiry and refresh automatically
    return token


# ─── Pydantic models for request bodies ────────────────────────

class UpdateDraftBody(BaseModel):
    subject: str
    body: str

class BatchLeadIds(BaseModel):
    lead_ids: list[str]


# ─── Single Draft ──────────────────────────────────────────────

@router.post("/draft/{lead_id}")
async def draft_email(lead_id: UUID, db: Session = Depends(get_db)):
    """Research challenges and draft a personalized email for a lead."""
    api_key = db_svc.get_setting(db, "perplexity_api_key")
    if not api_key:
        raise HTTPException(400, "Perplexity API Key fehlt.")

    lead = db_svc.get_lead(db, lead_id)
    if not lead:
        raise HTTPException(404, "Lead nicht gefunden.")

    if not lead.email and not lead.is_manually_created:
        raise HTTPException(400, "Lead hat keine E-Mail-Adresse.")

    # Find company for research
    company = db.query(CompanyDB).filter(
        CompanyDB.name.ilike(lead.company)
    ).first()
    company_name = company.name if company else lead.company
    company_industry = company.industry if company else ""

    # Step 1: Research challenges
    challenges = await pplx.research_challenges(company_name, company_industry, api_key)

    # Step 2: Draft email
    sender_name = db_svc.get_setting(db, "sender_name", "Martin Foerster")
    email_data = await pplx.draft_email(
        lead.name, lead.title, lead.company, challenges, sender_name, api_key
    )

    # Step 3: Generate dynamic subject alternatives
    try:
        subjects = await pplx.generate_subject_alternatives(
            company_name, company_industry, email_data["body"][:200], api_key
        )
        if subjects:
            email_data["subject"] = subjects[0]
    except Exception:
        pass  # Keep original subject

    # Save draft
    draft = OutboundEmail(
        id=uuid4(),
        subject=email_data["subject"],
        body=email_data["body"],
        is_approved=False,
    )
    lead.drafted_email_json = draft.model_dump_json()
    lead.status = "Email Drafted"
    lead.updated_at = datetime.utcnow()
    db.commit()

    return {"success": True, "data": draft.model_dump()}


# ─── Draft All (existing leads without draft) ─────────────────

@router.post("/draft-all")
async def draft_all_emails(db: Session = Depends(get_db)):
    """Draft emails for all leads that have an email but no draft."""
    api_key = db_svc.get_setting(db, "perplexity_api_key")
    if not api_key:
        raise HTTPException(400, "Perplexity API Key fehlt.")

    leads = db_svc.load_leads(db)
    to_draft = [l for l in leads if (l.email or l.is_manually_created) and not l.drafted_email_json]
    created = 0
    failed = 0

    for lead in to_draft:
        try:
            company = db.query(CompanyDB).filter(CompanyDB.name.ilike(lead.company)).first()
            company_name = company.name if company else lead.company
            company_industry = company.industry if company else ""

            challenges = await pplx.research_challenges(company_name, company_industry, api_key)
            sender_name = db_svc.get_setting(db, "sender_name", "Martin Foerster")
            email_data = await pplx.draft_email(
                lead.name, lead.title, lead.company, challenges, sender_name, api_key
            )

            draft = OutboundEmail(
                id=uuid4(),
                subject=email_data["subject"],
                body=email_data["body"],
            )
            lead.drafted_email_json = draft.model_dump_json()
            lead.status = "Email Drafted"
            lead.updated_at = datetime.utcnow()
            db.commit()
            created += 1
        except Exception as e:
            failed += 1
            continue

    return {"success": True, "created": created, "failed": failed}


# ─── Batch Draft (for specific lead IDs – campaign wizard) ────

@router.post("/draft-batch")
async def draft_batch_emails(data: BatchLeadIds, db: Session = Depends(get_db)):
    """Draft emails for specific leads by ID (campaign wizard step 2)."""
    api_key = db_svc.get_setting(db, "perplexity_api_key")
    if not api_key:
        raise HTTPException(400, "Perplexity API Key fehlt.")

    created = 0
    failed = 0
    skipped = 0

    for lid_str in data.lead_ids:
        try:
            lid = UUID(lid_str)
        except ValueError:
            failed += 1
            continue
        lead = db_svc.get_lead(db, lid)
        if not lead:
            failed += 1
            continue
        if lead.drafted_email_json:
            skipped += 1
            continue
        if not lead.email and not lead.is_manually_created:
            failed += 1
            continue

        try:
            company = db.query(CompanyDB).filter(CompanyDB.name.ilike(lead.company)).first()
            company_name = company.name if company else lead.company
            company_industry = company.industry if company else ""

            challenges = await pplx.research_challenges(company_name, company_industry, api_key)
            sender_name = db_svc.get_setting(db, "sender_name", "Martin Foerster")
            email_data = await pplx.draft_email(
                lead.name, lead.title, lead.company, challenges, sender_name, api_key
            )

            try:
                subjects = await pplx.generate_subject_alternatives(
                    company_name, company_industry, email_data["body"][:200], api_key
                )
                if subjects:
                    email_data["subject"] = subjects[0]
            except Exception:
                pass

            draft = OutboundEmail(
                id=uuid4(),
                subject=email_data["subject"],
                body=email_data["body"],
            )
            lead.drafted_email_json = draft.model_dump_json()
            lead.status = "Email Drafted"
            lead.updated_at = datetime.utcnow()
            db.commit()
            created += 1
        except Exception:
            failed += 1

    return {"success": True, "created": created, "failed": failed, "skipped": skipped}


# ─── Single Approve ───────────────────────────────────────────

@router.post("/approve/{lead_id}")
async def approve_email(lead_id: UUID, db: Session = Depends(get_db)):
    lead = db_svc.get_lead(db, lead_id)
    if not lead:
        raise HTTPException(404, "Lead nicht gefunden.")
    if not lead.drafted_email_json:
        raise HTTPException(400, "Kein E-Mail-Entwurf vorhanden.")

    draft = json.loads(lead.drafted_email_json)
    draft["is_approved"] = True
    lead.drafted_email_json = json.dumps(draft)
    lead.status = "Email Approved"
    lead.updated_at = datetime.utcnow()
    db.commit()

    return {"success": True}


@router.post("/unapprove/{lead_id}")
async def unapprove_email(lead_id: UUID, db: Session = Depends(get_db)):
    """Revoke approval for an email draft."""
    lead = db_svc.get_lead(db, lead_id)
    if not lead:
        raise HTTPException(404, "Lead nicht gefunden.")
    if not lead.drafted_email_json:
        raise HTTPException(400, "Kein E-Mail-Entwurf vorhanden.")

    draft = json.loads(lead.drafted_email_json)
    draft["is_approved"] = False
    lead.drafted_email_json = json.dumps(draft)
    lead.status = "Email Drafted"
    lead.updated_at = datetime.utcnow()
    db.commit()

    return {"success": True}


# ─── Approve / Unapprove All ─────────────────────────────────

@router.post("/approve-all")
async def approve_all(db: Session = Depends(get_db)):
    leads = db_svc.load_leads(db)
    count = 0
    for lead in leads:
        if lead.drafted_email_json:
            draft = json.loads(lead.drafted_email_json)
            if not draft.get("is_approved"):
                draft["is_approved"] = True
                lead.drafted_email_json = json.dumps(draft)
                lead.status = "Email Approved"
                lead.updated_at = datetime.utcnow()
                count += 1
    db.commit()
    return {"success": True, "approved": count}


# ─── Batch Approve (specific IDs) ────────────────────────────

@router.post("/approve-batch")
async def approve_batch(data: BatchLeadIds, db: Session = Depends(get_db)):
    """Approve emails for specific leads (campaign wizard step 3)."""
    approved = 0
    for lid_str in data.lead_ids:
        try:
            lid = UUID(lid_str)
        except ValueError:
            continue
        lead = db_svc.get_lead(db, lid)
        if not lead or not lead.drafted_email_json:
            continue
        draft = json.loads(lead.drafted_email_json)
        if not draft.get("is_approved"):
            draft["is_approved"] = True
            lead.drafted_email_json = json.dumps(draft)
            lead.status = "Email Approved"
            lead.updated_at = datetime.utcnow()
            approved += 1
    db.commit()
    return {"success": True, "approved": approved}


# ─── Update Draft ─────────────────────────────────────────────

@router.put("/update-draft/{lead_id}")
async def update_draft(
    lead_id: UUID,
    data: UpdateDraftBody,
    db: Session = Depends(get_db),
):
    lead = db_svc.get_lead(db, lead_id)
    if not lead:
        raise HTTPException(404, "Lead nicht gefunden.")

    # Update draft text but keep is_approved = False (user must re-approve after editing)
    draft = OutboundEmail(
        id=uuid4(),
        subject=data.subject,
        body=data.body,
        is_approved=False,
    )
    lead.drafted_email_json = draft.model_dump_json()
    lead.status = "Email Drafted"
    lead.updated_at = datetime.utcnow()
    db.commit()
    return {"success": True}


@router.delete("/draft/{lead_id}")
async def delete_draft(lead_id: UUID, db: Session = Depends(get_db)):
    lead = db_svc.get_lead(db, lead_id)
    if not lead:
        raise HTTPException(404, "Lead nicht gefunden.")
    lead.drafted_email_json = None
    lead.status = "Identified"
    lead.updated_at = datetime.utcnow()
    db.commit()
    return {"success": True}


# ─── Single Send ──────────────────────────────────────────────

@router.post("/send/{lead_id}")
async def send_email(lead_id: UUID, db: Session = Depends(get_db)):
    """Send an approved email to a lead."""
    access_token = _get_access_token(db)
    lead = db_svc.get_lead(db, lead_id)
    if not lead:
        raise HTTPException(404, "Lead nicht gefunden.")
    if not lead.drafted_email_json:
        raise HTTPException(400, "Kein E-Mail-Entwurf vorhanden.")

    draft = json.loads(lead.drafted_email_json)
    if not draft.get("is_approved"):
        raise HTTPException(400, "E-Mail muss erst genehmigt werden.")

    # Blocklist check
    if db_svc.is_blocked(db, lead.email):
        lead.status = "Do Not Contact"
        lead.opted_out = True
        lead.updated_at = datetime.utcnow()
        db.commit()
        raise HTTPException(400, f"{lead.email} steht auf der Opt-Out-Liste.")

    # Schedule check
    if lead.scheduled_send_date and lead.scheduled_send_date > datetime.utcnow():
        return {"success": False, "error": f"E-Mail an {lead.name} ist geplant fuer {lead.scheduled_send_date}. Uebersprungen."}

    sender = db_svc.get_setting(db, "sender_email", "mf@harpocrates-corp.com")
    try:
        msg_id = await gmail.send_email(
            to=lead.email,
            from_addr=sender,
            subject=draft["subject"],
            body=draft["body"],
            access_token=access_token,
        )
        lead.date_email_sent = datetime.utcnow()
        draft["sent_date"] = datetime.utcnow().isoformat()
        lead.drafted_email_json = json.dumps(draft)
        lead.status = "Email Sent"
        lead.delivery_status = "Delivered"
        lead.updated_at = datetime.utcnow()
        db.commit()
        return {"success": True, "message_id": msg_id}
    except Exception as e:
        lead.delivery_status = "Failed"
        lead.updated_at = datetime.utcnow()
        db.commit()
        raise HTTPException(500, f"Senden fehlgeschlagen: {str(e)}")


# ─── Send All Approved ────────────────────────────────────────

@router.post("/send-all")
async def send_all_approved(db: Session = Depends(get_db)):
    """Send all approved emails (batch limited)."""
    access_token = _get_access_token(db)
    batch_size = int(db_svc.get_setting(db, "batch_size", "10"))

    leads = db_svc.load_leads(db)
    approved = [
        l for l in leads
        if l.drafted_email_json
        and json.loads(l.drafted_email_json).get("is_approved")
        and l.date_email_sent is None
        and not l.opted_out
    ]

    if not approved:
        return {"success": True, "message": "Keine genehmigten E-Mails zum Senden."}

    batch = approved[:batch_size]
    sent = 0
    failed = 0
    skipped_opt_out = 0
    skipped_scheduled = 0
    sender = db_svc.get_setting(db, "sender_email", "mf@harpocrates-corp.com")

    for i, lead in enumerate(batch):
        if db_svc.is_blocked(db, lead.email):
            lead.status = "Do Not Contact"
            lead.opted_out = True
            db.commit()
            skipped_opt_out += 1
            continue

        if lead.scheduled_send_date and lead.scheduled_send_date > datetime.utcnow():
            skipped_scheduled += 1
            continue

        draft = json.loads(lead.drafted_email_json)
        try:
            await gmail.send_email(
                to=lead.email,
                from_addr=sender,
                subject=draft["subject"],
                body=draft["body"],
                access_token=access_token,
            )
            lead.status = "Email Sent"
            lead.date_email_sent = datetime.utcnow()
            draft["sent_date"] = datetime.utcnow().isoformat()
            lead.drafted_email_json = json.dumps(draft)
            lead.delivery_status = "Delivered"
            lead.updated_at = datetime.utcnow()
            db.commit()
            sent += 1

            # Random delay 30-90s between sends
            if i < len(batch) - 1:
                await asyncio.sleep(random.uniform(30, 90))
        except Exception:
            lead.delivery_status = "Failed"
            lead.updated_at = datetime.utcnow()
            db.commit()
            failed += 1

    remaining = len(approved) - len(batch)
    return {
        "success": True,
        "sent": sent,
        "failed": failed,
        "skipped_opt_out": skipped_opt_out,
        "skipped_scheduled": skipped_scheduled,
        "remaining": remaining,
    }


# ─── Batch Send (specific IDs – campaign wizard step 4) ──────

@router.post("/send-batch")
async def send_batch(data: BatchLeadIds, db: Session = Depends(get_db)):
    """Send approved emails for specific leads (campaign wizard step 4).
    Respects rate limits: 30-90s random delay between sends."""
    access_token = _get_access_token(db)
    sender = db_svc.get_setting(db, "sender_email", "mf@harpocrates-corp.com")

    sent = 0
    failed = 0
    skipped = 0

    for i, lid_str in enumerate(data.lead_ids):
        try:
            lid = UUID(lid_str)
        except ValueError:
            failed += 1
            continue

        lead = db_svc.get_lead(db, lid)
        if not lead or not lead.drafted_email_json:
            failed += 1
            continue

        draft = json.loads(lead.drafted_email_json)
        if not draft.get("is_approved"):
            skipped += 1
            continue

        if db_svc.is_blocked(db, lead.email):
            lead.status = "Do Not Contact"
            lead.opted_out = True
            db.commit()
            skipped += 1
            continue

        if lead.date_email_sent:
            skipped += 1
            continue

        try:
            await gmail.send_email(
                to=lead.email,
                from_addr=sender,
                subject=draft["subject"],
                body=draft["body"],
                access_token=access_token,
            )
            lead.status = "Email Sent"
            lead.date_email_sent = datetime.utcnow()
            draft["sent_date"] = datetime.utcnow().isoformat()
            lead.drafted_email_json = json.dumps(draft)
            lead.delivery_status = "Delivered"
            lead.updated_at = datetime.utcnow()
            db.commit()
            sent += 1

            # Rate limit: random 30-90s delay between sends
            if i < len(data.lead_ids) - 1:
                await asyncio.sleep(random.uniform(30, 90))
        except Exception as e:
            lead.delivery_status = "Failed"
            lead.updated_at = datetime.utcnow()
            db.commit()
            failed += 1

    return {"success": True, "sent": sent, "failed": failed, "skipped": skipped}


# ─── Follow-Up Draft ─────────────────────────────────────────

@router.post("/draft-follow-up/{lead_id}")
async def draft_follow_up(lead_id: UUID, db: Session = Depends(get_db)):
    """Draft a follow-up email for a lead."""
    api_key = db_svc.get_setting(db, "perplexity_api_key")
    if not api_key:
        raise HTTPException(400, "Perplexity API Key fehlt.")

    lead = db_svc.get_lead(db, lead_id)
    if not lead:
        raise HTTPException(404, "Lead nicht gefunden.")

    original = ""
    if lead.drafted_email_json:
        draft = json.loads(lead.drafted_email_json)
        original = f"Subject: {draft.get('subject', '')}\n\n{draft.get('body', '')}"

    existing_followup = ""
    if lead.follow_up_email_json:
        fu = json.loads(lead.follow_up_email_json)
        existing_followup = f"Subject: {fu.get('subject', '')}\n\n{fu.get('body', '')}"

    sender_name = db_svc.get_setting(db, "sender_name", "Martin Foerster")
    result = await pplx.draft_follow_up(
        lead.name, lead.company, original, existing_followup,
        lead.reply_received, sender_name, api_key
    )

    follow_up = OutboundEmail(
        id=uuid4(),
        subject=result["subject"],
        body=result["body"],
        is_approved=False,
    )
    lead.follow_up_email_json = follow_up.model_dump_json()
    lead.status = "Follow-Up Drafted"
    lead.updated_at = datetime.utcnow()
    db.commit()

    return {"success": True, "data": follow_up.model_dump()}
