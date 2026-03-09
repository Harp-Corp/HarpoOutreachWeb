# Data routes – CRUD for companies, leads, social posts, settings, dashboard
from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime
from uuid import UUID, uuid4

logger = logging.getLogger("harpo.data")

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..models.db import get_db
from ..services import database_service as db_svc
from ..services import perplexity_service as pplx
from ..models.schemas import ContentTopic, SocialPlatform

router = APIRouter(prefix="/data", tags=["Data"])

# ─── LinkedIn existing posts context (cached) ─────────────────────
_linkedin_context_cache: str = ""
_linkedin_cache_ts: float = 0.0

async def _get_linkedin_context(api_key: str) -> str:
    """Fetch recent Harpocrates LinkedIn posts via Perplexity.
    Uses Google-indexed LinkedIn post snippets (not direct LinkedIn access).
    Cached for 6 hours to avoid excessive API calls.
    
    NOTE: Perplexity cannot directly access LinkedIn behind the login wall.
    It searches Google-indexed snippets. Results may be incomplete.
    The primary dedup mechanism is the local DB posts (see generate_social_post).
    This function provides supplementary context from actually published posts."""
    import time
    global _linkedin_context_cache, _linkedin_cache_ts

    if _linkedin_context_cache and (time.time() - _linkedin_cache_ts) < 21600:
        return _linkedin_context_cache

    try:
        from ..services.perplexity_service import _call_api, MODEL_FAST
        system = """You are a search assistant. Find REAL, ACTUALLY PUBLISHED LinkedIn posts from a specific company page.
IMPORTANT:
- Search Google for: site:linkedin.com/posts/harpocrates OR "Harpocrates" linkedin post
- Only return posts that appear in ACTUAL search results with real URLs
- Do NOT invent or hallucinate posts. If you can't find any, say "No posts found."
- For each post found, give the first 1-2 sentences and the approximate date.
- Return ONLY verified content from search results."""

        user = """Find the most recent LinkedIn posts from Harpocrates / comply.reg.
Search for: site:linkedin.com/posts/harpocrates
Also search for: "Harpocrates" OR "comply.reg" site:linkedin.com

List each found post as:
- [date] First sentence or hook of the post

Only include posts you can actually verify from search results. If no posts are found, say "No posts found." """

        result = await _call_api(
            system, user, api_key,
            max_tokens=1500,
            model=MODEL_FAST,
            search_recency_filter="month",
            search_context_size="high",
            return_citations=True,
        )
        if isinstance(result, dict):
            raw = result.get("content", "")
            citations = result.get("citations", [])
            # Only trust the result if it has actual LinkedIn citations
            has_linkedin_citations = any("linkedin.com" in c for c in citations)
            if has_linkedin_citations:
                _linkedin_context_cache = raw.strip()
                _linkedin_cache_ts = time.time()
                logger.info(f"LinkedIn context fetched ({len(citations)} citations): {len(_linkedin_context_cache)} chars")
            else:
                logger.info("LinkedIn context: no LinkedIn citations found, discarding (likely hallucinated)")
                _linkedin_context_cache = ""
        else:
            raw = result if isinstance(result, str) else ""
            if "no posts found" in raw.lower() or "nicht gefunden" in raw.lower():
                _linkedin_context_cache = ""
            else:
                # Without citation verification, treat as unreliable
                _linkedin_context_cache = ""
                logger.info("LinkedIn context: no citation data, discarding")
    except Exception as e:
        logger.warning(f"Failed to fetch LinkedIn context: {e}")

    return _linkedin_context_cache


# ─── Companies ────────────────────────────────────────────────────

@router.get("/companies")
async def list_companies(db: Session = Depends(get_db)):
    companies = db_svc.load_companies(db)
    return {"data": [db_svc.company_db_to_response(c) for c in companies]}


@router.post("/companies")
async def create_company(data: dict, db: Session = Depends(get_db)):
    data["id"] = uuid4()
    obj = db_svc.save_company(db, data)
    return {"success": True, "data": db_svc.company_db_to_response(obj)}


@router.delete("/companies/{company_id}")
async def remove_company(company_id: UUID, db: Session = Depends(get_db)):
    db_svc.delete_company(db, company_id)
    return {"success": True}


