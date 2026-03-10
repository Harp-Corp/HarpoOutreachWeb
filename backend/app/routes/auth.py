# Google OAuth routes – server-side flow with multi-user session management
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..models.db import get_db
from ..services import database_service as db_svc
from ..services import google_auth_service as gauth
from ..services.auth_service import (
    COOKIE_NAME,
    create_session_token,
    get_current_user,
    get_current_user_optional,
    require_admin,
)

import logging

logger = logging.getLogger("harpo.auth")

router = APIRouter(prefix="/auth", tags=["Authentication"])

MAX_USERS = 10


@router.get("/google/login")
async def google_login(db: Session = Depends(get_db)):
    """Redirect user to Google OAuth consent screen."""
    client_id = db_svc.get_setting(db, "google_client_id")
    redirect_uri = db_svc.get_setting(db, "google_redirect_uri")
    if not client_id:
        raise HTTPException(400, "Google Client ID nicht konfiguriert.")
    url = gauth.get_auth_url(client_id=client_id, redirect_uri=redirect_uri)
    return RedirectResponse(url)


@router.get("/google/callback")
async def google_callback(code: str, db: Session = Depends(get_db)):
    """Handle OAuth callback — authenticate or reject user, create session."""
    from ..models.db_phase2 import UserDB

    client_id = db_svc.get_setting(db, "google_client_id")
    client_secret = db_svc.get_setting(db, "google_client_secret")
    redirect_uri = db_svc.get_setting(db, "google_redirect_uri")

    if not client_id or not client_secret:
        raise HTTPException(400, "Google Credentials nicht konfiguriert.")

    tokens = await gauth.exchange_code(
        code, client_id=client_id, client_secret=client_secret,
        redirect_uri=redirect_uri,
    )

    # Get user info from Google
    email = await gauth.get_user_email(tokens["access_token"])
    if not email:
        frontend_url = settings.frontend_url.rstrip("/")
        return RedirectResponse(f"{frontend_url}/?auth=error&reason=no_email")

    email = email.lower().strip()

    # Also get name/avatar from Google userinfo
    import httpx
    user_name = ""
    user_avatar = ""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            if resp.status_code == 200:
                info = resp.json()
                user_name = info.get("name", "")
                user_avatar = info.get("picture", "")
    except Exception:
        pass

    # Look up user in the users table
    user = db.query(UserDB).filter(UserDB.email == email).first()

    if not user:
        # Check if this is the FIRST user ever — auto-create as admin
        total_users = db.query(UserDB).count()
        if total_users == 0:
            user = UserDB(
                id=uuid4(),
                email=email,
                name=user_name or email.split("@")[0],
                role="admin",
                google_id=tokens.get("id_token", ""),
                avatar_url=user_avatar,
                is_active=True,
                last_login=datetime.utcnow(),
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info(f"First user auto-created as admin: {email}")
        else:
            # Not in users table → reject
            frontend_url = settings.frontend_url.rstrip("/")
            logger.warning(f"Login rejected — {email} not in users table")
            return RedirectResponse(f"{frontend_url}/?auth=denied&email={email}")

    if not user.is_active:
        frontend_url = settings.frontend_url.rstrip("/")
        return RedirectResponse(f"{frontend_url}/?auth=denied&reason=deactivated")

    # Update user profile from Google
    user.last_login = datetime.utcnow()
    if user_name and not user.name:
        user.name = user_name
    if user_avatar:
        user.avatar_url = user_avatar
    if tokens.get("id_token") and not user.google_id:
        user.google_id = tokens.get("id_token", "")[:200]
    db.commit()

    # Also save Google tokens in settings (for Gmail/Calendar API use by the platform)
    db_svc.set_setting(db, "google_access_token", tokens["access_token"])
    if tokens.get("refresh_token"):
        db_svc.set_setting(db, "google_refresh_token", tokens["refresh_token"])
    db_svc.set_setting(db, "google_token_expiry",
                       str(datetime.utcnow().timestamp() + tokens.get("expires_in", 3600)))
    db_svc.set_setting(db, "google_user_email", email)

    # Create JWT session
    session_token = create_session_token(str(user.id), user.email, user.role)

    # Redirect to frontend with session cookie
    frontend_url = settings.frontend_url.rstrip("/")
    response = RedirectResponse(f"{frontend_url}/?auth=success")
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=30 * 24 * 3600,  # 30 days
        path="/",
    )
    logger.info(f"User logged in: {email} (role={user.role})")
    return response


