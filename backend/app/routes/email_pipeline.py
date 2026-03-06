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


import logging
import time as _time

import httpx as _httpx

_logger = logging.getLogger("harpo.email_pipeline")


def _refresh_google_token(db: Session) -> str:
    """Refresh the Google access token using the refresh token. Returns new access token."""
    refresh_tok = db_svc.get_setting(db, "google_refresh_token")
    if not refresh_tok:
        raise HTTPException(401, "Kein Refresh-Token vorhanden. Bitte erneut mit Google verbinden.")
    client_id = db_svc.get_setting(db, "google_client_id")
    client_secret = db_svc.get_setting(db, "google_client_secret")
    if not client_id or not client_secret:
        raise HTTPException(401, "Google OAuth Credentials fehlen. Bitte erneut mit Google verbinden.")

    _logger.info("Refreshing Google access token...")
    resp = _httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "refresh_token": refresh_tok,
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        error_detail = resp.text[:300]
        _logger.error(f"Token refresh failed ({resp.status_code}): {error_detail}")
        raise HTTPException(401, f"Token-Refresh fehlgeschlagen ({resp.status_code}): {error_detail}")

    data = resp.json()
    new_token = data.get("access_token", "")
    if not new_token:
        raise HTTPException(401, "Token-Refresh lieferte kein neues Token.")

    db_svc.set_setting(db, "google_access_token", new_token)
    db_svc.set_setting(db, "google_token_expiry", str(_time.time() + data.get("expires_in", 3600)))
    if data.get("refresh_token"):
        db_svc.set_setting(db, "google_refresh_token", data["refresh_token"])
    _logger.info("Token refresh successful")
    return new_token


def _get_access_token(db: Session) -> str:
    """Get a valid Google access token — auto-refresh if expired or missing expiry."""
    token = db_svc.get_setting(db, "google_access_token")
    if not token:
        raise HTTPException(401, "Nicht mit Google authentifiziert. Bitte unter Einstellungen mit Google verbinden.")

    # Check expiry and refresh proactively
    expiry = db_svc.get_setting(db, "google_token_expiry")
    needs_refresh = False

    if not expiry:
        # No expiry recorded — always refresh to be safe
        _logger.warning("No token expiry recorded, refreshing proactively")
        needs_refresh = True
    else:
        try:
            expiry_ts = float(expiry)
            if expiry_ts < _time.time() + 120:  # refresh 2 min before actual expiry
                _logger.info(f"Token expired or expiring soon (expiry={expiry_ts}, now={_time.time()})")
                needs_refresh = True
        except (ValueError, TypeError):
            _logger.warning(f"Unparseable token expiry '{expiry}', refreshing proactively")
            needs_refresh = True

    if needs_refresh:
        try:
            return _refresh_google_token(db)
        except HTTPException:
            raise
        except Exception as e:
            _logger.error(f"Token refresh failed unexpectedly: {e}")
            # Fall through to try with existing token

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

    # Step 1: Research challenges (with fallback for unknown companies)
    try:
        challenges = await pplx.research_challenges(company_name, company_industry, api_key)
    except Exception as e:
        _logger.warning(f"Challenge research failed for {company_name}: {e}, using generic fallback")
        challenges = pplx._generic_compliance_challenges(company_name, company_industry)

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

            try:
                challenges = await pplx.research_challenges(company_name, company_industry, api_key)
            except Exception:
                challenges = pplx._generic_compliance_challenges(company_name, company_industry)
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

            try:
                challenges = await pplx.research_challenges(company_name, company_industry, api_key)
            except Exception:
                challenges = pplx._generic_compliance_challenges(company_name, company_industry)
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


@router.post("/reset/{lead_id}")
async def reset_lead_campaign(lead_id: UUID, db: Session = Depends(get_db)):
    """Full reset: clears draft, send date, thread ID, delivery status, blocklist entry."""
    lead = db_svc.get_lead(db, lead_id)
    if not lead:
        raise HTTPException(404, "Lead nicht gefunden.")
    lead.drafted_email_json = None
    lead.date_email_sent = None
    lead.delivery_status = "Pending"
    lead.gmail_thread_id = None
    lead.reply_received = ""
    lead.opted_out = False
    lead.opt_out_date = None
    lead.status = "Identified"
    lead.updated_at = datetime.utcnow()
    # Also remove from blocklist if present
    if lead.email:
        db_svc.remove_from_blocklist(db, lead.email)
    db.commit()
    _logger.info(f"Lead {lead_id} ({lead.name}) full campaign reset (incl. blocklist)")
    return {"success": True}


