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


def _strip_markdown(text: str) -> str:
    """Remove markdown formatting from text for LinkedIn plain-text output.
    Strips **bold**, *italic*, [text](url) links, and markdown lists."""
    import re as _re
    result = text
    # Remove markdown links [text](url) -> text (url)
    result = _re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1 (\2)', result)
    # Remove **bold** markers
    result = _re.sub(r'\*\*(.+?)\*\*', r'\1', result)
    # Remove *italic* markers (but not bullet points like * item)
    result = _re.sub(r'(?<!\n)\*(?!\s)(.+?)\*', r'\1', result)
    # Remove markdown list markers at line start (- item -> • item)
    result = _re.sub(r'^\s*[-*]\s+', '• ', result, flags=_re.MULTILINE)
    return result


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
    response_format: dict | None = None,
) -> str | dict:
    """Call Perplexity API with full filter stack.

    When return_citations=True, returns {"content": str, "citations": list}.
    When response_format is provided, enforces structured JSON output.
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

    # Structured JSON output (enforced by API, much more reliable than prompt-only)
    if response_format:
        payload["response_format"] = response_format

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


def _resolve_citations(text: str, citations: list[str]) -> str:
    """Replace [1], [2] etc. markers with actual URLs from Perplexity citations array.
    Produces readable inline links like: [Source Title](URL)"""
    if not citations:
        return text

    def _domain_label(url: str) -> str:
        """Extract a readable label from a URL."""
        try:
            from urllib.parse import urlparse
            host = urlparse(url).hostname or url
            host = host.replace("www.", "")
            # Map known domains to readable names
            domain_names = {
                "eba.europa.eu": "EBA",
                "esma.europa.eu": "ESMA",
                "ecb.europa.eu": "ECB",
                "bafin.de": "BaFin",
                "eur-lex.europa.eu": "EUR-Lex",
                "european-commission.europa.eu": "European Commission",
                "ec.europa.eu": "European Commission",
                "ft.com": "Financial Times",
                "reuters.com": "Reuters",
                "handelsblatt.com": "Handelsblatt",
                "fca.org.uk": "FCA",
                "consilium.europa.eu": "EU Council",
                "europarl.europa.eu": "EU Parliament",
            }
            for domain, name in domain_names.items():
                if domain in host:
                    return name
            # Fallback: use domain without TLD
            parts = host.split(".")
            return parts[0].capitalize() if parts else host
        except Exception:
            return "Source"

    # Replace [N] markers with plain-text source references
    # Output: (Source: ECB) — not markdown links, not bracketed URLs
    def replacer(match: re.Match) -> str:
        nums_str = match.group(1)  # e.g. "1" or "1, 2"
        nums = [int(n.strip()) for n in nums_str.split(",") if n.strip().isdigit()]
        labels = []
        for n in nums:
            idx = n - 1  # citations are 0-indexed
            if 0 <= idx < len(citations):
                label = _domain_label(citations[idx])
                labels.append(label)
        if labels:
            return " (" + ", ".join(labels) + ")"
        return match.group(0)

    resolved = re.sub(r"\[(\d+(?:,\s*\d+)*)\]", replacer, text)
    return resolved


def _normalize_name(name: str) -> str:
    n = name.lower().strip()
    for prefix in ["dr. ", "dr ", "prof. ", "prof "]:
        n = n.replace(prefix, "")
    return " ".join(n.split())


def _clean_email(email: str) -> str:
    t = email.strip()
    if "@" in t and "." in t:
        cleaned = t.lower()
        # Filter out masked/redacted emails from paywalled sources (ZoomInfo, Apollo etc.)
        local = cleaned.split("@")[0]
        if "***" in local or "*" * 3 in local or "..." in local:
            return ""  # Masked email like m***@db.com is useless
        if local.startswith("[email") or "[at]" in cleaned:
            return ""  # Obfuscated
        if len(local) < 2:
            return ""  # Too short to be real
        return cleaned
    return ""


def _derive_email_from_pattern(name: str, domain: str, pattern: str = "") -> list[str]:
    """Derive plausible email addresses from a person's name and company domain.
    Returns a list of candidates sorted by likelihood."""
    if not name or not domain:
        return []

    parts = name.strip().split()
    if len(parts) < 2:
        return []

    # Handle German umlauts
    umlaut_map = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
                  "Ä": "Ae", "Ö": "Oe", "Ü": "Ue"}
    def normalize(s):
        for k, v in umlaut_map.items():
            s = s.replace(k, v)
        return s.lower().strip().replace(" ", "")

    first = normalize(parts[0])
    last = normalize(parts[-1])

    # Strip academic titles
    if first in ("dr", "prof", "ing"):
        if len(parts) >= 3:
            first = normalize(parts[1])
            last = normalize(parts[-1])
        else:
            return []

    candidates = [
        f"{first}.{last}@{domain}",       # martin.foerster@domain.com (most common)
        f"{first[0]}.{last}@{domain}",     # m.foerster@domain.com
        f"{first}{last}@{domain}",          # martinfoerster@domain.com
        f"{first[0]}{last}@{domain}",       # mfoerster@domain.com
        f"{last}.{first}@{domain}",         # foerster.martin@domain.com
        f"{first}.{last[0]}@{domain}",      # martin.f@domain.com
        f"{first}_{last}@{domain}",         # martin_foerster@domain.com
        f"{first}-{last}@{domain}",         # martin-foerster@domain.com
    ]

    # If a pattern is provided, prioritize matching pattern
    if pattern:
        pattern_lower = pattern.lower()
        if "firstname.lastname" in pattern_lower or "vorname.nachname" in pattern_lower:
            candidates.insert(0, f"{first}.{last}@{domain}")
        elif "f.lastname" in pattern_lower or "initial" in pattern_lower:
            candidates.insert(0, f"{first[0]}.{last}@{domain}")

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


def _normalize_company_name(name: str) -> str:
    """Normalize company name for duplicate detection.
    E.g. 'Bayerische Landesbank (BayernLB)' and 'BayernLB' should match."""
    n = name.lower().strip()
    # Remove common suffixes
    for suffix in [" ag", " se", " gmbh", " sa", " ltd", " plc", " & co.",
                   " & co", " kg", " kgaa", " e.v.", " eg", " mbh"]:
        n = n.replace(suffix, "")
    # Remove content in parentheses
    n = re.sub(r"\([^)]*\)", "", n)
    # Remove special characters
    n = re.sub(r"[^a-z0-9äöüß ]", "", n)
    return " ".join(n.split()).strip()


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



# ─── 0) Search Single Company (targeted) ──────────────────────

async def search_single_company(
    company_name: str,
    api_key: str,
) -> dict | None:
    """Search for a single company by name via Perplexity API.
    Returns company details dict or None if not found.
    Used by the address book 'targeted search' feature."""

    location = _eu_location()

    system = """You are a B2B company research assistant specializing in European companies.
Given a company name, find detailed information about this SPECIFIC company.
Return EXACTLY ONE JSON object (not an array) with these fields:
name, industry, region, website, linkedInURL, description, size, country, employees, nace_code, founded_year, revenue_range, key_regulations.

