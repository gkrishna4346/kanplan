import os
from dotenv import load_dotenv

load_dotenv()


def _normalize_db_url(url):
    """Some hosts (Render, Heroku, etc.) hand out DATABASE_URL with the old
    'postgres://' scheme, but SQLAlchemy 1.4+/psycopg2 require 'postgresql://'.
    Normalizing here means you can paste whatever the host gives you as-is."""
    if url and url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

    SQLALCHEMY_DATABASE_URI = _normalize_db_url(os.environ.get("DATABASE_URL"))
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
    GOOGLE_DISCOVERY_URL = os.environ.get(
        "GOOGLE_DISCOVERY_URL",
        "https://accounts.google.com/.well-known/openid-configuration",
    )

    APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:5000")

    # Stream Chat (Convo) — free tier at getstream.io
    STREAM_API_KEY = os.environ.get("STREAM_API_KEY")
    STREAM_API_SECRET = os.environ.get("STREAM_API_SECRET")

    # Session cookie hardening
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Secure cookies only work over HTTPS — auto-enabled once APP_BASE_URL is
    # set to your real https:// domain, but stays off for local http:// dev
    # so login doesn't silently break on localhost.
    SESSION_COOKIE_SECURE = APP_BASE_URL.startswith("https://")
