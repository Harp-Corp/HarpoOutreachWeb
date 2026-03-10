# Campaign Sequence routes – multi-touch automated outreach
from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..models.db import CampaignTemplateDB, CompanyDB, LeadDB, get_db
from ..services import database_service as db_svc
from ..services import perplexity_service as pplx
from ..services import smtp_service as smtp
from ..config import settings

logger = logging.getLogger("harpo.campaigns")

router = APIRouter(prefix="/campaigns", tags=["Campaign Sequences"])


# ─── Pydantic Models ──────────────────────────────────────────────

class SequenceStep(BaseModel):
    step: int
    type: str  # "initial" | "follow_up_1" | "follow_up_2" | "follow_up_3" | "breakup"
    delay_days: int  # days after previous step
    subject_template: str = ""  # optional — if empty, auto-generate
    body_template: str = ""  # optional — if empty, auto-generate


class CreateTemplateBody(BaseModel):
    name: str
    description: str = ""
    steps: list[SequenceStep]


class StartCampaignBody(BaseModel):
    lead_ids: list[str]
    template_id: str = ""  # empty = use default


class AdvanceStepBody(BaseModel):
    lead_ids: list[str] = []  # empty = all eligible


# ─── Default Campaign Template ────────────────────────────────────

DEFAULT_SEQUENCE = [
    {"step": 1, "type": "initial", "delay_days": 0, "subject_template": "", "body_template": ""},
    {"step": 2, "type": "follow_up_1", "delay_days": 3, "subject_template": "", "body_template": ""},
    {"step": 3, "type": "follow_up_2", "delay_days": 5, "subject_template": "", "body_template": ""},
    {"step": 4, "type": "breakup", "delay_days": 7, "subject_template": "", "body_template": ""},
]


def _get_default_template(db: Session) -> dict:
    """Get or create the default campaign template."""
    existing = db.query(CampaignTemplateDB).filter(CampaignTemplateDB.name == "Standard-Sequenz").first()
    if existing:
        return {
            "id": str(existing.id),
            "name": existing.name,
            "description": existing.description,
            "steps": json.loads(existing.steps_json),
            "is_active": existing.is_active,
        }
    # Create default
    tpl = CampaignTemplateDB(
        id=uuid4(),
        name="Standard-Sequenz",
        description="4-Schritt-Sequenz: Initial → Follow-Up 1 (Tag 3) → Follow-Up 2 (Tag 8) → Breakup (Tag 15)",
        steps_json=json.dumps(DEFAULT_SEQUENCE),
        is_active=True,
    )
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return {
        "id": str(tpl.id),
        "name": tpl.name,
        "description": tpl.description,
        "steps": DEFAULT_SEQUENCE,
        "is_active": True,
    }


# ─── Template CRUD ────────────────────────────────────────────────

@router.get("/templates")
async def list_templates(db: Session = Depends(get_db)):
    """List all campaign templates."""
    templates = db.query(CampaignTemplateDB).order_by(CampaignTemplateDB.created_at).all()
    if not templates:
        # Ensure default exists
        _get_default_template(db)
        templates = db.query(CampaignTemplateDB).all()
    return {
        "data": [
            {
                "id": str(t.id),
                "name": t.name,
                "description": t.description,
                "steps": json.loads(t.steps_json),
                "is_active": t.is_active,
            }
            for t in templates
        ]
    }


@router.post("/templates")
async def create_template(body: CreateTemplateBody, db: Session = Depends(get_db)):
    """Create a new campaign template."""
    steps_data = [s.model_dump() for s in body.steps]
    tpl = CampaignTemplateDB(
        id=uuid4(),
        name=body.name,
        description=body.description,
        steps_json=json.dumps(steps_data),
        is_active=True,
    )
    db.add(tpl)
    db.commit()
    return {"success": True, "id": str(tpl.id)}


@router.delete("/templates/{template_id}")
async def delete_template(template_id: UUID, db: Session = Depends(get_db)):
    obj = db.get(CampaignTemplateDB, template_id)
    if obj:
        db.delete(obj)
        db.commit()
    return {"success": True}


# ─── Start Campaign for Leads ────────────────────────────────────

