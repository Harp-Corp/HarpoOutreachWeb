# Application configuration via environment variables
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://harpo:harpo@db:5432/harpo"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # CORS (frontend origin)
    frontend_url: str = "http://localhost:3000"

    # Session secret (for cookie-based auth sessions)
    secret_key: str = "harpo-secret-change-in-production"

    # Google OAuth (server-side flow for the web app)
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"

    # Perplexity API
    perplexity_api_key: str = ""

    # Sender defaults
    sender_name: str = "Martin Foerster"
    sender_email: str = "mf@harpocrates-corp.com"

    # Google Sheets
    google_spreadsheet_id: str = ""

    # Batch settings
    batch_size: int = 10

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
