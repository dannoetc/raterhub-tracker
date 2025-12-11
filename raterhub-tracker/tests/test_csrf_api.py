import json
from http.cookies import SimpleCookie

import pytest

from app.auth import get_password_hash
from app.database import SessionLocal, engine
from app.db_models import Base, User
from app.main import app, CSRF_HEADER_NAME


class JsonASGIClient:
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

    async def request(self, method: str, path: str, json_data: dict | None = None, headers: dict | None = None):
        header_list: list[tuple[bytes, bytes]] = []
        if headers:
            for k, v in headers.items():
                header_list.append((k.lower().encode(), str(v).encode()))

        cookie_header = self._cookie_header()
        if cookie_header:
            header_list.append((b"cookie", cookie_header.encode()))

        body = b""
        if json_data is not None:
            body = json.dumps(json_data).encode()
            header_list.extend(
                [
                    (b"content-type", b"application/json"),
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
            "headers": header_list,
            "app": self.app,
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
        return status_code, response_headers, body_bytes

    async def get_json(self, path: str):
        status, headers, body = await self.request("GET", path)
        return status, headers, json.loads(body.decode()) if body else {}

    async def post_json(self, path: str, payload: dict, headers: dict | None = None):
        status, resp_headers, body = await self.request("POST", path, json_data=payload, headers=headers)
        parsed = json.loads(body.decode()) if body else {}
        return status, resp_headers, parsed


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def anyio_backend():
    return "asyncio"


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


@pytest.mark.anyio
async def test_api_login_requires_csrf_token():
    create_user()
    client = JsonASGIClient(app)

    status, _, body = await client.post_json(
        "/auth/login",
        {"email": "user@example.com", "password": "hunter2"},
    )
    assert status == 400
    assert body["detail"] == "Invalid or missing CSRF token"

    status, _, csrf_body = await client.get_json("/auth/csrf")
    assert status == 200
    csrf_token = csrf_body["csrf_token"]

    status, _, login_body = await client.post_json(
        "/auth/login",
        {"email": "user@example.com", "password": "hunter2"},
        headers={CSRF_HEADER_NAME: csrf_token},
    )
    assert status == 200
    assert "access_token" in login_body


@pytest.mark.anyio
async def test_api_login_rejects_invalid_csrf_token():
    create_user()
    client = JsonASGIClient(app)

    await client.get_json("/auth/csrf")
    status, _, body = await client.post_json(
        "/auth/login",
        {"email": "user@example.com", "password": "hunter2"},
        headers={CSRF_HEADER_NAME: "not-valid"},
    )
    assert status == 400
    assert body["detail"] == "Invalid or missing CSRF token"


@pytest.mark.anyio
async def test_api_login_accepts_signed_token_without_cookie():
    create_user()
    issuing_client = JsonASGIClient(app)

    status, _, csrf_body = await issuing_client.get_json("/auth/csrf")
    assert status == 200
    csrf_token = csrf_body["csrf_token"]

    stateless_client = JsonASGIClient(app)
    status, _, body = await stateless_client.post_json(
        "/auth/login",
        {"email": "user@example.com", "password": "hunter2"},
        headers={CSRF_HEADER_NAME: csrf_token},
    )
    assert status == 200
    assert "access_token" in body


@pytest.mark.anyio
async def test_csrf_cookie_allows_cross_site_requests():
    client = JsonASGIClient(app)

    status, headers, body = await client.get_json("/auth/csrf")
    assert status == 200
    assert body["csrf_token"]

    set_cookie_headers = [value.decode() for name, value in headers if name.lower() == b"set-cookie"]
    assert set_cookie_headers, "CSRF cookie not set"

    jar = SimpleCookie()
    for header in set_cookie_headers:
        jar.load(header)

    assert "csrf_token" in jar
    morsel = jar["csrf_token"]

    # SameSite=None is required for the userscript on raterhub.com to send the cookie to the API origin.
    assert morsel["samesite"].lower() == "none"
    # Depending on Python version / cookie parser, the secure flag may parse as bool or string.
    assert str(morsel["secure"]).lower() == "true"
