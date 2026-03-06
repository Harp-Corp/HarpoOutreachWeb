# HarpoOutreachWeb – Setup & Deployment

## Voraussetzungen

- Docker & Docker Compose
- Google Cloud Projekt mit aktivierten APIs (Gmail, Sheets, OAuth)
- Perplexity API Key

## Quick Start

```bash
git clone https://github.com/Harp-Corp/HarpoOutreachWeb.git
cd HarpoOutreachWeb
chmod +x setup.sh && ./setup.sh
docker-compose up --build
```

Die App läuft dann unter **http://localhost:3000**.

## Manuelle .env-Erstellung

Falls `setup.sh` nicht verwendet wird:

```bash
cp .env.example .env
```

Dann `.env` bearbeiten und alle Werte eintragen.

## Google OAuth einrichten

1. [Google Cloud Console](https://console.cloud.google.com/apis/credentials) öffnen
2. OAuth 2.0 Client bearbeiten (Typ: Web Application)
3. **Authorized redirect URI** hinzufügen:
   ```
   http://localhost:8000/api/auth/google/callback
   ```
4. Client ID und Secret in die `.env` eintragen

## Architektur

```
┌─────────────────┐     ┌──────────────────┐     ┌────────────┐
│  React Frontend │────▶│  FastAPI Backend  │────▶│ PostgreSQL │
│  (nginx :3000)  │     │  (:8000)          │     │  (:5432)   │
└─────────────────┘     └──────────────────┘     └────────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
             Perplexity API      Gmail/Sheets API
```

## Credentials-Verwaltung

Beim Start liest das Backend die `.env`-Werte und schreibt sie automatisch in die Datenbank (`app_settings`-Tabelle). Credentials können danach auch über die Settings-Seite im UI geändert werden.

**Wichtig:** Die `.env`-Datei wird NIE in Git committet (ist in `.gitignore`).

## Docker Services

| Service   | Port | Beschreibung           |
|-----------|------|------------------------|
| frontend  | 3000 | React App (nginx)      |
| backend   | 8000 | FastAPI API Server     |
| db        | 5432 | PostgreSQL 16          |

## API Endpoints

| Methode | Pfad                        | Beschreibung              |
|---------|-----------------------------|---------------------------|
| GET     | /api/health                 | Health Check              |
| GET     | /api/auth/google/login      | OAuth Login starten       |
| GET     | /api/auth/google/callback   | OAuth Callback            |
| GET     | /api/auth/status            | Auth-Status prüfen        |
| POST    | /api/prospecting/search     | Firmensuche               |
| POST    | /api/prospecting/contacts   | Kontaktsuche              |
| GET     | /api/data/companies         | Firmen auflisten          |
| GET     | /api/data/leads             | Leads auflisten           |
| GET     | /api/data/settings          | Einstellungen lesen       |
| PUT     | /api/data/settings          | Einstellungen ändern      |
| GET     | /api/data/dashboard         | Dashboard-Statistiken     |
