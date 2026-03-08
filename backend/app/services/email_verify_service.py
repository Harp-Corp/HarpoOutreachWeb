# Email Verification Service – Real SMTP/MX verification
# Technical checks with graceful degradation for cloud environments (Port 25 blocked):
# 1. Syntax check
# 2. DNS MX record lookup
# 3. SMTP handshake (RCPT TO) — best-effort, not required for verification
# 4. Catch-all detection
# 5. Disposable email detection
from __future__ import annotations

import asyncio
import logging
import re
import socket
import smtplib
from typing import Optional

logger = logging.getLogger("harpo.email_verify")

# Common disposable email domains
DISPOSABLE_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "tempmail.com", "throwaway.email",
    "yopmail.com", "sharklasers.com", "guerrillamailblock.com", "grr.la",
    "guerrillamail.info", "guerrillamail.net", "trashmail.com", "trashmail.me",
    "10minutemail.com", "temp-mail.org", "fakeinbox.com", "dispostable.com",
    "maildrop.cc", "mailnesia.com", "tmpmail.net", "tmpmail.org",
    "getnada.com", "mohmal.com", "emailondeck.com",
}

# Generic role-based prefixes (less likely to be real person)
ROLE_PREFIXES = {
    "info", "contact", "admin", "support", "sales", "marketing",
    "hello", "office", "team", "service", "noreply", "no-reply",
    "postmaster", "webmaster", "abuse", "billing", "help",
}

# Well-known corporate email domains that definitely exist (skip SMTP check)
KNOWN_CORPORATE_DOMAINS = {
    # DACH Banks & Financial Services
    "allianz.com", "db.com", "commerzbank.com", "deutsche-bank.com",
    "siemens.com", "sap.com", "bosch.com", "bmw.com", "daimler.com",
    "volkswagen.de", "basf.com", "bayer.com", "eon.com", "rwe.com",
    "telekom.de", "t-systems.com", "infineon.com", "continental.com",
    "fresenius.com", "henkel.com", "merck.de", "thyssenkrupp.com",
    "munichre.com", "swissre.com", "ubs.com", "credit-suisse.com",
    "zurich.com", "axa.com", "generali.com", "ergo.de", "ergo.com",
    "lbbw.de", "bayernlb.de", "dz-bank.de", "kfw.de", "helaba.de",
    "nordlb.de", "deka.de", "union-investment.de", "dws.com",
    "herrenknecht.com", "trumpf.com", "zeiss.com", "festo.com",
    # Additional major European corporates
    "deutsche-boerse.com", "ing.com", "rabobank.com", "abnamro.com",
    "bnpparibas.com", "societegenerale.com", "creditagricole.com",
    "unicredit.de", "unicredit.it", "intesasanpaolo.com",
    "hsbc.com", "barclays.com", "lloydsbanking.com", "rbs.com",
    "standardchartered.com", "santander.com", "bbva.com",
    "raiffeisen.at", "erste-group.com", "wienerstaedtische.at",
    "swisslife.com", "baloise.com", "helvetia.com",
    "talanx.com", "hannover-re.com", "scor.com",
    # Insurance
    "signal-iduna.de", "gothaer.de", "huk-coburg.de", "debeka.de",
    "r-v.de", "nuernberger.de", "wuerttembergische.de",
    "provinzial.com", "vhv-gruppe.de", "lvm.de",
    # Asset Management / PE
    "blackrock.com", "vanguard.com", "statestreet.com",
    "amundi.com", "robeco.com", "nordea.com",
    # Tech / Big companies
    "microsoft.com", "google.com", "amazon.com", "apple.com",
    "meta.com", "oracle.com", "ibm.com", "salesforce.com",
    "adobe.com", "cisco.com", "dell.com", "hp.com",
    # German Mittelstand
    "wacker.com", "evonik.com", "lanxess.com", "symrise.com",
    "covestro.com", "sartorius.com", "carl-zeiss.com",
    "mtu.de", "rheinmetall.com", "knorr-bremse.com",
    "draeger.com", "gea.com", "krones.com", "wilo.com",
    "viessmann.com", "stihl.de", "wuerth.com", "brose.com",
    # Swiss
    "novartis.com", "roche.com", "nestle.com", "abb.com",
    "julius-baer.com", "vontobel.com", "raiffeisen.ch",
    # Austrian
    "voestalpine.com", "omv.com", "verbund.com",
    # Payment / FinTech
    "wirecard.com", "adyen.com", "klarna.com", "n26.com",
    "revolut.com", "stripe.com", "paypal.com",
    # Consulting
    "deloitte.com", "pwc.com", "ey.com", "kpmg.com",
    "mckinsey.com", "bcg.com", "bain.com",
}


def _is_valid_syntax(email: str) -> bool:
    """Check email syntax validity."""
    pattern = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email.strip()))


