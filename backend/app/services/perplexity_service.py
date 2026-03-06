# PerplexityService – ported from Swift PerplexityService.swift
# All Perplexity API interactions: company search, contact search, email verify,
# challenge research, email drafting, social post generation.
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import httpx

logger = logging.getLogger("harpo.perplexity")

API_URL = "https://api.perplexity.ai/chat/completions"
MODEL = "sonar-pro"

COMPANY_FOOTER = "\n\n🔗 www.harpocrates-corp.com | 📧 info@harpocrates-corp.com"


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
) -> str:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "web_search_options": {"search_context_size": "high"},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    max_retries = 3
    last_error: Exception | None = None

    async with httpx.AsyncClient(timeout=60) as client:
        for attempt in range(1, max_retries + 1):
            try:
                resp = await client.post(API_URL, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
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
    if s.startswith("```json"):
        s = s[7:]
    elif s.startswith("```"):
        s = s[3:]
    if s.endswith("```"):
        s = s[:-3]
    s = s.strip()
    if s.startswith("[") or s.startswith("{"):
        return s
    # try to extract
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


# ─── 1) Find Companies ──────────────────────────────────────────

async def find_companies(industry_value: str, region_countries: str, api_key: str) -> list[dict]:
    system = """You are a B2B company research assistant. You MUST return EXACTLY 25 real companies as a JSON array.
Each object in the array MUST have these fields: name, industry, region, website, linkedInURL, description, size, country, employees.
CRITICAL RULES:
- Return ONLY a valid JSON array. No markdown, no explanation, no text before or after.
- You MUST return exactly 25 companies. Count them. Do NOT stop at 10 or 15.
- All companies must be REAL, currently operating companies.
- Include the full website URL (https://...) and LinkedIn company page URL.
- The "employees" field MUST be a realistic integer representing the approximate number of employees (e.g. 150, 3500, 85000). Research the actual company size. NEVER use 0.
- If you cannot find 25, return as many as possible but aim for 25."""

    user = f"""Find exactly 25 real {industry_value} companies in {region_countries}.
Requirements:
- Revenue > 50M EUR or equivalent
- 200+ employees
- Currently active and operating
- Include company website URL and LinkedIn company page URL
- Include approximate number of employees as integer in the "employees" field (e.g. 250, 4500, 120000). This is MANDATORY.
Return ALL 25 companies as a single JSON array. Do not truncate. Do not stop early. Count your results before returning - there must be 25 objects in the array.
Example format: [{{"name":"Example GmbH","industry":"...","region":"...","website":"https://...","linkedInURL":"https://...","description":"...","size":"large","country":"Germany","employees":2500}}]"""

    content = await _call_api(system, user, api_key, max_tokens=8000)
    raw = _parse_json_array(content)
    companies = []
    for d in raw:
        emp_raw = d.get("employees", "0")
        emp_cleaned = emp_raw.replace(",", "").replace(".", "").strip()
        try:
            emp = int(emp_cleaned)
        except ValueError:
            emp = 0
        companies.append({
            "name": d.get("name", "Unknown"),
            "industry": d.get("industry", industry_value),
            "region": d.get("region", ""),
            "website": d.get("website", ""),
            "linkedin_url": d.get("linkedInURL", ""),
            "description": d.get("description", ""),
            "size": d.get("size", ""),
            "country": d.get("country", ""),
            "employee_count": emp,
        })
    return companies


# ─── 2) Find Contacts ───────────────────────────────────────────

async def find_contacts(
    company_name: str,
    company_industry: str,
    company_region: str,
    company_website: str,
    api_key: str,
) -> list[dict]:
    system1 = """You are a B2B research assistant. Search ALL available sources to find compliance and regulatory professionals at a specific company.
Search these sources:
- LinkedIn profiles and company pages
- Company website (team, about, leadership, impressum pages)
- Business directories (Bloomberg, Reuters, Crunchbase, ZoomInfo, Apollo)
- Press releases and news articles
- Regulatory filings and registrations
- Conference speaker lists and industry events
- Professional associations and memberships
- XING profiles (for DACH region)
- Annual reports and corporate governance documents
- theorg.com organizational charts
Return a JSON array of objects. Each object must have these fields:
- name: Full name of the person
- title: Their job title
- email: Email if found, empty string if not
- linkedInURL: LinkedIn profile URL if found, empty string if not
- source: Where you found this person
IMPORTANT: Return ALL people you find. Include anyone in compliance, legal, regulatory, data protection, or risk management roles."""

    user1 = f"""Find compliance and regulatory professionals at {company_name} (Industry: {company_industry}, Region: {company_region}).
Company website: {company_website}
Search for people with roles like:
- Chief Compliance Officer (CCO)
- Head of Compliance
- Compliance Manager/Director
- VP/SVP Regulatory Affairs
- Data Protection Officer (DPO/DSB)
- General Counsel / Chief Legal Officer
- Head of Risk Management
- Head of Legal
- Geldwaeschebeauftragter (for financial services)
- Datenschutzbeauftragter
Search LinkedIn, {company_website}, theorg.com, business directories, press releases, XING, annual reports.
Return ALL people you find as JSON array."""

    content1 = await _call_api(system1, user1, api_key, max_tokens=4000)
    all_candidates = _parse_json_array(content1)

    # If fewer than 3 results, do a broader second pass
    if len(all_candidates) < 3:
        system2 = """You are a research assistant. Search the web for executives and senior managers at a specific company.
Return a JSON array with fields: name, title, email, linkedInURL, source.
Search LinkedIn, company websites, theorg.com, news, business directories, XING, and any other public source.
Return ALL people you find. Include email if available, empty string if not."""

        user2 = f"""Find senior managers and executives at {company_name} who work in compliance, legal, regulatory, risk, or data protection.
Also search for: Vorstand, Geschaeftsfuehrung, C-Level executives at {company_name}.
Website: {company_website}
Search broadly across LinkedIn, XING, theorg.com, {company_website}, Google, business registers.
Return JSON array with: name, title, email, linkedInURL, source."""

        try:
            content2 = await _call_api(system2, user2, api_key, max_tokens=4000)
            more = _parse_json_array(content2)
            existing_names = {_normalize_name(c.get("name", "")) for c in all_candidates}
            for candidate in more:
                n = candidate.get("name", "")
                if n and _normalize_name(n) not in existing_names:
                    all_candidates.append(candidate)
                    existing_names.add(_normalize_name(n))
        except Exception:
            pass

    # Deduplicate and clean
    leads = []
    seen_names: set[str] = set()
    for c in all_candidates:
        name = c.get("name", "")
        if not name or name == "Unknown" or len(name) < 3:
            continue
        norm = _normalize_name(name)
        if norm in seen_names:
            continue
        seen_names.add(norm)
        leads.append({
            "name": name,
            "title": c.get("title", ""),
            "company": company_name,
            "email": _clean_email(c.get("email", "")),
            "linkedin_url": c.get("linkedInURL", ""),
            "source": c.get("source", "Perplexity Search"),
        })
    return leads


# ─── 3) Verify Email ────────────────────────────────────────────

async def verify_email(
    lead_name: str,
    lead_title: str,
    lead_company: str,
    lead_email: str,
    lead_linkedin: str,
    api_key: str,
) -> dict:
    """Returns {email, verified, notes}."""
    all_emails: list[dict] = []
    all_notes: list[str] = []

    # Pass 1: exhaustive search
    system1 = """You are an expert at finding verified business email addresses from public sources.
Search EXHAUSTIVELY across ALL of these sources:
1. LinkedIn - profile page, contact info section
2. Company website - team page, about us, leadership, impressum, Kontakt
3. theorg.com - organizational charts
4. XING profiles (critical for DACH region)
5. Business directories: ZoomInfo, Apollo.io, Lusha, RocketReach, Hunter.io
6. Financial databases: Bloomberg, Reuters, Crunchbase
7. Press releases and news articles
8. Conference speaker listings
9. Regulatory filings (BaFin, SEC, Handelsregister)
10. Google search: "firstname lastname email company"
Return a JSON object with:
- emails: array of objects, each with {email, source, confidence} where confidence is "high", "medium", or "low"
- company_email_pattern: the naming pattern used at this company
- pattern_examples: array of other verified emails at the same company
- notes: string with additional context"""

    user1 = f"""Find the business email address for:
Name: {lead_name}
Title: {lead_title}
Company: {lead_company}
Current email (may be empty or wrong): {lead_email}
LinkedIn: {lead_linkedin}
Search ALL sources. Return JSON."""

    try:
        content1 = await _call_api(system1, user1, api_key, max_tokens=4000)
        cleaned = _clean_json(content1)
        data = json.loads(cleaned)
        if isinstance(data, dict):
            for e in data.get("emails", []):
                addr = e.get("email", "")
                if addr and "@" in addr:
                    all_emails.append({
                        "email": addr.lower().strip(),
                        "source": e.get("source", "Search"),
                        "confidence": e.get("confidence", "medium"),
                    })
            pattern = data.get("company_email_pattern", "")
            if pattern:
                all_notes.append(f"Pattern: {pattern}")
            notes = data.get("notes", "")
            if notes:
                all_notes.append(notes)
    except Exception as ex:
        all_notes.append(f"Pass 1: {ex}")

    # Pass 2: verification
    system2 = """You are an email verification specialist. Given a person and candidate emails, verify them.
Return JSON with: best_email, verified (boolean), confidence, verification_sources, alternative_emails, reasoning."""

    candidate_str = ", ".join([e["email"] for e in all_emails[:5]]) or "none found yet"
    user2 = f"""Verify the best email for: {lead_name}, {lead_title} at {lead_company}
LinkedIn: {lead_linkedin}
Candidate emails: {candidate_str}
Return verification result as JSON."""

    try:
        content2 = await _call_api(system2, user2, api_key, max_tokens=3000)
        cleaned2 = _clean_json(content2)
        data2 = json.loads(cleaned2)
        if isinstance(data2, dict):
            best = data2.get("best_email", "")
            if best and "@" in best:
                conf = data2.get("confidence", "medium")
                verified = data2.get("verified", False)
                all_emails.insert(0, {
                    "email": best.lower().strip(),
                    "source": "Cross-verification",
                    "confidence": "high" if verified else conf,
                })
            for alt in data2.get("alternative_emails", []):
                if alt and "@" in alt:
                    c = alt.lower().strip()
                    if not any(e["email"] == c for e in all_emails):
                        all_emails.append({"email": c, "source": "Alternative", "confidence": "low"})
            reasoning = data2.get("reasoning", "")
            if reasoning:
                all_notes.append(reasoning)
    except Exception as ex:
        all_notes.append(f"Pass 2: {ex}")

    # Pick best
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
        notes_parts.append(f"Best: {best_entry['email']} ({best_entry['source']}, {best_entry['confidence']} confidence)")
    else:
        notes_parts.append("No email found")
    notes_parts.append(f"Total candidates: {len(all_emails)}")
    notes_parts.extend(all_notes)
    notes_str = " | ".join(notes_parts)[:500]

    final = _clean_email(final_email or lead_email)
    return {"email": final, "verified": is_verified, "notes": notes_str}


# ─── 4) Research Challenges ──────────────────────────────────────

async def research_challenges(company_name: str, company_industry: str, api_key: str) -> str:
    system = "You research specific regulatory and compliance challenges. Return a concise summary of key challenges. ALWAYS respond in English."
    user = f"What are the top 3-5 regulatory compliance challenges for {company_name} in {company_industry}? Focus on current regulations, upcoming changes, and pain points. Respond in English."
    return await _call_api(system, user, api_key)


# ─── 5) Draft Email ──────────────────────────────────────────────

async def draft_email(
    lead_name: str,
    lead_title: str,
    lead_company: str,
    challenges: str,
    sender_name: str,
    api_key: str,
) -> dict:
    """Returns {subject, body}."""
    system = """You write professional B2B outreach emails. CRITICAL RULES:
1. ALWAYS write in English - no German, no other language.
2. Write a personalized, non-salesy email that provides genuine value.
3. Reference SPECIFIC challenges the recipient's company faces based on their industry.
4. Show you understand their role and responsibilities.
5. Keep it under 150 words, personal, value-focused. No hard sell.
6. The email must feel like it was written specifically for this person, not a template.
Return ONLY a valid JSON object with: subject, body"""

    user = f"""Write a cold outreach email from {sender_name} at Harpocrates Corp (RegTech company) to:
Name: {lead_name}, Title: {lead_title}, Company: {lead_company}
Their specific challenges: {challenges}
Our solution: comply.reg - Automated compliance monitoring, regulatory change tracking, risk assessment.

IMPORTANT:
- Write ENTIRELY in English
- Reference their specific regulatory challenges (e.g. DORA, NIS2, GDPR specifics)
- Make the subject line compelling and specific to their situation
- Include a soft CTA (e.g. brief call, sharing a relevant case study)
Return JSON with: subject, body"""

    content = await _call_api(system, user, api_key)
    cleaned = _clean_json(content)
    try:
        data = json.loads(cleaned)
        raw_body = data.get("body", content)
        return {
            "subject": data.get("subject", f"Compliance Solutions for {lead_company}"),
            "body": _strip_citations(raw_body),
        }
    except json.JSONDecodeError:
        return {"subject": "Compliance Solutions", "body": content}


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
    system = """You write professional follow-up emails for B2B outreach. CRITICAL RULES:
1. ALWAYS write in English - no German, no other language.
2. Based on previous emails and any replies, write a follow-up that:
   - References the previous conversation naturally
   - If there was a reply: acknowledge it and continue the dialogue
   - If there was no reply: add new value and a different angle
   - Keeps it under 150 words, professional, value-focused
   - Do NOT repeat the same pitch. Bring fresh insights or a relevant case study.
3. Make the content specifically relevant to the recipient's company and role.
Return ONLY a valid JSON object with: subject, body"""

    ctx = f"Previous email sent to {lead_name} at {lead_company}:\n{original_email}"
    if follow_up_email:
        ctx += f"\n\nPrevious follow-up sent:\n{follow_up_email}"
    if reply_received:
        ctx += f"\n\nReply received from {lead_name}:\n{reply_received}"

    user = f"""Write a follow-up email in English from {sender_name} at Harpocrates Corp.
CONVERSATION HISTORY:
{ctx}
Based on the above, write the next follow-up. If a reply was received, respond to it directly.
If no reply, try a different angle to provide value. Write ENTIRELY in English.
Return JSON with: subject, body"""

    content = await _call_api(system, user, api_key)
    cleaned = _clean_json(content)
    try:
        data = json.loads(cleaned)
        raw_body = data.get("body", content)
        return {
            "subject": data.get("subject", f"Following up - {lead_company}"),
            "body": _strip_citations(raw_body),
        }
    except json.JSONDecodeError:
        return {"subject": f"Following up - {lead_company}", "body": content}


# ─── 7) Generate Social Post ────────────────────────────────────

async def generate_social_post(
    topic: str,
    topic_prefix: str,
    platform: str,
    industries: list[str],
    existing_posts_preview: list[str],
    api_key: str,
) -> dict:
    """Returns {content, hashtags}."""
    dupe_context = ""
    if existing_posts_preview:
        titles = "\n- ".join(existing_posts_preview[:10])
        dupe_context = f"\n\nALREADY POSTED CONTENT (DO NOT REPEAT):\n- {titles}"

    system = f"""You are a social media expert for Harpocrates Corp and the product comply.reg.
comply.reg is a RegTech SaaS platform for automated compliance monitoring, regulatory change management, and risk assessment for fintech, banks, and regulated enterprises.

MANDATORY RULES for every post:
1. LANGUAGE: Write ENTIRELY in English. No German, no other language.
2. FACTS & FIGURES: Every post MUST contain at least 1-2 concrete numbers, statistics, or data (e.g. fines up to 10M EUR, 72h reporting obligation, DORA effective from Jan 17 2025)
3. SOURCE CITATION: Numbers and facts MUST be cited with source. Format: (Source: EBA, BaFin, ECB, ESMA, EU Official Journal, etc.)
4. NO HALLUCINATIONS: Only use verifiable facts. If unsure, do not include specific numbers.
5. COMPLY.REG RELEVANCE: Post must address problems that comply.reg solves.
6. NO DUPLICATE: Topic and hook must differ from already posted content.
7. FOOTER: The footer is added AUTOMATICALLY. Do NOT generate any footer in the post content!
8. VALUE-DRIVEN: Every post must provide genuine insight or actionable knowledge for compliance professionals.
Return JSON: {{"content": "...", "hashtags": [...]}}"""

    industry_context = ", ".join(industries) if industries else "Financial Services, RegTech, Compliance"

    user = f"""Write a {platform} post for Harpocrates Corp / comply.reg.
Topic: {topic} - {topic_prefix} {industry_context}

REQUIREMENTS:
- Write ENTIRELY in English
- Hook in line 1 (number or provocative thesis)
- At least 1 concrete number/statistic with source in parentheses
- Reference DORA, NIS2, GDPR, MiCA, EU AI Act, CSRD or current EU regulations
- Question or CTA at the end
- Mention comply.reg naturally (no hard sell)
- LinkedIn: 150-250 words, line breaks for readability{dupe_context}
Hashtags: 5-7 from: #DORA #NIS2 #GDPR #RegTech #Compliance #FinTech #RegulatoryCompliance #comply #RiskManagement #AML #BaFin #EBA
Return ONLY valid JSON: {{"content": "...", "hashtags": [...]}}"""

    content = await _call_api(system, user, api_key, max_tokens=2000)
    cleaned = _clean_json(content)
    try:
        data = json.loads(cleaned)
        raw_content = data.get("content", content)
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
        return {"content": ensure_footer(content), "hashtags": []}


# ─── 8) Generate Subject Alternatives ───────────────────────────

async def generate_subject_alternatives(
    company_name: str,
    company_industry: str,
    email_body_preview: str,
    api_key: str,
) -> list[str]:
    system = """You are an expert at writing compelling B2B cold email subject lines for RegTech/Compliance outreach.
Generate exactly 3 different subject lines. Each must:
- Be personalized to the company name and their industry
- Reference a specific compliance challenge or regulation relevant to them
- Be concise (max 60 characters)
- Not be generic or spammy
- Be in English
Return ONLY 3 subject lines, one per line. No numbering, no quotes."""

    user = f"""Company: {company_name}
Industry: {company_industry}
Email body summary: {email_body_preview[:300]}

Generate 3 compelling subject lines:"""

    content = await _call_api(system, user, api_key, max_tokens=200)
    subjects = [
        line.strip()
        for line in content.split("\n")
        if line.strip() and 5 < len(line.strip()) < 100
    ]
    return subjects or [f"Compliance Partnership Opportunity - {company_name}"]