@router.delete("/companies")
async def remove_all_companies(db: Session = Depends(get_db)):
    """Delete ALL companies from the database."""
    from ..models.db import CompanyDB
    count = db.query(CompanyDB).count()
    db.query(CompanyDB).delete()
    db.commit()
    return {"success": True, "deleted": count}


@router.get("/companies/export")
async def export_companies_csv(db: Session = Depends(get_db)):
    """Export all companies as CSV download."""
    companies = db_svc.load_companies(db)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Branche", "Region", "Land", "Website", "LinkedIn", "Mitarbeiter", "Beschreibung"])
    for c in companies:
        writer.writerow([
            c.name, c.industry, c.region, c.country,
            c.website, c.linkedin_url, c.employee_count, c.description,
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=unternehmen_{datetime.utcnow().strftime('%Y%m%d')}.csv"},
    )


# ─── Leads ────────────────────────────────────────────────────────

@router.get("/leads")
async def list_leads(db: Session = Depends(get_db)):
    leads = db_svc.load_leads(db)
    return {"data": [db_svc.lead_db_to_response(l) for l in leads]}


@router.get("/leads/export")
async def export_leads_csv(db: Session = Depends(get_db)):
    """Export all leads as CSV download."""
    leads = db_svc.load_leads(db)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Titel", "Unternehmen", "E-Mail", "Verifiziert", "LinkedIn", "Status", "Quelle"])
    for l in leads:
        resp = db_svc.lead_db_to_response(l)
        writer.writerow([
            resp.get("name", ""), resp.get("title", ""), resp.get("company", ""),
            resp.get("email", ""), "Ja" if resp.get("email_verified") else "Nein",
            resp.get("linkedin_url", ""), resp.get("status", ""), resp.get("source", ""),
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=kontakte_{datetime.utcnow().strftime('%Y%m%d')}.csv"},
    )


@router.get("/leads/{lead_id}")
async def get_lead(lead_id: UUID, db: Session = Depends(get_db)):
    lead = db_svc.get_lead(db, lead_id)
    if not lead:
        raise HTTPException(404, "Lead nicht gefunden.")
    return {"data": db_svc.lead_db_to_response(lead)}


@router.post("/leads")
async def create_lead(data: dict, db: Session = Depends(get_db)):
    data["id"] = uuid4()
    data["is_manually_created"] = True
    obj = db_svc.save_lead(db, data)
    return {"success": True, "data": db_svc.lead_db_to_response(obj)}


@router.put("/leads/{lead_id}")
async def update_lead(lead_id: UUID, data: dict, db: Session = Depends(get_db)):
    data["id"] = lead_id
    obj = db_svc.save_lead(db, data)
    return {"success": True, "data": db_svc.lead_db_to_response(obj)}


@router.delete("/leads/{lead_id}")
async def remove_lead(lead_id: UUID, db: Session = Depends(get_db)):
    db_svc.delete_lead(db, lead_id)
    return {"success": True}


@router.delete("/leads")
async def remove_all_leads(db: Session = Depends(get_db)):
    """Delete ALL leads from the database."""
    from ..models.db import LeadDB
    count = db.query(LeadDB).count()
    db.query(LeadDB).delete()
    db.commit()
    return {"success": True, "deleted": count}


# ─── Social Posts ─────────────────────────────────────────────────

@router.get("/social-posts")
async def list_social_posts(db: Session = Depends(get_db)):
    posts = db_svc.load_social_posts(db)
    return {"data": [db_svc.social_post_to_response(p) for p in posts]}


@router.post("/social-posts/generate")
async def generate_social_post(
    topic: str,
    platform: str = "LinkedIn",
    industries: str = "",
    db: Session = Depends(get_db),
):
    api_key = db_svc.get_setting(db, "perplexity_api_key")
    if not api_key:
        raise HTTPException(400, "Perplexity API Key fehlt.")

    # Support both predefined enum topics AND free-text custom topics
    topic_value = topic
    topic_prefix = ""
    try:
        ct = ContentTopic(topic)
        topic_value = ct.value
        topic_prefix = ct.prompt_prefix
    except ValueError:
        # Free-text custom topic — use as-is with a generic prompt prefix
        topic_value = topic.strip()
        if not topic_value:
            raise HTTPException(400, "Thema darf nicht leer sein.")
        topic_prefix = f"Write an expert analysis about {topic_value} and its impact on"
        logger.info(f"[GeneratePost] Custom topic: {topic_value}")

    # Always LinkedIn — Twitter/X removed
    sp = SocialPlatform.linkedin

    ind_list = [i.strip() for i in industries.split(",") if i.strip()] if industries else []

    existing_posts = db_svc.load_social_posts(db)
    # Use longer previews (200 chars) and more posts (20) for better dedup
    previews = [p.content[:200] for p in existing_posts[:20]]

    # Fetch LinkedIn context (existing company page posts) for dedup + audience building
    linkedin_context = ""
    try:
        linkedin_context = await _get_linkedin_context(api_key)
    except Exception:
        pass

    # Combine local DB previews with LinkedIn context
    if linkedin_context:
        previews.append(f"--- K\u00dcRZLICH AUF LINKEDIN VER\u00d6FFENTLICHT ---\n{linkedin_context}")

    result = await pplx.generate_social_post(
        topic_value, topic_prefix, sp.value, ind_list, previews, api_key
    )

    # Add timestamp to the post content
    timestamp_str = datetime.utcnow().strftime("%d.%m.%Y %H:%M UTC")
    content_with_ts = result["content"]
    # Insert timestamp before the footer
    if "\U0001f517 www.harpocrates-corp.com" in content_with_ts:
        content_with_ts = content_with_ts.replace(
            "\U0001f517 www.harpocrates-corp.com",
            f"\n\n\U0001f4c5 {timestamp_str}\n\n\U0001f517 www.harpocrates-corp.com",
        )
    else:
        content_with_ts += f"\n\n\U0001f4c5 {timestamp_str}"

    post_data = {
        "id": uuid4(),
        "platform": sp.value,
        "content": content_with_ts,
        "hashtags": result["hashtags"],
        "created_date": datetime.utcnow(),
        "is_published": False,
    }
    obj = db_svc.save_social_post(db, post_data)

    # Auto-run cross-check verification after generation
    try:
        from ..models.db import SocialPostDB
        post_obj = db.query(SocialPostDB).filter(SocialPostDB.id == post_data["id"]).first()
        if post_obj:
            post_obj.verification_status = "checking"
            db.commit()
            verification = await pplx.cross_check_post(content_with_ts, api_key)
            post_obj.verification_status = verification["status"]
            post_obj.verification_score = verification["score"]
            post_obj.verification_json = json.dumps(verification, ensure_ascii=False)
            db.commit()
            db.refresh(post_obj)
            obj = post_obj
            logger.info(f"Auto cross-check: score={verification['score']}, status={verification['status']}")
    except Exception as e:
        logger.warning(f"Auto cross-check failed (non-blocking): {e}")

    return {"success": True, "data": db_svc.social_post_to_response(obj)}


@router.post("/social-posts/{post_id}/verify")
async def verify_social_post(post_id: UUID, db: Session = Depends(get_db)):
    """Run multi-pass cross-check verification on a social post.
    Checks claims against sources, verifies URLs, validates entities."""
    from ..models.db import SocialPostDB
    post = db.query(SocialPostDB).filter(SocialPostDB.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post nicht gefunden.")

    api_key = db_svc.get_setting(db, "perplexity_api_key")
    if not api_key:
        raise HTTPException(400, "Perplexity API Key fehlt.")

    # Mark as checking
    post.verification_status = "checking"
    db.commit()

    try:
        result = await pplx.cross_check_post(post.content, api_key)

        post.verification_status = result["status"]
        post.verification_score = result["score"]
        post.verification_json = json.dumps(result, ensure_ascii=False)
        db.commit()
        db.refresh(post)

        return {
            "success": True,
            "data": db_svc.social_post_to_response(post),
        }
    except Exception as e:
        post.verification_status = "unverified"
        db.commit()
        logger.error(f"Cross-check failed for post {post_id}: {e}")
        raise HTTPException(500, f"Cross-Check fehlgeschlagen: {str(e)}")


@router.delete("/social-posts/{post_id}")
async def remove_social_post(post_id: UUID, db: Session = Depends(get_db)):
    db_svc.delete_social_post(db, post_id)
    return {"success": True}


@router.post("/social-posts/{post_id}/mark-copied")
async def mark_post_copied(post_id: UUID, db: Session = Depends(get_db)):
    """Mark a social post as copied (to prevent duplicate usage)."""
    obj = db_svc.save_social_post(db, {"id": post_id, "is_copied": True})
    return {"success": True, "data": db_svc.social_post_to_response(obj)}


@router.post("/social-posts/{post_id}/publish-linkedin")
async def publish_to_linkedin(post_id: UUID, db: Session = Depends(get_db)):
    """Queue a social post for publishing to LinkedIn as Harpocrates organization.
    Sets publish_pending=True. A background worker (cron) picks it up and posts
    via the Pipedream LinkedIn connector which has w_organization_social scope."""
    from ..models.db import SocialPostDB
    post = db.query(SocialPostDB).filter(SocialPostDB.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post nicht gefunden.")
    if post.is_published:
        raise HTTPException(400, "Post wurde bereits veröffentlicht.")
    if getattr(post, "publish_pending", False):
        raise HTTPException(400, "Post ist bereits in der Warteschlange.")

    post.publish_pending = True
    db.commit()
    db.refresh(post)
    logger.info(f"Post {post_id} queued for LinkedIn publishing")

    return {
        "success": True,
        "queued": True,
        "data": db_svc.social_post_to_response(post),
    }


@router.get("/social-posts/pending")
async def get_pending_posts(db: Session = Depends(get_db)):
    """Returns posts queued for LinkedIn publishing (publish_pending=True, is_published=False).
    Used by the cron worker to pick up posts to publish."""
    from ..models.db import SocialPostDB
    posts = db.query(SocialPostDB).filter(
        SocialPostDB.publish_pending == True,
        SocialPostDB.is_published == False,
    ).order_by(SocialPostDB.created_date.asc()).all()
    return {"data": [db_svc.social_post_to_response(p) for p in posts]}


@router.post("/social-posts/{post_id}/mark-published")
async def mark_post_published(post_id: UUID, db: Session = Depends(get_db)):
    """Mark a post as published after the cron worker successfully posted it via Pipedream."""
    from ..models.db import SocialPostDB
    post = db.query(SocialPostDB).filter(SocialPostDB.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post nicht gefunden.")

    post.is_published = True
    post.publish_pending = False
    post.published_at = datetime.utcnow()
    db.commit()
    db.refresh(post)
    logger.info(f"Post {post_id} marked as published")

    return {"success": True, "data": db_svc.social_post_to_response(post)}


@router.post("/social-posts/{post_id}/cancel-publish")
async def cancel_publish(post_id: UUID, db: Session = Depends(get_db)):
    """Cancel a pending publish request."""
    from ..models.db import SocialPostDB
    post = db.query(SocialPostDB).filter(SocialPostDB.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post nicht gefunden.")
    if post.is_published:
        raise HTTPException(400, "Post wurde bereits veröffentlicht.")

    post.publish_pending = False
    db.commit()
    db.refresh(post)
    return {"success": True, "data": db_svc.social_post_to_response(post)}


# ─── Address Book ─────────────────────────────────────────────────

@router.get("/address-book")
async def list_address_book(db: Session = Depends(get_db)):
    entries = db_svc.load_address_book(db)
    return {"data": [db_svc.address_book_to_response(e) for e in entries]}


@router.post("/address-book")
async def create_address_book_entry(data: dict, db: Session = Depends(get_db)):
    """Manually add a contact to the address book."""
    data["id"] = uuid4()
    data["source"] = "manual"
    data["email_verified"] = False  # manual entries don't need verification
    obj = db_svc.save_address_book_entry(db, data)
    return {"success": True, "data": db_svc.address_book_to_response(obj)}


@router.post("/address-book/from-lead/{lead_id}")
async def add_lead_to_address_book(lead_id: UUID, db: Session = Depends(get_db)):
    """Copy a verified lead into the address book."""
    lead = db_svc.get_lead(db, lead_id)
    if not lead:
        raise HTTPException(404, "Lead nicht gefunden.")
    if not lead.email_verified:
        raise HTTPException(400, "Nur verifizierte Kontakte können ins Adressbuch übernommen werden.")
    if db_svc.address_book_exists(db, lead.email):
        raise HTTPException(400, f"{lead.email} ist bereits im Adressbuch.")
    entry = db_svc.save_address_book_entry(db, {
        "id": uuid4(),
        "name": lead.name,
        "title": lead.title,
        "company": lead.company,
        "email": lead.email,
        "email_verified": True,
        "linkedin_url": lead.linkedin_url,
        "phone": lead.phone or "",
        "notes": lead.verification_notes or "",
        "source": "verified",
    })
    return {"success": True, "data": db_svc.address_book_to_response(entry)}


@router.post("/address-book/from-leads-batch")
async def add_leads_to_address_book_batch(data: dict, db: Session = Depends(get_db)):
    """Batch-add multiple verified leads to the address book in one request."""
    lead_ids = data.get("lead_ids", [])
    if not lead_ids:
        raise HTTPException(400, "Keine Lead-IDs angegeben.")
    added = 0
    skipped = 0
    for lid in lead_ids:
        try:
            lead = db_svc.get_lead(db, UUID(str(lid)))
            if not lead or not lead.email_verified:
                skipped += 1
                continue
            if db_svc.address_book_exists(db, lead.email):
                skipped += 1
                continue
            db_svc.save_address_book_entry(db, {
                "id": uuid4(),
                "name": lead.name,
                "title": lead.title,
                "company": lead.company,
                "email": lead.email,
                "email_verified": True,
                "linkedin_url": lead.linkedin_url,
                "phone": lead.phone or "",
                "notes": lead.verification_notes or "",
                "source": "verified",
            })
            added += 1
        except Exception:
            skipped += 1
    return {"success": True, "added": added, "skipped": skipped}


@router.put("/address-book/{entry_id}")
async def update_address_book_entry(entry_id: UUID, data: dict, db: Session = Depends(get_db)):
    data["id"] = entry_id
    obj = db_svc.save_address_book_entry(db, data)
    return {"success": True, "data": db_svc.address_book_to_response(obj)}


@router.delete("/address-book/{entry_id}")
async def remove_address_book_entry(entry_id: UUID, db: Session = Depends(get_db)):
    db_svc.delete_address_book_entry(db, entry_id)
    return {"success": True}


@router.put("/address-book/{entry_id}/status")
async def update_address_book_status(entry_id: UUID, data: dict, db: Session = Depends(get_db)):
    """Change a contact's status: 'active' (nutzbar) or 'blocked' (gesperrt)."""
    entry = db_svc.get_address_book_entry(db, entry_id)
    if not entry:
        raise HTTPException(404, "Kontakt nicht gefunden.")
    new_status = data.get("contact_status", "active")
    if new_status not in ("active", "blocked"):
        raise HTTPException(400, "Ungültiger Status. Erlaubt: 'active', 'blocked'.")

    entry.contact_status = new_status
    entry.updated_at = datetime.utcnow()

    # Sync with blocklist
    if new_status == "blocked":
        db_svc.add_to_blocklist(db, entry.email, reason="Opt-out via Adressbuch")
    elif new_status == "active":
        db_svc.remove_from_blocklist(db, entry.email)

    db.commit()
    db.refresh(entry)
    return {"success": True, "data": db_svc.address_book_to_response(entry)}


@router.delete("/address-book/{entry_id}/permanent")
async def permanently_delete_address_book_entry(entry_id: UUID, db: Session = Depends(get_db)):
    """Permanently delete a contact from the address book."""
    entry = db_svc.get_address_book_entry(db, entry_id)
    if not entry:
        raise HTTPException(404, "Kontakt nicht gefunden.")
    db_svc.delete_address_book_entry(db, entry_id)
    return {"success": True}


@router.get("/address-book/export")
async def export_address_book_csv(db: Session = Depends(get_db)):
    """Export address book as CSV."""
    entries = db_svc.load_address_book(db)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Titel", "Unternehmen", "E-Mail", "Verifiziert", "LinkedIn", "Telefon", "Quelle", "Status", "Notizen"])
    for e in entries:
        status_label = "Nutzbar" if (getattr(e, 'contact_status', 'active') or 'active') == 'active' else "Gesperrt"
        writer.writerow([
            e.name, e.title, e.company, e.email,
            "Ja" if e.email_verified else "Nein",
            e.linkedin_url, e.phone, e.source, status_label, e.notes,
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=adressbuch_{datetime.utcnow().strftime('%Y%m%d')}.csv"},
    )


# ─── Blocklist ────────────────────────────────────────────────────

@router.get("/blocklist")
async def list_blocklist(db: Session = Depends(get_db)):
    entries = db_svc.load_blocklist(db)
    return {
        "data": [
            {"email": e.email, "reason": e.reason, "opted_out_at": e.opted_out_at.isoformat()}
            for e in entries
        ]
    }


@router.post("/blocklist")
async def add_to_blocklist(email: str, reason: str = "", db: Session = Depends(get_db)):
    db_svc.add_to_blocklist(db, email, reason)
    return {"success": True}


@router.delete("/blocklist/all")
async def clear_blocklist(db: Session = Depends(get_db)):
    """Remove ALL entries from the blocklist (admin reset)."""
    from ..models.db import BlocklistDB
    count = db.query(BlocklistDB).count()
    db.query(BlocklistDB).delete()
    # Also reset opted_out on all leads that were blocked
    from ..models.db import LeadDB
    db.query(LeadDB).filter(LeadDB.opted_out == True).update({
        LeadDB.opted_out: False,
        LeadDB.opt_out_date: None,
    })
    db.commit()
    return {"success": True, "removed": count}


@router.delete("/blocklist/{email}")
async def remove_from_blocklist(email: str, db: Session = Depends(get_db)):
    db_svc.remove_from_blocklist(db, email)
    return {"success": True}


# ─── Settings ─────────────────────────────────────────────────────

@router.get("/settings")
async def get_settings(db: Session = Depends(get_db)):
    all_settings = db_svc.get_all_settings(db)
    # Mask sensitive keys
    safe = {}
    for k, v in all_settings.items():
        if k in ("perplexity_api_key", "google_client_secret", "google_access_token", "google_refresh_token", "linkedin_access_token"):
            safe[k] = "***" if v else ""
        else:
            safe[k] = v
    return {"data": safe}


@router.put("/settings")
async def update_settings(data: dict, db: Session = Depends(get_db)):
    for k, v in data.items():
        if v is not None:
            db_svc.set_setting(db, k, v)
    return {"success": True}


# ─── CSV Import ────────────────────────────────────────────────────────

from fastapi import File, UploadFile

@router.post("/address-book/import-csv")
async def import_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Import contacts from CSV file into the address book.
    Expected columns (flexible matching): name, email, company, title, linkedin_url, phone
    """
    content = await file.read()
    text = content.decode("utf-8-sig")  # handle BOM

    # Detect delimiter
    first_line = text.split("\n")[0] if text else ""
    delimiter = ";" if ";" in first_line else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)

    # Normalize header names
    def find_col(row, candidates):
        for c in candidates:
            for k in row:
                if k and k.strip().lower().replace("-", "_").replace(" ", "_") == c:
                    return row[k]
        return ""

    imported = 0
    skipped = 0
    from ..models.db import AddressBookDB as ABImport
    existing_emails = {a.email.lower() for a in db.query(ABImport).all() if a.email}

    for row in reader:
        email = find_col(row, ["email", "e_mail", "mail"]).strip()
        if not email or email.lower() in existing_emails:
            skipped += 1
            continue
        name = find_col(row, ["name", "full_name", "fullname", "kontakt"]).strip()
        company = find_col(row, ["company", "firma", "unternehmen", "organisation"]).strip()
        title = find_col(row, ["title", "titel", "position", "role", "rolle"]).strip()
        linkedin = find_col(row, ["linkedin_url", "linkedin", "li_url"]).strip()
        phone = find_col(row, ["phone", "telefon", "tel"]).strip()

        if not name:
            name = email.split("@")[0].replace(".", " ").title()

        entry = ABImport(
            id=uuid4(),
            name=name,
            email=email,
            company=company or "",
            title=title or "",
            linkedin_url=linkedin or None,
            phone=phone or None,
            source="csv_import",
            email_verified=False,
            contact_status="active",
        )
        db.add(entry)
        existing_emails.add(email.lower())
        imported += 1

    db.commit()
    return {"success": True, "imported": imported, "skipped": skipped}


# ─── Dashboard ────────────────────────────────────────────────────

@router.get("/dashboard")
async def dashboard(db: Session = Depends(get_db)):
    stats = db_svc.get_dashboard_stats(db)
    return {"data": stats}
