# HarpoOutreach Web – FastAPI Application
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .models.db import SessionLocal, init_db
from .routes import auth, data, email_pipeline, prospecting, analytics, campaigns
from .routes import phase2 as phase2_routes
from .services import database_service as db_svc

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

logger = logging.getLogger("harpo.main")

app = FastAPI(
    title="HarpoOutreach Web",
    description="B2B Compliance Outreach Platform – Web API",
    version="2.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(auth.router, prefix="/api")
app.include_router(prospecting.router, prefix="/api")
app.include_router(email_pipeline.router, prefix="/api")
app.include_router(data.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(campaigns.router, prefix="/api")
app.include_router(phase2_routes.router, prefix="/api")


def _seed_settings():
    """Seed app_settings from environment variables (only if not already set)."""
    env_to_db = {
        "google_client_id": settings.google_client_id,
        "google_client_secret": settings.google_client_secret,
        "google_redirect_uri": settings.google_redirect_uri,
        "perplexity_api_key": settings.perplexity_api_key,
        "sender_name": settings.sender_name,
        "sender_email": settings.sender_email,
        "google_spreadsheet_id": settings.google_spreadsheet_id,
    }

    db = SessionLocal()
    try:
        seeded = []
        for key, value in env_to_db.items():
            if not value:
                continue
            existing = db_svc.get_setting(db, key)
            if not existing:
                db_svc.set_setting(db, key, value)
                # Mask secrets in log output
                if key in ("google_client_secret", "perplexity_api_key"):
                    display = value[:8] + "***"
                else:
                    display = value
                seeded.append(f"{key}={display}")
        if seeded:
            logger.info(f"Seeded {len(seeded)} settings from .env: {', '.join(seeded)}")
        else:
            logger.info("All settings already present in database — no seeding needed")
    finally:
        db.close()


def _init_phase2_tables():
    """Create Phase 2 tables (warmup, sender pool, tracking, users, ab tests, sequences)."""
    from .models.db import engine, Base
    from .models import db_phase2  # noqa: F401 — import so models are registered
    Base.metadata.create_all(bind=engine)
    logger.info("Phase 2 tables initialized")


def _migrate_users_table():
    """Add password_hash column if not exists (for email/password login)."""
    from sqlalchemy import text, inspect
    db = SessionLocal()
    try:
        insp = inspect(db.bind)
        cols = [c["name"] for c in insp.get_columns("users")]
        if "password_hash" not in cols:
            db.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR"))
            db.commit()
            logger.info("Migration: added password_hash column to users")
    except Exception as e:
        logger.warning(f"Migration check failed (may be fine on first run): {e}")
        db.rollback()
    finally:
        db.close()


@app.on_event("startup")
async def startup():
    init_db()
    logger.info("Database initialized")
    _init_phase2_tables()
    _migrate_users_table()
    _seed_settings()
    logger.info("Settings seeding complete — app ready")


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "HarpoOutreach Web", "version": "2.0.0"}
