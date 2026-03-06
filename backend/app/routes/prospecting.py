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
from ..models.schemas import Industry, Region

logger = logging.getLogger("harpo.prospecting")

router = APIRouter(prefix="/prospecting", tags=["Prospecting"])


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


@router.post("/verify-email/{lead_id}")
async def verify_email(
    lead_id: UUID,
    db: Session = Depends(get_db),
):
    """Verify a lead's email address."""
    api_key = db_svc.get_setting(db, "perplexity_api_key")
    if not api_key:
        raise HTTPException(400, "Perplexity API Key nicht konfiguriert.")

    lead = db_svc.get_lead(db, lead_id)
    if not lead:
        raise HTTPException(404, "Lead nicht gefunden.")

    try:
        result = await pplx.verify_email(
            lead.name, lead.title, lead.company, lead.email, lead.linkedin_url, api_key
        )
    except Exception as ex:
        logger.error(f"Email verification failed for lead {lead_id}: {ex}")
        raise HTTPException(500, f"Verifikation fehlgeschlagen: {str(ex)[:200]}")

    # Update lead — only email fields, NEVER change status automatically
    # Status changes (e.g. to "Contacted") happen ONLY when user explicitly sends an email
    lead.email = result["email"]
    lead.email_verified = result["verified"]
    lead.verification_notes = result.get("notes", "")
    if result["verified"] and lead.status == "Identified":
        lead.status = "Email Verified"
    db.commit()

    return {"success": True, "data": result}


@router.post("/verify-all")
async def verify_all_emails(db: Session = Depends(get_db)):
    """Verify emails for all unverified leads."""
    api_key = db_svc.get_setting(db, "perplexity_api_key")
    if not api_key:
        raise HTTPException(400, "Perplexity API Key nicht konfiguriert.")

    leads = db_svc.load_leads(db)
    unverified = [l for l in leads if not l.email_verified]
    verified_count = 0
    errors = []
    for lead in unverified:
        try:
            result = await pplx.verify_email(
                lead.name, lead.title, lead.company, lead.email, lead.linkedin_url, api_key
            )
            lead.email = result["email"]
            lead.email_verified = result["verified"]
            lead.verification_notes = result.get("notes", "")
            if result["verified"]:
                if lead.status == "Identified":
                    lead.status = "Email Verified"
                verified_count += 1
            db.commit()
        except Exception as ex:
            logger.warning(f"Verify failed for {lead.name}: {ex}")
            errors.append(f"{lead.name}: {str(ex)[:100]}")
            continue

    return {
        "success": True,
        "verified": verified_count,
        "total": len(unverified),
        "errors": errors[:5] if errors else [],
    }

