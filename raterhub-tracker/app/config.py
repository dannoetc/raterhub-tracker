import os
from pathlib import Path

class Settings:
    PROJECT_NAME = "RaterHub Tracker"
    VERSION = "0.5.2"
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"

    # JWT
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 1440))

    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    
    # Templates
    TEMPLATES_DIR = str(Path(__file__).resolve().parent / "templates") + "/"

    # CORS
    ALLOWED_ORIGINS = (
        os.getenv("ALLOWED_ORIGINS")
        or "https://raterhub.steigenga.com,https://api.raterhub.steigenga.com,https://raterhub.com,https://www.raterhub.com"
    ).split(",")

settings = Settings()