CRITICAL RULES:
- Return ONLY valid JSON. No markdown, no explanation, no code fences.
- The company must be REAL and currently operating.
- Full website URL (https://...) and LinkedIn company page URL.
- "employees" must be a NUMBER (integer), not a string.
- "region" should be the European region (e.g. "DACH", "Nordics", "UK", "Benelux", "France", "Iberia").
- "key_regulations" is a comma-separated list of applicable regulations (e.g. "DSGVO, MaRisk, DORA, NIS2").
- If the company cannot be found or does not exist, return: {"error": "not_found"}"""

    user = f"""Find detailed information about this company: {company_name}

Search across business databases, LinkedIn, company registries, and news sources.
Return a single JSON object with all fields."""

    try:
        content_resp = await _call_api(
            system, user, api_key,
            max_tokens=2000,
            model=MODEL_FAST,
            search_domain_filter=DOMAINS_COMPANY,
            search_language_filter=["en", "de"],
            user_location=location,
            search_context_size="high",
        )
        cleaned = _clean_json(content_resp if isinstance(content_resp, str) else content_resp.get("content", ""))
        data = json.loads(cleaned)

        # Handle error response
        if isinstance(data, dict) and data.get("error") == "not_found":
            return None

        # If API returned an array, take the first item
        if isinstance(data, list):
            data = data[0] if data else None

        if not data or not isinstance(data, dict):
            return None

        # Normalize employees to int
        emp = data.get("employees", 0)
        if isinstance(emp, str):
            emp = int(re.sub(r"[^0-9]", "", emp) or "0")
        data["employees"] = emp
        data["employee_count"] = emp

        return data

    except Exception as ex:
        err_str = str(ex).lower()
        # Re-raise quota/auth errors so the route can handle them properly
        if "quota" in err_str or "401" in err_str or "insufficient" in err_str:
            logger.warning(f"[SearchSingleCompany] API quota error for {company_name}: {ex}")
            raise
        logger.warning(f"[SearchSingleCompany] Failed for {company_name}: {ex}")
        return None


# ─── 1) Find Companies — DEEP RESEARCH with multi-source ────────

# JSON Schema for structured company output (enforced by Perplexity API)
_COMPANY_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "company_list",
        "schema": {
            "type": "object",
            "properties": {
                "companies": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "industry": {"type": "string"},
                            "region": {"type": "string"},
                            "website": {"type": "string"},
                            "linkedInURL": {"type": "string"},
                            "description": {"type": "string"},
                            "size": {"type": "string"},
                            "country": {"type": "string"},
                            "employees": {"type": "integer"},
                            "nace_code": {"type": "string"},
                            "founded_year": {"type": "string"},
                            "revenue_range": {"type": "string"},
                            "key_regulations": {"type": "string"},
                        },
                        "required": ["name", "industry", "country", "employees"],
                    },
                },
            },
            "required": ["companies"],
        },
    },
}


async def find_companies(
    industry_value: str,
    region_countries: str,
    api_key: str,
    size_filter: str = "",
) -> list[dict]:
    """Use sonar-pro with structured JSON output + sharper industry filtering.
    Two passes:
    1) Major players + compliance-relevant companies
    2) Hidden Champions supplement
    Includes fuzzy dedup via _normalize_company_name.
    """

    # Build dynamic size constraint for the prompt
    if "5001" in size_filter or "5.001" in size_filter:
        size_constraint = "ONLY companies with MORE THAN 5,000 employees."
    elif "201" in size_filter:
        size_constraint = "ONLY mid-size companies with 201–5,000 employees (Mittelstand / Hidden Champions)."
    elif "0-200" in size_filter:
        size_constraint = "ONLY small companies with up to 200 employees (startups, niche players)."
    else:
        size_constraint = "Any size — from large corporates to Mittelstand Hidden Champions."

    system = f"""You are a B2B company research assistant specializing in European enterprise companies.
Return a JSON object with a "companies" array containing EXACTLY 25 real companies.

CRITICAL INDUSTRY RULE:
The user searches for "{industry_value}". Return ONLY companies whose PRIMARY business activity is {industry_value}.
- A company's PRIMARY business is its main revenue source and core activity.
- Do NOT include companies that merely have a subsidiary, department, or division in {industry_value}.
- Example: If searching for "Finanzdienstleistungen" (Financial Services), return banks, insurance, asset managers, payment providers — NOT Volkswagen (automotive), Deutsche Telekom (telecom), or Bosch (engineering) even though they have financial arms.
- Example: If searching for "Automobilindustrie", return car manufacturers, auto suppliers — NOT banks that finance cars.

CRITICAL VALIDATION:
- Every company MUST be REAL, currently operating, and verifiable.
- "employees" MUST be a realistic integer > 0. Research the actual number.
- "website" MUST be a real, working company website URL (https://...).
- "linkedInURL" MUST be a real LinkedIn company page URL (https://www.linkedin.com/company/...).
- Do NOT invent or hallucinate company names. If unsure, omit.
- Each company must be UNIQUE — no duplicates or name variations of the same entity.

EMPLOYEE SIZE FILTER: {size_constraint}

PRIORITY ORDER — rank by COMPLIANCE RELEVANCE:
1. Companies in HIGHLY REGULATED sub-sectors of {industry_value}
2. Companies facing IMMINENT regulatory deadlines or known compliance challenges
3. Companies recently fined or under regulatory scrutiny
4. Major players that EVERYONE knows in {industry_value}
5. Hidden Champions — lesser-known but highly regulated mid-size firms

Aim for roughly 60% well-known + 40% Hidden Champions."""

    user = f"""Find exactly 25 real companies whose PRIMARY business is {industry_value} in {region_countries}.

Employee filter: {size_constraint}

IMPORTANT: Only companies where {industry_value} is the CORE business — not companies with a minor division in this field.

Search stock indices (DAX, MDAX, SDAX, SMI, ATX), BaFin/EBA regulated entity lists, LinkedIn, Crunchbase, industry associations, Handelsregister.
Include both well-known leaders and Hidden Champions.
For each company, list specific EU regulations that apply (DORA, NIS2, GDPR, MiCA, CSRD, EU AI Act, etc.).

Return as JSON object with "companies" array."""

    location = _eu_location(region_countries)

    # Pass 1: Major players + regulated companies (with structured JSON output)
    try:
        content1 = await _call_api(
            system, user, api_key,
            max_tokens=8000,
            model=MODEL_FAST,
            search_domain_filter=DOMAINS_COMPANY,
            search_language_filter=["en", "de", "fr", "nl", "sv"],
            user_location=location,
            search_context_size="high",
            response_format=_COMPANY_JSON_SCHEMA,
        )
        raw_text = content1 if isinstance(content1, str) else content1.get("content", "")
        parsed = json.loads(_clean_json(raw_text))
        if isinstance(parsed, dict) and "companies" in parsed:
            raw1 = [
                {k: str(v) if not isinstance(v, (int, float)) else str(v) for k, v in item.items()}
                for item in parsed["companies"] if isinstance(item, dict)
            ]
        elif isinstance(parsed, list):
            raw1 = [{k: str(v) for k, v in item.items()} for item in parsed if isinstance(item, dict)]
        else:
            raw1 = []
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"[FindCompanies] Structured output parse failed, falling back: {e}")
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

    # Pass 2: Hidden Champions supplement
    system2 = f"""You are a compliance-focused company researcher. Find HIDDEN CHAMPIONS — lesser-known but highly regulated companies.
CRITICAL: Only companies whose PRIMARY business is {industry_value}. No companies from other industries.
Focus on: Mittelstand world market leaders, SDAX-listed firms, companies subject to export controls, REACH, dual-use regulations, critical infrastructure (NIS2 scope), or sector-specific compliance.
Return a JSON object with a "companies" array. Each object: name, industry, region, website, linkedInURL, description, size, country, employees (integer), nace_code, founded_year, revenue_range, key_regulations.
Employee filter: {size_constraint}"""

    already_found = ", ".join(d.get("name", "") for d in raw1[:30])
    need = max(25 - len(raw1), 5)
    user2 = f"""Find {need} MORE companies whose PRIMARY business is {industry_value} in {region_countries}.
These companies must NOT be in this list: {already_found}

CRITICAL: Only companies where {industry_value} is the CORE business.

Focus on HIDDEN CHAMPIONS:
- Mittelstand firms with world-market-leading positions in regulated niches
- Companies newly in scope of NIS2, CSRD, or EU AI Act
- Companies recently in BaFin/regulatory news
- Family-owned enterprises with complex compliance needs

Search Mittelstand rankings, SDAX listings, industry association member lists, BaFin regulated entity registers.
Return JSON object with "companies" array."""

    try:
        content2 = await _call_api(
            system2, user2, api_key,
            max_tokens=6000,
            model=MODEL_FAST,
            search_recency_filter="year",
            search_language_filter=["en", "de"],
            user_location=location,
            search_context_size="high",
            response_format=_COMPANY_JSON_SCHEMA,
        )
        raw_text2 = content2 if isinstance(content2, str) else content2.get("content", "")
        parsed2 = json.loads(_clean_json(raw_text2))
        if isinstance(parsed2, dict) and "companies" in parsed2:
            raw2 = [
                {k: str(v) if not isinstance(v, (int, float)) else str(v) for k, v in item.items()}
                for item in parsed2["companies"] if isinstance(item, dict)
            ]
        elif isinstance(parsed2, list):
            raw2 = [{k: str(v) for k, v in item.items()} for item in parsed2 if isinstance(item, dict)]
        else:
            raw2 = []
        # Fuzzy dedup against pass 1
        existing_norms = {_normalize_company_name(d.get("name", "")) for d in raw1}
        for item in raw2:
            norm = _normalize_company_name(item.get("name", ""))
            if norm and norm not in existing_norms:
                raw1.append(item)
                existing_norms.add(norm)
    except Exception as e:
        logger.warning(f"[FindCompanies] Pass 2 failed: {e}")

    # Normalize results + fuzzy dedup
    companies = []
    seen_norms: set[str] = set()
    for d in raw1[:40]:
        name = d.get("name", "Unknown").strip()
        if not name or name == "Unknown":
            continue
        norm = _normalize_company_name(name)
        if norm in seen_norms:
            continue  # Skip fuzzy duplicate
        seen_norms.add(norm)

        emp_raw = d.get("employees", "0")
        emp_cleaned = str(emp_raw).replace(",", "").replace(".", "").strip()
        try:
            emp = int(emp_cleaned)
        except ValueError:
            emp = 0

        website = d.get("website", "")
        # Skip companies with no employees AND no website (likely hallucinated)
        if emp == 0 and not website:
            logger.info(f"[FindCompanies] Skipping {name}: no employees and no website")
            continue

        companies.append({
            "name": name,
            "industry": d.get("industry", industry_value),
            "region": d.get("region", ""),
            "website": website,
            "linkedin_url": d.get("linkedInURL", d.get("linkedin_url", "")),
            "description": d.get("description", ""),
            "size": d.get("size", ""),
            "country": d.get("country", ""),
            "employee_count": emp,
            "nace_code": d.get("nace_code", ""),
        })

    logger.info(f"[FindCompanies] Returning {len(companies)} companies for {industry_value}/{region_countries}")
    return companies


# ─── 2) Find Contacts — MULTI-PASS with domain-targeted searches ─

# JSON Schema for structured contact output
_CONTACT_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "contact_list",
        "schema": {
            "type": "object",
            "properties": {
                "contacts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "title": {"type": "string"},
                            "email": {"type": "string"},
                            "linkedInURL": {"type": "string"},
                            "phone": {"type": "string"},
                            "source": {"type": "string"},
                            "seniority_level": {"type": "string"},
                        },
                        "required": ["name", "title"],
                    },
                },
                "company_email_domain": {"type": "string"},
                "company_email_pattern": {"type": "string"},
            },
            "required": ["contacts"],
        },
    },
}


async def find_contacts(
    company_name: str,
    company_industry: str,
    company_region: str,
    company_website: str,
    api_key: str,
) -> list[dict]:
    """Four-pass contact search:
    1) LinkedIn/XING/theorg.com for org charts and profiles
    2) Company website + press releases + regulatory filings
    3) Google/general web search for compliance contacts
    4) Email pattern derivation for contacts without emails
    
    Note: Pass 2 no longer searches paywalled directories (ZoomInfo, Apollo, Lusha)
    because Perplexity cannot extract data from behind paywalls — it returns
    masked emails (m***@db.com) or hallucinated data.
    """
    location = _eu_location(company_region)

    # Extract company domain for email derivation later
    company_domain = ""
    if company_website:
        company_domain = company_website.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]

    # ─── Pass 1: Professional networks (LinkedIn, XING, theorg) ───
    system1 = """You are a B2B research assistant. Search professional networks to find compliance, legal, regulatory, and risk management professionals.
