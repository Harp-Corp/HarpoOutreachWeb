# PerplexityService – MAXIMIZED Perplexity API usage
# All Perplexity API interactions: company search, contact search, email verify,
# challenge research, email drafting, social post generation.
# Uses sonar-pro, sonar-reasoning-pro, sonar-deep-research with full filter stack.
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import httpx

logger = logging.getLogger("harpo.perplexity")

API_URL = "https://api.perplexity.ai/chat/completions"

# Model selection per task type
MODEL_FAST = "sonar-pro"                # Standard search + structured output
MODEL_REASONING = "sonar-reasoning-pro"  # Complex analysis, email personalization
MODEL_DEEP = "sonar-deep-research"       # Exhaustive multi-source research

COMPANY_FOOTER = "\n\n🔗 www.harpocrates-corp.com | 📧 info@harpocrates-corp.com"

# Domain pools for targeted searches
DOMAINS_COMPANY = [
    "linkedin.com", "crunchbase.com", "bloomberg.com",
    "reuters.com", "handelsblatt.com", "dnb.com",
    "northdata.com", "firmenwissen.de", "bundesanzeiger.de",
    "companyhouse.gov.uk",
]
DOMAINS_PEOPLE = [
    "linkedin.com", "xing.com", "theorg.com",
    "zoominfo.com", "apollo.io", "rocketreach.co",
    "lusha.com",
]
DOMAINS_EMAIL = [
    "linkedin.com", "xing.com", "zoominfo.com",
    "apollo.io", "rocketreach.co", "lusha.com",
    "hunter.io", "signalhire.com",
]
DOMAINS_REGULATORY = [
    "bafin.de", "eba.europa.eu", "esma.europa.eu",
    "ecb.europa.eu", "eur-lex.europa.eu", "sec.gov",
    "fca.org.uk",
]


def ensure_footer(content: str) -> str:
    clean = content.strip()
    if "🔗 www.harpocrates-corp.com" in clean:
        clean = clean[: clean.index("🔗 www.harpocrates-corp.com")].strip()
    if " www.harpocrates-corp.com" in clean:
        clean = clean[: clean.index(" www.harpocrates-corp.com")].strip()
    return clean + COMPANY_FOOTER


def strip_trailing_hashtags(content: str) -> str:
    lines = content.split("\n")
    result: list[str] = []
    found_non_hashtag = False
    for line in reversed(lines):
        trimmed = line.strip()
        if not trimmed and not found_non_hashtag:
            continue
        if trimmed.startswith("#") and not found_non_hashtag:
            continue
        found_non_hashtag = True
        result.insert(0, line)
    return "\n".join(result)


# ─── Generic API call with retry ────────────────────────────────