@router.post("/start")
async def start_campaign(body: StartCampaignBody, db: Session = Depends(get_db)):
    """Assign a campaign sequence to leads. This sets up the sequence steps
    but does NOT send anything — all sends require explicit approval."""
    # Get template
    if body.template_id:
        tpl = db.get(CampaignTemplateDB, UUID(body.template_id))
        if not tpl:
            raise HTTPException(404, "Template nicht gefunden.")
        steps = json.loads(tpl.steps_json)
    else:
        default = _get_default_template(db)
        steps = default["steps"]

    started = 0
    skipped = 0
    for lid_str in body.lead_ids:
        try:
            lid = UUID(lid_str)
        except ValueError:
            skipped += 1
            continue
        lead = db_svc.get_lead(db, lid)
        if not lead:
            skipped += 1
            continue
        if lead.campaign_sequence_json:
            # Already has a campaign — skip
            skipped += 1
            continue

        # Initialize campaign sequence on lead
        now = datetime.utcnow()
        sequence_entries = []
        cumulative_days = 0
        for step in steps:
            cumulative_days += step.get("delay_days", 0)
            scheduled_at = (now + timedelta(days=cumulative_days)).isoformat()
            sequence_entries.append({
                "step": step["step"],
                "type": step["type"],
                "delay_days": step.get("delay_days", 0),
                "subject": "",  # generated when drafted
                "body": "",
                "status": "pending",  # pending | drafted | approved | sent | skipped
                "scheduled_at": scheduled_at,
                "sent_at": None,
            })

        lead.campaign_sequence_json = json.dumps(sequence_entries)
        lead.campaign_current_step = 0
        lead.campaign_paused = False
        lead.updated_at = datetime.utcnow()
        started += 1

    db.commit()
    return {"success": True, "started": started, "skipped": skipped}


# ─── Draft Next Step ─────────────────────────────────────────────

@router.post("/draft-next/{lead_id}")
async def draft_next_step(lead_id: UUID, db: Session = Depends(get_db)):
    """Draft the next pending step in a lead's campaign sequence."""
    api_key = db_svc.get_setting(db, "perplexity_api_key")
    if not api_key:
        raise HTTPException(400, "Perplexity API Key fehlt.")

    lead = db_svc.get_lead(db, lead_id)
    if not lead:
        raise HTTPException(404, "Lead nicht gefunden.")
    if not lead.campaign_sequence_json:
        raise HTTPException(400, "Kein Kampagnen-Sequenz zugewiesen.")
    if lead.campaign_paused:
        raise HTTPException(400, "Kampagne ist pausiert.")

    sequence = json.loads(lead.campaign_sequence_json)
    # Find next pending step
    next_step = None
    for s in sequence:
        if s["status"] == "pending":
            next_step = s
            break

    if not next_step:
        return {"success": True, "message": "Alle Schritte abgeschlossen."}

    # Generate content based on step type
    company = db.query(CompanyDB).filter(CompanyDB.name.ilike(lead.company)).first()
    company_name = company.name if company else lead.company
    company_industry = company.industry if company else ""
    sender_name = db_svc.get_setting(db, "sender_name", "Martin Foerster")

    step_type = next_step["type"]

    if step_type == "initial":
        # Research + draft initial email
        try:
            challenges = await pplx.research_challenges(company_name, company_industry, api_key)
        except Exception:
            challenges = pplx._generic_compliance_challenges(company_name, company_industry)

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

    elif step_type == "breakup":
        # Breakup email — short, final touch
        email_data = await _draft_breakup(lead, sender_name, api_key)

    else:
        # Follow-up: use existing follow-up logic with fresh angle
        original = ""
        if lead.drafted_email_json:
            draft = json.loads(lead.drafted_email_json)
            original = f"Subject: {draft.get('subject', '')}\n\n{draft.get('body', '')}"

        # Collect previous follow-ups from sequence
        prev_followups = ""
        for s in sequence:
            if s["status"] == "sent" and s["type"].startswith("follow_up"):
                prev_followups += f"\nSubject: {s.get('subject', '')}\n{s.get('body', '')}\n"

        email_data = await pplx.draft_follow_up(
            lead.name, lead.company, original, prev_followups,
            lead.reply_received, sender_name, api_key
        )

    next_step["subject"] = email_data.get("subject", "")
    next_step["body"] = email_data.get("body", "")
    next_step["status"] = "drafted"

    lead.campaign_sequence_json = json.dumps(sequence)
    lead.campaign_current_step = next_step["step"]
    lead.updated_at = datetime.utcnow()

    # Also update drafted_email_json for backward compatibility
    if step_type == "initial":
        from ..models.schemas import OutboundEmail
        draft = OutboundEmail(
            id=uuid4(),
            subject=email_data["subject"],
            body=email_data["body"],
            is_approved=False,
        )
        lead.drafted_email_json = draft.model_dump_json()
        lead.status = "Email Drafted"
    elif step_type.startswith("follow_up"):
        from ..models.schemas import OutboundEmail
        fu = OutboundEmail(
            id=uuid4(),
            subject=email_data["subject"],
            body=email_data["body"],
            is_approved=False,
        )
        lead.follow_up_email_json = fu.model_dump_json()
        lead.status = "Follow-Up Drafted"

    db.commit()

    return {
        "success": True,
        "step": next_step["step"],
        "type": step_type,
        "subject": email_data.get("subject", ""),
        "body": email_data.get("body", ""),
    }