Return a JSON object with a "contacts" array, plus "company_email_domain" and "company_email_pattern" if found.
Each contact object: name, title, email (empty string if not found), linkedInURL, phone, source, seniority_level.
- seniority_level: "C-Level", "VP", "Director", "Manager", "Other"
CRITICAL: 
- Return ONLY real people you can verify from LinkedIn/XING profiles.
- Do NOT invent names or titles. If you can't find someone, return fewer contacts.
- Email addresses must be REAL and COMPLETE — no masked emails (no ***), no placeholder emails.
- If you don't have a verified email, leave it as empty string."""

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
Search LinkedIn profiles, XING profiles, theorg.com org charts for {company_name}.
Also identify the company email pattern if visible (e.g. firstname.lastname@domain.com).
Return JSON object with "contacts" array."""

    content1 = await _call_api(
        system1, user1, api_key,
        max_tokens=4000,
        model=MODEL_FAST,
        search_domain_filter=["linkedin.com", "xing.com", "theorg.com"],
        search_language_filter=["en", "de"],
        user_location=location,
        search_context_size="high",
        response_format=_CONTACT_JSON_SCHEMA,
    )
    raw1 = content1 if isinstance(content1, str) else content1.get("content", "")
    pass1 = []
    email_pattern = ""
    email_domain = company_domain
    try:
        parsed1 = json.loads(_clean_json(raw1))
        if isinstance(parsed1, dict):
            contacts_list = parsed1.get("contacts", [])
            pass1 = [{k: str(v) for k, v in item.items()} for item in contacts_list if isinstance(item, dict)]
            email_pattern = parsed1.get("company_email_pattern", "")
            found_domain = parsed1.get("company_email_domain", "")
            if found_domain and "." in found_domain:
                email_domain = found_domain
        elif isinstance(parsed1, list):
            pass1 = [{k: str(v) for k, v in item.items()} for item in parsed1 if isinstance(item, dict)]
    except (json.JSONDecodeError, Exception):
        pass1 = _parse_json_array(raw1)
    logger.info(f"[FindContacts] Pass 1 (networks): {len(pass1)} for {company_name}")

    # ─── Pass 2: Company website, press, regulatory filings ───────
    # (Replaces old Pass 2 which searched paywalled directories)
    system2 = """You are a research assistant. Search company websites, press releases, regulatory filings, annual reports, and conference speaker lists.
Return a JSON object with a "contacts" array. Each object: name, title, email, linkedInURL, phone, source, seniority_level.
Look at:
- Company team/about/leadership/impressum pages
- Press releases mentioning compliance or legal hires
- Regulatory filings (BaFin, FCA registrations)
- Annual reports and corporate governance sections
- Conference speaker lists from compliance events
CRITICAL: Only return REAL people. Do NOT hallucinate names or emails."""

    already_names = ", ".join(d.get("name", "") for d in pass1[:10])
    website_domains = [d for d in [company_domain, "bafin.de", "handelsregister.de", "companyhouse.gov.uk"] if d]
    user2 = f"""Find compliance, legal, and regulatory professionals at {company_name}.
Company website: {company_website}
Already found (avoid duplicates): {already_names}
Search the company website ({company_website}), especially team/about/impressum/leadership pages.
Search press releases about {company_name} compliance hires.
Search regulatory registrations and filings mentioning {company_name}.
Return JSON object with "contacts" array."""

    try:
        content2 = await _call_api(
            system2, user2, api_key,
            max_tokens=4000,
            model=MODEL_FAST,
            search_domain_filter=website_domains[:20],
            search_language_filter=["en", "de"],
            user_location=location,
            search_context_size="high",
            response_format=_CONTACT_JSON_SCHEMA,
        )
        raw2 = content2 if isinstance(content2, str) else content2.get("content", "")
        try:
            parsed2 = json.loads(_clean_json(raw2))
            if isinstance(parsed2, dict):
                pass2 = [{k: str(v) for k, v in item.items()} for item in parsed2.get("contacts", []) if isinstance(item, dict)]
                # Pick up email pattern/domain from pass 2 if not found in pass 1
                if not email_pattern and parsed2.get("company_email_pattern"):
                    email_pattern = parsed2["company_email_pattern"]
                if not email_domain and parsed2.get("company_email_domain"):
                    email_domain = parsed2["company_email_domain"]
            elif isinstance(parsed2, list):
                pass2 = [{k: str(v) for k, v in item.items()} for item in parsed2 if isinstance(item, dict)]
            else:
                pass2 = []
        except (json.JSONDecodeError, Exception):
            pass2 = _parse_json_array(raw2)
        logger.info(f"[FindContacts] Pass 2 (website/press): {len(pass2)} for {company_name}")
    except Exception:
        pass2 = []

    # ─── Pass 3: General web search ──────────────────────────────
    system3 = """You are a research assistant finding compliance professionals via general web search.