async def _call_api(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    max_tokens: int = 4000,
    model: str = MODEL_FAST,
    search_domain_filter: list[str] | None = None,
    search_recency_filter: str | None = None,
    search_language_filter: list[str] | None = None,
    user_location: dict | None = None,
    search_context_size: str = "high",
    return_citations: bool = False,
) -> str | dict:
    """Call Perplexity API with full filter stack.

    When return_citations=True, returns {"content": str, "citations": list}.
    """
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "web_search_options": {"search_context_size": search_context_size},
    }

    # Location filter (EU-centric by default)
    if user_location:
        payload["web_search_options"]["user_location"] = user_location

    # Domain filter – max 20 domains
    if search_domain_filter:
        payload["search_domain_filter"] = search_domain_filter[:20]

    # Recency filter
    if search_recency_filter:
        payload["search_recency_filter"] = search_recency_filter

    # Language filter
    if search_language_filter:
        payload["search_language_filter"] = search_language_filter[:10]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    max_retries = 3
    last_error: Exception | None = None

    async with httpx.AsyncClient(timeout=120) as client:
        for attempt in range(1, max_retries + 1):
            try:
                resp = await client.post(API_URL, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    if return_citations:
                        citations = data.get("citations", [])
                        return {"content": content, "citations": citations}
                    return content

                retryable = {429, 500, 502, 503, 504}
                if resp.status_code in retryable and attempt < max_retries:
                    delay = attempt * 3
                    logger.warning(
                        f"[PerplexityAPI] HTTP {resp.status_code} – retry {attempt}/{max_retries} in {delay}s"
                    )
                    await asyncio.sleep(delay)
                    last_error = Exception(
                        f"HTTP {resp.status_code}: Server temporarily unavailable"
                    )
                    continue

                body = resp.text[:300]
                if "<html" in body.lower() or "<!doctype" in body.lower():
                    body = f"Server temporarily unavailable (HTTP {resp.status_code})"
                raise Exception(f"API Error {resp.status_code}: {body}")

            except httpx.HTTPError as e:
                if attempt < max_retries:
                    delay = attempt * 3
                    logger.warning(
                        f"[PerplexityAPI] Network error – retry {attempt}: {e}"
                    )
                    await asyncio.sleep(delay)
                    last_error = e
                    continue
                raise

    if last_error:
        raise last_error
    raise Exception("Perplexity API call failed after retries")


# ─── JSON helpers ────────────────────────────────────────────────

def _clean_json(content: str) -> str:
    s = content.strip()
    # Strip <think>...</think> blocks from reasoning models
    think_end = s.find("</think>")
    if think_end != -1:
        s = s[think_end + 8:].strip()
    if s.startswith("```json"):
        s = s[7:]
    elif s.startswith("```"):
        s = s[3:]
    if s.endswith("```"):
        s = s[:-3]
    s = s.strip()
    if s.startswith("[") or s.startswith("{"):
        return s
    for open_c, close_c in [("[", "]"), ("{", "}")]:
        start = s.find(open_c)
        end = s.rfind(close_c)
        if start != -1 and end != -1:
            return s[start : end + 1]
    return s


def _parse_json_array(content: str) -> list[dict[str, str]]:
    cleaned = _clean_json(content)
    try:
        arr = json.loads(cleaned)
        if isinstance(arr, list):
            return [{k: str(v) for k, v in item.items()} for item in arr if isinstance(item, dict)]
    except json.JSONDecodeError:
        pass
    return []


def _strip_citations(text: str) -> str:
    return re.sub(r"\s*\[\d+(?:,\s*\d+)*\]", "", text).strip()


def _normalize_name(name: str) -> str:
    n = name.lower().strip()
    for prefix in ["dr. ", "dr ", "prof. ", "prof "]:
        n = n.replace(prefix, "")
    return " ".join(n.split())


def _clean_email(email: str) -> str:
    t = email.strip()
    if "@" in t and "." in t:
        return t.lower()
    return ""


# ─── EU location helper ─────────────────────────────────────────

def _eu_location(region: str = "") -> dict:
    """Return location context for European B2B searches."""
    region_lower = region.lower() if region else ""
    if "uk" in region_lower:
        return {"country": "GB", "city": "London", "latitude": 51.5074, "longitude": -0.1278}
    if "nordic" in region_lower:
        return {"country": "SE", "city": "Stockholm", "latitude": 59.3293, "longitude": 18.0686}
    if "benelux" in region_lower:
        return {"country": "NL", "city": "Amsterdam", "latitude": 52.3676, "longitude": 4.9041}
    if "france" in region_lower:
        return {"country": "FR", "city": "Paris", "latitude": 48.8566, "longitude": 2.3522}
    if "iberia" in region_lower:
        return {"country": "ES", "city": "Madrid", "latitude": 40.4168, "longitude": -3.7038}
    if "baltic" in region_lower:
        return {"country": "EE", "city": "Tallinn", "latitude": 59.437, "longitude": 24.7536}
    # Default: DACH (Frankfurt, financial hub)
    return {"country": "DE", "city": "Frankfurt", "latitude": 50.1109, "longitude": 8.6821}


# ─── 1) Find Companies — DEEP RESEARCH with multi-source ────────

async def find_companies(industry_value: str, region_countries: str, api_key: str) -> list[dict]:
    """Use sonar-pro with domain-filtered search across business directories,
    company databases, and LinkedIn. Two passes: structured + supplementary."""

    system = """You are a B2B company research assistant specializing in European enterprise companies.
You MUST return EXACTLY 25 real companies as a JSON array.
Each object MUST have: name, industry, region, website, linkedInURL, description, size, country, employees, nace_code, founded_year, revenue_range, key_regulations.
CRITICAL RULES:
- Return ONLY valid JSON. No markdown, no explanation.
- All 25 companies must be REAL, currently operating.
- Full website URL (https://...) and LinkedIn company page URL.
- "employees" = realistic integer (e.g. 150, 3500, 85000). NEVER 0.
- "nace_code" = the company's NACE/SIC industry code if known.
- "founded_year" = year founded.
- "revenue_range" = approximate revenue range (e.g. "100M-500M EUR").
- "key_regulations" = comma-separated list of regulations that apply (e.g. "DORA, NIS2, GDPR, MiCA, PSD2").
- Include a MIX of large enterprises AND mid-cap companies (200-5000 employees).
- Prioritize companies with active compliance/regulatory needs."""

    user = f"""Find exactly 25 real {industry_value} companies in {region_countries}.
Requirements:
- Revenue > 50M EUR or equivalent
- 200+ employees
- Currently active and operating
- Strong compliance/regulatory relevance (subject to EU regulations like DORA, NIS2, GDPR, MiCA, CSRD, EU AI Act)
- Include full website URL and LinkedIn company page URL
- Include approximate number of employees as integer
- Include which regulations apply to each company
Search business registries, financial databases, LinkedIn, industry reports, annual reports.
Return ALL 25 as a single JSON array. Count them before returning."""

    location = _eu_location(region_countries)

    # Pass 1: Business directories + company databases
    content1 = await _call_api(
        system, user, api_key,
        max_tokens=8000,
        model=MODEL_FAST,
        search_domain_filter=DOMAINS_COMPANY,
        search_language_filter=["en", "de", "fr", "nl", "sv"],
        user_location=location,
        search_context_size="high",
    )
    raw1 = _parse_json_array(content1 if isinstance(content1, str) else content1.get("content", ""))

    # Pass 2: If < 20 results, supplement with unrestricted search
    if len(raw1) < 20:
        system2 = """You are a B2B company research assistant. Return additional real companies as JSON array.
Each object: name, industry, region, website, linkedInURL, description, size, country, employees, nace_code, key_regulations.
Return ONLY valid JSON."""

        already_found = ", ".join(d.get("name", "") for d in raw1[:25])
        user2 = f"""Find {25 - len(raw1)} MORE {industry_value} companies in {region_countries}.
EXCLUDE these already found: {already_found}
Requirements: Revenue > 50M EUR, 200+ employees, active, compliance-relevant.
Search LinkedIn, Crunchbase, company websites, financial databases, annual reports, industry directories.
Return JSON array."""

        try:
            content2 = await _call_api(
                system2, user2, api_key,
                max_tokens=6000,
                model=MODEL_FAST,
                search_recency_filter="year",
                search_language_filter=["en", "de"],
                user_location=location,
                search_context_size="high",
            )
            raw2 = _parse_json_array(content2 if isinstance(content2, str) else content2.get("content", ""))
            existing_names = {d.get("name", "").lower() for d in raw1}
            for item in raw2:
                if item.get("name", "").lower() not in existing_names:
                    raw1.append(item)
        except Exception:
            pass

    # Normalize results
    companies = []
    for d in raw1[:30]:
        emp_raw = d.get("employees", "0")
        emp_cleaned = str(emp_raw).replace(",", "").replace(".", "").strip()
        try:
            emp = int(emp_cleaned)
        except ValueError:
            emp = 0
        companies.append({
            "name": d.get("name", "Unknown"),
            "industry": d.get("industry", industry_value),
            "region": d.get("region", ""),
            "website": d.get("website", ""),
            "linkedin_url": d.get("linkedInURL", d.get("linkedin_url", "")),
            "description": d.get("description", ""),
            "size": d.get("size", ""),
            "country": d.get("country", ""),
            "employee_count": emp,
            "nace_code": d.get("nace_code", ""),
        })
    return companies


# ─── 2) Find Contacts — MULTI-PASS with domain-targeted searches ─

async def find_contacts(
    company_name: str,
    company_industry: str,
    company_region: str,
    company_website: str,
    api_key: str,
) -> list[dict]:
    """Three-pass contact search:
    1) LinkedIn/XING/theorg.com for org charts and profiles
    2) Business directories (ZoomInfo, Apollo, Lusha, RocketReach)
    3) Company website + press releases + regulatory filings
    """
    location = _eu_location(company_region)

    # ─── Pass 1: Professional networks (LinkedIn, XING, theorg) ───
    system1 = """You are a B2B research assistant. Search professional networks to find compliance, legal, regulatory, and risk management professionals.
Return a JSON array. Each object: name, title, email, linkedInURL, phone, source, seniority_level.
- name: Full name
- title: Job title
- email: Email if found, empty string if not
- linkedInURL: LinkedIn or XING profile URL
- phone: Phone if found, empty string if not
- source: Where found (e.g. "LinkedIn", "XING", "theorg.com")
- seniority_level: "C-Level", "VP", "Director", "Manager", "Other"
IMPORTANT: Return ALL people found. Include compliance, legal, regulatory, data protection, risk management, GRC roles."""

    user1 = f"""Find compliance and regulatory professionals at {company_name}.
Industry: {company_industry}, Region: {company_region}, Website: {company_website}
Target roles:
- Chief Compliance Officer (CCO), Head of Compliance, Compliance Manager/Director
- VP/SVP Regulatory Affairs, Head of Regulatory
- Data Protection Officer (DPO/DSB), Datenschutzbeauftragter
- General Counsel, Chief Legal Officer, Head of Legal
- Head of Risk / Chief Risk Officer (CRO)
- Geldwäschebeauftragter (MLRO), AML Officer
- Head of GRC, Information Security Officer (CISO)
- Vorstand, Geschäftsführung with compliance responsibility
Search LinkedIn profiles, XING profiles, theorg.com org charts for {company_name}.
Return ALL found as JSON array."""

    content1 = await _call_api(
        system1, user1, api_key,
        max_tokens=4000,
        model=MODEL_FAST,
        search_domain_filter=["linkedin.com", "xing.com", "theorg.com"],
        search_language_filter=["en", "de"],
        user_location=location,
        search_context_size="high",
    )
    pass1 = _parse_json_array(content1 if isinstance(content1, str) else content1.get("content", ""))
    logger.info(f"[FindContacts] Pass 1 (networks): {len(pass1)} for {company_name}")

    # ─── Pass 2: Business directories ─────────────────────────────
    system2 = """You are a research assistant specializing in finding business professionals through directories and databases.
Return a JSON array. Each object: name, title, email, linkedInURL, phone, source, seniority_level.
Search ZoomInfo, Apollo.io, RocketReach, Lusha, Hunter.io, SignalHire for contact data.
Return ALL people found with emails when available."""

    already_names = ", ".join(d.get("name", "") for d in pass1[:10])
    user2 = f"""Find compliance, legal, and regulatory contacts at {company_name} ({company_industry}).
Website: {company_website}
Already found (avoid duplicates): {already_names}
Search business contact databases: ZoomInfo, Apollo.io, RocketReach, Lusha, Hunter.io, SignalHire.
Focus on finding email addresses and phone numbers for compliance and legal professionals.
Return JSON array."""

    try:
        content2 = await _call_api(
            system2, user2, api_key,
            max_tokens=4000,
            model=MODEL_FAST,
            search_domain_filter=["zoominfo.com", "apollo.io", "rocketreach.co", "lusha.com", "hunter.io", "signalhire.com"],
            search_language_filter=["en", "de"],
            user_location=location,
            search_context_size="high",
        )
        pass2 = _parse_json_array(content2 if isinstance(content2, str) else content2.get("content", ""))
        logger.info(f"[FindContacts] Pass 2 (directories): {len(pass2)} for {company_name}")
    except Exception:
        pass2 = []

    # ─── Pass 3: Company website, press, regulatory filings ───────
    system3 = """You are a research assistant. Search company websites, press releases, regulatory filings, annual reports, and conference speaker lists.
Return a JSON array. Each object: name, title, email, linkedInURL, phone, source, seniority_level.
Look at:
- Company team/about/leadership/impressum pages
- Press releases mentioning compliance or legal hires
- Regulatory filings (BaFin, FCA, SEC registrations)
- Annual reports and corporate governance sections
- Conference speaker lists from compliance events
- Handelsregister entries
Return ALL people found."""

    # Extract company domain for targeted search
    domain = ""
    if company_website:
        domain = company_website.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]

    website_domains = [d for d in [domain, "bafin.de", "handelsregister.de", "companyhouse.gov.uk"] if d]
    user3 = f"""Find compliance, legal, and regulatory professionals at {company_name}.
Company website: {company_website}
Already found: {already_names}
Search the company website ({company_website}), especially team/about/impressum/leadership pages.
Search press releases about {company_name} compliance hires.
Search regulatory registrations and filings mentioning {company_name}.
Search annual reports and corporate governance documents.
Return JSON array."""

    try:
        content3 = await _call_api(
            system3, user3, api_key,
            max_tokens=4000,
            model=MODEL_FAST,
            search_domain_filter=website_domains[:20],
            search_language_filter=["en", "de"],
            user_location=location,
            search_context_size="high",
        )
        pass3 = _parse_json_array(content3 if isinstance(content3, str) else content3.get("content", ""))
        logger.info(f"[FindContacts] Pass 3 (website/press): {len(pass3)} for {company_name}")
    except Exception:
        pass3 = []

    # ─── Merge & deduplicate all passes ───────────────────────────
    all_candidates = pass1 + pass2 + pass3
    leads = []
    seen_names: set[str] = set()
    for c in all_candidates:
        name = c.get("name", "")
        if not name or name == "Unknown" or len(name) < 3:
            continue
        norm = _normalize_name(name)
        if norm in seen_names:
            # Merge: if we already have this person but new pass has more data, update
            for existing in leads:
                if _normalize_name(existing["name"]) == norm:
                    if not existing["email"] and c.get("email"):
                        existing["email"] = _clean_email(c.get("email", ""))
                    if not existing["linkedin_url"] and c.get("linkedInURL"):
                        existing["linkedin_url"] = c.get("linkedInURL", "")
                    if not existing.get("phone") and c.get("phone"):
                        existing["phone"] = c.get("phone", "")
                    if c.get("source") and c["source"] not in existing.get("source", ""):
                        existing["source"] = f"{existing.get('source', '')} + {c['source']}"
                    break
            continue
        seen_names.add(norm)
        leads.append({
            "name": name,
            "title": c.get("title", ""),
            "company": company_name,
            "email": _clean_email(c.get("email", "")),
            "linkedin_url": c.get("linkedInURL", c.get("linkedin_url", "")),
            "phone": c.get("phone", ""),
            "source": c.get("source", "Perplexity Search"),
        })

    logger.info(f"[FindContacts] Total deduplicated: {len(leads)} for {company_name}")
    return leads