def validate_email_pattern(email: str, person_name: str = "") -> dict:
    """Validate if an email matches expected corporate patterns for a person.
    Returns {plausible: bool, reason: str, pattern_type: str}.
    This helps catch hallucinated emails that have valid syntax but wrong patterns."""
    result = {"plausible": True, "reason": "", "pattern_type": "unknown"}
    
    if not email or "@" not in email:
        return {"plausible": False, "reason": "Invalid email", "pattern_type": "invalid"}
    
    local, domain = email.lower().split("@", 1)
    
    # Check for masked/redacted emails
    if "***" in local or "..." in local or "[email" in local:
        return {"plausible": False, "reason": "Masked email", "pattern_type": "masked"}
    
    # Check for suspicious local parts
    if len(local) < 2:
        return {"plausible": False, "reason": "Local part too short", "pattern_type": "suspicious"}
    if local.count(".") > 3:
        return {"plausible": False, "reason": "Too many dots in local part", "pattern_type": "suspicious"}
    
    # If we have a person's name, check if email plausibly matches
    if person_name:
        name_parts = person_name.lower().strip().split()
        # Remove titles
        name_parts = [p for p in name_parts if p not in ("dr", "dr.", "prof", "prof.", "ing", "ing.")]
        if len(name_parts) >= 2:
            first = name_parts[0]
            last = name_parts[-1]
            # Handle German umlauts
            umlaut_map = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
            first_norm = first
            last_norm = last
            for k, v in umlaut_map.items():
                first_norm = first_norm.replace(k, v)
                last_norm = last_norm.replace(k, v)
            
            # Check common patterns
            if f"{first_norm}.{last_norm}" in local or f"{first_norm[0]}.{last_norm}" in local:
                result["pattern_type"] = "firstname.lastname"
            elif f"{first_norm}{last_norm}" in local or f"{first_norm[0]}{last_norm}" in local:
                result["pattern_type"] = "firstnamelastname"
            elif f"{last_norm}.{first_norm}" in local:
                result["pattern_type"] = "lastname.firstname"
            elif first_norm in local or last_norm in local:
                result["pattern_type"] = "partial_match"
            elif first_norm[0] in local and last_norm[:3] in local:
                result["pattern_type"] = "likely_match"
            else:
                # Email doesn't contain any part of the person's name
                # This is suspicious but not necessarily wrong (could be role-based)
                if local not in ROLE_PREFIXES:
                    result["reason"] = f"Email '{local}' does not match name '{person_name}'"
                    result["pattern_type"] = "name_mismatch"
                    # Don't mark as implausible — just flag for review
    
    return result


def _is_disposable(email: str) -> bool:
    """Check if email domain is a known disposable provider."""
    domain = email.split("@")[1].lower()
    return domain in DISPOSABLE_DOMAINS


def _is_role_based(email: str) -> bool:
    """Check if email is a generic role-based address."""
    local = email.split("@")[0].lower()
    return local in ROLE_PREFIXES


def _is_known_corporate(email: str) -> bool:
    """Check if domain is a well-known corporate domain."""
    domain = email.split("@")[1].lower()
    return domain in KNOWN_CORPORATE_DOMAINS


async def _lookup_mx(domain: str) -> list[str]:
    """Look up MX records for a domain. Returns list of mail server hostnames."""
    import dns.resolver
    try:
        answers = await asyncio.get_event_loop().run_in_executor(
            None, lambda: dns.resolver.resolve(domain, 'MX')
        )
        mx_hosts = sorted(answers, key=lambda r: r.preference)
        return [str(r.exchange).rstrip('.') for r in mx_hosts]
    except Exception as e:
        logger.debug(f"MX lookup failed for {domain}: {e}")
        return []


async def _smtp_verify(email: str, mx_host: str, timeout: int = 8) -> dict:
    """Perform SMTP handshake to verify email exists.
    Returns {exists: bool, catch_all: bool, error: str}.
    Best-effort — many cloud environments block port 25."""

    def _do_smtp():
        result = {"exists": None, "catch_all": False, "error": ""}
        try:
            with smtplib.SMTP(mx_host, 25, timeout=timeout) as smtp:
                smtp.ehlo("harpocrates-corp.com")
                smtp.mail("verify@harpocrates-corp.com")
                code, msg = smtp.rcpt(email)

                if code == 250:
                    result["exists"] = True
                elif code == 550:
                    result["exists"] = False
                    result["error"] = "Mailbox does not exist"
                elif code in (450, 451, 452):
                    result["exists"] = None
                    result["error"] = f"Temporary error: {code}"
                elif code == 421:
                    result["error"] = "Server busy / rate limited"
                else:
                    result["error"] = f"SMTP code {code}: {msg.decode('utf-8', errors='replace')[:100]}"

                # Catch-all detection
                random_addr = f"harpo_test_nonexist_xq7z@{email.split('@')[1]}"
                code2, _ = smtp.rcpt(random_addr)
                if code2 == 250:
                    result["catch_all"] = True

                smtp.quit()
        except (smtplib.SMTPConnectError, ConnectionRefusedError, OSError):
            result["error"] = "Port 25 blocked (cloud environment)"
        except smtplib.SMTPServerDisconnected:
            result["error"] = "Server disconnected"
        except socket.timeout:
            result["error"] = "Connection timeout"
        except Exception as e:
            result["error"] = str(e)[:100]
        return result

    return await asyncio.get_event_loop().run_in_executor(None, _do_smtp)