Return a JSON object with a "contacts" array. Each object: name, title, email, linkedInURL, phone, source, seniority_level.
Search Google for names, conference speaker lists, published articles, podcast appearances, panel discussions.
CRITICAL: Only return REAL people you can verify. No invented names or emails."""

    user3 = f"""Find compliance and regulatory professionals at {company_name} ({company_industry}).
Already found: {already_names}
Search for:
- "{company_name}" compliance officer OR "head of compliance" OR CCO
- Conference speakers from {company_name} at compliance/regulatory events
- Published articles by compliance professionals at {company_name}
Return JSON object with "contacts" array."""

    try:
        content3 = await _call_api(
            system3, user3, api_key,
            max_tokens=3000,
            model=MODEL_FAST,
            search_language_filter=["en", "de"],
            user_location=location,
            search_context_size="high",
            response_format=_CONTACT_JSON_SCHEMA,
        )
        raw3 = content3 if isinstance(content3, str) else content3.get("content", "")
        try:
            parsed3 = json.loads(_clean_json(raw3))
            if isinstance(parsed3, dict):
                pass3 = [{k: str(v) for k, v in item.items()} for item in parsed3.get("contacts", []) if isinstance(item, dict)]
            elif isinstance(parsed3, list):
                pass3 = [{k: str(v) for k, v in item.items()} for item in parsed3 if isinstance(item, dict)]
            else:
                pass3 = []
        except (json.JSONDecodeError, Exception):
            pass3 = _parse_json_array(raw3)
        logger.info(f"[FindContacts] Pass 3 (web search): {len(pass3)} for {company_name}")
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
                    email_candidate = _clean_email(c.get("email", ""))
                    if not existing["email"] and email_candidate:
                        existing["email"] = email_candidate
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

    # ─── Pass 4: Email pattern derivation for contacts without email ─
    if email_domain:
        for lead in leads:
            if not lead["email"]:
                candidates = _derive_email_from_pattern(lead["name"], email_domain, email_pattern)
                if candidates:
                    # Use the most likely pattern as the email (will be verified later)
                    lead["email"] = candidates[0]
                    lead["source"] = f"{lead['source']} + Pattern-derived ({email_domain})"
                    logger.info(f"[FindContacts] Derived email for {lead['name']}: {candidates[0]}")

    logger.info(f"[FindContacts] Total deduplicated: {len(leads)} for {company_name}")
    return leads


# ─── 3) Verify Email — STRICT multi-source verification ─────────

# JSON Schema for structured verification output
_VERIFY_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "email_verification",
        "schema": {
            "type": "object",
            "properties": {
                "emails": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "email": {"type": "string"},
                            "source": {"type": "string"},
                            "confidence": {"type": "string"},
                        },
                        "required": ["email", "source", "confidence"],
                    },
                },
                "company_email_pattern": {"type": "string"},
                "company_domain": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["emails"],
        },
    },
}

_CROSSVERIFY_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "email_crossverification",
        "schema": {
            "type": "object",
            "properties": {
                "best_email": {"type": "string"},
                "verified": {"type": "boolean"},
                "confidence": {"type": "string"},
                "reasoning": {"type": "string"},
                "alternative_emails": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "verification_sources": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["best_email", "verified", "confidence", "reasoning"],
        },
    },
}


async def verify_email(
    lead_name: str,
    lead_title: str,
    lead_company: str,
    lead_email: str,
    lead_linkedin: str,
    api_key: str,
) -> dict:
    """STRICT three-pass verification with higher bar for 'verified':
    1) Professional networks + company website (NOT paywalled directories)
    2) General web search for email mentions
    3) Cross-verification with reasoning model

    VERIFICATION CRITERIA (stricter than before):
    - verified=True requires: high confidence from reasoning model
      OR same email confirmed by 2+ independent sources
    - Single medium-confidence source is NOT sufficient for verified=True
    - Pattern-derived emails without independent confirmation = NOT verified
    
    Returns {email, verified, notes}.
    """
    all_emails: list[dict] = []
    all_notes: list[str] = []

    # Extract company domain
    company_domain = ""
    if lead_email and "@" in lead_email:
        company_domain = lead_email.split("@")[1]

    # ─── Pass 1: Professional networks + company website ─────────
    system1 = """You are an expert at finding verified business email addresses.
Search LinkedIn profiles (contact info sections), XING profiles, company websites (impressum, team, about pages), and public directories.
Return a JSON object with:
- emails: [{email, source, confidence}] where confidence = "high"/"medium"/"low"
  - "high" = email directly visible on official source (LinkedIn profile, company website, regulatory filing)
  - "medium" = email mentioned on a third-party site or in a press release
  - "low" = email inferred or from an unreliable source
- company_email_pattern: naming convention (e.g. "firstname.lastname@domain.com")
- company_domain: the company's primary email domain
- notes: additional context

CRITICAL:
- Return ONLY complete, unmasked email addresses.
- Do NOT return masked emails like m***@domain.com or j...@domain.com.
- Do NOT invent or guess email addresses. Only return emails you actually found.
- If you cannot find a verified email, return an empty emails array."""

    user1 = f"""Find the business email for:
Name: {lead_name}
Title: {lead_title}
Company: {lead_company}
Known email (may be wrong): {lead_email}
LinkedIn: {lead_linkedin}
Search their LinkedIn profile contact section, XING profile, company website impressum/team pages.
Also determine the company email pattern by looking at other employees' public emails.
Return JSON object."""

    try:
        content1 = await _call_api(
            system1, user1, api_key,
            max_tokens=4000,
            model=MODEL_FAST,
            search_domain_filter=["linkedin.com", "xing.com"],
            search_language_filter=["en", "de"],
            search_context_size="high",
            response_format=_VERIFY_JSON_SCHEMA,
        )
        raw1 = content1 if isinstance(content1, str) else content1.get("content", "")
        cleaned = _clean_json(raw1)
        data = json.loads(cleaned)
        if isinstance(data, dict):
            for e in data.get("emails", []):
                addr = _clean_email(e.get("email", ""))
                if addr:
                    all_emails.append({
                        "email": addr,
                        "source": e.get("source", "LinkedIn/XING"),
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
                all_notes.append(str(notes) if not isinstance(notes, list) else "; ".join(str(n) for n in notes))
    except Exception as ex:
        all_notes.append(f"Pass 1 (networks): {ex}")

    # ─── Pass 2: Company website + general web search ─────────────
    system2 = """You are a research assistant finding email addresses from company websites and public web sources.
Search company websites (impressum, contact, team pages), press releases, regulatory filings, conference speaker lists, published articles.
Return a JSON object with:
- emails: [{email, source, confidence}]
- company_email_pattern: if discoverable
- notes: context
CRITICAL: Only return REAL, COMPLETE email addresses. No masked or guessed emails."""

    # Build targeted search domains
    search_domains = []
    if company_domain:
        search_domains.append(company_domain)
    search_domains.extend(["bafin.de", "handelsregister.de"])

    user2 = f"""Find email address for {lead_name}, {lead_title} at {lead_company}.