# ─── 3) Verify Email — 3-PASS with targeted domain searches ─────

async def verify_email(
    lead_name: str,
    lead_title: str,
    lead_company: str,
    lead_email: str,
    lead_linkedin: str,
    api_key: str,
) -> dict:
    """Three-pass verification:
    1) Email databases (Hunter, ZoomInfo, Apollo, etc.)
    2) Professional networks (LinkedIn, XING)
    3) Cross-verification with reasoning model
    Returns {email, verified, notes}.
    """
    all_emails: list[dict] = []
    all_notes: list[str] = []

    # Extract company domain
    company_domain = ""
    if lead_email and "@" in lead_email:
        company_domain = lead_email.split("@")[1]

    # ─── Pass 1: Email databases ──────────────────────────────────
    system1 = """You are an expert at finding verified business email addresses from email databases and contact platforms.
Search EXHAUSTIVELY across:
1. Hunter.io - email finder and verifier
2. ZoomInfo - contact database
3. Apollo.io - B2B contact data
4. RocketReach - professional emails
5. Lusha - business contact info
6. SignalHire - professional contact data
7. Clearbit - company data
8. Kaspr - LinkedIn email finder
Return JSON:
- emails: [{email, source, confidence}] where confidence = "high"/"medium"/"low"
- company_email_pattern: the naming convention (e.g. "firstname.lastname@domain.com")
- pattern_examples: other verified emails at this company
- company_domain: the company's primary email domain
- notes: additional context"""

    user1 = f"""Find the business email for:
Name: {lead_name}
Title: {lead_title}
Company: {lead_company}
Known email (may be wrong): {lead_email}
LinkedIn: {lead_linkedin}
Search Hunter.io, ZoomInfo, Apollo, RocketReach, Lusha, SignalHire for this person's email.
Also find the company email pattern by looking at other employees' emails.
Return JSON."""

    try:
        content1 = await _call_api(
            system1, user1, api_key,
            max_tokens=4000,
            model=MODEL_FAST,
            search_domain_filter=DOMAINS_EMAIL,
            search_language_filter=["en", "de"],
            search_context_size="high",
        )
        raw1 = content1 if isinstance(content1, str) else content1.get("content", "")
        cleaned = _clean_json(raw1)
        data = json.loads(cleaned)
        if isinstance(data, dict):
            for e in data.get("emails", []):
                addr = e.get("email", "")
                if addr and "@" in addr:
                    all_emails.append({
                        "email": addr.lower().strip(),
                        "source": e.get("source", "Email DB"),
                        "confidence": e.get("confidence", "medium"),
                    })
            pattern = data.get("company_email_pattern", "")
            if pattern:
                all_notes.append(f"Pattern: {pattern}")
            cd = data.get("company_domain", "")
            if cd:
                all_notes.append(f"Domain: {cd}")
                if not company_domain:
                    company_domain = cd
            notes = data.get("notes", "")
            if notes:
                all_notes.append(notes)
    except Exception as ex:
        all_notes.append(f"Pass 1 (email DBs): {ex}")

    # ─── Pass 2: Professional networks ────────────────────────────
    system2 = """You are a research assistant finding email addresses from professional networks.
Search LinkedIn profiles (contact info section), XING profiles, and company websites (impressum, about, team pages).
Return JSON:
- emails: [{email, source, confidence}]
- linkedin_data: any additional info found on their LinkedIn profile
- notes: context about the search results"""

    user2 = f"""Find email address for {lead_name}, {lead_title} at {lead_company}.
LinkedIn: {lead_linkedin}
Search their LinkedIn profile contact section, XING profile, and the company website's impressum/team pages.
Also search Google for "{lead_name}" "{lead_company}" email.
Return JSON."""

    try:
        content2 = await _call_api(
            system2, user2, api_key,
            max_tokens=3000,
            model=MODEL_FAST,
            search_domain_filter=["linkedin.com", "xing.com"],
            search_language_filter=["en", "de"],
            search_context_size="high",
        )
        raw2 = content2 if isinstance(content2, str) else content2.get("content", "")
        cleaned2 = _clean_json(raw2)
        data2 = json.loads(cleaned2)
        if isinstance(data2, dict):
            for e in data2.get("emails", []):
                addr = e.get("email", "")
                if addr and "@" in addr:
                    c = addr.lower().strip()
                    if not any(ex["email"] == c for ex in all_emails):
                        all_emails.append({
                            "email": c,
                            "source": e.get("source", "LinkedIn/XING"),
                            "confidence": e.get("confidence", "medium"),
                        })
    except Exception as ex:
        all_notes.append(f"Pass 2 (networks): {ex}")

    # ─── Pass 3: Cross-verification with REASONING model ──────────
    system3 = """You are an email verification specialist with deep analytical capabilities.
Given a person, candidate emails, and company email patterns, determine the most likely correct email.
Analyze:
1. Does the email follow the company's naming pattern?
2. Is the domain correct for this company?
3. Cross-reference with multiple sources
4. Check for common email patterns (firstname.lastname, f.lastname, first.last, etc.)
Return JSON: {best_email, verified (bool), confidence, verification_sources, alternative_emails, reasoning}"""

    candidate_str = ", ".join([e["email"] for e in all_emails[:8]]) or "none found"
    pattern_str = " | ".join(all_notes) or "no patterns found"
    user3 = f"""Verify the best email for:
Name: {lead_name}
Title: {lead_title}
Company: {lead_company}
LinkedIn: {lead_linkedin}
Company domain: {company_domain}
Candidate emails: {candidate_str}
Known patterns: {pattern_str}
Analyze all candidates. Which is most likely correct? Cross-verify across sources.
Return JSON with best_email, verified, confidence, reasoning."""

    try:
        content3 = await _call_api(
            system3, user3, api_key,
            max_tokens=3000,
            model=MODEL_REASONING,
            search_context_size="high",
            search_language_filter=["en", "de"],
        )
        raw3 = content3 if isinstance(content3, str) else content3.get("content", "")
        cleaned3 = _clean_json(raw3)
        data3 = json.loads(cleaned3)
        if isinstance(data3, dict):
            best = data3.get("best_email", "")
            if best and "@" in best:
                conf = data3.get("confidence", "medium")
                verified = data3.get("verified", False)
                all_emails.insert(0, {
                    "email": best.lower().strip(),
                    "source": "Cross-verification (Reasoning)",
                    "confidence": "high" if verified else conf,
                })
            for alt in data3.get("alternative_emails", []):
                if alt and "@" in alt:
                    c = alt.lower().strip()
                    if not any(e["email"] == c for e in all_emails):
                        all_emails.append({"email": c, "source": "Alternative", "confidence": "low"})
            reasoning = data3.get("reasoning", "")
            if reasoning:
                all_notes.append(f"Reasoning: {reasoning}")
    except Exception as ex:
        all_notes.append(f"Pass 3 (reasoning): {ex}")

    # ─── Pick best email ──────────────────────────────────────────
    email_counts: dict[str, int] = {}
    for e in all_emails:
        email_counts[e["email"]] = email_counts.get(e["email"], 0) + 1

    best_entry = (
        next((e for e in all_emails if e["confidence"] == "high"), None)
        or next((e for e in all_emails if e["confidence"] == "medium" and email_counts.get(e["email"], 0) > 1), None)
        or next((e for e in all_emails if e["confidence"] == "medium"), None)
        or (all_emails[0] if all_emails else None)
    )

    final_email = best_entry["email"] if best_entry else lead_email
    is_verified = bool(
        best_entry
        and (
            best_entry["confidence"] == "high"
            or email_counts.get(best_entry["email"], 0) > 1
            or best_entry["confidence"] == "medium"
        )
    )

    notes_parts = []
    if best_entry:
        notes_parts.append(f"Best: {best_entry['email']} ({best_entry['source']}, {best_entry['confidence']})")
    else:
        notes_parts.append("No email found")
    notes_parts.append(f"Candidates: {len(all_emails)}, Sources: {len(set(e['source'] for e in all_emails))}")
    notes_parts.extend(all_notes[:5])
    notes_str = " | ".join(notes_parts)[:500]

    final = _clean_email(final_email or lead_email)
    return {"email": final, "verified": is_verified, "notes": notes_str}


