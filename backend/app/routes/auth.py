# Google OAuth routes – server-side flow
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..models.db import get_db
from ..services import database_service as db_svc
from ..services import google_auth_service as gauth

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/google/login")
async def google_login(db: Session = Depends(get_db)):
    """Redirect user to Google OAuth consent screen."""
    client_id = db_svc.get_setting(db, "google_client_id")
    if not client_id:
        raise HTTPException(400, "Google Client ID nicht konfiguriert.")
    url = gauth.get_auth_url(client_id=client_id)
    return RedirectResponse(url)


@router.get("/google/callback")
async def google_callback(code: str, db: Session = Depends(get_db)):
    """Handle OAuth callback, exchange code for tokens."""
    client_id = db_svc.get_setting(db, "google_client_id")
    client_secret = db_svc.get_setting(db, "google_client_secret")

    if not client_id or not client_secret:
        raise HTTPException(400, "Google Credentials nicht konfiguriert.")

    tokens = await gauth.exchange_code(
        code, client_id=client_id, client_secret=client_secret
    )

    # Save tokens
    db_svc.set_setting(db, "google_access_token", tokens["access_token"])
    if tokens.get("refresh_token"):
        db_svc.set_setting(db, "google_refresh_token", tokens["refresh_token"])
    db_svc.set_setting(db, "google_token_expiry",
                       (datetime.utcnow().timestamp() + tokens.get("expires_in", 3600)))

    # Fetch user email
    email = await gauth.get_user_email(tokens["access_token"])
    if email:
        db_svc.set_setting(db, "google_user_email", email)

    # Redirect to frontend
    return RedirectResponse("/?auth=success")


@router.get("/status")
async def auth_status(db: Session = Depends(get_db)):
    """Check current authentication status."""
    access_token = db_svc.get_setting(db, "google_access_token")
    email = db_svc.get_setting(db, "google_user_email")
    expiry = db_svc.get_setting(db, "google_token_expiry")

    is_authenticated = bool(access_token)
    is_expired = False
    if expiry:
        try:
            is_expired = float(expiry) < datetime.utcnow().timestamp()
        except (ValueError, TypeError):
            pass

    return {
        "authenticated": is_authenticated and not is_expired,
        "email": email or "",
        "token_expired": is_expired,
    }


@router.post("/refresh")
async def refresh_token(db: Session = Depends(get_db)):
    """Refresh the Google access token."""
    refresh_tok = db_svc.get_setting(db, "google_refresh_token")
    if not refresh_tok:
        raise HTTPException(401, "Kein Refresh-Token vorhanden. Bitte erneut anmelden.")

    client_id = db_svc.get_setting(db, "google_client_id")
    client_secret = db_svc.get_setting(db, "google_client_secret")

    try:
        result = await gauth.refresh_token(refresh_tok, client_id=client_id, client_secret=client_secret)
        db_svc.set_setting(db, "google_access_token", result["access_token"])
        db_svc.set_setting(db, "google_token_expiry",
                           (datetime.utcnow().timestamp() + result.get("expires_in", 3600)))
        if result.get("refresh_token"):
            db_svc.set_setting(db, "google_refresh_token", result["refresh_token"])
        return {"success": True}
    except Exception as e:
        raise HTTPException(401, f"Token-Refresh fehlgeschlagen: {e}")


@router.post("/logout")
async def logout(db: Session = Depends(get_db)):
    """Clear all Google auth tokens."""
    for key in ["google_access_token", "google_refresh_token", "google_token_expiry", "google_user_email"]:
        db_svc.set_setting(db, key, "")
    return {"success": True}