LinkedIn: {lead_linkedin}
Company domain: {company_domain}
Search the company website for contact/team/impressum pages.
Search Google for "{lead_name}" "{lead_company}" email.
Search press releases and conference speaker lists.
Return JSON object."""

    try:
        content2 = await _call_api(
            system2, user2, api_key,
            max_tokens=3000,
            model=MODEL_FAST,
            search_domain_filter=search_domains[:20] if search_domains else None,
            search_language_filter=["en", "de"],
            search_context_size="high",
            response_format=_VERIFY_JSON_SCHEMA,
        )
        raw2 = content2 if isinstance(content2, str) else content2.get("content", "")
        cleaned2 = _clean_json(raw2)
        data2 = json.loads(cleaned2)
        if isinstance(data2, dict):
            for e in data2.get("emails", []):
                addr = _clean_email(e.get("email", ""))
                if addr and not any(ex["email"] == addr for ex in all_emails):
                    all_emails.append({
                        "email": addr,
                        "source": e.get("source", "Company website"),
                        "confidence": e.get("confidence", "medium"),
                    })
            if not company_domain and data2.get("company_domain"):
                company_domain = data2["company_domain"]
    except Exception as ex:
        all_notes.append(f"Pass 2 (website/web): {ex}")

    # ─── Derive pattern-based emails if we have a domain but no email yet ──
    if company_domain and not all_emails:
        pattern_str = " | ".join(n for n in all_notes if "Pattern:" in n)
        derived = _derive_email_from_pattern(lead_name, company_domain, pattern_str)
        for d_email in derived[:3]:
            all_emails.append({
                "email": d_email,
                "source": "Pattern-derived",
                "confidence": "low",  # Pattern-derived = always low until confirmed
            })
        if derived:
            all_notes.append(f"Pattern-derived {len(derived)} candidates from {company_domain}")

    # Also derive if we only have low-confidence emails
    if company_domain and all(e.get("confidence") == "low" for e in all_emails):
        derived = _derive_email_from_pattern(lead_name, company_domain)
        for d_email in derived[:2]:
            if not any(ex["email"] == d_email for ex in all_emails):
                all_emails.append({
                    "email": d_email,
                    "source": "Pattern-derived",
                    "confidence": "low",
                })

    # ─── Pass 3: Cross-verification with REASONING model ──────────
    system3 = """You are an email verification specialist with deep analytical capabilities.
Given a person, candidate emails, and company email patterns, determine the most likely correct email.
Analyze:
1. Does the email follow the company's naming pattern?
2. Is the domain correct for this company?
3. Cross-reference with multiple sources
4. Check for common patterns (firstname.lastname, f.lastname, first.last, etc.)
5. Is this a real person at this company? (verify on LinkedIn/web)

CRITICAL VERIFICATION RULES:
- verified=true ONLY if you have STRONG evidence: email found on an official source (LinkedIn, company website, regulatory filing) OR confirmed by 2+ independent sources.
- verified=false if: email is only pattern-derived, only from one medium-confidence source, or cannot be independently confirmed.
- Do NOT mark pattern-guessed emails as verified.
- If the person doesn't seem to work at this company, set verified=false.

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
Known patterns/notes: {pattern_str}

IMPORTANT: Only mark as verified=true if you have strong independent confirmation.
A pattern-derived email without independent verification is NOT verified.
Analyze all candidates carefully. Return JSON."""

    try:
        content3 = await _call_api(
            system3, user3, api_key,
            max_tokens=3000,
            model=MODEL_REASONING,
            search_context_size="high",
            search_language_filter=["en", "de"],
            response_format=_CROSSVERIFY_JSON_SCHEMA,
        )
        raw3 = content3 if isinstance(content3, str) else content3.get("content", "")
        cleaned3 = _clean_json(raw3)
        data3 = json.loads(cleaned3)
        if isinstance(data3, dict):
            best = _clean_email(data3.get("best_email", ""))
            if best:
                conf = data3.get("confidence", "medium")
                verified = data3.get("verified", False)
                # Only trust "high" confidence from reasoning model
                effective_confidence = "high" if (verified and conf in ("high",)) else conf
                all_emails.insert(0, {
                    "email": best,
                    "source": "Cross-verification (Reasoning)",
                    "confidence": effective_confidence,
                })
            for alt in data3.get("alternative_emails", []):
                c = _clean_email(alt if isinstance(alt, str) else "")
                if c and not any(e["email"] == c for e in all_emails):
                    all_emails.append({"email": c, "source": "Alternative", "confidence": "low"})
            reasoning = data3.get("reasoning", "")
            if reasoning:
                reasoning_str = str(reasoning) if not isinstance(reasoning, list) else "; ".join(str(r) for r in reasoning)
                all_notes.append(f"Reasoning: {reasoning_str[:300]}")
    except Exception as ex:
        all_notes.append(f"Pass 3 (reasoning): {ex}")

    # ─── Pick best email with STRICT verification ────────────────
    email_counts: dict[str, int] = {}
    for e in all_emails:
        email_counts[e["email"]] = email_counts.get(e["email"], 0) + 1

    # Count independent high/medium sources per email
    email_source_quality: dict[str, dict] = {}
    for e in all_emails:
        addr = e["email"]
        if addr not in email_source_quality:
            email_source_quality[addr] = {"high": 0, "medium": 0, "low": 0}
        conf = e.get("confidence", "low")
        if conf in email_source_quality[addr]:
            email_source_quality[addr][conf] += 1

    best_entry = (
        next((e for e in all_emails if e["confidence"] == "high"), None)
        or next((e for e in all_emails if e["confidence"] == "medium" and email_counts.get(e["email"], 0) >= 2), None)
        or next((e for e in all_emails if e["confidence"] == "medium"), None)
        or (all_emails[0] if all_emails else None)
    )

    final_email = best_entry["email"] if best_entry else lead_email

    # STRICT verification logic:
    # Verified ONLY if:
    # 1) At least one HIGH confidence source, OR
    # 2) Same email from 2+ independent sources (at least medium confidence), OR
    # 3) Reasoning model explicitly confirmed with high confidence
    # NOT verified if:
    # - Only pattern-derived (low confidence)
    # - Only one medium-confidence source
    is_verified = False
    if best_entry:
        addr = best_entry["email"]
        quality = email_source_quality.get(addr, {"high": 0, "medium": 0, "low": 0})
        
        if quality["high"] >= 1:
            is_verified = True  # At least one high-confidence source
        elif quality["medium"] >= 2:
            is_verified = True  # Two+ medium-confidence independent sources
        elif quality["medium"] >= 1 and email_counts.get(addr, 0) >= 2:
            is_verified = True  # Medium confidence + found in multiple passes
        # Single medium or any number of low = NOT verified

    notes_parts = []
    if best_entry:
        notes_parts.append(f"Best: {best_entry['email']} ({best_entry['source']}, {best_entry['confidence']})")
    else:
        notes_parts.append("No email found")
    notes_parts.append(f"Candidates: {len(all_emails)}, Sources: {len(set(e['source'] for e in all_emails))}")
    notes_parts.extend(str(n) for n in all_notes[:5])
    notes_str = " | ".join(str(p) for p in notes_parts)[:500]

    final = _clean_email(final_email or lead_email)
    return {"email": final, "verified": is_verified, "notes": notes_str}


# ─── 4) Research Challenges — DEEP multi-source ─────────────────

async def research_challenges(company_name: str, company_industry: str, api_key: str) -> str:
    """Use sonar-reasoning-pro to deeply analyze a company's regulatory challenges.
    Pulls from regulatory bodies, news, annual reports, and industry analysis."""

    system = f"""Du bist ein Regulatory-Compliance-Experte mit tiefem Wissen über EU-Regulierung.
Recherchiere KONKRETE, AKTUELLE regulatorische Herausforderungen für {company_name}.

KRITISCHE REGELN:
- Recherchiere NUR über {company_name} selbst — keine anderen Unternehmen.
- Nenne NUR Regulierungen, die TATSÄCHLICH für {company_name} in der Branche {company_industry} gelten.
- Nutze ECHTE, VERIFIZIERBARE Fakten: konkrete Fristen, Bußgelder, Artikelnummern, aktuelle Fälle.
- KEINE erfundenen Referenzen, Konferenzen, Artikel oder Events.
- Wenn du etwas nicht sicher weißt, lass es weg statt es zu erfinden.
- Antworte auf Englisch.

Struktur deiner Antwort:
1. Welche EU/nationale Regulierungen gelten DIREKT für {company_name}? (z.B. DORA, NIS2, GDPR, CSRD, EU AI Act, MiCA, PSD2, AML6)
2. Nächste konkrete Compliance-Fristen für {company_name}
3. Aktuelle Bußgelder oder Enforcement-Aktionen in deren Sektor
4. Typische Compliance-Lücken für Unternehmen wie {company_name}"""

    user = f"""Recherchiere die wichtigsten regulatorischen Compliance-Herausforderungen für {company_name} (Branche: {company_industry}).

Ich brauche SPEZIFISCHE, VERIFIZIERBARE Informationen über dieses Unternehmen:
- Welche konkreten EU-Regulierungen betreffen {company_name}?
- Welche Fristen stehen an?
- Gab es kürzlich Bußgelder oder behördliche Maßnahmen in deren Sektor?
- Welche Compliance-Lücken sind typisch für Unternehmen dieser Art?