# ─── 4) Research Challenges — DEEP multi-source ─────────────────

async def research_challenges(company_name: str, company_industry: str, api_key: str) -> str:
    """Use sonar-reasoning-pro to deeply analyze a company's regulatory challenges.
    Pulls from regulatory bodies, news, annual reports, and industry analysis."""

    system = """You are a regulatory compliance expert. Research SPECIFIC, CURRENT challenges for the given company.
Analyze:
1. Which EU regulations directly apply (DORA, NIS2, GDPR, MiCA, CSRD, EU AI Act, PSD2, AML6)?
2. Upcoming regulatory deadlines and changes
3. Recent enforcement actions or fines in their industry
4. Specific compliance pain points based on company size and geography
5. Current regulatory consultations affecting them
Use CONCRETE data: deadlines, fine amounts, specific articles, recent cases.
ALWAYS respond in English. Be specific — not generic."""

    user = f"""Research the top 5-7 regulatory compliance challenges for {company_name} in {company_industry}.

I need SPECIFIC information for personalized outreach:
1. Which EU/national regulations apply directly to {company_name}?
2. What are the nearest compliance deadlines?
3. Have there been recent fines or enforcement actions in their sector?
4. What technology/process gaps do companies like {company_name} typically face?
5. What upcoming regulatory changes will impact them most?

Search regulatory bodies (BaFin, EBA, ESMA, FCA), recent news, compliance reports.
Include specific dates, amounts, and regulation articles. Respond in English."""

    result = await _call_api(
        system, user, api_key,
        max_tokens=4000,
        model=MODEL_REASONING,
        search_domain_filter=DOMAINS_REGULATORY + ["ft.com", "reuters.com", "handelsblatt.com"],
        search_recency_filter="month",
        search_language_filter=["en", "de"],
        user_location=_eu_location(),
        search_context_size="high",
        return_citations=True,
    )

    if isinstance(result, dict):
        content = result["content"]
        citations = result.get("citations", [])
        # Append citations as context for email drafting
        if citations:
            content += "\n\nSources: " + ", ".join(citations[:10])
        return content
    return result


