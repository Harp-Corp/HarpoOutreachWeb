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
from ..services import brave_fallback as brave
from ..services import multi_verify_service as multi_verify
from ..models.schemas import Industry, Region
from ..config import settings

logger = logging.getLogger("harpo.prospecting")

router = APIRouter(prefix="/prospecting", tags=["Prospecting"])

# Max concurrent Perplexity API calls for verify-all
MAX_CONCURRENT_VERIFY = 3



from pydantic import BaseModel as PydanticBaseModel

class SearchCompanyRequest(PydanticBaseModel):
    company_name: str


@router.post("/search-company")
async def search_company(
    req: SearchCompanyRequest,
    db: Session = Depends(get_db),
):
    """Targeted company search: find a single company by name, get its contacts,
    and verify them. Used by the address book page for quick lookups.
    Returns company info + verified contacts ready for the address book."""
    api_key = db_svc.get_setting(db, "perplexity_api_key")
    if not api_key:
        raise HTTPException(400, "Perplexity API Key nicht konfiguriert.")

    company_name = req.company_name.strip()
    if not company_name:
        raise HTTPException(400, "Unternehmensname darf nicht leer sein.")

    brave_api_key = settings.brave_api_key    # Fallback search key (may be empty)
    tavily_api_key = settings.tavily_api_key  # Second fallback (may be empty)

    # Step 1: Check if company already exists in DB (fuzzy match)
    existing = db_svc.get_company_by_name(db, company_name)
    if existing:
        company = existing
        logger.info(f"[SearchCompany] Found existing company: {company.name}")
    else:
        # Search via Perplexity (with Brave fallback)
        logger.info(f"[SearchCompany] Searching for: {company_name}")
        company_data = None
        used_fallback = False

        try:
            company_data = await pplx.search_single_company(company_name, api_key)
        except Exception as ex:
            err_str = str(ex)
            is_quota_error = "quota" in err_str.lower() or "401" in err_str or "insufficient" in err_str.lower()
            if is_quota_error and (brave_api_key or tavily_api_key):
                logger.info(f"[SearchCompany] Perplexity quota exhausted, falling back to Brave Search")
                try:
                    company_data = await brave.search_single_company_brave(company_name, brave_api_key, tavily_api_key)
                    used_fallback = True
                except Exception as bex:
                    logger.warning(f"[SearchCompany] Brave fallback also failed: {bex}")
            elif is_quota_error:
                return {"success": False, "error": "api_quota", "message": "Perplexity API Quota erschöpft und kein Fallback konfiguriert. Brave oder Tavily API Key in den Einstellungen hinterlegen."}
            else:
                return {"success": False, "error": "api_error", "message": f"API-Fehler: {err_str[:200]}"}
        
        if not company_data:
            return {"success": False, "error": "not_found", "message": f"Unternehmen '{company_name}' nicht gefunden. Tipp: Offiziellen Firmennamen verwenden (z.B. 'Deutsche Bank AG' statt 'Deutsche Bank')."}
        
        if used_fallback:
            logger.info(f"[SearchCompany] Using Brave fallback data for {company_name}")
        
        # Map Perplexity response keys to DB column names
        mapped = {
            "id": uuid4(),
            "name": company_data.get("name", company_name),
            "industry": company_data.get("industry", ""),
            "region": company_data.get("region", ""),
            "website": company_data.get("website", ""),
            "linkedin_url": company_data.get("linkedInURL", company_data.get("linkedin_url", "")),
            "description": company_data.get("description", ""),
            "size": company_data.get("size", ""),
            "country": company_data.get("country", ""),
            "nace_code": company_data.get("nace_code", ""),
            "employee_count": company_data.get("employee_count", company_data.get("employees", 0)),
        }
        company = db_svc.save_company(db, mapped)
        logger.info(f"[SearchCompany] Saved new company: {company.name}")

    company_resp = db_svc.company_db_to_response(company)

    # Step 2: Check if contacts already exist for this company
    existing_company_leads = [l for l in db_svc.load_leads(db) if l.company == company.name]
    
    if existing_company_leads:
        # Company already has contacts — return them directly without re-searching
        logger.info(f"[SearchCompany] Returning {len(existing_company_leads)} existing contacts for {company.name}")
        company_leads = [_slim_lead_response(db_svc.lead_db_to_response(l)) for l in existing_company_leads]
        return {
            "success": True,
            "company": company_resp,
            "contacts": company_leads,
            "total_contacts": len(company_leads),
            "verified_contacts": sum(1 for l in company_leads if l.get("email_verified")),
        }

    # Step 3: Find new contacts at this company
    logger.info(f"[SearchCompany] Finding contacts at {company.name}...")
    contacts = []
    contact_warning = None
    try:
        contacts = await pplx.find_contacts(
            company.name, company.industry or "", company.region or "", company.website or "", api_key
        )
    except Exception as ex:
        err_str = str(ex)
        is_quota = "quota" in err_str.lower() or "401" in err_str or "insufficient" in err_str.lower()
        logger.warning(f"[SearchCompany] Contact search failed (quota={is_quota}): {ex}")
        if is_quota and (brave_api_key or tavily_api_key):
            # Fallback to Brave for contacts
            logger.info(f"[SearchCompany] Falling back to Brave for contacts at {company.name}")
            try:
                contacts = await brave.find_contacts_brave(
                    company.name, company.industry or "", company.website or "",
                    brave_api_key, tavily_api_key
                )
                contact_warning = "Kontakte via Fallback-Suche gefunden (eingeschr\u00e4nkte Datenqualit\u00e4t). Verifizierung empfohlen."
            except Exception as bex:
                logger.warning(f"[SearchCompany] Brave contact fallback failed: {bex}")
                contact_warning = "Kontaktsuche eingeschr\u00e4nkt \u2014 Perplexity Quota ersch\u00f6pft, Fallback fehlgeschlagen."
        elif is_quota:
            contact_warning = "Perplexity API Quota ersch\u00f6pft \u2014 Kontaktsuche nicht m\u00f6glich. Bitte API-Guthaben pr\u00fcfen."
        else:
            logger.warning(f"[SearchCompany] Non-quota error in contact search: {ex}")

    saved_leads = []
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
        saved_leads.append(obj)

    # Step 4: Verify emails for new contacts (parallel)
    unverified = [l for l in saved_leads if not l.email_verified]
    if unverified:
        logger.info(f"[SearchCompany] Verifying {len(unverified)} contacts...")
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_VERIFY)
        
        async def verify_one(lead):
            async with semaphore:
                try:
                    from ..models.db import SessionLocal
                    session = SessionLocal()
                    try:
                        fresh_lead = db_svc.get_lead(session, lead.id)
                        if not fresh_lead:
                            return None
                        result = await _verify_single_lead(fresh_lead, api_key, session)
                        return result
                    finally:
                        session.close()
                except Exception as ex:
                    logger.warning(f"[SearchCompany] Verify failed for {lead.name}: {ex}")
                    return None
        
        verify_results = await asyncio.gather(*[verify_one(l) for l in unverified], return_exceptions=True)
        verified_count = sum(1 for r in verify_results if isinstance(r, dict) and r.get("verified"))
        logger.info(f"[SearchCompany] Verified {verified_count}/{len(unverified)} contacts")
    
    # Step 5: Cross-verification via independent sources (if fallback APIs available)
    has_cross_verify = brave_api_key or tavily_api_key or settings.hunter_api_key
    cross_verify_count = 0
    if has_cross_verify and saved_leads:
        logger.info(f"[SearchCompany] Cross-verifying {len(saved_leads)} contacts via independent sources...")
        try:
            cross_contacts = [
                {
                    "name": l.name,
                    "title": l.title or "",
                    "email": l.email or "",
                    "linkedin_url": l.linkedin_url or "",
                }
                for l in saved_leads
            ]
            cross_results = await multi_verify.cross_verify_contacts(
                contacts=cross_contacts,
                company=company.name,
                company_website=company.website or "",
                brave_api_key=brave_api_key,
                tavily_api_key=tavily_api_key,
                hunter_api_key=settings.hunter_api_key,
                max_concurrent=2,
            )
            # Update leads in DB with cross-verification results
            for lead, cv_result in zip(saved_leads, cross_results):
                update_data = {}
                if cv_result.get("confidence_score", 0) > 0:
                    notes = cv_result.get("verification_summary", "")
                    update_data["verification_notes"] = notes
                if cv_result.get("email_corrected"):
                    update_data["email"] = cv_result["email_corrected"]
                if cv_result.get("linkedin_url") and not lead.linkedin_url:
                    update_data["linkedin_url"] = cv_result["linkedin_url"]
                if update_data:
                    db_svc.update_lead(db, lead.id, update_data)
                if cv_result.get("cross_verified"):
                    cross_verify_count += 1
            logger.info(f"[SearchCompany] Cross-verified {cross_verify_count}/{len(saved_leads)} contacts")
        except Exception as ex:
            logger.warning(f"[SearchCompany] Cross-verification failed: {ex}")

    # Reload leads to get updated verification status — slim response
    all_leads = db_svc.load_leads(db)
    company_leads = [_slim_lead_response(db_svc.lead_db_to_response(l)) for l in all_leads if l.company == company.name]

    result = {
        "success": True,
        "company": company_resp,
        "contacts": company_leads,
        "total_contacts": len(company_leads),
        "verified_contacts": sum(1 for l in company_leads if l.get("email_verified")),
    }
    if cross_verify_count > 0:
        result["cross_verified_contacts"] = cross_verify_count
    if contact_warning:
        result["warning"] = contact_warning
    return result


def _slim_lead_response(lead: dict) -> dict:
    """Return only the fields needed for the address book search results.
    Avoids sending huge verification_notes in the response."""
    return {
        "id": lead.get("id"),
        "name": lead.get("name"),
        "title": lead.get("title"),
        "company": lead.get("company"),
        "email": lead.get("email"),
        "email_verified": lead.get("email_verified"),
        "status": lead.get("status"),
        "source": lead.get("source"),
        "linkedin_url": lead.get("linkedin_url"),
        "email_risk_level": lead.get("email_risk_level"),
        "email_smtp_verified": lead.get("email_smtp_verified"),
    }


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