Suche bei Regulierungsbehörden (BaFin, EBA, ESMA, FCA), aktuellen Nachrichten, Compliance-Berichten.
Nenne konkrete Daten, Beträge und Regulierungsartikel. Antworte auf Englisch.

WICHTIG: Erfinde NICHTS. Nur verifizierbare Fakten."""

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
        # Fallback: if Perplexity couldn't find company-specific info
        if _is_unknown_company(content):
            return _generic_compliance_challenges(company_name, company_industry)
        return content
    if isinstance(result, str) and _is_unknown_company(result):
        return _generic_compliance_challenges(company_name, company_industry)
    return result


def _is_unknown_company(content: str) -> bool:
    """Detect when Perplexity couldn't find useful information about a company."""
    lower = content.lower()
    indicators = [
        "nicht bekannt",
        "not known",
        "no information",
        "keine informationen",
        "could not find",
        "unable to find",
        "no results",
        "i could not",
        "i couldn't",
        "no specific",
        "not publicly available",
        "nicht öffentlich",
        "business model is unclear",
        "geschäftsmodell",
        "does not appear to be",
        "no publicly available",
    ]
    hit_count = sum(1 for ind in indicators if ind in lower)
    # If content is very short or has multiple unknown indicators, treat as unknown
    return hit_count >= 2 or (len(content.strip()) < 100 and hit_count >= 1)


def _generic_compliance_challenges(company_name: str, company_industry: str) -> str:
    """Return generic EU compliance challenges when company-specific info is unavailable."""
    industry_hint = f" in the {company_industry} sector" if company_industry else ""
    return f"""Generic EU Regulatory Compliance Challenges for {company_name}{industry_hint}:

1. GDPR (General Data Protection Regulation): All EU-based companies must ensure lawful data processing, maintain Records of Processing Activities (ROPA), respond to Data Subject Access Requests (DSARs) within 30 days, and report data breaches to supervisory authorities within 72 hours. Non-compliance fines up to EUR 20M or 4% of global annual turnover.

2. NIS2 Directive (Network and Information Security): Effective October 2024, NIS2 significantly expands the scope of cybersecurity obligations across the EU. Companies must implement risk management measures, supply chain security assessments, and incident reporting within 24 hours. Fines up to EUR 10M or 2% of global turnover.

3. CSRD (Corporate Sustainability Reporting Directive): Phased implementation 2024-2026 requires detailed ESG reporting aligned with European Sustainability Reporting Standards (ESRS). Mandatory double materiality assessments and third-party assurance.

4. EU AI Act: Effective August 2024 with phased compliance deadlines through 2026. Requires risk classification of AI systems, transparency obligations, and conformity assessments for high-risk AI. Fines up to EUR 35M or 7% of global turnover.

5. AML/CFT Regulations: The EU Anti-Money Laundering Authority (AMLA) starts operations in 2025. Enhanced due diligence requirements, beneficial ownership transparency, and cross-border cooperation obligations.

Key Compliance Deadlines:
- NIS2 transposition: October 2024 (enforcement ongoing)
- CSRD first reports: FY2024 for large PIEs, FY2025 for large companies
- EU AI Act prohibited practices: February 2025
- EU AI Act high-risk obligations: August 2026

These regulations create significant operational complexity, requiring continuous monitoring of regulatory changes, gap analyses, and cross-departmental coordination."""


# ─── 5) Draft Email — REASONING model for deep personalization ──