# ─── 5) Draft Email — REASONING model for deep personalization ──

async def draft_email(
    lead_name: str,
    lead_title: str,
    lead_company: str,
    challenges: str,
    sender_name: str,
    api_key: str,
) -> dict:
    """Use sonar-reasoning-pro for deeply personalized emails.
    First researches the person, then crafts the email.
    Returns {subject, body}."""

    # Pre-research: Find personal context about the lead
    system_research = """You are a B2B research assistant. Find professional context about a specific person.
Search for:
- Their recent posts, articles, or interviews
- Conference talks or panel appearances
- Published opinions on compliance/regulatory topics
- Career history and expertise areas
- Any public statements about their company's strategy
Return a brief profile (max 200 words) with specific details useful for personalized outreach."""

    user_research = f"""Research {lead_name}, {lead_title} at {lead_company}.
Find their professional background, recent public statements, expertise areas, conference appearances.
Search LinkedIn, industry publications, conference websites.
Return a brief profile."""

    personal_context = ""
    try:
        result = await _call_api(
            system_research, user_research, api_key,
            max_tokens=1500,
            model=MODEL_FAST,
            search_domain_filter=["linkedin.com", "compliance-praxis.de", "handelsblatt.com"],
            search_language_filter=["en", "de"],
            search_context_size="high",
        )
        personal_context = result if isinstance(result, str) else result.get("content", "")
        personal_context = _strip_citations(personal_context)
    except Exception:
        pass

    # Now draft the email with full context
    system = """You write highly personalized B2B outreach emails. CRITICAL RULES:
1. ALWAYS write in English - no German.
2. Reference SPECIFIC, VERIFIABLE facts about the recipient and their company.
3. Mention a specific regulation, deadline, or industry event relevant to them.
4. If you know something personal about them (talk, article, post), reference it naturally.
5. Show deep understanding of their role and daily challenges.
6. Keep under 150 words, personal, value-focused. No hard sell, no generic pitch.
7. The email must feel like it was written specifically for this ONE person.
8. Include a soft CTA (brief call, relevant case study, industry report).
Return ONLY valid JSON: {subject, body}"""

    user = f"""Write a cold outreach email from {sender_name} at Harpocrates Corp (RegTech company) to:
Name: {lead_name}
Title: {lead_title}
Company: {lead_company}

THEIR SPECIFIC CHALLENGES:
{challenges}

PERSONAL CONTEXT ABOUT {lead_name}:
{personal_context if personal_context else "No additional personal context found."}

OUR SOLUTION: comply.reg - Automated compliance monitoring, regulatory change tracking, risk assessment.
Supports: DORA, NIS2, GDPR, MiCA, CSRD, EU AI Act, AML/KYC compliance.

IMPORTANT:
- Reference their SPECIFIC regulatory challenges with concrete details (dates, fines, articles)
- If personal context available, weave it in naturally
- Make subject line compelling AND specific to their situation
- Include a soft CTA
Return JSON: {{subject, body}}"""

    content = await _call_api(
        system, user, api_key,
        max_tokens=2000,
        model=MODEL_REASONING,
        search_context_size="high",
    )
    raw = content if isinstance(content, str) else content.get("content", "")
    cleaned = _clean_json(raw)
    try:
        data = json.loads(cleaned)
        raw_body = data.get("body", raw)
        return {
            "subject": data.get("subject", f"Compliance Solutions for {lead_company}"),
            "body": _strip_citations(raw_body),
        }
    except json.JSONDecodeError:
        return {"subject": "Compliance Solutions", "body": _strip_citations(raw)}


