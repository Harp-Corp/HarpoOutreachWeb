# FallbackSearchService – Fallback when Perplexity API quota is exhausted
# Supports Brave Search API and Tavily as alternatives.
# Brave: free $5/month (~1000 requests). Register at https://api.search.brave.com
# Tavily: free 1000 requests/month. Register at https://tavily.com
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("harpo.fallback_search")

BRAVE_API_URL = "https://api.search.brave.com/res/v1/web/search"
TAVILY_API_URL = "https://api.tavily.com/search"


# ─── Low-level search providers ──────────────────────────────────

async def _brave_search(query: str, api_key: str, count: int = 10) -> list[dict]:
    """Execute a Brave web search and return normalized results."""
    headers = {
        "X-Subscription-Token": api_key,
        "Accept": "application/json",
    }
    params = {
        "q": query,
        "count": count,
        "search_lang": "en",
        "country": "DE",
        "text_decorations": False,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(BRAVE_API_URL, headers=headers, params=params)
        if resp.status_code != 200:
            logger.warning(f"[BraveSearch] HTTP {resp.status_code}: {resp.text[:200]}")
            return []
        data = resp.json()
        results = data.get("web", {}).get("results", [])
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "description": r.get("description", ""),
                "extra_snippets": r.get("extra_snippets", []),
            }
            for r in results
        ]


async def _tavily_search(query: str, api_key: str, count: int = 10) -> list[dict]:
    """Execute a Tavily search and return normalized results."""
    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": count,
        "search_depth": "basic",
        "include_answer": False,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(TAVILY_API_URL, json=payload)
        if resp.status_code != 200:
            logger.warning(f"[TavilySearch] HTTP {resp.status_code}: {resp.text[:200]}")
            return []
        data = resp.json()
        results = data.get("results", [])
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "description": r.get("content", ""),
                "extra_snippets": [],
            }
            for r in results
        ]


async def _fallback_search(
    query: str,
    brave_api_key: str = "",
    tavily_api_key: str = "",
    count: int = 10,
) -> list[dict]:
    """Try Brave first, then Tavily. Returns normalized search results."""
    if brave_api_key:
        try:
            results = await _brave_search(query, brave_api_key, count)
            if results:
                return results
        except Exception as ex:
            logger.warning(f"[FallbackSearch] Brave failed: {ex}")

    if tavily_api_key:
        try:
            results = await _tavily_search(query, tavily_api_key, count)
            if results:
                return results
        except Exception as ex:
            logger.warning(f"[FallbackSearch] Tavily failed: {ex}")

    return []


# ─── Extraction helpers ──────────────────────────────────────────

INDUSTRY_KEYWORDS = {
    "Banking & Financial Services": ["bank", "banking", "financial services", "kreditinstitut", "fintech"],
    "Insurance": ["insurance", "versicherung", "reinsurance", "rückversicherung"],
    "Technology": ["technology", "software", "IT services", "tech", "saas", "cloud"],
    "Automotive": ["automotive", "automobile", "fahrzeug", "car manufacturer", "zulieferer"],
    "Manufacturing": ["manufacturing", "industrial", "produktion", "maschinenbau"],
    "Energy": ["energy", "energie", "utilities", "strom", "renewables"],
    "Pharmaceuticals & Healthcare": ["pharmaceutical", "pharma", "healthcare", "gesundheit", "biotech"],
    "Telecommunications": ["telecom", "telecommunications", "telekommunikation"],
    "Chemicals": ["chemical", "chemie", "chemicals"],
    "Retail": ["retail", "einzelhandel", "e-commerce"],
    "Logistics": ["logistics", "logistik", "shipping", "transport"],
    "Real Estate": ["real estate", "immobilien"],
    "Consulting": ["consulting", "beratung", "advisory"],
    "Aerospace & Defense": ["aerospace", "defense", "defence", "rüstung", "luftfahrt"],
}

REGION_KEYWORDS = {
    "UK": ["united kingdom", "london", "british", "england"],
    "Nordics": ["sweden", "norway", "denmark", "finland", "stockholm", "oslo"],
    "Benelux": ["netherlands", "belgium", "luxembourg", "amsterdam", "brussels"],
    "France": ["france", "paris", "french"],
    "Iberia": ["spain", "portugal", "madrid", "barcelona"],
    "Italy": ["italy", "italian", "milan", "rome", "milano"],
    "DACH": ["germany", "austria", "switzerland", "deutschland", "münchen", "frankfurt", "berlin", "zürich", "wien"],
}

