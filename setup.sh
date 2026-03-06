#!/bin/bash
# ─── HarpoOutreachWeb – Automatisches Setup ────────────
# Erstellt die .env Datei mit allen Credentials.
# ACHTUNG: Die .env darf NIE in Git committet werden!
#
# Nutzung:
#   chmod +x setup.sh && ./setup.sh
#   docker-compose up --build

set -e

ENV_FILE=".env"

echo "╔══════════════════════════════════════════════╗"
echo "║  HarpoOutreachWeb – Setup                    ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

if [ -f "$ENV_FILE" ]; then
    echo "⚠️  .env existiert bereits."
    read -p "Überschreiben? (j/N): " OVERWRITE
    if [ "$OVERWRITE" != "j" ] && [ "$OVERWRITE" != "J" ]; then
        echo "Abgebrochen."
        exit 0
    fi
fi

# Generiere zufälligen Secret Key
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null || openssl rand -base64 32)

# ─── Credentials abfragen ──────────────────────────────

echo ""
echo "── Google OAuth ──────────────────────────────"
echo "   (Aus Google Cloud Console → APIs & Credentials)"
echo ""
read -p "Google Client ID: " GOOGLE_CLIENT_ID

read -p "Google Client Secret: " GOOGLE_CLIENT_SECRET

echo ""
echo "── Perplexity API ────────────────────────────"
read -p "Perplexity API Key (pplx-...): " PERPLEXITY_API_KEY

echo ""
echo "── Optional: Google Spreadsheet ──────────────"
read -p "Spreadsheet ID (leer = überspringen): " SPREADSHEET_ID

# ─── .env schreiben ─────────────────────────────────────

cat > "$ENV_FILE" << EOF
# ─── HarpoOutreachWeb Environment ───────────────────────
# Generiert am $(date '+%Y-%m-%d %H:%M:%S')
# ACHTUNG: Diese Datei NIE in Git committen!

# Database
DATABASE_URL=postgresql://harpo:harpo@db:5432/harpo

# Session Secret
SECRET_KEY=${SECRET_KEY}

# Google OAuth
GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}
GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}
GOOGLE_REDIRECT_URI=http://localhost:3000/api/auth/google/callback

# Perplexity API
PERPLEXITY_API_KEY=${PERPLEXITY_API_KEY}

# Sender
SENDER_NAME=Martin Foerster
SENDER_EMAIL=mf@harpocrates-corp.com

# Google Sheets
GOOGLE_SPREADSHEET_ID=${SPREADSHEET_ID}

# Batch
BATCH_SIZE=10

# Frontend
FRONTEND_URL=http://localhost:3000
EOF

echo ""
echo "✅ .env wurde erstellt!"
echo ""
echo "── Wichtig ────────────────────────────────────"
echo "   Google Cloud Console → APIs & Credentials:"
echo "   Redirect URI muss eingetragen sein:"
echo "   → http://localhost:3000/api/auth/google/callback"
echo ""
echo "── Starten ────────────────────────────────────"
echo "   docker-compose up --build"
echo ""
echo "── Öffnen ─────────────────────────────────────"
echo "   → http://localhost:3000"
echo ""