# ─── 6) Draft Follow-Up ─────────────────────────────────────────

async def draft_follow_up(
    lead_name: str,
    lead_company: str,
    original_email: str,
    follow_up_email: str,
    reply_received: str,
    sender_name: str,
    api_key: str,
) -> dict:
    """Use reasoning model for intelligent follow-up that researches NEW angles."""

    # Research fresh angle for follow-up
    system_angle = """You are a compliance industry researcher. Find a RECENT, SPECIFIC compliance event, fine, regulation update, or industry development.
This will be used as a fresh angle for a follow-up email. Find something from the past 7 days if possible.
Return: a 1-2 sentence description of the event with specific details (date, amount, regulation)."""

    user_angle = f"""Find a recent compliance or regulatory event relevant to {lead_company}'s industry.
Something from the past 7-14 days: a new fine, regulation update, enforcement action, or compliance deadline.
This should be a conversation starter for a follow-up email."""

    fresh_angle = ""
    try:
        result = await _call_api(
            system_angle, user_angle, api_key,
            max_tokens=500,
            model=MODEL_FAST,
            search_recency_filter="week",
            search_domain_filter=DOMAINS_REGULATORY + ["ft.com", "reuters.com"],
            search_language_filter=["en", "de"],
            search_context_size="high",
        )
        fresh_angle = result if isinstance(result, str) else result.get("content", "")
        fresh_angle = _strip_citations(fresh_angle)
    except Exception:
        pass

    system = """You write professional follow-up emails for B2B outreach. CRITICAL RULES:
1. ALWAYS write in English.
2. Based on previous emails and any replies, write a follow-up that:
   - References the previous conversation naturally
   - If reply: acknowledge and continue dialogue
   - If no reply: use a FRESH ANGLE with new value (recent event, new insight)
   - Under 150 words, professional, value-focused
   - Do NOT repeat the same pitch
3. Make content specifically relevant to the recipient.
Return ONLY valid JSON: {subject, body}"""

    ctx = f"Previous email to {lead_name} at {lead_company}:\n{original_email}"
    if follow_up_email:
        ctx += f"\n\nPrevious follow-up:\n{follow_up_email}"
    if reply_received:
        ctx += f"\n\nReply from {lead_name}:\n{reply_received}"

    user = f"""Write a follow-up from {sender_name} at Harpocrates Corp.
CONVERSATION HISTORY:
{ctx}

FRESH ANGLE (recent industry event):
{fresh_angle if fresh_angle else "No specific recent event found."}

Write the next follow-up in English. Use the fresh angle if available.
If a reply was received, respond directly. If no reply, bring new value.
Return JSON: {{subject, body}}"""

    content = await _call_api(
        system, user, api_key,
        max_tokens=2000,
        model=MODEL_REASONING,
        search_context_size="high",
    )
    raw = content if isinstance(content, str) else content.get("content", "")
    cleaned = _clean_json(raw)
    try:
        data = json.loads(cleaned)
        raw_body = data.get("body", raw)
        return {
            "subject": data.get("subject", f"Following up - {lead_company}"),
            "body": _strip_citations(raw_body),
        }
    except json.JSONDecodeError:
        return {"subject": f"Following up - {lead_company}", "body": _strip_citations(raw)}


