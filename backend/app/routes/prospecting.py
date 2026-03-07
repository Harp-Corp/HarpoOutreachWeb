# Prospecting routes – find companies, contacts, verify emails
from __future__ import annotations

import asyncio
import logging
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..models.db import get_db
from ..services import database_service as db_svc
from ..services import perplexity_service as pplx
from ..services import email_verify_service as email_verify
from ..models.schemas import Industry, Region

logger = logging.getLogger("harpo.prospecting")

router = APIRouter(prefix="/prospecting", tags=["Prospecting"])

# Max concurrent Perplexity API calls for verify-all
MAX_CONCURRENT_VERIFY = 3


@router.post("/find-companies")
async def find_companies(
    industries: list[str] = Query(...),
    regions: list[str] = Query(...),
    sizes: list[str] = Query(default=[]),
    db: Session = Depends(get_db),
):
    """Find companies by multiple industries and regions via Perplexity API."""
    api_key = db_svc.get_setting(db, "perplexity_api_key")
    if not api_key:
        raise HTTPException(400, "Perplexity API Key nicht konfiguriert.")

    # Resolve industries & regions
    resolved_industries = []
    for ind_str in industries:
        try:
            resolved_industries.append(Industry(ind_str))
        except ValueError:
            raise HTTPException(400, f"Unbekannte Branche: {ind_str}")

    resolved_regions = []
    for reg_str in regions:
        try:
            resolved_regions.append(Region(reg_str))
        except ValueError:
            raise HTTPException(400, f"Unbekannte Region: {reg_str}")

    if not resolved_industries or not resolved_regions:
        raise HTTPException(400, "Mindestens eine Branche und eine Region auswählen.")

    # Search for each industry-region combination
    all_saved = []
    for ind in resolved_industries:
        for reg in resolved_regions:
            try:
                # Pass size filter to Perplexity so the prompt targets the right companies
                size_hint = ",".join(sizes) if sizes else ""
                companies_raw = await pplx.find_companies(ind.value, reg.countries, api_key, size_filter=size_hint)
                for c in companies_raw:
                    if db_svc.company_exists(db, c["name"]):
                        continue
                    # Filter by size if specified
                    if sizes:
                        emp = c.get("employee_count", 0)
                        matches_size = False
                        for s in sizes:
                            if s == "0-200 Mitarbeiter" and emp <= 200:
                                matches_size = True
                            elif s == "201-5.000 Mitarbeiter" and 201 <= emp <= 5000:
                                matches_size = True
                            elif s == "5.001-500.000 Mitarbeiter" and emp > 5000:
                                matches_size = True
                        if not matches_size and emp > 0:
                            continue
                    c["id"] = uuid4()
                    obj = db_svc.save_company(db, c)
                    all_saved.append(db_svc.company_db_to_response(obj))
            except Exception as ex:
                logger.warning(f"Search failed for {ind.value} / {reg.value}: {ex}")
                continue

    return {"success": True, "data": all_saved, "total": len(all_saved)}


@router.post("/find-contacts/{company_id}")
async def find_contacts(
    company_id: UUID,
    db: Session = Depends(get_db),
):
    """Find contacts at a company."""
    api_key = db_svc.get_setting(db, "perplexity_api_key")
    if not api_key:
        raise HTTPException(400, "Perplexity API Key nicht konfiguriert.")

    company = db.get(db_svc.CompanyDB, company_id)
    if not company:
        raise HTTPException(404, "Unternehmen nicht gefunden.")

    contacts = await pplx.find_contacts(
        company.name, company.industry, company.region, company.website, api_key
    )

    saved = []
    for c in contacts:
        if db_svc.lead_exists(db, c["name"], company.name):
            continue
        lead_data = {
            "id": uuid4(),
            "name": c["name"],
            "title": c.get("title", ""),
            "company": company.name,
            "email": c.get("email", ""),
            "email_verified": False,
            "linkedin_url": c.get("linkedin_url", ""),
            "source": c.get("source", "Perplexity Search"),
            "status": "Identified",
        }
        obj = db_svc.save_lead(db, lead_data)
        saved.append(db_svc.lead_db_to_response(obj))

    return {"success": True, "data": saved, "total": len(saved)}


