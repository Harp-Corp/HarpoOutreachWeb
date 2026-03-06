# HarpoOutreach Web

Web-basierte Version der HarpoOutreach B2B-Compliance-Outreach-Plattform. Ermöglicht Prospecting, E-Mail-Pipeline, Social-Post-Generierung und Dashboard-Übersicht im Browser.

## Architektur

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────┐
│  React Frontend │────▶│  FastAPI Backend  │────▶│ PostgreSQL  │
│  (Vite + React) │     │  (Python 3.12)   │     │  (Docker)   │
└─────────────────┘     └──────────────────┘     └─────────────┘
         │                       │
         │                       ├──▶ Perplexity API (Prospecting, AI)
         │                       ├──▶ Gmail API (E-Mail senden)
         │                       └──▶ Google OAuth (Authentifizierung)
         │
         └── Nginx Reverse Proxy (Production)
```

## Schnellstart (Docker)

```bash
# 1. Repo klonen
git clone https://github.com/Harp-Corp/HarpoOutreachWeb.git
cd HarpoOutreachWeb

# 2. Environment konfigurieren
cp .env.example .env
# .env bearbeiten: API Keys, Google OAuth Credentials eintragen

# 3. Starten
docker compose up --build

# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

## API-Endpunkte

### Prospecting
- `POST /api/prospecting/find-companies?industry=...&region=...` – Unternehmen suchen
- `POST /api/prospecting/find-contacts/{company_id}` – Kontakte finden
- `POST /api/prospecting/verify-email/{lead_id}` – E-Mail verifizieren
- `POST /api/prospecting/verify-all` – Alle E-Mails verifizieren

### E-Mail Pipeline
- `POST /api/email/draft/{lead_id}` – E-Mail-Entwurf erstellen
- `POST /api/email/draft-all` – Alle Entwürfe erstellen
- `POST /api/email/approve/{lead_id}` – E-Mail genehmigen
- `POST /api/email/approve-all` – Alle genehmigen
- `POST /api/email/send/{lead_id}` – E-Mail senden
- `POST /api/email/send-all` – Alle genehmigten senden (Batch)
- `POST /api/email/draft-follow-up/{lead_id}` – Follow-Up erstellen

### Daten
- `GET /api/data/companies` – Alle Unternehmen
- `GET /api/data/leads` – Alle Leads
- `GET /api/data/social-posts` – Alle Social Posts
- `POST /api/data/social-posts/generate` – Social Post generieren
- `GET /api/data/dashboard` – Dashboard-Statistiken
- `GET/PUT /api/data/settings` – Einstellungen

### Authentifizierung
- `GET /api/auth/google/login` – OAuth-Flow starten
- `GET /api/auth/google/callback` – OAuth-Callback
- `GET /api/auth/status` – Auth-Status prüfen
- `POST /api/auth/refresh` – Token erneuern
- `POST /api/auth/logout` – Abmelden

## Deployment (Google Cloud Run)

```bash
# Backend-Image bauen und pushen
docker build -t europe-west1-docker.pkg.dev/harpo-outreach/harpo-docker/backend:latest ./backend
docker push europe-west1-docker.pkg.dev/harpo-outreach/harpo-docker/backend:latest

# Frontend-Image bauen und pushen
docker build -t europe-west1-docker.pkg.dev/harpo-outreach/harpo-docker/frontend:latest ./frontend
docker push europe-west1-docker.pkg.dev/harpo-outreach/harpo-docker/frontend:latest

# Cloud Run deployen
gcloud run deploy harpo-backend \
  --image europe-west1-docker.pkg.dev/harpo-outreach/harpo-docker/backend:latest \
  --region europe-west1 \
  --set-env-vars "DATABASE_URL=..." \
  --allow-unauthenticated
```

## Technologie-Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy, asyncpg
- **Frontend:** React 18, Vite, React Router
- **Datenbank:** PostgreSQL 16
- **Container:** Docker, Docker Compose
- **Cloud:** Google Cloud Run, Artifact Registry
- **APIs:** Perplexity AI (sonar-pro), Gmail API, Google OAuth 2.0
