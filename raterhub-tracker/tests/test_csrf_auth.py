import asyncio
import os
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlencode

import pytest

os.environ.setdefault("SECRET_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_csrf.db")

from app.auth import get_password_hash
from app.database import SessionLocal, engine
from app.db_models import Base, User
from app.main import app


class ASGIResponse:
    def __init__(self, status_code: int, headers: list[tuple[bytes, bytes]], body: bytes):
        self.status_code = status_code
        self.headers = headers
        self.body = body

    @property
    def text(self) -> str:
        return self.body.decode()


class SimpleASGIClient:
    def __init__(self, app):
        self.app = app
        self.cookies: dict[str, str] = {}

    def _cookie_header(self) -> str | None:
        if not self.cookies:
            return None
        return "; ".join(f"{k}={v}" for k, v in self.cookies.items())

    def _update_cookies(self, headers: list[tuple[bytes, bytes]]):
        jar = SimpleCookie()
        for name, value in headers:
            if name.lower() == b"set-cookie":
                jar.load(value.decode())
        for key, morsel in jar.items():
            self.cookies[key] = morsel.value

    async def _request(self, method: str, path: str, data: dict | None = None) -> ASGIResponse:
        headers: list[tuple[bytes, bytes]] = []

        cookie_header = self._cookie_header()
        if cookie_header:
            headers.append((b"cookie", cookie_header.encode()))

        body = b""
        if data:
            body = urlencode(data, doseq=True).encode()
            headers.extend(
                [
                    (b"content-type", b"application/x-www-form-urlencoded"),
                    (b"content-length", str(len(body)).encode()),
                ]
            )

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": method.upper(),
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": headers,
            "app": app,
        }

        messages: list[dict] = []

        async def receive():
            nonlocal body
            if body is None:
                return {"type": "http.disconnect"}
            chunk = body
            body = None
            return {"type": "http.request", "body": chunk, "more_body": False}

        async def send(message):
            messages.append(message)

        await self.app(scope, receive, send)

        status_code = 500
        response_headers: list[tuple[bytes, bytes]] = []
        body_bytes = b""

        for message in messages:
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers = message.get("headers", [])
            elif message["type"] == "http.response.body":
                body_bytes += message.get("body", b"")

        self._update_cookies(response_headers)
        return ASGIResponse(status_code=status_code, headers=response_headers, body=body_bytes)

    def request(self, method: str, path: str, data: dict | None = None) -> ASGIResponse:
        return asyncio.run(self._request(method, path, data=data))

    def get(self, path: str) -> ASGIResponse:
        return self.request("GET", path)

    def post(self, path: str, data: dict) -> ASGIResponse:
        return self.request("POST", path, data=data)


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def create_user(email: str = "user@example.com", password: str = "hunter2"):
    db = SessionLocal()
    user = User(
        external_id=email,
        email=email,
        password_hash=get_password_hash(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user


def test_login_requires_valid_csrf_token():
    create_user()
    client = SimpleASGIClient(app)

    client.get("/login")
    csrf_token = client.cookies.get("csrf_token")

    post_resp = client.post(
        "/login",
        data={
            "email": "user@example.com",
            "password": "hunter2",
            "csrf_token": csrf_token,
        },
    )

    assert post_resp.status_code == 303
    assert "access_token" in client.cookies


def test_login_rejects_missing_or_invalid_csrf():
    create_user()
    client = SimpleASGIClient(app)

    missing_token = client.post(
        "/login",
        data={"email": "user@example.com", "password": "hunter2"},
    )
    assert missing_token.status_code == 400
    assert "Invalid or missing CSRF token" in missing_token.text

    client.get("/login")
    invalid_token = client.post(
        "/login",
        data={
            "email": "user@example.com",
            "password": "hunter2",
            "csrf_token": "not-the-right-token",
        },
    )
    assert invalid_token.status_code == 400
    assert "Invalid or missing CSRF token" in invalid_token.text


def test_register_requires_valid_csrf_token():
    client = SimpleASGIClient(app)

    client.get("/register")
    csrf_token = client.cookies.get("csrf_token")

    post_resp = client.post(
        "/register",
        data={
            "email": "newuser@example.com",
            "password": "hunter2",
            "password_confirm": "hunter2",
            "csrf_token": csrf_token,
        },
    )

    assert post_resp.status_code == 303
    assert "access_token" in client.cookies


def test_register_rejects_missing_csrf_token():
    client = SimpleASGIClient(app)

    post_resp = client.post(
        "/register",
        data={
            "email": "newuser@example.com",
            "password": "hunter2",
            "password_confirm": "hunter2",
        },
    )

    assert post_resp.status_code == 400
    assert "Invalid or missing CSRF token" in post_resp.text
