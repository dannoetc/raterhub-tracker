# app/config.py
import os

class Settings:
    PROJECT_NAME = "RaterHub Tracker"
    VERSION = "0.5.2"
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"

    # JWT
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 1440))

    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

    # CORS
    ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "").split(",") or [
        "https://raterhub.steigenga.com",
        "https://api.raterhub.steigenga.com",
        "https://raterhub.com",
        "https://www.raterhub.com",
    ]

settings = Settings()
