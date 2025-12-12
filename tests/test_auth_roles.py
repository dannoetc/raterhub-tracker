import json

import pytest

from app.auth import decode_access_token, get_password_hash
from app.database import SessionLocal, engine
from app.db_models import Base, User
from app.main import app, CSRF_HEADER_NAME
from tests.test_csrf_api import JsonASGIClient


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def create_user(email: str, password: str, role: str = "user") -> User:
    db = SessionLocal()
    user = User(
        external_id=email,
        email=email,
        password_hash=get_password_hash(password),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user


async def _login(client: JsonASGIClient, email: str, password: str) -> tuple[int, dict]:
    status, _, csrf_body = await client.get_json("/auth/csrf")
    assert status == 200
    csrf_token = csrf_body["csrf_token"]

    status, _, body = await client.post_json(
        "/auth/login",
        {"email": email, "password": password},
        headers={CSRF_HEADER_NAME: csrf_token},
    )
    return status, body


@pytest.mark.anyio
async def test_standard_user_login_and_admin_denial():
    user = create_user("user@example.com", "hunter2", role="user")
    client = JsonASGIClient(app)

    status, body = await _login(client, user.email, "hunter2")
    assert status == 200
    assert "access_token" in body

    payload = decode_access_token(body["access_token"])
    assert payload["role"] == "user"

    status, _, raw_response = await client.request(
        "GET",
        "/admin/debug/user-sessions",
        headers={"authorization": f"Bearer {body['access_token']}"},
    )
    response = json.loads(raw_response.decode())
    assert status == 403
    assert response["detail"] == "Admin privileges required"


@pytest.mark.anyio
async def test_admin_login_and_access():
    admin = create_user("admin@example.com", "s3cretpass!", role="admin")
    client = JsonASGIClient(app)

    status, body = await _login(client, admin.email, "s3cretpass!")
    assert status == 200
    token = body["access_token"]

    payload = decode_access_token(token)
    assert payload["role"] == "admin"

    status, _, raw_sessions = await client.request(
        "GET",
        "/admin/debug/user-sessions",
        headers={"authorization": f"Bearer {token}"},
    )
    sessions = json.loads(raw_sessions.decode())
    assert status == 200
    assert sessions == []


@pytest.mark.anyio
async def test_invalid_credentials_return_unauthorized():
    create_user("user@example.com", "hunter2", role="user")
    client = JsonASGIClient(app)

    status, body = await _login(client, "user@example.com", "wrong-password")
    assert status == 401
    assert body["detail"] == "Invalid credentials"
