# HarpoOutreach Web – FastAPI Application
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .models.db import SessionLocal, init_db
from .routes import auth, data, email_pipeline, prospecting, analytics
from .services import database_service as db_svc

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

logger = logging.getLogger("harpo.main")

app = FastAPI(
    title="HarpoOutreach Web",
    description="B2B Compliance Outreach Platform – Web API",
    version="1.0.0",
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


@app.on_event("startup")
async def startup():
    init_db()
    logger.info("Database initialized")
    _seed_settings()
    logger.info("Settings seeding complete — app ready")


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "HarpoOutreach Web"}
