# MultiVerifyService – Cross-source verification for contacts
# Verifies contact data found by one source against independent sources.
#
# Verification stages:
#   Stage 1: MX + SMTP check (free, no API key needed)
#   Stage 2: Brave/Tavily web search for name+company confirmation
#   Stage 3: Hunter.io email finder + verifier (50 free credits/month)
#   Stage 4: LinkedIn profile search via Brave/Tavily (site:linkedin.com)
#
# Confidence scoring:
#   - Each stage that confirms adds to the confidence score
#   - Minimum 2 independent confirmations for "verified" status
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("harpo.multi_verify")

HUNTER_API_URL = "https://api.hunter.io/v2"


# ─── Stage 1: MX + DNS check (always available, no API key) ─────

async def _check_email_mx(email: str) -> dict:
    """Check if the email domain has valid MX records via DNS."""
    if not email or "@" not in email:
        return {"stage": "mx_check", "confirmed": False, "detail": "Keine gültige E-Mail"}

    domain = email.split("@")[1]
    try:
        import dns.resolver
        mx_records = dns.resolver.resolve(domain, "MX")
        mx_hosts = [str(r.exchange).rstrip(".") for r in mx_records]
        return {
            "stage": "mx_check",
            "confirmed": True,
            "detail": f"MX Records: {', '.join(mx_hosts[:3])}",
            "mx_hosts": mx_hosts,
        }
    except ImportError:
        # dns.resolver not available — use a simple socket check
        import socket
        try:
            socket.getaddrinfo(domain, 25)
            return {"stage": "mx_check", "confirmed": True, "detail": f"Domain {domain} erreichbar"}
        except socket.gaierror:
            return {"stage": "mx_check", "confirmed": False, "detail": f"Domain {domain} nicht erreichbar"}
    except Exception as ex:
        return {"stage": "mx_check", "confirmed": False, "detail": str(ex)[:100]}


# ─── Stage 2: Web search confirmation (Brave/Tavily) ────────────

async def _web_search_confirm(
    name: str, company: str, title: str,
    brave_api_key: str = "", tavily_api_key: str = "",
) -> dict:
    """Search the web to confirm a person works at the stated company with the stated role."""
    from . import brave_fallback as fallback

    query = f'"{name}" "{company}" {title}'
    results = await fallback._fallback_search(query, brave_api_key, tavily_api_key, count=5)

    if not results:
        return {"stage": "web_confirm", "confirmed": False, "detail": "Keine Webresultate"}

    # Check if name AND company appear together in results
    name_lower = name.lower()
    company_lower = company.lower().split()[0]  # First word of company name
    matches = 0
    sources = []

    for r in results:
        text = f"{r['title']} {r['description']}".lower()
        name_parts = name_lower.split()
        # At least last name + company must appear
        if len(name_parts) >= 2 and name_parts[-1] in text and company_lower in text:
            matches += 1
            sources.append(r.get("url", "")[:80])

    confirmed = matches >= 1
    return {
        "stage": "web_confirm",
        "confirmed": confirmed,
        "detail": f"{matches} Webquellen bestätigen" if confirmed else "Person nicht in Websuche gefunden",
        "match_count": matches,
        "sources": sources[:3],
    }


# ─── Stage 3: Hunter.io email finder + verifier ─────────────────

