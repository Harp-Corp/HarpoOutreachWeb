# JWT-based session authentication for multi-user team access
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, Request
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from ..config import settings
from ..models.db import get_db

logger = logging.getLogger("harpo.auth")

# JWT config
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 30  # Long-lived session for team use
COOKIE_NAME = "harpo_session"


def create_session_token(user_id: str, email: str, role: str) -> str:
    """Create a signed JWT session token."""
    expire = datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_session_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT session token. Returns payload or None."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


async def get_current_user(request: Request, db: Session = Depends(get_db)) -> dict:
    """FastAPI dependency — extracts and validates the current user from session cookie.
    Returns user dict with id, email, role, name.
    Raises 401 if not authenticated."""
    from ..models.db_phase2 import UserDB

    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(401, "Nicht angemeldet. Bitte einloggen.")

    payload = decode_session_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(401, "Session abgelaufen. Bitte erneut einloggen.")

    user_id = payload["sub"]
    user = db.query(UserDB).filter(UserDB.id == UUID(user_id), UserDB.is_active == True).first()
    if not user:
        raise HTTPException(401, "Benutzer nicht gefunden oder deaktiviert.")

    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "avatar_url": user.avatar_url or "",
        "must_change_password": getattr(user, 'must_change_password', False),
    }


async def get_current_user_or_apikey(request: Request, db: Session = Depends(get_db)) -> dict:
    """Like get_current_user but also accepts Bearer <SECRET_KEY> for server-to-server calls (cron jobs).
    Returns a system user dict when API key auth is used."""
    # Check for Bearer API key first (used by cron jobs)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if token == settings.secret_key:
            return {"id": "system", "email": "system@harpocrates", "name": "System", "role": "admin", "avatar_url": ""}
    # Fall back to session cookie auth
    return await get_current_user(request, db)


async def get_current_user_optional(request: Request, db: Session = Depends(get_db)) -> Optional[dict]:
    """Like get_current_user but returns None instead of raising 401.
    Used for endpoints that work both authenticated and unauthenticated."""
    try:
        return await get_current_user(request, db)
    except HTTPException:
        return None


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """FastAPI dependency — requires admin role."""
    if user.get("role") != "admin":
        raise HTTPException(403, "Nur Administratoren können diese Aktion ausführen.")
    return user
