# Authentication routes – Google OAuth + Email/Password login
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse
import bcrypt
from pydantic import BaseModel
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

# Password hashing — using bcrypt directly (passlib incompatible with bcrypt>=4.1)
def _hash_password(password: str) -> str:
    """Hash a password with bcrypt. Truncates to 72 bytes (bcrypt limit)."""
    pw_bytes = password.encode('utf-8')[:72]
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode('utf-8')

def _verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a bcrypt hash."""
    pw_bytes = password.encode('utf-8')[:72]
    return bcrypt.checkpw(pw_bytes, hashed.encode('utf-8'))


def _set_session_cookie(response, user_id: str, email: str, role: str):
    """Helper to set JWT session cookie on a response."""
    session_token = create_session_token(user_id, email, role)
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=30 * 24 * 3600,  # 30 days
        path="/",
    )
    return response


# ─── Google OAuth ─────────────────────────────────────────────────

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

    # Create JWT session + redirect
    frontend_url = settings.frontend_url.rstrip("/")
    response = RedirectResponse(f"{frontend_url}/?auth=success")
    _set_session_cookie(response, str(user.id), user.email, user.role)
    logger.info(f"User logged in via Google: {email} (role={user.role})")
    return response


# ─── Email/Password Login ─────────────────────────────────────────

class EmailLoginBody(BaseModel):
    email: str
    password: str


@router.post("/login")
async def email_login(body: EmailLoginBody, db: Session = Depends(get_db)):
    """Authenticate with email + password. Returns session cookie."""
    from ..models.db_phase2 import UserDB

    email = body.email.lower().strip()
    user = db.query(UserDB).filter(UserDB.email == email).first()

    if not user:
        raise HTTPException(401, "Ungültige Anmeldedaten.")

    if not user.is_active:
        raise HTTPException(401, "Konto deaktiviert. Bitte kontaktiere den Administrator.")

    if not user.password_hash:
        raise HTTPException(401, "Für dieses Konto ist kein Passwort hinterlegt. Bitte mit Google anmelden oder den Admin bitten, ein Passwort zu setzen.")

    if not _verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Ungültige Anmeldedaten.")

    # Update last login
    user.last_login = datetime.utcnow()
    db.commit()

    response = JSONResponse({"success": True, "name": user.name, "role": user.role})
    _set_session_cookie(response, str(user.id), user.email, user.role)
    logger.info(f"User logged in via email/password: {email} (role={user.role})")
    return response


class SetPasswordBody(BaseModel):
    current_password: str = ""
    new_password: str


@router.post("/set-password")
async def set_own_password(body: SetPasswordBody, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Let a logged-in user set/change their own password."""
    from ..models.db_phase2 import UserDB
    from uuid import UUID as UUID_type

    db_user = db.query(UserDB).filter(UserDB.id == UUID_type(user["id"])).first()
    if not db_user:
        raise HTTPException(404, "Benutzer nicht gefunden.")

    # If user already has a password, require old password
    if db_user.password_hash and body.current_password:
        if not _verify_password(body.current_password, db_user.password_hash):
            raise HTTPException(400, "Aktuelles Passwort ist falsch.")

    if len(body.new_password) < 8:
        raise HTTPException(400, "Passwort muss mindestens 8 Zeichen lang sein.")

    db_user.password_hash = _hash_password(body.new_password)
    db.commit()
    return {"success": True, "message": "Passwort gesetzt."}


# ─── Auth Status & Session ────────────────────────────────────────

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

    # No valid session
    return {
        "authenticated": False,
        "email": "",
        "name": "",
        "role": "",
        "avatar_url": "",
        "user_id": None,
        "token_expired": False,
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
            "has_password": bool(u.password_hash),
            "has_google": bool(u.google_id),
            "avatar_url": u.avatar_url or "",
            "last_login": u.last_login.isoformat() if u.last_login else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]}


class InviteBody(BaseModel):
    email: str
    name: str = ""
    role: str = "user"
    password: str = ""  # optional initial password for email/password users


@router.post("/users/invite")
async def invite_user(body: InviteBody, admin: dict = Depends(require_admin), db: Session = Depends(get_db)):
    """Invite a new user (admin only, max 10). Optionally set a password for non-Google users."""
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
            if body.password and len(body.password) >= 8:
                existing.password_hash = _hash_password(body.password)
            db.commit()
            return {"success": True, "data": {"id": str(existing.id), "email": existing.email, "role": existing.role}, "reactivated": True}
        raise HTTPException(400, f"Benutzer {email} existiert bereits.")

    pw_hash = None
    if body.password:
        if len(body.password) < 8:
            raise HTTPException(400, "Passwort muss mindestens 8 Zeichen lang sein.")
        pw_hash = _hash_password(body.password)

    user = UserDB(
        id=uuid4(),
        email=email,
        name=body.name or email.split("@")[0],
        role=body.role,
        password_hash=pw_hash,
        is_active=True,
    )
    db.add(user)
    db.commit()
    logger.info(f"User invited: {email} (password={'yes' if pw_hash else 'no'}) by {admin['email']}")
    return {"success": True, "data": {"id": str(user.id), "email": user.email, "role": user.role, "has_password": bool(pw_hash)}}


class AdminSetPasswordBody(BaseModel):
    password: str


@router.post("/users/{user_id}/set-password")
async def admin_set_password(user_id: str, body: AdminSetPasswordBody, admin: dict = Depends(require_admin), db: Session = Depends(get_db)):
    """Admin can set/reset password for any user."""
    from ..models.db_phase2 import UserDB
    from uuid import UUID as UUID_type

    user = db.query(UserDB).filter(UserDB.id == UUID_type(user_id)).first()
    if not user:
        raise HTTPException(404, "Benutzer nicht gefunden.")
    if len(body.password) < 8:
        raise HTTPException(400, "Passwort muss mindestens 8 Zeichen lang sein.")

    user.password_hash = _hash_password(body.password)
    db.commit()
    logger.info(f"Password set for {user.email} by admin {admin['email']}")
    return {"success": True, "message": f"Passwort für {user.email} gesetzt."}


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