async def _draft_breakup(lead, sender_name: str, api_key: str) -> dict:
    """Draft a short breakup email."""
    system = f"""Du schreibst eine letzte, kurze Abschluss-E-Mail (Breakup-E-Mail) für B2B-Outreach.

REGELN:
1. Auf ENGLISCH schreiben.
2. Maximal 50 Wörter.
3. Freundlich, nicht vorwurfsvoll.
4. Anbieten, den Kontakt zu schließen, es sei denn, sie möchten noch reden.
5. KEINE Signatur oder Footer — wird automatisch hinzugefügt.
6. Return ONLY valid JSON: {{"subject": "...", "body": "..."}}"""

    user = f"""Schreibe eine kurze Breakup-E-Mail von {sender_name} (Harpocrates Corp) an {lead.name} bei {lead.company}.
Letzte Chance, bevor wir den Kontakt schließen.
Return JSON: {{"subject": "...", "body": "..."}}"""

    content = await pplx._call_api(
        system, user, api_key, max_tokens=500, model=pplx.MODEL_FAST, search_context_size="low",
    )
    raw = content if isinstance(content, str) else content.get("content", "")
    cleaned = pplx._clean_json(raw)
    try:
        data = json.loads(cleaned)
        return {
            "subject": data.get("subject", f"Closing the loop — {lead.company}"),
            "body": data.get("body", raw),
        }
    except Exception:
        return {"subject": f"Closing the loop — {lead.company}", "body": raw}


# ─── Campaign Status ──────────────────────────────────────────────

@router.get("/status")
async def campaign_status(db: Session = Depends(get_db)):
    """Get overview of all leads with active campaigns."""
    leads = db_svc.load_leads(db)
    campaigns = []
    for lead in leads:
        if not lead.campaign_sequence_json:
            continue
        sequence = json.loads(lead.campaign_sequence_json)
        total_steps = len(sequence)
        completed = sum(1 for s in sequence if s["status"] == "sent")
        pending = sum(1 for s in sequence if s["status"] == "pending")
        drafted = sum(1 for s in sequence if s["status"] == "drafted")
        approved = sum(1 for s in sequence if s["status"] == "approved")

        # Find next action
        next_action = None
        for s in sequence:
            if s["status"] in ("pending", "drafted", "approved"):
                next_action = {
                    "step": s["step"],
                    "type": s["type"],
                    "status": s["status"],
                    "scheduled_at": s.get("scheduled_at"),
                }
                break

        campaigns.append({
            "lead_id": str(lead.id),
            "name": lead.name,
            "company": lead.company,
            "email": lead.email,
            "total_steps": total_steps,
            "completed_steps": completed,
            "pending_steps": pending,
            "drafted_steps": drafted,
            "approved_steps": approved,
            "current_step": lead.campaign_current_step,
            "is_paused": lead.campaign_paused,
            "has_reply": bool(lead.reply_received),
            "status": lead.status,
            "next_action": next_action,
            "sequence": sequence,
        })

    return {"data": campaigns, "total": len(campaigns)}


# ─── Pause / Resume Campaign ─────────────────────────────────────

@router.post("/pause/{lead_id}")
async def pause_campaign(lead_id: UUID, db: Session = Depends(get_db)):
    lead = db_svc.get_lead(db, lead_id)
    if not lead:
        raise HTTPException(404, "Lead nicht gefunden.")
    lead.campaign_paused = True
    lead.updated_at = datetime.utcnow()
    db.commit()
    return {"success": True}


