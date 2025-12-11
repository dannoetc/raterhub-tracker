# auth.py
import hashlib
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

import requests
from jose import JWTError, jwt
from passlib.context import CryptContext
from passlib.exc import UnknownHashError

from .config import settings

pwd_context = CryptContext(
    # pbkdf2_sha256 avoids bcrypt backend quirks and 72-byte limits for new hashes
    # while bcrypt/bcrypt_sha256 remain for verifying any existing hashes already
    # stored in the database.
    schemes=["pbkdf2_sha256", "bcrypt_sha256", "bcrypt"],
    deprecated="auto",
)

MIN_PASSWORD_LENGTH = 12
HIBP_LOOKUP_ENABLED = os.getenv("HIBP_LOOKUP_ENABLED", "false").lower() == "true"
HIBP_TIMEOUT_SECONDS = 2.0

# Small offline list to block extremely common or compromised passwords when
# network checks are unavailable.
_WEAK_PASSWORDS_PATH = Path(__file__).resolve().parent / "weak_passwords.txt"
try:
    _OFFLINE_WEAK_PASSWORDS = {
        line.strip()
        for line in _WEAK_PASSWORDS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
except FileNotFoundError:
    _OFFLINE_WEAK_PASSWORDS = set()


def _hibp_range_check(password: str) -> bool:
    """
    Optional k-anonymity lookup using the Have I Been Pwned range API.

    Returns True if the password hash suffix is present in the response.
    Network errors simply disable the check and return False so that offline
    environments still work while relying on the offline list.
    """

    if not HIBP_LOOKUP_ENABLED:
        return False

    sha1_hash = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = sha1_hash[:5], sha1_hash[5:]

    try:
        resp = requests.get(
            f"https://api.pwnedpasswords.com/range/{prefix}",
            timeout=HIBP_TIMEOUT_SECONDS,
        )
        if resp.status_code != 200:
            return False
    except requests.RequestException:
        return False

    for line in resp.text.splitlines():
        hash_suffix, _count = line.split(":")
        if hash_suffix.strip().upper() == suffix:
            return True
    return False


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except UnknownHashError:
        return False


def password_meets_complexity(password: str) -> bool:
    if len(password) < MIN_PASSWORD_LENGTH:
        return False

    has_upper = any(char.isupper() for char in password)
    has_lower = any(char.islower() for char in password)
    has_digit = any(char.isdigit() for char in password)
    has_symbol = any(not char.isalnum() for char in password)

    return has_upper and has_lower and has_digit and has_symbol


def is_password_breached(password: str) -> bool:
    if password in _OFFLINE_WEAK_PASSWORDS:
        return True

    return _hibp_range_check(password)


def is_password_reused(password: str, recent_hashes: Iterable[str]) -> bool:
    for hashed in recent_hashes:
        if verify_password(password, hashed):
            return True
    return False


def validate_password_policy(password: str, recent_hashes: Iterable[str] | None = None):
    """
    Validate password against length/complexity, breach screening, and recent reuse.

    Returns a tuple of (is_valid: bool, error_message: str | None). The error
    message remains general to avoid disclosing precise policy gaps to attackers.
    """

    recent_hashes = recent_hashes or []
    errors: list[str] = []

    if not password_meets_complexity(password):
        errors.append("Password must meet length and complexity requirements.")

    if is_password_breached(password):
        errors.append("Password is too weak or appears in known breaches.")

    if is_password_reused(password, recent_hashes):
        errors.append("Password cannot reuse a recently used credential.")

    if errors:
        return False, " ".join(errors)

    return True, None


def create_access_token(user: "User") -> str:
    to_encode = {
        "sub": str(user.id),
        "email": user.email,
        "exp": datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return payload
    except JWTError:
        return None