# ─── 7) Generate Social Post — with citations ───────────────────

async def generate_social_post(
    topic: str,
    topic_prefix: str,
    platform: str,
    industries: list[str],
    existing_posts_preview: list[str],
    api_key: str,
) -> dict:
    """Generate social posts with real citations from regulatory sources."""
    dupe_context = ""
    if existing_posts_preview:
        titles = "\n- ".join(existing_posts_preview[:10])
        dupe_context = f"\n\nALREADY POSTED (DO NOT REPEAT):\n- {titles}"

    system = f"""You are a social media expert for Harpocrates Corp and comply.reg.
comply.reg: RegTech SaaS for automated compliance monitoring, regulatory change management, risk assessment.

MANDATORY RULES:
1. LANGUAGE: Write ENTIRELY in English.
2. FACTS: Every post MUST have 1-2 concrete numbers/statistics with source citation (e.g. Source: EBA, BaFin).
3. NO HALLUCINATIONS: Only verifiable facts.
4. COMPLY.REG RELEVANCE: Address problems comply.reg solves.
5. NO DUPLICATE topic/hook.
6. FOOTER: Added automatically — do NOT include any footer.
7. VALUE: Genuine insight for compliance professionals.
8. TIMELINESS: Reference recent regulatory developments.
Return JSON: {{"content": "...", "hashtags": [...]}}"""

    industry_context = ", ".join(industries) if industries else "Financial Services, RegTech, Compliance"

    user = f"""Write a {platform} post for Harpocrates Corp / comply.reg.
Topic: {topic} - {topic_prefix} {industry_context}

REQUIREMENTS:
- Write in English
- Hook in line 1 (number or provocative thesis)
- At least 1 concrete number/statistic with source
- Reference DORA, NIS2, GDPR, MiCA, EU AI Act, CSRD or current EU regulations
- Question or CTA at end
- Mention comply.reg naturally
- LinkedIn: 150-250 words, line breaks{dupe_context}
Hashtags: 5-7 from: #DORA #NIS2 #GDPR #RegTech #Compliance #FinTech #RegulatoryCompliance #comply #RiskManagement #AML #BaFin #EBA
Return ONLY valid JSON."""

    content = await _call_api(
        system, user, api_key,
        max_tokens=2000,
        model=MODEL_FAST,
        search_recency_filter="week",
        search_domain_filter=DOMAINS_REGULATORY + ["ft.com", "reuters.com"],
        search_language_filter=["en", "de"],
        user_location=_eu_location(),
        search_context_size="high",
        return_citations=True,
    )

    raw = content if isinstance(content, str) else content.get("content", "")
    citations = content.get("citations", []) if isinstance(content, dict) else []

    cleaned = _clean_json(raw)
    try:
        data = json.loads(cleaned)
        raw_content = data.get("content", raw)
        hashtags = data.get("hashtags", [])
        hashtag_line = " ".join(
            h if h.startswith("#") else f"#{h}" for h in hashtags
        )
        full = strip_trailing_hashtags(raw_content)
        if hashtag_line:
            full += "\n\n" + hashtag_line
        full = ensure_footer(full)
        return {"content": full, "hashtags": hashtags}
    except json.JSONDecodeError:
        return {"content": ensure_footer(raw), "hashtags": []}


# ─── 8) Generate Subject Alternatives ───────────────────────────

async def generate_subject_alternatives(
    company_name: str,
    company_industry: str,
    email_body_preview: str,
    api_key: str,
) -> list[str]:
    system = """You write compelling B2B cold email subject lines for RegTech/Compliance outreach.
Generate exactly 3 different subject lines. Each must:
- Be personalized to the company and industry
- Reference a specific compliance challenge or regulation
- Be concise (max 60 characters)
- Not be generic or spammy
- Be in English
Return ONLY 3 lines. No numbering, no quotes."""

    user = f"""Company: {company_name}
Industry: {company_industry}
Email summary: {email_body_preview[:300]}
Generate 3 compelling subject lines."""

    content = await _call_api(
        system, user, api_key,
        max_tokens=200,
        model=MODEL_FAST,
        search_context_size="low",
    )
    raw = content if isinstance(content, str) else content.get("content", "")
    subjects = [
        line.strip()
        for line in raw.split("\n")
        if line.strip() and 5 < len(line.strip()) < 100
    ]
    return subjects or [f"Compliance Partnership Opportunity - {company_name}"]