@router.post("/resume/{lead_id}")
async def resume_campaign(lead_id: UUID, db: Session = Depends(get_db)):
    lead = db_svc.get_lead(db, lead_id)
    if not lead:
        raise HTTPException(404, "Lead nicht gefunden.")
    lead.campaign_paused = False
    lead.updated_at = datetime.utcnow()
    db.commit()
    return {"success": True}


# ─── Approve Step ─────────────────────────────────────────────────

@router.post("/approve-step/{lead_id}/{step_num}")
async def approve_step(lead_id: UUID, step_num: int, db: Session = Depends(get_db)):
    """Approve a specific step in a lead's campaign sequence."""
    lead = db_svc.get_lead(db, lead_id)
    if not lead:
        raise HTTPException(404, "Lead nicht gefunden.")
    if not lead.campaign_sequence_json:
        raise HTTPException(400, "Keine Kampagne zugewiesen.")

    sequence = json.loads(lead.campaign_sequence_json)
    updated = False
    for s in sequence:
        if s["step"] == step_num and s["status"] == "drafted":
            s["status"] = "approved"
            updated = True
            break

    if not updated:
        raise HTTPException(400, f"Schritt {step_num} ist nicht im Status 'drafted'.")

    lead.campaign_sequence_json = json.dumps(sequence)

    # Also update backward-compatible fields
    step = next(s for s in sequence if s["step"] == step_num)
    if step["type"] == "initial" and lead.drafted_email_json:
        draft = json.loads(lead.drafted_email_json)
        draft["is_approved"] = True
        lead.drafted_email_json = json.dumps(draft)
        lead.status = "Email Approved"
    elif step["type"].startswith("follow_up") and lead.follow_up_email_json:
        fu = json.loads(lead.follow_up_email_json)
        fu["is_approved"] = True
        lead.follow_up_email_json = json.dumps(fu)

    lead.updated_at = datetime.utcnow()
    db.commit()
    return {"success": True}


# ─── Draft All Next Steps (batch) ────────────────────────────────

@router.post("/draft-all-next")
async def draft_all_next_steps(db: Session = Depends(get_db)):
    """Draft the next pending step for all leads with active campaigns."""
    api_key = db_svc.get_setting(db, "perplexity_api_key")
    if not api_key:
        raise HTTPException(400, "Perplexity API Key fehlt.")

    leads = db_svc.load_leads(db)
    drafted = 0
    skipped = 0
    errors = []

    for lead in leads:
        if not lead.campaign_sequence_json or lead.campaign_paused:
            continue
        if lead.reply_received:
            # Auto-pause campaign if reply received
            lead.campaign_paused = True
            db.commit()
            continue

        sequence = json.loads(lead.campaign_sequence_json)
        next_step = None
        for s in sequence:
            if s["status"] == "pending":
                # Check if scheduled time has passed
                sched = s.get("scheduled_at", "")
                if sched:
                    try:
                        sched_dt = datetime.fromisoformat(sched)
                        if sched_dt > datetime.utcnow():
                            break  # Not time yet
                    except Exception:
                        pass
                next_step = s
                break

        if not next_step:
            skipped += 1
            continue

        try:
            # Call draft-next logic
            # (Simplified — re-uses same logic as draft_next_step)
            company = db.query(CompanyDB).filter(CompanyDB.name.ilike(lead.company)).first()
            company_name = company.name if company else lead.company
            company_industry = company.industry if company else ""
            sender_name = db_svc.get_setting(db, "sender_name", "Martin Foerster")

            step_type = next_step["type"]

            if step_type == "initial":
                try:
                    challenges = await pplx.research_challenges(company_name, company_industry, api_key)
                except Exception:
                    challenges = pplx._generic_compliance_challenges(company_name, company_industry)
                email_data = await pplx.draft_email(
                    lead.name, lead.title, lead.company, challenges, sender_name, api_key
                )
            elif step_type == "breakup":
                email_data = await _draft_breakup(lead, sender_name, api_key)
            else:
                original = ""
                if lead.drafted_email_json:
                    draft = json.loads(lead.drafted_email_json)
                    original = f"Subject: {draft.get('subject', '')}\n\n{draft.get('body', '')}"
                email_data = await pplx.draft_follow_up(
                    lead.name, lead.company, original, "",
                    lead.reply_received, sender_name, api_key
                )

            next_step["subject"] = email_data.get("subject", "")
            next_step["body"] = email_data.get("body", "")
            next_step["status"] = "drafted"
            lead.campaign_sequence_json = json.dumps(sequence)
            lead.campaign_current_step = next_step["step"]
            lead.updated_at = datetime.utcnow()
            db.commit()
            drafted += 1
        except Exception as e:
            errors.append(f"{lead.name}: {str(e)[:100]}")
            continue

    return {"success": True, "drafted": drafted, "skipped": skipped, "errors": errors[:5]}


