# Email Verification Service – Real SMTP/MX verification
# Replaces pure Perplexity-based "verification" with actual technical checks:
# 1. Syntax check
# 2. DNS MX record lookup
# 3. SMTP handshake (RCPT TO) without sending
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


def _is_valid_syntax(email: str) -> bool:
    """Check email syntax validity."""
    pattern = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email.strip()))


def _is_disposable(email: str) -> bool:
    """Check if email domain is a known disposable provider."""
    domain = email.split("@")[1].lower()
    return domain in DISPOSABLE_DOMAINS


def _is_role_based(email: str) -> bool:
    """Check if email is a generic role-based address."""
    local = email.split("@")[0].lower()
    return local in ROLE_PREFIXES


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


async def _smtp_verify(email: str, mx_host: str, timeout: int = 10) -> dict:
    """Perform SMTP handshake to verify email exists.
    Returns {exists: bool, catch_all: bool, error: str}."""

    def _do_smtp():
        result = {"exists": False, "catch_all": False, "error": ""}
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
                    # Temporary error — treat as unknown
                    result["exists"] = None  # uncertain
                    result["error"] = f"Temporary error: {code}"
                elif code == 421:
                    result["error"] = "Server busy / rate limited"
                else:
                    result["error"] = f"SMTP code {code}: {msg.decode('utf-8', errors='replace')[:100]}"

                # Catch-all detection: test a random nonexistent address
                random_addr = f"harpo_test_nonexist_xq7z@{email.split('@')[1]}"
                code2, _ = smtp.rcpt(random_addr)
                if code2 == 250:
                    result["catch_all"] = True

                smtp.quit()
        except smtplib.SMTPConnectError:
            result["error"] = "Connection refused"
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
    Returns:
    {
        email: str,
        is_valid_syntax: bool,
        has_mx_records: bool,
        mx_host: str,
        smtp_exists: bool | None,  # None = uncertain
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

    # Step 5: SMTP verification (try first 2 MX hosts)
    smtp_result = None
    for mx in mx_hosts[:2]:
        try:
            smtp_result = await asyncio.wait_for(
                _smtp_verify(email, mx),
                timeout=15,
            )
            if smtp_result.get("exists") is not None:
                break
        except asyncio.TimeoutError:
            smtp_result = {"exists": None, "catch_all": False, "error": "Timeout"}
        except Exception as e:
            smtp_result = {"exists": None, "catch_all": False, "error": str(e)[:100]}

    if smtp_result:
        result["smtp_exists"] = smtp_result.get("exists")
        result["is_catch_all"] = smtp_result.get("catch_all", False)
        result["verification_method"] = "smtp_handshake"

        if smtp_result.get("error"):
            result["notes"] = smtp_result["error"]

        # Determine risk level
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
            # Uncertain — server didn't give clear answer
            result["risk_level"] = "medium"
            if not result["notes"]:
                result["notes"] = "SMTP-Prüfung nicht eindeutig"
    else:
        # No SMTP result at all — rely on MX only
        result["risk_level"] = "medium"
        result["notes"] = "MX-Records vorhanden, SMTP-Prüfung nicht möglich"

    return result