@router.get("/status")
async def auth_status(user: dict = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    """Check current authentication status."""
    if user:
        return {
            "authenticated": True,
            "email": user["email"],
            "name": user["name"],
            "role": user["role"],
            "avatar_url": user.get("avatar_url", ""),
            "user_id": user["id"],
            "token_expired": False,
        }

    # Fallback: check old-style token auth (backwards compatibility)
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
        "name": "",
        "role": "admin",  # Legacy single-user is always admin
        "avatar_url": "",
        "user_id": None,
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
                           str(datetime.utcnow().timestamp() + result.get("expires_in", 3600)))
        if result.get("refresh_token"):
            db_svc.set_setting(db, "google_refresh_token", result["refresh_token"])
        return {"success": True}
    except Exception as e:
        raise HTTPException(401, f"Token-Refresh fehlgeschlagen: {e}")


@router.post("/logout")
async def logout():
    """Clear session cookie."""
    response = JSONResponse({"success": True})
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


# ─── User Management (Admin only) ───────────────────────────────

@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Return current user profile."""
    return {"success": True, "data": user}


@router.get("/users")
async def list_users(admin: dict = Depends(require_admin), db: Session = Depends(get_db)):
    """List all users (admin only)."""
    from ..models.db_phase2 import UserDB
    users = db.query(UserDB).order_by(UserDB.created_at).all()
    return {"success": True, "data": [
        {
            "id": str(u.id),
            "email": u.email,
            "name": u.name,
            "role": u.role,
            "is_active": u.is_active,
            "avatar_url": u.avatar_url or "",
            "last_login": u.last_login.isoformat() if u.last_login else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]}


from pydantic import BaseModel


class InviteBody(BaseModel):
    email: str
    name: str = ""
    role: str = "user"


@router.post("/users/invite")
async def invite_user(body: InviteBody, admin: dict = Depends(require_admin), db: Session = Depends(get_db)):
    """Invite a new user (admin only, max 10)."""
    from ..models.db_phase2 import UserDB

    email = body.email.lower().strip()
    count = db.query(UserDB).filter(UserDB.is_active == True).count()
    if count >= MAX_USERS:
        raise HTTPException(400, f"Maximale Anzahl von {MAX_USERS} Benutzern erreicht.")
    existing = db.query(UserDB).filter(UserDB.email == email).first()
    if existing:
        if not existing.is_active:
            existing.is_active = True
            existing.role = body.role
            db.commit()
            return {"success": True, "data": {"id": str(existing.id), "email": existing.email, "role": existing.role}, "reactivated": True}
        raise HTTPException(400, f"Benutzer {email} existiert bereits.")

    user = UserDB(
        id=uuid4(),
        email=email,
        name=body.name or email.split("@")[0],
        role=body.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    logger.info(f"User invited: {email} by {admin['email']}")
    return {"success": True, "data": {"id": str(user.id), "email": user.email, "role": user.role}}


@router.delete("/users/{user_id}")
async def remove_user(user_id: str, admin: dict = Depends(require_admin), db: Session = Depends(get_db)):
    """Deactivate a user (admin only)."""
    from ..models.db_phase2 import UserDB
    from uuid import UUID as UUID_type

    user = db.query(UserDB).filter(UserDB.id == UUID_type(user_id)).first()
    if not user:
        raise HTTPException(404, "Benutzer nicht gefunden.")
    if user.email == admin["email"]:
        raise HTTPException(400, "Du kannst dich nicht selbst deaktivieren.")
    user.is_active = False
    db.commit()
    logger.info(f"User deactivated: {user.email} by {admin['email']}")
    return {"success": True, "message": f"Benutzer {user.email} deaktiviert."}


@router.patch("/users/{user_id}")
async def update_user_role(user_id: str, body: dict, admin: dict = Depends(require_admin), db: Session = Depends(get_db)):
    """Update user role (admin only)."""
    from ..models.db_phase2 import UserDB
    from uuid import UUID as UUID_type

    user = db.query(UserDB).filter(UserDB.id == UUID_type(user_id)).first()
    if not user:
        raise HTTPException(404, "Benutzer nicht gefunden.")
    if "role" in body:
        if body["role"] not in ("admin", "user"):
            raise HTTPException(400, "Rolle muss 'admin' oder 'user' sein.")
        user.role = body["role"]
    if "name" in body:
        user.name = body["name"]
    db.commit()
    return {"success": True}