# ─── SMTP Send Helper (shared with email_pipeline) ──────────────

def _get_smtp_config(db: Session) -> dict:
    """Get SMTP configuration from DB settings with fallback to env vars."""
    return {
        "smtp_host": db_svc.get_setting(db, "smtp_host") or settings.smtp_host,
        "smtp_port": int(db_svc.get_setting(db, "smtp_port") or settings.smtp_port),
        "smtp_user": db_svc.get_setting(db, "smtp_user") or settings.smtp_user,
        "smtp_password": db_svc.get_setting(db, "smtp_password") or settings.smtp_password,
    }


async def _send_step_via_smtp(
    to: str, from_addr: str, subject: str, body: str,
    db: Session, reply_to: str | None = None,
) -> dict:
    """Send campaign step email via Hostinger SMTP."""
    smtp_cfg = _get_smtp_config(db)
    if not smtp_cfg["smtp_password"]:
        raise HTTPException(400, "SMTP-Passwort nicht konfiguriert.")
    return await asyncio.to_thread(
        smtp.send_email,
        to=to, from_addr=from_addr, subject=subject, body=body,
        smtp_host=smtp_cfg["smtp_host"], smtp_port=smtp_cfg["smtp_port"],
        smtp_user=smtp_cfg["smtp_user"], smtp_password=smtp_cfg["smtp_password"],
        reply_to=reply_to,
    )


# ─── Send Campaign Step ──────────────────────────────────────────

@router.post("/send-step/{lead_id}/{step_num}")
async def send_campaign_step(lead_id: UUID, step_num: int, db: Session = Depends(get_db)):
    """Send an approved campaign step via SMTP. Requires explicit user approval first."""
    lead = db_svc.get_lead(db, lead_id)
    if not lead:
        raise HTTPException(404, "Lead nicht gefunden.")
    if not lead.campaign_sequence_json:
        raise HTTPException(400, "Keine Kampagne zugewiesen.")
    if lead.campaign_paused:
        raise HTTPException(400, "Kampagne ist pausiert.")

    sequence = json.loads(lead.campaign_sequence_json)
    target_step = None
    for s in sequence:
        if s["step"] == step_num:
            target_step = s
            break

    if not target_step:
        raise HTTPException(404, f"Schritt {step_num} nicht gefunden.")
    if target_step["status"] != "approved":
        raise HTTPException(400, f"Schritt {step_num} ist nicht genehmigt (Status: {target_step['status']}).")

    # Blocklist check
    if db_svc.is_blocked(db, lead.email):
        lead.status = "Do Not Contact"
        lead.opted_out = True
        lead.campaign_paused = True
        lead.updated_at = datetime.utcnow()
        db.commit()
        raise HTTPException(400, f"{lead.email} steht auf der Opt-Out-Liste.")

    sender = db_svc.get_setting(db, "sender_email", "mf@harpocrates-corp.com")
    reply_to = db_svc.get_setting(db, "reply_to_email") or settings.reply_to_email

    try:
        send_result = await _send_step_via_smtp(
            to=lead.email, from_addr=sender,
            subject=target_step["subject"], body=target_step["body"],
            db=db, reply_to=reply_to,
        )
    except Exception as e:
        logger.error(f"Campaign step send failed for {lead.email}: {e}")
        target_step["status"] = "failed"
        lead.campaign_sequence_json = json.dumps(sequence)
        lead.updated_at = datetime.utcnow()
        db.commit()
        raise HTTPException(500, f"Senden fehlgeschlagen: {str(e)}")

    # Update step
    target_step["status"] = "sent"
    target_step["sent_at"] = datetime.utcnow().isoformat()
    target_step["msg_id"] = send_result.get("msg_id", "")
    lead.campaign_sequence_json = json.dumps(sequence)

    # Update lead status based on step type
    step_type = target_step["type"]
    if step_type == "initial":
        lead.status = "Email Sent"
        lead.date_email_sent = datetime.utcnow()
        lead.delivery_status = "Delivered"
        lead.gmail_thread_id = send_result.get("msg_id", "")
        if lead.drafted_email_json:
            draft = json.loads(lead.drafted_email_json)
            draft["sent_date"] = datetime.utcnow().isoformat()
            lead.drafted_email_json = json.dumps(draft)
    elif step_type.startswith("follow_up"):
        lead.status = "Follow-Up Sent"
        lead.date_follow_up_sent = datetime.utcnow()
    elif step_type == "breakup":
        lead.status = "Breakup Sent"

    lead.campaign_current_step = step_num
    lead.updated_at = datetime.utcnow()
    db.commit()

    logger.info(f"Campaign step {step_num} ({step_type}) sent to {lead.email}")
    return {"success": True, "step": step_num, "type": step_type, "message_id": send_result.get("msg_id")}