@router.post("/resend/{lead_id}")
async def resend_lead(lead_id: UUID, db: Session = Depends(get_db)):
    """Soft reset for re-sending: keeps draft+approval, only clears send date so it can be sent again."""
    lead = db_svc.get_lead(db, lead_id)
    if not lead:
        raise HTTPException(404, "Lead nicht gefunden.")
    if not lead.drafted_email_json:
        raise HTTPException(400, "Kein E-Mail-Entwurf vorhanden. Bitte erst einen Draft erstellen.")
    lead.date_email_sent = None
    lead.delivery_status = "Pending"
    lead.gmail_thread_id = None
    lead.reply_received = ""
    lead.opted_out = False
    lead.opt_out_date = None
    # Keep draft and approval, set status to Email Approved if was approved
    draft = json.loads(lead.drafted_email_json)
    if draft.get("is_approved"):
        lead.status = "Email Approved"
    else:
        lead.status = "Email Drafted"
    lead.updated_at = datetime.utcnow()
    # Also remove from blocklist if present
    if lead.email:
        db_svc.remove_from_blocklist(db, lead.email)
    db.commit()
    _logger.info(f"Lead {lead_id} ({lead.name}) reset for resend (draft kept, blocklist cleared)")
    return {"success": True}


@router.post("/reset-batch")
async def reset_batch(data: BatchLeadIds, db: Session = Depends(get_db)):
    """Reset multiple leads for re-sending (campaign wizard reset)."""
    reset_count = 0
    for lid_str in data.lead_ids:
        try:
            lid = UUID(lid_str)
        except ValueError:
            continue
        lead = db_svc.get_lead(db, lid)
        if not lead:
            continue
        lead.drafted_email_json = None
        lead.date_email_sent = None
        lead.delivery_status = "Pending"
        lead.gmail_thread_id = None
        lead.reply_received = ""
        lead.opted_out = False
        lead.opt_out_date = None
        lead.status = "Identified"
        lead.updated_at = datetime.utcnow()
        # Also remove from blocklist if present
        if lead.email:
            db_svc.remove_from_blocklist(db, lead.email)
        reset_count += 1
    db.commit()
    _logger.info(f"Batch reset: {reset_count} leads (incl. blocklist)")
    return {"success": True, "reset": reset_count}


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
    _logger.info(f"Sending email to {lead.email} (lead={lead_id}, subject='{draft.get('subject', '')[:50]}')")

    async def _try_send(token):
        return await gmail.send_email(
            to=lead.email, from_addr=sender,
            subject=draft["subject"], body=draft["body"],
            access_token=token,
        )

    try:
        send_result = await _try_send(access_token)
    except PermissionError:
        # Token expired mid-request — refresh and retry once
        _logger.warning(f"Gmail 401 for {lead.email}, refreshing token and retrying")
        try:
            access_token = _refresh_google_token(db)
            send_result = await _try_send(access_token)
        except Exception as retry_e:
            _logger.error(f"Retry also failed for {lead.email}: {retry_e}")
            lead.delivery_status = "Failed"
            lead.updated_at = datetime.utcnow()
            db.commit()
            raise HTTPException(500, f"Senden fehlgeschlagen (auch nach Token-Refresh): {str(retry_e)}")
    except Exception as e:
        _logger.error(f"Send failed for {lead.email}: {e}")
        lead.delivery_status = "Failed"
        lead.updated_at = datetime.utcnow()
        db.commit()
        raise HTTPException(500, f"Senden fehlgeschlagen: {str(e)}")

    lead.date_email_sent = datetime.utcnow()
    draft["sent_date"] = datetime.utcnow().isoformat()
    lead.drafted_email_json = json.dumps(draft)
    lead.status = "Email Sent"
    lead.delivery_status = "Delivered"
    lead.gmail_thread_id = send_result.get("thread_id", "")
    lead.updated_at = datetime.utcnow()
    db.commit()
    _logger.info(f"Email sent successfully to {lead.email}, msg_id={send_result.get('msg_id')}, thread_id={send_result.get('thread_id')}")
    return {"success": True, "message_id": send_result.get("msg_id")}


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
        _logger.info(f"[send-all] Sending to {lead.email} ({lead.name})")
        try:
            send_result = await gmail.send_email(
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
            lead.gmail_thread_id = send_result.get("thread_id", "")
            lead.updated_at = datetime.utcnow()
            db.commit()
            sent += 1
            _logger.info(f"[send-all] Sent to {lead.email}")

            # Random delay 30-90s between sends
            if i < len(batch) - 1:
                await asyncio.sleep(random.uniform(30, 90))
        except PermissionError:
            _logger.warning(f"[send-all] Gmail 401 for {lead.email}, refreshing token")
            try:
                access_token = _refresh_google_token(db)
                send_result = await gmail.send_email(
                    to=lead.email, from_addr=sender,
                    subject=draft["subject"], body=draft["body"],
                    access_token=access_token,
                )
                lead.status = "Email Sent"
                lead.date_email_sent = datetime.utcnow()
                draft["sent_date"] = datetime.utcnow().isoformat()
                lead.drafted_email_json = json.dumps(draft)
                lead.delivery_status = "Delivered"
                lead.gmail_thread_id = send_result.get("thread_id", "")
                lead.updated_at = datetime.utcnow()
                db.commit()
                sent += 1
            except Exception as retry_e:
                _logger.error(f"[send-all] Retry failed for {lead.email}: {retry_e}")
                lead.delivery_status = "Failed"
                lead.updated_at = datetime.utcnow()
                db.commit()
                failed += 1
        except Exception as e:
            _logger.error(f"[send-all] Failed for {lead.email}: {e}")
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

    _logger.info(f"send-batch called with {len(data.lead_ids)} lead IDs, sender={sender}")

    sent = 0
    failed = 0
    skipped = 0
    errors = []

    for i, lid_str in enumerate(data.lead_ids):
        try:
            lid = UUID(lid_str)
        except ValueError:
            _logger.error(f"Invalid UUID: {lid_str}")
            failed += 1
            errors.append(f"Ungültige ID: {lid_str}")
            continue

        lead = db_svc.get_lead(db, lid)
        if not lead:
            _logger.error(f"Lead not found: {lid}")
            failed += 1
            errors.append(f"Lead {lid} nicht gefunden")
            continue
        if not lead.drafted_email_json:
            _logger.error(f"Lead {lid} ({lead.name}) has no draft")
            failed += 1
            errors.append(f"{lead.name}: kein Entwurf")
            continue

        draft = json.loads(lead.drafted_email_json)
        if not draft.get("is_approved"):
            _logger.warning(f"Lead {lid} ({lead.name}) draft not approved")
            skipped += 1
            continue

        if db_svc.is_blocked(db, lead.email):
            _logger.warning(f"Lead {lid} ({lead.name}) is on blocklist")
            lead.status = "Do Not Contact"
            lead.opted_out = True
            db.commit()
            skipped += 1
            continue

        if lead.date_email_sent:
            _logger.info(f"Lead {lid} ({lead.name}) already sent on {lead.date_email_sent}")
            skipped += 1
            continue

        _logger.info(f"Sending to {lead.email} ({lead.name} @ {lead.company}), subject='{draft.get('subject', '')[:60]}'")

        try:
            send_result = await gmail.send_email(
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
            lead.gmail_thread_id = send_result.get("thread_id", "")
            lead.updated_at = datetime.utcnow()
            db.commit()
            sent += 1
            _logger.info(f"Successfully sent to {lead.email}")

            # Rate limit: random 30-90s delay between sends
            if i < len(data.lead_ids) - 1:
                delay = random.uniform(30, 90)
                _logger.info(f"Rate limit delay: {delay:.0f}s before next send")
                await asyncio.sleep(delay)
        except PermissionError:
            # Token expired — refresh and retry
            _logger.warning(f"Gmail 401 for {lead.email}, refreshing token")
            try:
                access_token = _refresh_google_token(db)
                send_result = await gmail.send_email(
                    to=lead.email, from_addr=sender,
                    subject=draft["subject"], body=draft["body"],
                    access_token=access_token,
                )
                lead.status = "Email Sent"
                lead.date_email_sent = datetime.utcnow()
                draft["sent_date"] = datetime.utcnow().isoformat()
                lead.drafted_email_json = json.dumps(draft)
                lead.delivery_status = "Delivered"
                lead.gmail_thread_id = send_result.get("thread_id", "")
                lead.updated_at = datetime.utcnow()
                db.commit()
                sent += 1
                _logger.info(f"Sent on retry to {lead.email}")
            except Exception as retry_e:
                _logger.error(f"Retry failed for {lead.email}: {retry_e}")
                lead.delivery_status = "Failed"
                lead.updated_at = datetime.utcnow()
                db.commit()
                failed += 1
                errors.append(f"{lead.name}: {str(retry_e)[:100]}")
        except Exception as e:
            _logger.error(f"Send failed for {lead.email}: {e}")
            lead.delivery_status = "Failed"
            lead.updated_at = datetime.utcnow()
            db.commit()
            failed += 1
            errors.append(f"{lead.name}: {str(e)[:100]}")

    _logger.info(f"send-batch result: sent={sent}, failed={failed}, skipped={skipped}")
    result = {"success": True, "sent": sent, "failed": failed, "skipped": skipped}
    if errors:
        result["errors"] = errors
    return result


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