async def draft_email(
    lead_name: str,
    lead_title: str,
    lead_company: str,
    challenges: str,
    sender_name: str,
    api_key: str,
) -> dict:
    """Use sonar-pro for clear, company-specific outreach emails.
    Returns {subject, body}."""

    # Trim challenges to avoid token overflow — keep essential info
    challenges_trimmed = challenges[:2000] if challenges else "No specific challenges researched."

    system = f"""Du schreibst professionelle B2B-Outreach-E-Mails für Harpocrates Corp / comply.reg.

KRITISCHE REGELN:
1. Schreibe die E-Mail auf ENGLISCH.
2. Der Betreff MUSS den Firmennamen "{lead_company}" enthalten und sich auf eine KONKRETE Regulierung beziehen, die für {lead_company} relevant ist (z.B. DORA, NIS2, CSRD, GDPR).
3. Die E-Mail muss KLAR und VERSTÄNDLICH sein — ein Compliance-Manager muss sofort verstehen, worum es geht.
4. KEINE erfundenen Referenzen: Keine erfundenen Artikel, Konferenzen, Reports, Zitate oder Events. Wenn du etwas nicht verifizieren kannst, erwähne es NICHT.
5. KEINE Marketing-Phrasen wie "caught in the exact squeeze", "pulling real-time regulatory updates", oder ähnlichen Jargon.
6. STRUKTUR der E-Mail:
   - Zeile 1-2: Konkret sagen, WARUM du dich an diese Person wendest (welche Regulierung betrifft {lead_company})
   - Zeile 3-5: Wie comply.reg KONKRET bei diesem spezifischen Problem hilft
   - Letzte Zeile: Höfliche Frage nach einem kurzen Gespräch (15 Min)
7. Maximal 120 Wörter. Jeder Satz muss einen klaren Zweck haben.
8. Absender: {sender_name}, Harpocrates Corp
9. KEINE Signatur oder Footer — wird automatisch hinzugefügt.
10. Die E-Mail muss KOMPLETT sein — nicht abschneiden.

ÜBER COMPLY.REG:
comply.reg ist eine RegTech-SaaS-Plattform für automatisiertes Compliance-Monitoring:
- Automatische Erkennung regulatorischer Änderungen (DORA, NIS2, GDPR, CSRD, EU AI Act, MiCA, AML)
- Echtzeit-Überwachung von Compliance-Anforderungen
- Automatische Gap-Analyse und Risikobewertung
- Zentrale Verwaltung aller Compliance-Pflichten

Return ONLY valid JSON: {{"subject": "...", "body": "..."}}"""

    user = f"""Schreibe eine Outreach-E-Mail von {sender_name} (Harpocrates Corp) an:
Name: {lead_name}
Position: {lead_title}
Unternehmen: {lead_company}

RECHERCHIERTE REGULATORISCHE HERAUSFORDERUNGEN FÜR {lead_company}:
{challenges_trimmed}

ANWEISUNGEN:
- Der Betreff MUSS "{lead_company}" enthalten
- Beziehe dich auf 1-2 KONKRETE Regulierungen, die {lead_company} betreffen
- Erkläre klar, wie comply.reg bei genau diesem Problem hilft
- Maximal 120 Wörter
- E-Mail muss KOMPLETT sein (vollständiger Text, nicht abgeschnitten)
- KEINE erfundenen Events, Artikel oder Konferenzen
- Schreibe auf Englisch

Return ONLY valid JSON: {{"subject": "...", "body": "..."}}"""

    content = await _call_api(
        system, user, api_key,
        max_tokens=3000,
        model=MODEL_FAST,
        search_context_size="low",
    )
    raw = content if isinstance(content, str) else content.get("content", "")
    cleaned = _clean_json(raw)
    try:
        data = json.loads(cleaned)
        raw_body = data.get("body", "")
        raw_subject = data.get("subject", "")
        if not raw_body:
            raw_body = raw
        if not raw_subject:
            raw_subject = f"Regulatory Compliance for {lead_company}"
        # Ensure subject contains company name
        if lead_company.lower() not in raw_subject.lower():
            raw_subject = f"{raw_subject} — {lead_company}"
        return {
            "subject": _strip_citations(raw_subject),
            "body": _strip_citations(raw_body),
        }
    except json.JSONDecodeError:
        return {
            "subject": f"Regulatory Compliance for {lead_company}",
            "body": _strip_citations(raw),
        }


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
    """Generate social posts with real citations from regulatory sources.
    
    Key design decisions:
    - Output is PLAIN TEXT for LinkedIn (no markdown, no [text](url) links)
    - Sources come ONLY from Perplexity API citations (not LLM-generated URLs)
    - COMPLY is referenced as Harpocrates' own product (not a third-party tool)
    - All URLs in the post are plain text (LinkedIn renders them as clickable)
    """
    dupe_context = ""
    if existing_posts_preview:
        titles = "\n- ".join(existing_posts_preview[:10])
        dupe_context = f"\n\nALREADY POSTED (DO NOT REPEAT):\n- {titles}"

    system = f"""You are a social media expert writing LinkedIn posts for Harpocrates Solutions GmbH.

ABOUT HARPOCRATES:
Harpocrates Solutions is a Berlin-based RegTech company. Their product COMPLY is a SaaS platform for automated compliance monitoring, regulatory change management, and risk assessment. COMPLY.Reg is the core module for regulatory obligation tracking. This is HARPOCRATES' OWN PRODUCT — reference it as "our COMPLY platform" or "COMPLY.Reg", never as a third-party tool.

CRITICAL FORMAT RULES (LinkedIn is PLAIN TEXT, not Markdown):
1. NO MARKDOWN whatsoever. No **bold**, no *italic*, no [text](url) links.
2. URLs must be written as plain text: https://example.com (LinkedIn auto-links them)
3. Use CAPS or UPPER CASE for emphasis instead of markdown bold.
4. Use bullet points with • or — characters, not markdown lists.
5. Line breaks for readability. Short paragraphs (2-3 sentences max).

CONTENT RULES:
1. LANGUAGE: English with correct capitalisation.
2. GEOGRAPHIC FOCUS: Europe only (EU, EEA, UK, Switzerland). No US/SEC references.
3. CURRENCY: All amounts in EUR (€).
4. FACTS: 1-2 concrete numbers with INLINE source attribution (e.g. "According to ESMA's March 2026 report"). No unsourced claims.
5. NO HALLUCINATIONS: Only verifiable facts. Do NOT invent URLs, reports, or statistics.
6. DO NOT generate source URLs yourself. Leave [1], [2] citation markers — they will be resolved to real URLs from search results.
7. COMPLY MENTION: Reference COMPLY naturally as "our platform" or "At Harpocrates, our COMPLY.Reg module...". It is YOUR product.
8. NO DUPLICATE topics — check the ALREADY POSTED list.
9. FOOTER: Do NOT include any footer, website, email, or timestamp. These are added automatically.
10. NO HASHTAGS in the content body. Return them separately in the JSON.

Return JSON: {{"content": "...", "hashtags": [...]}}"""

    industry_context = ", ".join(industries) if industries else "Financial Services, RegTech, Compliance"

    user = f"""Write a LinkedIn post for Harpocrates Solutions.
Topic: {topic} - {topic_prefix} {industry_context}

REQUIREMENTS:
- PLAIN TEXT only (no markdown, no bold syntax, no [link](url) format)
- Europe-focused (EU, EEA, UK, Switzerland)
- All amounts in EUR (€)
- Strong hook in line 1
- 1-2 verified statistics with source attribution in the text
- Reference relevant EU regulation (DORA, NIS2, GDPR, MiCA, EU AI Act, CSRD, PSD3, AMLD, EMIR, EBA Guidelines)
- Mention COMPLY or COMPLY.Reg as Harpocrates' own solution (not a third-party recommendation)
- Closing question or CTA
- 150-250 words
- Leave [1], [2] citation markers — do NOT write URLs yourself{dupe_context}
Hashtags: 5-7 from: #DORA #NIS2 #GDPR #RegTech #Compliance #FinTech #RegulatoryCompliance #COMPLY #RiskManagement #AML #BaFin #EBA #ESMA #ECB #CSRD #EUAIAct #Harpocrates
Return ONLY valid JSON with content and hashtags."""

    content = await _call_api(
        system, user, api_key,
        max_tokens=3000,
        model=MODEL_REASONING,
        search_recency_filter="week",
        search_domain_filter=DOMAINS_REGULATORY + ["ft.com", "reuters.com", "ecb.europa.eu", "eba.europa.eu", "esma.europa.eu", "european-commission.europa.eu"],
        search_language_filter=["en", "de", "fr"],
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

        # Resolve [1], [2] citation markers to actual URLs from Perplexity
        full = _resolve_citations(raw_content, citations)
        full = strip_trailing_hashtags(full)

        # Strip any markdown formatting that slipped through
        full = _strip_markdown(full)

        # Build sources section ONLY from real Perplexity citations
        # (never from LLM-generated URLs which are often hallucinated)
        source_entries = []
        if citations:
            seen_domains = set()
            for url in citations[:8]:
                try:
                    from urllib.parse import urlparse
                    domain = urlparse(url).hostname or ""
                    domain = domain.replace("www.", "")
                except Exception:
                    domain = url
                if domain not in seen_domains:
                    seen_domains.add(domain)
                    source_entries.append(url)
        if source_entries:
            full += "\n\nQuellen:\n" + "\n".join(f"• {url}" for url in source_entries[:5])

        if hashtag_line:
            full += "\n\n" + hashtag_line
        full = ensure_footer(full)
        return {"content": full, "hashtags": hashtags}
    except json.JSONDecodeError:
        # Fallback: resolve citations and append
        fallback = _resolve_citations(raw, citations)
        fallback = _strip_markdown(fallback)
        if citations:
            fallback += "\n\nQuellen:\n" + "\n".join(f"• {url}" for url in citations[:5])
        return {"content": ensure_footer(fallback), "hashtags": []}


# ─── 7b) Cross-Check / Fact-Verify a Social Post ────────────────

async def cross_check_post(
    post_content: str,
    api_key: str,
) -> dict:
    """Multi-pass fact verification for a social media post.
    
    Runs 3 verification passes:
    1) CLAIM EXTRACTION + VERIFICATION — extracts factual claims, verifies each against sources
    2) URL REACHABILITY + RELEVANCE — checks every URL in the post
    3) ENTITY VERIFICATION — checks that mentioned products, organisations, regulations exist
    
    Returns a structured verification result with score and details.
    """
    import re as _re
    from datetime import datetime as _dt

    logger.info("[CrossCheck] Starting multi-pass verification")

    # ── Pass 1: Claim extraction + verification ──────────────────
    system_claims = """You are a meticulous fact-checker for regulatory and compliance content.
Your job: extract every FACTUAL CLAIM from the post, then verify each one.

A factual claim is any statement that can be true or false, e.g.:
- Dates ("On 5 March 2026, the ECB launched...")
- Numbers/statistics ("PSD2 compliance costs rose 40%")
- Deadlines ("selections by end of June 2026")
- Regulatory requirements ("PSPs must demonstrate PSD2, GDPR and AML compliance")
- Product/company references ("comply.reg helps PSPs map obligations")
- Cause-effect claims ("this represents a compliance acceleration")

For each claim:
1. Search for the ORIGINAL SOURCE (ECB, EBA, ESMA, EU Commission, etc.)
2. Compare the claim to what the source actually says
3. Rate: "verified" (matches source), "inaccurate" (partially wrong or overstated), "unverifiable" (no source found), "false" (contradicted by source)
4. Explain the difference if inaccurate

CRITICAL: Do NOT trust the post's own citations. Verify independently.
Return ONLY valid JSON."""

    user_claims = f"""Fact-check this LinkedIn post. Extract EVERY factual claim and verify each one.

POST CONTENT:
{post_content}

Return JSON:
{{
  "claims": [
    {{
      "claim": "the exact claim text from the post",
      "verdict": "verified|inaccurate|unverifiable|false",
      "source_url": "URL of the authoritative source used to verify (or empty)",
      "source_name": "e.g. ECB Press Release, EBA Guidelines",
      "details": "Explanation: what the source actually says vs what the post claims"
    }}
  ]
}}"""

    claims_result = []
    try:
        resp1 = await _call_api(
            system_claims, user_claims, api_key,
            max_tokens=4000,
            model=MODEL_REASONING,
            search_domain_filter=DOMAINS_REGULATORY + ["ft.com", "reuters.com", "handelsblatt.com"],
            search_recency_filter="month",
            search_language_filter=["en", "de"],
            user_location=_eu_location(),
            search_context_size="high",
            return_citations=True,
        )
        raw1 = resp1 if isinstance(resp1, str) else resp1.get("content", "")
        citations1 = resp1.get("citations", []) if isinstance(resp1, dict) else []
        parsed1 = json.loads(_clean_json(raw1))
        claims_result = parsed1.get("claims", [])
        # Enrich source_url from Perplexity citations if empty
        for i, claim in enumerate(claims_result):
            if not claim.get("source_url") and citations1:
                # Try to match by mentioned source name
                for cit_url in citations1:
                    sn = claim.get("source_name", "").lower()
                    if sn and any(part in cit_url.lower() for part in sn.split() if len(part) > 3):
                        claim["source_url"] = cit_url
                        break
        logger.info(f"[CrossCheck] Pass 1: {len(claims_result)} claims extracted")
    except Exception as e:
        logger.warning(f"[CrossCheck] Pass 1 failed: {e}")

    # ── Pass 2: URL reachability + relevance ──────────────────────
    urls_in_post = _re.findall(r'https?://[^\s)>"\]]+', post_content)
    urls_checked = []
    if urls_in_post:
        system_urls = """You are a URL verification assistant.
For each URL provided, determine:
1. Is this a real, reachable URL? (Check if the domain exists and the path is plausible)
2. Does the content at this URL support the context it's cited in?
3. Is the URL still current (not outdated, moved, or broken)?

Search for each URL or its content. If you can't access a URL directly, search for the page title or content.
Return ONLY valid JSON."""

        # Build context for each URL
        url_contexts = []
        for url in urls_in_post[:10]:  # max 10 URLs
            # Find surrounding text in the post
            idx = post_content.find(url)
            start = max(0, idx - 100)
            end = min(len(post_content), idx + len(url) + 100)
            ctx = post_content[start:end].replace(url, "[THIS URL]")
            url_contexts.append(f"URL: {url}\nContext: {ctx}")

        user_urls = f"""Verify these URLs from a LinkedIn post. For each, check if it's real, reachable, and relevant to its context.

{chr(10).join(url_contexts)}

Return JSON:
{{
  "urls": [
    {{
      "url": "the URL",
      "reachable": true/false,
      "relevant": true/false,
      "domain_exists": true/false,
      "details": "explanation"
    }}
  ]
}}"""

        try:
            resp2 = await _call_api(
                system_urls, user_urls, api_key,
                max_tokens=2000,
                model=MODEL_FAST,
                search_context_size="high",
                return_citations=False,
            )
            raw2 = resp2 if isinstance(resp2, str) else resp2.get("content", "")
            parsed2 = json.loads(_clean_json(raw2))
            urls_checked = parsed2.get("urls", [])
            logger.info(f"[CrossCheck] Pass 2: {len(urls_checked)} URLs checked")
        except Exception as e:
            logger.warning(f"[CrossCheck] Pass 2 failed: {e}")

    # ── Pass 3: Entity verification ──────────────────────────────
    system_entities = """You are an entity verification specialist for regulatory and fintech content.
Extract all NAMED ENTITIES from the post (products, companies, regulations, institutions, programmes) and verify each exists.

For each entity:
- Is it a REAL product/company/regulation/programme? (not hallucinated)
- If it's a product: does it actually do what the post claims?
- If it's a regulation: is the name/acronym correct?
- If it's a programme/initiative: does it actually exist with the described characteristics?

Return ONLY valid JSON."""

    user_entities = f"""Verify all named entities in this LinkedIn post:

{post_content}

Return JSON:
{{
  "entities": [
    {{
      "name": "entity name",
      "type": "product|company|regulation|institution|programme",
      "exists": true/false,
      "details": "verification notes — what you found or didn't find"
    }}
  ]
}}"""

    entities_result = []
    try:
        resp3 = await _call_api(
            system_entities, user_entities, api_key,
            max_tokens=2000,
            model=MODEL_FAST,
            search_context_size="high",
            search_language_filter=["en", "de"],
            return_citations=False,
        )
        raw3 = resp3 if isinstance(resp3, str) else resp3.get("content", "")
        parsed3 = json.loads(_clean_json(raw3))
        entities_result = parsed3.get("entities", [])
        logger.info(f"[CrossCheck] Pass 3: {len(entities_result)} entities checked")
    except Exception as e:
        logger.warning(f"[CrossCheck] Pass 3 failed: {e}")

    # ── Scoring ──────────────────────────────────────────────────
    total_checks = 0
    passed_checks = 0

    for c in claims_result:
        total_checks += 1
        v = c.get("verdict", "unverifiable").lower()
        if v == "verified":
            passed_checks += 1
        elif v == "inaccurate":
            passed_checks += 0.3  # partial credit

    for u in urls_checked:
        total_checks += 1
        if u.get("reachable") and u.get("relevant"):
            passed_checks += 1
        elif u.get("reachable") or u.get("domain_exists"):
            passed_checks += 0.3

    for e in entities_result:
        total_checks += 1
        if e.get("exists"):
            passed_checks += 1

    score = round(passed_checks / total_checks, 2) if total_checks > 0 else 0.0

    # Determine overall status
    has_false = any(c.get("verdict", "").lower() == "false" for c in claims_result)
    has_inaccurate = any(c.get("verdict", "").lower() == "inaccurate" for c in claims_result)
    has_fake_entity = any(not e.get("exists") for e in entities_result)
    has_broken_url = any(not u.get("reachable") for u in urls_checked)
    has_irrelevant_url = any(not u.get("relevant") and u.get("reachable") for u in urls_checked)

    issues = []
    if has_false:
        issues.append("Falsche Behauptungen gefunden")
    if has_inaccurate:
        issues.append("Ungenaue/übertriebene Aussagen")
    if has_fake_entity:
        issues.append("Nicht-existierende Entitäten referenziert")
    if has_broken_url:
        issues.append("Nicht erreichbare URLs")
    if has_irrelevant_url:
        issues.append("URLs ohne relevanten Inhalt")

    status = "verified" if not issues else "issues_found"

    # Build summary
    summary_parts = []
    verified_count = sum(1 for c in claims_result if c.get("verdict", "").lower() == "verified")
    summary_parts.append(f"{verified_count}/{len(claims_result)} Fakten verifiziert")
    reachable_count = sum(1 for u in urls_checked if u.get("reachable"))
    summary_parts.append(f"{reachable_count}/{len(urls_checked)} URLs erreichbar")
    existing_count = sum(1 for e in entities_result if e.get("exists"))
    summary_parts.append(f"{existing_count}/{len(entities_result)} Entitäten bestätigt")
    if issues:
        summary_parts.append(f"Probleme: {'; '.join(issues)}")

    result = {
        "claims": claims_result,
        "urls_checked": urls_checked,
        "entities": entities_result,
        "score": score,
        "status": status,
        "issues": issues,
        "summary": " | ".join(summary_parts),
        "checked_at": _dt.utcnow().isoformat(),
        "passes_completed": 3,
    }

    logger.info(f"[CrossCheck] Done: score={score}, status={status}, issues={len(issues)}")
    return result


# ─── 8) Generate Subject Alternatives ───────────────────────────

async def generate_subject_alternatives(
    company_name: str,
    company_industry: str,
    email_body_preview: str,
    api_key: str,
) -> list[str]:
    system = f"""Generiere genau 3 verschiedene E-Mail-Betreffzeilen für RegTech/Compliance-Outreach.
Jede Betreffzeile MUSS:
- Den Firmennamen "{company_name}" enthalten
- Sich auf eine KONKRETE Regulierung beziehen (DORA, NIS2, CSRD, GDPR, EU AI Act, etc.)
- Maximal 70 Zeichen lang sein
- Auf Englisch sein
- NICHT generisch oder spammig klingen
Return ONLY 3 lines. No numbering, no quotes, no explanation."""

    user = f"""Company: {company_name}
Industry: {company_industry}
Email context: {email_body_preview[:300]}
Generate 3 subject lines. Each MUST contain "{company_name}"."""

    content = await _call_api(
        system, user, api_key,
        max_tokens=200,
        model=MODEL_FAST,
        search_context_size="low",
    )
    raw = content if isinstance(content, str) else content.get("content", "")
    subjects = [
        line.strip().strip('"').strip("'").lstrip('0123456789.-) ')
        for line in raw.split("\n")
        if line.strip() and 5 < len(line.strip()) < 100
    ]
    # Ensure company name is in each subject
    filtered = []
    for s in subjects:
        if company_name.lower() in s.lower():
            filtered.append(s)
        else:
            filtered.append(f"{s} — {company_name}")
    return filtered[:3] or [f"Regulatory Compliance for {company_name}"]