# ─── Send All Approved Steps (batch) ─────────────────────────────

@router.post("/send-approved-steps")
async def send_approved_steps(db: Session = Depends(get_db)):
    """Send all approved campaign steps that are due. Respects scheduling and rate limits.
    This is the main batch send endpoint for campaign automation."""
    leads = db_svc.load_leads(db)
    sent = 0
    failed = 0
    skipped = 0
    errors = []

    sender = db_svc.get_setting(db, "sender_email", "mf@harpocrates-corp.com")
    reply_to = db_svc.get_setting(db, "reply_to_email") or settings.reply_to_email

    for lead in leads:
        if not lead.campaign_sequence_json or lead.campaign_paused:
            continue
        if lead.reply_received:
            # Auto-pause on reply
            lead.campaign_paused = True
            db.commit()
            continue

        sequence = json.loads(lead.campaign_sequence_json)
        approved_step = None
        for s in sequence:
            if s["status"] == "approved":
                # Check if scheduled time has passed
                sched = s.get("scheduled_at", "")
                if sched:
                    try:
                        sched_dt = datetime.fromisoformat(sched)
                        if sched_dt > datetime.utcnow():
                            break  # Not time yet
                    except Exception:
                        pass
                approved_step = s
                break

        if not approved_step:
            skipped += 1
            continue

        if db_svc.is_blocked(db, lead.email):
            lead.status = "Do Not Contact"
            lead.opted_out = True
            lead.campaign_paused = True
            lead.updated_at = datetime.utcnow()
            db.commit()
            skipped += 1
            continue

        try:
            send_result = await _send_step_via_smtp(
                to=lead.email, from_addr=sender,
                subject=approved_step["subject"], body=approved_step["body"],
                db=db, reply_to=reply_to,
            )

            approved_step["status"] = "sent"
            approved_step["sent_at"] = datetime.utcnow().isoformat()
            approved_step["msg_id"] = send_result.get("msg_id", "")
            lead.campaign_sequence_json = json.dumps(sequence)

            step_type = approved_step["type"]
            if step_type == "initial":
                lead.status = "Email Sent"
                lead.date_email_sent = datetime.utcnow()
                lead.delivery_status = "Delivered"
                lead.gmail_thread_id = send_result.get("msg_id", "")
            elif step_type.startswith("follow_up"):
                lead.status = "Follow-Up Sent"
                lead.date_follow_up_sent = datetime.utcnow()
            elif step_type == "breakup":
                lead.status = "Breakup Sent"

            lead.campaign_current_step = approved_step["step"]
            lead.updated_at = datetime.utcnow()
            db.commit()
            sent += 1
            logger.info(f"Campaign step {approved_step['step']} sent to {lead.email}")

            # Rate limit: 30-90s between sends
            await asyncio.sleep(random.uniform(30, 90))

        except Exception as e:
            logger.error(f"Campaign send failed for {lead.email}: {e}")
            failed += 1
            errors.append(f"{lead.name}: {str(e)[:100]}")

    return {"success": True, "sent": sent, "failed": failed, "skipped": skipped, "errors": errors[:5]}