@router.post("/find-contacts-all")
async def find_contacts_all(db: Session = Depends(get_db)):
    """Find contacts for all companies in the DB."""
    api_key = db_svc.get_setting(db, "perplexity_api_key")
    if not api_key:
        raise HTTPException(400, "Perplexity API Key nicht konfiguriert.")

    companies = db_svc.load_companies(db)
    total_new = 0
    for company in companies:
        contacts = await pplx.find_contacts(
            company.name, company.industry, company.region, company.website, api_key
        )
        for c in contacts:
            if db_svc.lead_exists(db, c["name"], company.name):
                continue
            db_svc.save_lead(db, {
                "id": uuid4(),
                "name": c["name"],
                "title": c.get("title", ""),
                "company": company.name,
                "email": c.get("email", ""),
                "linkedin_url": c.get("linkedin_url", ""),
                "source": c.get("source", "Perplexity Search"),
                "status": "Identified",
            })
            total_new += 1

    return {"success": True, "total_new": total_new}


async def _verify_single_lead(lead, api_key: str, db: Session) -> dict:
    """Verify a single lead's email. Returns result dict.
    Used by both single-verify and batch-verify endpoints."""

    lead_id = lead.id

    # Step 1: Perplexity web search for email
    try:
        pplx_result = await pplx.verify_email(
            lead.name, lead.title, lead.company, lead.email, lead.linkedin_url, api_key
        )
    except Exception as ex:
        logger.warning(f"Perplexity verification failed for {lead.name}: {ex}")
        return {"lead_id": str(lead_id), "name": lead.name, "error": str(ex)[:200]}

    # Update email from Perplexity result
    found_email = pplx_result.get("email", lead.email)
    if found_email:
        lead.email = found_email

    pplx_verified = pplx_result.get("verified", False)
    pplx_notes = pplx_result.get("notes", "")

    # Step 2: Technical SMTP/MX verification (best-effort)
    tech_result = {"risk_level": "unknown", "notes": "Keine E-Mail für technische Prüfung"}
    if lead.email and "@" in lead.email:
        try:
            tech_result = await email_verify.verify_email_technical(lead.email)
        except Exception as ex:
            logger.warning(f"Technical email verification failed for {lead.email}: {ex}")
            tech_result = {"risk_level": "unknown", "notes": f"Technische Prüfung fehlgeschlagen: {str(ex)[:100]}"}

    # Combine results
    risk = tech_result.get("risk_level", "unknown")
    smtp_ok = tech_result.get("smtp_exists", None)
    is_catch_all = tech_result.get("is_catch_all", False)

    # Determine final verification status
    # Verified if:
    # - Perplexity found and confirmed an email (pplx_verified=True)
    #   AND risk is low or medium (MX exists, syntax OK, not disposable)
    #   AND SMTP didn't explicitly reject (smtp_ok is not False)
    # OR:
    # - Perplexity confirmed with high confidence even if risk is "unknown"
    #   (because SMTP may be unavailable in cloud)
    is_verified = (
        pplx_verified
        and risk in ("low", "medium")
        and smtp_ok is not False  # Not explicitly rejected by server
    ) or (
        # Fallback: Perplexity high confidence + email has valid syntax + not disposable
        pplx_verified
        and risk == "unknown"
        and lead.email
        and "@" in lead.email
        and not tech_result.get("is_disposable", False)
    )

    # Update lead fields — NEVER change status to 'Contacted' automatically
    lead.email_verified = is_verified
    lead.email_risk_level = risk
    lead.email_smtp_verified = smtp_ok is True
    lead.email_is_catch_all = is_catch_all
    lead.email_mx_host = tech_result.get("mx_host", "")

    # Build comprehensive notes (ensure all parts are strings)
    pplx_notes_str = str(pplx_notes) if not isinstance(pplx_notes, (list, dict)) else str(pplx_notes)[:200]
    notes_parts = [f"Perplexity: {pplx_notes_str}"]
    tech_notes = tech_result.get("notes", "")
    if tech_notes:
        notes_parts.append(f"SMTP: {str(tech_notes)}")
    notes_parts.append(f"Risiko: {risk}")
    if is_catch_all:
        notes_parts.append("Catch-All-Domain")
    lead.verification_notes = " | ".join(str(p) for p in notes_parts)[:500]

    if is_verified and lead.status == "Identified":
        lead.status = "Email Verified"

    db.commit()

    return {
        "lead_id": str(lead_id),
        "name": lead.name,
        "email": lead.email,
        "verified": is_verified,
        "risk_level": risk,
        "smtp_verified": smtp_ok is True,
        "is_catch_all": is_catch_all,
        "notes": lead.verification_notes,
    }