async def verify_email_technical(email: str) -> dict:
    """Full technical email verification pipeline.
    Gracefully degrades when SMTP port 25 is blocked (common in cloud environments).
    MX records + valid syntax + non-disposable = sufficient for "low" risk when SMTP unavailable.

    Returns:
    {
        email: str,
        is_valid_syntax: bool,
        has_mx_records: bool,
        mx_host: str,
        smtp_exists: bool | None,  # None = uncertain / unavailable
        is_catch_all: bool,
        is_disposable: bool,
        is_role_based: bool,
        risk_level: "low" | "medium" | "high" | "invalid",
        verification_method: str,
        notes: str,
    }
    """
    email = email.strip().lower()
    result = {
        "email": email,
        "is_valid_syntax": False,
        "has_mx_records": False,
        "mx_host": "",
        "smtp_exists": None,
        "is_catch_all": False,
        "is_disposable": False,
        "is_role_based": False,
        "risk_level": "invalid",
        "verification_method": "syntax",
        "notes": "",
    }

    # Step 1: Syntax check
    if not _is_valid_syntax(email):
        result["notes"] = "Ungültige E-Mail-Syntax"
        return result
    result["is_valid_syntax"] = True

    domain = email.split("@")[1]

    # Step 2: Disposable check
    result["is_disposable"] = _is_disposable(email)
    if result["is_disposable"]:
        result["risk_level"] = "high"
        result["notes"] = f"Wegwerf-E-Mail-Domain: {domain}"
        result["verification_method"] = "disposable_check"
        return result

    # Step 3: Role-based check
    result["is_role_based"] = _is_role_based(email)

    # Step 4: MX record lookup
    try:
        mx_hosts = await _lookup_mx(domain)
    except Exception:
        mx_hosts = []

    if not mx_hosts:
        result["risk_level"] = "high"
        result["notes"] = f"Keine MX-Records für {domain}"
        result["verification_method"] = "mx_lookup"
        return result

    result["has_mx_records"] = True
    result["mx_host"] = mx_hosts[0]
    result["verification_method"] = "mx_lookup"

    # Step 5: SMTP verification (best-effort, 8s timeout)
    smtp_attempted = False
    smtp_result = None
    for mx in mx_hosts[:2]:
        try:
            smtp_result = await asyncio.wait_for(
                _smtp_verify(email, mx, timeout=8),
                timeout=10,
            )
            smtp_attempted = True
            if smtp_result.get("exists") is not None:
                break
        except asyncio.TimeoutError:
            smtp_result = {"exists": None, "catch_all": False, "error": "Timeout"}
            smtp_attempted = True
        except Exception as e:
            smtp_result = {"exists": None, "catch_all": False, "error": str(e)[:100]}
            smtp_attempted = True

    smtp_blocked = (
        smtp_result is not None
        and smtp_result.get("exists") is None
        and "blocked" in smtp_result.get("error", "").lower()
        or smtp_result is not None
        and "refused" in smtp_result.get("error", "").lower()
        or smtp_result is not None
        and "timeout" in smtp_result.get("error", "").lower()
    )

    if smtp_result and smtp_result.get("exists") is not None:
        # SMTP gave a definitive answer
        result["smtp_exists"] = smtp_result.get("exists")
        result["is_catch_all"] = smtp_result.get("catch_all", False)
        result["verification_method"] = "smtp_handshake"

        if smtp_result["exists"] is True:
            if result["is_catch_all"]:
                result["risk_level"] = "medium"
                result["notes"] = "Catch-All-Domain (akzeptiert alle Adressen)"
            elif result["is_role_based"]:
                result["risk_level"] = "medium"
                result["notes"] = "Rollenbasierte Adresse"
            else:
                result["risk_level"] = "low"
                result["notes"] = "SMTP-verifiziert: Postfach existiert"
        elif smtp_result["exists"] is False:
            result["risk_level"] = "invalid"
            result["notes"] = "SMTP: Postfach existiert nicht"
    else:
        # SMTP unavailable (port 25 blocked, timeout, etc.)
        # Fall back to MX-based verification — this is valid for business emails
        result["verification_method"] = "mx_verified"

        if _is_known_corporate(email):
            # Known corporate domain + valid syntax + MX records = low risk
            result["risk_level"] = "low"
            result["notes"] = "MX-verifiziert (bekannte Firmen-Domain)"
        elif result["is_role_based"]:
            result["risk_level"] = "medium"
            result["notes"] = "MX-verifiziert, rollenbasierte Adresse"
        else:
            # Valid syntax + MX records + non-disposable = low risk
            # (SMTP check is nice-to-have but not required for B2B outreach)
            result["risk_level"] = "low"
            result["notes"] = "MX-verifiziert (SMTP-Prüfung nicht verfügbar in Cloud)"

        if smtp_result and smtp_result.get("error"):
            result["notes"] += f" | {smtp_result['error']}"

    return result
