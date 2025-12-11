import os
from pathlib import Path


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")

class Settings:
    PROJECT_NAME = "RaterHub Tracker"
    VERSION = "0.5.2"
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"

    # JWT
    SECRET_KEY = os.getenv("SECRET_KEY")
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY environment variable must be set")
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 1440))

    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

    # Cookies
    SESSION_COOKIE_SECURE = _env_flag("SESSION_COOKIE_SECURE", default=not DEBUG)

    # Templates
    TEMPLATES_DIR = str(Path(__file__).resolve().parent / "templates") + "/"

    # CORS
    ALLOWED_ORIGINS = []
    for raw_origin in (
        os.getenv("ALLOWED_ORIGINS")
        or "https://raterhub.steigenga.com,https://api.raterhub.steigenga.com,https://raterhub.com,https://www.raterhub.com"
    ).split(","):
        origin = raw_origin.strip()
        if origin:
            ALLOWED_ORIGINS.append(origin)

settings = Settings()