@router.post("/verify-email/{lead_id}")
async def verify_email(
    lead_id: UUID,
    db: Session = Depends(get_db),
):
    """Verify a lead's email address using:
    1. Perplexity web search (find/validate email)
    2. Technical SMTP/MX verification (check deliverability)
    """
    api_key = db_svc.get_setting(db, "perplexity_api_key")
    if not api_key:
        raise HTTPException(400, "Perplexity API Key nicht konfiguriert.")

    lead = db_svc.get_lead(db, lead_id)
    if not lead:
        raise HTTPException(404, "Lead nicht gefunden.")

    result = await _verify_single_lead(lead, api_key, db)

    if "error" in result:
        raise HTTPException(500, f"Verifikation fehlgeschlagen: {result['error']}")

    return {
        "success": True,
        "data": {
            "email": result.get("email", ""),
            "verified": result.get("verified", False),
            "risk_level": result.get("risk_level", "unknown"),
            "smtp_verified": result.get("smtp_verified", False),
            "is_catch_all": result.get("is_catch_all", False),
            "notes": result.get("notes", ""),
        },
    }


@router.post("/verify-all")
async def verify_all_emails(db: Session = Depends(get_db)):
    """Verify emails for all unverified leads — parallel with semaphore.
    Runs up to MAX_CONCURRENT_VERIFY Perplexity calls in parallel.
    Returns progress in real-time-friendly format."""
    api_key = db_svc.get_setting(db, "perplexity_api_key")
    if not api_key:
        raise HTTPException(400, "Perplexity API Key nicht konfiguriert.")

    leads = db_svc.load_leads(db)
    unverified = [l for l in leads if not l.email_verified]

    if not unverified:
        return {"success": True, "verified": 0, "total": 0, "errors": [], "message": "Alle Leads bereits verifiziert."}

    logger.info(f"[VerifyAll] Starting parallel verification for {len(unverified)} leads (concurrency={MAX_CONCURRENT_VERIFY})")

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_VERIFY)
    results = []

    async def verify_with_semaphore(lead):
        async with semaphore:
            try:
                # Each lead gets its own DB session to avoid conflicts
                from ..models.db import SessionLocal
                session = SessionLocal()
                try:
                    # Re-fetch lead in this session
                    fresh_lead = db_svc.get_lead(session, lead.id)
                    if not fresh_lead:
                        return {"lead_id": str(lead.id), "name": lead.name, "error": "Lead not found in session"}
                    result = await _verify_single_lead(fresh_lead, api_key, session)
                    return result
                finally:
                    session.close()
            except Exception as ex:
                logger.warning(f"[VerifyAll] Failed for {lead.name}: {ex}")
                return {"lead_id": str(lead.id), "name": lead.name, "error": str(ex)[:200]}

    # Run all verifications in parallel with semaphore limiting concurrency
    tasks = [verify_with_semaphore(lead) for lead in unverified]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Process results
    verified_count = 0
    errors = []
    for r in results:
        if isinstance(r, Exception):
            errors.append(str(r)[:100])
        elif isinstance(r, dict):
            if r.get("verified"):
                verified_count += 1
            if r.get("error"):
                errors.append(f"{r.get('name', '?')}: {r['error'][:100]}")

    logger.info(f"[VerifyAll] Done: {verified_count}/{len(unverified)} verified, {len(errors)} errors")

    return {
        "success": True,
        "verified": verified_count,
        "total": len(unverified),
        "errors": errors[:10] if errors else [],
    }


@router.post("/verify-email-technical/{lead_id}")
async def verify_email_technical_only(
    lead_id: UUID,
    db: Session = Depends(get_db),
):
    """Run only the technical SMTP/MX verification (skip Perplexity)."""
    lead = db_svc.get_lead(db, lead_id)
    if not lead:
        raise HTTPException(404, "Lead nicht gefunden.")
    if not lead.email or "@" not in lead.email:
        raise HTTPException(400, "Lead hat keine gültige E-Mail-Adresse.")

    try:
        result = await email_verify.verify_email_technical(lead.email)
    except Exception as ex:
        raise HTTPException(500, f"Technische Prüfung fehlgeschlagen: {str(ex)[:200]}")

    # Update lead
    lead.email_risk_level = result.get("risk_level", "unknown")
    lead.email_smtp_verified = result.get("smtp_exists") is True
    lead.email_is_catch_all = result.get("is_catch_all", False)
    lead.email_mx_host = result.get("mx_host", "")

    existing_notes = lead.verification_notes or ""
    tech_note = f"SMTP: {result.get('notes', '')} | Risiko: {result['risk_level']}"
    if existing_notes:
        lead.verification_notes = f"{existing_notes} | {tech_note}"[:500]
    else:
        lead.verification_notes = tech_note[:500]

    # Mark as verified if low risk
    if result["risk_level"] in ("low", "medium") and result.get("smtp_exists") is not False:
        lead.email_verified = True
        if lead.status == "Identified":
            lead.status = "Email Verified"

    db.commit()

    return {"success": True, "data": result}