async def _hunter_verify(
    email: str, company_domain: str, name: str, hunter_api_key: str
) -> dict:
    """Use Hunter.io to verify an email and/or find the correct email."""
    if not hunter_api_key:
        return {"stage": "hunter", "confirmed": False, "detail": "Kein Hunter.io API Key", "skipped": True}

    result = {"stage": "hunter", "confirmed": False, "detail": "", "found_email": ""}

    async with httpx.AsyncClient(timeout=15) as client:
        # If we have an email, verify it
        if email:
            try:
                resp = await client.get(
                    f"{HUNTER_API_URL}/email-verifier",
                    params={"email": email, "api_key": hunter_api_key}
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    status = data.get("status", "unknown")
                    score = data.get("score", 0)
                    result["hunter_status"] = status
                    result["hunter_score"] = score
                    result["smtp_check"] = data.get("smtp_check", False)

                    if status == "valid" and score >= 80:
                        result["confirmed"] = True
                        result["detail"] = f"Hunter.io: valid (Score {score})"
                        result["found_email"] = email
                        return result
                    elif status == "accept_all":
                        result["detail"] = f"Hunter.io: accept_all (Score {score}) — Domain akzeptiert alles"
                    else:
                        result["detail"] = f"Hunter.io: {status} (Score {score})"
                elif resp.status_code == 429:
                    result["detail"] = "Hunter.io Rate Limit"
                    result["skipped"] = True
                    return result
            except Exception as ex:
                logger.warning(f"[Hunter] Verify failed for {email}: {ex}")

        # If email not verified or no email, try email finder
        if company_domain and name:
            try:
                name_parts = name.split()
                if len(name_parts) >= 2:
                    resp = await client.get(
                        f"{HUNTER_API_URL}/email-finder",
                        params={
                            "domain": company_domain,
                            "first_name": name_parts[0],
                            "last_name": name_parts[-1],
                            "api_key": hunter_api_key,
                        }
                    )
                    if resp.status_code == 200:
                        data = resp.json().get("data", {})
                        found_email = data.get("email", "")
                        confidence = data.get("confidence", 0)
                        if found_email and confidence >= 70:
                            result["confirmed"] = True
                            result["found_email"] = found_email
                            result["detail"] = f"Hunter.io Finder: {found_email} (Confidence {confidence})"
                        elif found_email:
                            result["found_email"] = found_email
                            result["detail"] = f"Hunter.io Finder: {found_email} (low confidence {confidence})"
            except Exception as ex:
                logger.warning(f"[Hunter] Finder failed for {name} @ {company_domain}: {ex}")

    if not result["detail"]:
        result["detail"] = "Hunter.io: keine Ergebnisse"
    return result


# ─── Stage 4: LinkedIn profile search ───────────────────────────

async def _linkedin_search(
    name: str, company: str,
    brave_api_key: str = "", tavily_api_key: str = "",
) -> dict:
    """Search for a person's LinkedIn profile to confirm their role."""
    from . import brave_fallback as fallback

    query = f'site:linkedin.com/in "{name}" "{company}"'
    results = await fallback._fallback_search(query, brave_api_key, tavily_api_key, count=3)

    if not results:
        # Try without site: restriction
        query = f'linkedin.com "{name}" "{company}"'
        results = await fallback._fallback_search(query, brave_api_key, tavily_api_key, count=3)

    linkedin_url = ""
    confirmed = False
    detail = "Kein LinkedIn-Profil gefunden"

    name_lower = name.lower()
    name_parts = name_lower.split()

    for r in results:
        url = r.get("url", "")
        text = f"{r['title']} {r['description']}".lower()

        # Check if this is actually a LinkedIn profile
        if "linkedin.com/in/" in url:
            # Check if name matches (at least last name)
            if len(name_parts) >= 2 and name_parts[-1] in text:
                linkedin_url = url
                confirmed = True
                detail = f"LinkedIn-Profil bestätigt: {url[:80]}"
                break

    return {
        "stage": "linkedin_search",
        "confirmed": confirmed,
        "detail": detail,
        "linkedin_url": linkedin_url,
    }


# ─── Main verification pipeline ─────────────────────────────────

async def cross_verify_contact(
    name: str,
    title: str,
    company: str,
    email: str,
    company_website: str = "",
    brave_api_key: str = "",
    tavily_api_key: str = "",
    hunter_api_key: str = "",
) -> dict:
    """Run multi-stage cross-verification for a single contact.

    Returns:
        {
            "confidence_score": int (0-100),
            "verified": bool,
            "stages": [...],
            "best_email": str,
            "linkedin_url": str,
            "summary": str,
        }
    """
    # Determine company domain for Hunter
    company_domain = ""
    if company_website:
        try:
            parsed = urlparse(company_website if "://" in company_website else f"https://{company_website}")
            company_domain = parsed.netloc.replace("www.", "")
        except Exception:
            pass
    elif email and "@" in email:
        company_domain = email.split("@")[1]

    # Run all stages in parallel
    tasks = [
        _check_email_mx(email),
        _web_search_confirm(name, company, title, brave_api_key, tavily_api_key),
        _hunter_verify(email, company_domain, name, hunter_api_key),
        _linkedin_search(name, company, brave_api_key, tavily_api_key),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    stages = []
    for r in results:
        if isinstance(r, Exception):
            stages.append({"stage": "error", "confirmed": False, "detail": str(r)[:100]})
        else:
            stages.append(r)

    # Calculate confidence score
    score = 0
    confirmations = 0
    best_email = email
    linkedin_url = ""

    for s in stages:
        if s.get("skipped"):
            continue
        if s.get("confirmed"):
            confirmations += 1
            if s["stage"] == "mx_check":
                score += 15  # Basic check
            elif s["stage"] == "web_confirm":
                score += 30  # Independent web confirmation
                match_count = s.get("match_count", 0)
                if match_count >= 3:
                    score += 10  # Bonus for multiple sources
            elif s["stage"] == "hunter":
                score += 30  # Professional email verification
                if s.get("found_email"):
                    best_email = s["found_email"]
            elif s["stage"] == "linkedin_search":
                score += 25  # LinkedIn profile confirmation
                if s.get("linkedin_url"):
                    linkedin_url = s["linkedin_url"]

    # Cap at 100
    score = min(score, 100)

    # Determine verification status
    verified = confirmations >= 2 and score >= 40

    # Build summary
    confirmed_stages = [s["stage"] for s in stages if s.get("confirmed")]
    if verified:
        summary = f"Bestätigt durch {confirmations} Quellen: {', '.join(confirmed_stages)}"
    elif confirmations == 1:
        summary = f"Teilweise bestätigt ({confirmed_stages[0]}), weitere Prüfung empfohlen"
    else:
        summary = "Nicht verifiziert — keine unabhängige Bestätigung gefunden"

    return {
        "confidence_score": score,
        "verified": verified,
        "confirmations": confirmations,
        "stages": stages,
        "best_email": best_email,
        "linkedin_url": linkedin_url,
        "summary": summary,
    }


async def cross_verify_contacts(
    contacts: list[dict],
    company: str,
    company_website: str = "",
    brave_api_key: str = "",
    tavily_api_key: str = "",
    hunter_api_key: str = "",
    max_concurrent: int = 3,
) -> list[dict]:
    """Verify a batch of contacts with concurrency limit.
    Returns contacts enriched with verification data."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def verify_one(contact: dict) -> dict:
        async with semaphore:
            try:
                result = await cross_verify_contact(
                    name=contact.get("name", ""),
                    title=contact.get("title", ""),
                    company=company,
                    email=contact.get("email", ""),
                    company_website=company_website,
                    brave_api_key=brave_api_key,
                    tavily_api_key=tavily_api_key,
                    hunter_api_key=hunter_api_key,
                )
                contact["cross_verified"] = result["verified"]
                contact["confidence_score"] = result["confidence_score"]
                contact["verification_summary"] = result["summary"]
                if result["best_email"] and result["best_email"] != contact.get("email"):
                    contact["email_corrected"] = result["best_email"]
                if result["linkedin_url"] and not contact.get("linkedin_url"):
                    contact["linkedin_url"] = result["linkedin_url"]
                return contact
            except Exception as ex:
                logger.warning(f"[CrossVerify] Failed for {contact.get('name')}: {ex}")
                contact["cross_verified"] = False
                contact["confidence_score"] = 0
                contact["verification_summary"] = f"Fehler: {str(ex)[:100]}"
                return contact

    return await asyncio.gather(*[verify_one(c) for c in contacts])
