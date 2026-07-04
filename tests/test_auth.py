"""tests/test_auth.py

Tests for mango.Auth's dependency factories against a fake in-memory
"user store" and a trivial token scheme (token IS the user id, for test
simplicity — a real project plugs in real JWT verification).

Classes: none — pytest test functions only.

Functions (8):
    - _make_app: builds a FastAPI app wired to a fake Auth setup, with
      three routes exercising current_user/require_role/require, plus a
      websocket route exercising current_user_ws.
    - test_missing_token_is_401
    - test_unknown_user_is_401
    - test_wrong_role_is_403
    - test_correct_role_is_200
    - test_require_predicate_gate
    - test_ws_missing_token_is_rejected
    - test_ws_invalid_token_is_rejected
    - test_ws_valid_token_is_accepted
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import mango

_USERS = {
    "creator-token": {"id": "creator-token", "role": "creator", "approved": True},
    "brand-token": {"id": "brand-token", "role": "brand", "approved": False},
}  # fake user store keyed by "token" (== user id, for test simplicity)


class _FakeUser:
    """Stand-in for an ORM row — Auth only needs attribute access, not a real model."""

    def __init__(self, data: dict):
        self.id = data["id"]  # user id
        self.role = data["role"]  # user role
        self.approved = data["approved"]  # whether the user is approved


def _verify_token(token: str) -> dict:
    """Fake verifier: the raw token IS the claims' "sub", for test simplicity."""
    if token not in _USERS:
        raise ValueError("unknown token")
    return {"sub": token}


async def _load_user(session, claims: dict):
    """Fake loader: look the user up in the in-memory store, ignoring `session`."""
    data = _USERS.get(claims["sub"])
    return _FakeUser(data) if data else None


async def _noop_get_db():
    """Fake DB dependency — Auth requires one, but this test's loader ignores it."""
    yield None


@pytest.fixture
def _client() -> TestClient:
    """Build a FastAPI app with three routes exercising Auth's guards."""
    auth = mango.Auth(verify_token=_verify_token, load_user=_load_user, get_db=_noop_get_db)  # Auth under test

    app = FastAPI()
    mango.register_error_handlers(app)

    @app.get("/me")
    async def me(user=mango.Depends(auth.current_user())):
        return {"id": user.id}

    @app.get("/creator-only")
    async def creator_only(user=mango.Depends(auth.require_role("creator"))):
        return {"id": user.id}

    @app.get("/approved-only")
    async def approved_only(user=mango.Depends(auth.require(lambda u: u.approved))):
        return {"id": user.id}

    @app.websocket("/ws")
    async def ws_route(websocket: mango.WebSocket, user=mango.Depends(auth.current_user_ws())):
        await websocket.accept()
        await websocket.send_json({"id": user.id})

    return TestClient(app)


def test_missing_token_is_401(_client: TestClient):
    """No Authorization header at all -> 401."""
    response = _client.get("/me")
    assert response.status_code == 401


def test_unknown_user_is_401(_client: TestClient):
    """A token that doesn't verify -> 401, not a 500."""
    response = _client.get("/me", headers={"Authorization": "Bearer nonsense"})
    assert response.status_code == 401


def test_wrong_role_is_403(_client: TestClient):
    """A valid, known token with the wrong role -> 403."""
    response = _client.get("/creator-only", headers={"Authorization": "Bearer brand-token"})
    assert response.status_code == 403


def test_correct_role_is_200(_client: TestClient):
    """A valid token with the right role passes through."""
    response = _client.get("/creator-only", headers={"Authorization": "Bearer creator-token"})
    assert response.status_code == 200
    assert response.json() == {"id": "creator-token"}


def test_require_predicate_gate(_client: TestClient):
    """require(predicate) gates on an arbitrary check, not just role."""
    denied = _client.get("/approved-only", headers={"Authorization": "Bearer brand-token"})
    assert denied.status_code == 403  # brand-token is not approved

    allowed = _client.get("/approved-only", headers={"Authorization": "Bearer creator-token"})
    assert allowed.status_code == 200  # creator-token is approved


def test_ws_missing_token_is_rejected(_client: TestClient):
    """No ?token= query param at all -> the connection is rejected, not silently accepted."""
    with pytest.raises(Exception):  # noqa: B017 — TestClient's websocket rejection exception type isn't part of mango's own contract
        with _client.websocket_connect("/ws"):
            pass


def test_ws_invalid_token_is_rejected(_client: TestClient):
    """A token that doesn't verify -> rejected, same as the HTTP-route case."""
    with pytest.raises(Exception):  # noqa: B017
        with _client.websocket_connect("/ws?token=nonsense"):
            pass


def test_ws_valid_token_is_accepted(_client: TestClient):
    """A valid, known token -> accepted, and current_user_ws() resolved the right user."""
    with _client.websocket_connect("/ws?token=creator-token") as websocket:
        assert websocket.receive_json() == {"id": "creator-token"}
