import os

import pytest

os.environ.setdefault("SECRET_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_policy.db")

from app.auth import (
    get_password_hash,
    validate_password_policy,
)


@pytest.mark.parametrize(
    "password",
    [
        "StrongPass!234",
        "Another$Good1",
    ],
)
def test_password_policy_accepts_complex_password(password):
    ok, message = validate_password_policy(password)
    assert ok is True
    assert message is None


def test_password_policy_rejects_simple_password():
    ok, message = validate_password_policy("short")
    assert ok is False
    assert "length and complexity" in message


def test_password_policy_rejects_breached_password_from_offline_list():
    ok, message = validate_password_policy("password123!")
    assert ok is False
    assert "known breaches" in message


def test_password_policy_blocks_recent_reuse():
    prior_hashes = [get_password_hash("ReuseMe!234")]
    ok, message = validate_password_policy("ReuseMe!234", recent_hashes=prior_hashes)
    assert ok is False
    assert "reuse" in message
