# HarpoOutreach Web – FastAPI Application
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .models.db import init_db
from .routes import auth, data, email_pipeline, prospecting

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

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


@app.on_event("startup")
async def startup():
    init_db()
    logging.info("Database initialized")


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "HarpoOutreach Web"}
