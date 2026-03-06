# Google OAuth2 service – server-side flow for the web app
# Ported from GoogleAuthService.swift (adapted for server-side OAuth)
from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import quote

import httpx

from ..config import settings

logger = logging.getLogger("harpo.google_auth")

TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/userinfo.email",
]


def get_auth_url(client_id: str = "", redirect_uri: str = "") -> str:
    """Build the Google OAuth consent URL."""
    cid = client_id or settings.google_client_id
    ruri = redirect_uri or settings.google_redirect_uri
    scope = quote(" ".join(SCOPES))
    return (
        f"{AUTH_URL}?"
        f"client_id={cid}"
        f"&redirect_uri={quote(ruri, safe='')}"
        f"&response_type=code"
        f"&scope={scope}"
        f"&access_type=offline"
        f"&prompt=consent"
    )


async def exchange_code(code: str, client_id: str = "", client_secret: str = "", redirect_uri: str = "") -> dict:
    """Exchange authorization code for tokens."""
    cid = client_id or settings.google_client_id
    cs = client_secret or settings.google_client_secret
    ruri = redirect_uri or settings.google_redirect_uri

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": cid,
                "client_secret": cs,
                "redirect_uri": ruri,
                "grant_type": "authorization_code",
            },
        )
    data = resp.json()
    if "error" in data:
        raise Exception(f"OAuth error: {data.get('error_description', data['error'])}")

    tokens = {
        "access_token": data.get("access_token", ""),
        "refresh_token": data.get("refresh_token", ""),
        "expires_in": data.get("expires_in", 3600),
    }
    logger.info("OAuth tokens obtained successfully")
    return tokens


async def refresh_token(refresh_tok: str, client_id: str = "", client_secret: str = "") -> dict:
    """Refresh an expired access token."""
    cid = client_id or settings.google_client_id
    cs = client_secret or settings.google_client_secret

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "refresh_token": refresh_tok,
                "client_id": cid,
                "client_secret": cs,
                "grant_type": "refresh_token",
            },
        )
    data = resp.json()
    if "error" in data:
        raise Exception(f"Token refresh failed: {data.get('error_description', data['error'])}")

    result = {
        "access_token": data["access_token"],
        "expires_in": data.get("expires_in", 3600),
    }
    # Google sometimes returns a new refresh token
    if "refresh_token" in data:
        result["refresh_token"] = data["refresh_token"]
    logger.info("Access token refreshed successfully")
    return result


async def get_user_email(access_token: str) -> Optional[str]:
    """Fetch the authenticated user's email address."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code == 200:
        data = resp.json()
        return data.get("email")
    return None
