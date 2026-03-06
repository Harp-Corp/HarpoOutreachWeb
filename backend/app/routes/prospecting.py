# Prospecting routes – find companies, contacts, verify emails
from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..models.db import get_db
from ..services import database_service as db_svc
from ..services import perplexity_service as pplx
from ..models.schemas import Industry, Region

router = APIRouter(prefix="/prospecting", tags=["Prospecting"])


@router.post("/find-companies")
async def find_companies(
    industry: str,
    region: str,
    db: Session = Depends(get_db),
):
    """Find companies by industry and region via Perplexity API."""
    api_key = db_svc.get_setting(db, "perplexity_api_key")
    if not api_key:
        raise HTTPException(400, "Perplexity API Key nicht konfiguriert.")

    # Resolve industry & region
    try:
        ind = Industry(industry)
    except ValueError:
        raise HTTPException(400, f"Unbekannte Branche: {industry}")
    try:
        reg = Region(region)
    except ValueError:
        raise HTTPException(400, f"Unbekannte Region: {region}")

    companies_raw = await pplx.find_companies(ind.value, reg.countries, api_key)

    # Deduplicate against existing DB
    saved = []
    for c in companies_raw:
        if db_svc.company_exists(db, c["name"]):
            continue
        c["id"] = uuid4()
        obj = db_svc.save_company(db, c)
        saved.append(db_svc.company_db_to_response(obj))

    return {"success": True, "data": saved, "total": len(saved)}


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

    result = await pplx.verify_email(
        lead.name, lead.title, lead.company, lead.email, lead.linkedin_url, api_key
    )
    # Update lead
    lead.email = result["email"]
    lead.email_verified = result["verified"]
    lead.verification_notes = result["notes"]
    if result["verified"]:
        lead.status = "Contacted"
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
    for lead in unverified:
        try:
            result = await pplx.verify_email(
                lead.name, lead.title, lead.company, lead.email, lead.linkedin_url, api_key
            )
            lead.email = result["email"]
            lead.email_verified = result["verified"]
            lead.verification_notes = result["notes"]
            if result["verified"]:
                lead.status = "Contacted"
                verified_count += 1
            db.commit()
        except Exception:
            continue

    return {"success": True, "verified": verified_count, "total": len(unverified)}
