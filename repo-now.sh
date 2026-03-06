#!/bin/bash
# ─── repo-now: HarpoOutreachWeb – Clone, Configure & Run ───────
# Klont das Repo, erstellt .env, startet Docker.
# Nutzung: repo-now
set -e

REPO="https://github.com/Harp-Corp/HarpoOutreachWeb.git"
DIR="$HOME/SpecialProjects/HarpoOutreachWeb"

echo "╔══════════════════════════════════════════════╗"
echo "║  repo-now · HarpoOutreachWeb                 ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# 1. Altes Verzeichnis aufräumen
if [ -d "$DIR" ]; then
    echo "⚠️  $DIR existiert – wird entfernt..."
    (cd "$DIR" && docker-compose down 2>/dev/null) || true
    rm -rf "$DIR"
fi

# 2. Klonen
echo "📦 Klone Repository..."
mkdir -p "$HOME/SpecialProjects"
git clone "$REPO" "$DIR"
cd "$DIR"

# 3. .env erstellen
echo "🔑 Erstelle .env..."

# Credentials aus Umgebungsvariablen oder interaktiv
GOOGLE_CID="${HARPO_GOOGLE_CLIENT_ID:-}"
GOOGLE_CS="${HARPO_GOOGLE_CLIENT_SECRET:-}"
PPLX_KEY="${HARPO_PERPLEXITY_API_KEY:-}"
SHEET_ID="${HARPO_SPREADSHEET_ID:-}"

if [ -z "$GOOGLE_CID" ]; then
    echo ""
    echo "── Credentials ──────────────────────────────"
    echo "   (Tipp: Setze HARPO_GOOGLE_CLIENT_ID etc. in ~/.zshrc"
    echo "    fuer automatische Konfiguration)"
    echo ""
    read -p "Google Client ID: " GOOGLE_CID
    read -p "Google Client Secret: " GOOGLE_CS
    read -p "Perplexity API Key: " PPLX_KEY
    read -p "Spreadsheet ID (Enter = leer): " SHEET_ID
fi

SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null || openssl rand -base64 32)

cat > .env << ENVEOF
# ─── HarpoOutreachWeb Environment ───────────────────────
# Auto-generiert von repo-now am $(date '+%Y-%m-%d %H:%M:%S')

DATABASE_URL=postgresql://harpo:harpo@db:5432/harpo
SECRET_KEY=${SECRET_KEY}

# Google OAuth
GOOGLE_CLIENT_ID=${GOOGLE_CID}
GOOGLE_CLIENT_SECRET=${GOOGLE_CS}
GOOGLE_REDIRECT_URI=http://localhost:3000/api/auth/google/callback

# Perplexity
PERPLEXITY_API_KEY=${PPLX_KEY}

# Sender
SENDER_NAME=Martin Foerster
SENDER_EMAIL=mf@harpocrates-corp.com

# Google Sheets
GOOGLE_SPREADSHEET_ID=${SHEET_ID}

# Batch & Frontend
BATCH_SIZE=10
FRONTEND_URL=http://localhost:3000
ENVEOF

echo "   ✅ .env erstellt"

# 4. Berechtigungen
chmod +x setup.sh 2>/dev/null || true

# 5. Docker starten
echo ""
echo "🐳 Starte Docker Stack..."
echo "   → PostgreSQL + Backend (Port 8000) + Frontend (Port 3000)"
echo "   → Öffne http://localhost:3000"
echo ""
docker-compose up --build