COUNTRY_KEYWORDS = {
    "DE": ["germany", "deutschland", "frankfurt", "münchen", "berlin", "hamburg", "düsseldorf"],
    "AT": ["austria", "österreich", "wien", "vienna"],
    "CH": ["switzerland", "schweiz", "zürich", "zurich", "geneva", "bern"],
    "GB": ["united kingdom", "london", "british", "england"],
    "FR": ["france", "paris"],
    "NL": ["netherlands", "amsterdam", "den haag"],
    "SE": ["sweden", "stockholm"],
    "NO": ["norway", "oslo"],
    "DK": ["denmark", "copenhagen"],
    "FI": ["finland", "helsinki"],
    "BE": ["belgium", "brussels", "brüssel"],
    "LU": ["luxembourg"],
    "ES": ["spain", "madrid", "barcelona"],
    "IT": ["italy", "milan", "rome", "milano"],
    "IE": ["ireland", "dublin"],
}


def _detect_from_text(text: str, keyword_map: dict, default: str) -> str:
    """Match text against keyword map, return the first match or default."""
    text_lower = text.lower()
    for key, keywords in keyword_map.items():
        if any(kw in text_lower for kw in keywords):
            return key
    return default


def _extract_employee_count(text: str) -> int:
    """Extract employee count from text using common patterns."""
    patterns = [
        r"(\d[\d,\.]+)\s*(?:employees|mitarbeiter|beschäftigte|staff|workers)",
        r"(?:employees|mitarbeiter|beschäftigte|staff)[:\s]*(\d[\d,\.]+)",
        r"(?:approximately|about|ca\.?|circa|over|mehr als)\s*(\d[\d,\.]+)\s*(?:employees|mitarbeiter)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            num_str = m.group(1).replace(",", "").replace(".", "")
            try:
                return int(num_str)
            except ValueError:
                pass
    return 0


def _size_label(employee_count: int) -> str:
    if employee_count > 10000:
        return "10,000+ employees"
    elif employee_count > 5000:
        return "5,001-10,000 employees"
    elif employee_count > 1000:
        return "1,001-5,000 employees"
    elif employee_count > 200:
        return "201-1,000 employees"
    elif employee_count > 0:
        return "1-200 employees"
    return "Unknown"


def _find_linkedin_url(results: list[dict]) -> str:
    for r in results:
        if "linkedin.com/company" in r.get("url", ""):
            return r["url"]
    return ""


def _find_website(company_name: str, results: list[dict]) -> str:
    skip_domains = {
        "linkedin.com", "crunchbase.com", "bloomberg.com", "wikipedia.org",
        "northdata.com", "dnb.com", "zoominfo.com", "apollo.io", "google.com",
        "reddit.com", "twitter.com", "x.com", "facebook.com", "youtube.com",
    }
    name_stem = re.sub(r"\s*(AG|SE|GmbH|Ltd|plc|SA|NV)\s*$", "", company_name, flags=re.IGNORECASE).strip().lower()
    name_parts = name_stem.split()[:2]

    for r in results:
        url = r.get("url", "")
        try:
            domain = urlparse(url).netloc.lower().replace("www.", "")
        except Exception:
            continue
        if any(skip in domain for skip in skip_domains):
            continue
        # Check if company name is in the domain
        if any(part in domain for part in name_parts if len(part) > 3):
            return url
    return ""


def _clean_official_name(company_name: str, results: list[dict]) -> str:
    """Try to find the official company name (with suffix like AG, SE, GmbH) from results."""
    suffixes = [" AG", " SE", " GmbH", " Ltd", " plc", " S.A.", " N.V.", " SA", " & Co. KG", " KGaA"]
    for r in results:
        title = r.get("title", "")
        for suffix in suffixes:
            idx = title.find(suffix)
            if idx > 0 and company_name.lower().split()[0] in title[:idx].lower():
                candidate = title[:idx + len(suffix)]
                # Remove leading junk from title
                for sep in [" - ", " | ", " – ", " : "]:
                    if sep in candidate:
                        parts = candidate.split(sep)
                        for p in parts:
                            if company_name.lower().split()[0] in p.lower():
                                candidate = p.strip()
                                break
                if 3 < len(candidate) < 60:
                    return candidate
    return company_name


def _best_description(company_name: str, results: list[dict]) -> str:
    """Pick the best description from search results."""
    name_part = company_name.lower().split()[0]
    best = ""
    for r in results:
        desc = r.get("description", "")
        if len(desc) > len(best) and name_part in desc.lower():
            best = desc
    return best[:500]


# ─── Public functions ────────────────────────────────────────────

async def search_single_company_brave(
    company_name: str,
    brave_api_key: str = "",
    tavily_api_key: str = "",
) -> dict | None:
    """Fallback: Search for a company using Brave/Tavily Search API."""
    logger.info(f"[FallbackSearch] Company search: {company_name}")

    queries = [
        f"{company_name} company headquarters employees industry Europe",
        f"{company_name} linkedin company page",
    ]

    all_results = []
    for q in queries:
        results = await _fallback_search(q, brave_api_key, tavily_api_key, count=5)
        all_results.extend(results)

    if not all_results:
        logger.warning(f"[FallbackSearch] No results for {company_name}")
        return None

    all_text = "\n".join(
        f"{r['title']}: {r['description']} {' '.join(r.get('extra_snippets', []))}"
        for r in all_results
    )

    employee_count = _extract_employee_count(all_text)
    official_name = _clean_official_name(company_name, all_results)

    data = {
        "name": official_name,
        "industry": _detect_from_text(all_text, INDUSTRY_KEYWORDS, ""),
        "region": _detect_from_text(all_text, REGION_KEYWORDS, "DACH"),
        "website": _find_website(company_name, all_results),
        "linkedInURL": _find_linkedin_url(all_results),
        "description": _best_description(company_name, all_results),
        "size": _size_label(employee_count),
        "country": _detect_from_text(all_text, COUNTRY_KEYWORDS, "DE"),
        "employees": employee_count,
        "employee_count": employee_count,
        "nace_code": "",
        "founded_year": "",
        "revenue_range": "",
        "key_regulations": "",
        "_source": "fallback_search",
    }

    logger.info(f"[FallbackSearch] Found: {data['name']} ({data['industry']}, {data['employees']} emp)")
    return data


async def find_contacts_brave(
    company_name: str,
    industry: str,
    website: str,
    brave_api_key: str = "",
    tavily_api_key: str = "",
) -> list[dict]:
    """Fallback: Find compliance/legal contacts using Brave/Tavily Search."""
    logger.info(f"[FallbackSearch] Contact search at {company_name}")

    queries = [
        f"{company_name} Chief Compliance Officer Head of Legal",
        f"{company_name} CISO Data Protection Officer DPO",
        f"{company_name} Head of Risk Management General Counsel",
    ]

    all_results = []
    for q in queries:
        results = await _fallback_search(q, brave_api_key, tavily_api_key, count=5)
        all_results.extend(results)

    contacts = []
    seen_names: set[str] = set()

    # Determine email domain from company website
    domain = ""
    if website:
        try:
            parsed = urlparse(website if "://" in website else f"https://{website}")
            domain = parsed.netloc.replace("www.", "")
        except Exception:
            pass

    # Extract names and titles from search results
    name_patterns = [
        r"([A-Z][a-zà-ÿ]+ (?:von |van |de |di |le )?[A-Z][a-zà-ÿ]+(?:-[A-Z][a-zà-ÿ]+)?)\s*[-–,]\s*((?:Chief|Head|Director|VP|Vice President|Senior|Managing|Global|Group)[^,\n]{5,60})",
        r"([A-Z][a-zà-ÿ]+ (?:von |van |de |di |le )?[A-Z][a-zà-ÿ]+(?:-[A-Z][a-zà-ÿ]+)?)\s+(?:is|als|as|serves as)\s+(?:the\s+)?((?:Chief|Head|Director|VP|Vice President|Senior|Managing|Global|Group)[^,\n]{5,60})",
    ]

    for r in all_results:
        text = f"{r['title']} {r['description']} {' '.join(r.get('extra_snippets', []))}"

        for pat in name_patterns:
            for m in re.finditer(pat, text):
                name = m.group(1).strip()
                title = m.group(2).strip().rstrip(".")

                if name in seen_names or len(name.split()) < 2:
                    continue
                seen_names.add(name)

                # Construct probable email
                email = ""
                if domain:
                    parts = name.lower().split()
                    email = f"{parts[0]}.{parts[-1]}@{domain}"

                linkedin_url = ""
                if "linkedin.com/in/" in r.get("url", ""):
                    linkedin_url = r["url"]

                contacts.append({
                    "name": name,
                    "title": title,
                    "email": email,
                    "linkedin_url": linkedin_url,
                    "source": f"Fallback Search ({r.get('url', 'web')[:80]})",
                })

    logger.info(f"[FallbackSearch] Found {len(contacts)} contacts at {company_name}")
    return contacts[:15]
