"""tests/test_security_and_plugins.py

Tests for mango.App's production-hardening middleware (security headers,
rate limiting, CORS) and the plugin/extension mechanism (use(),
RequestIDPlugin, on_startup/on_shutdown).

Classes: none — pytest test functions only.

Functions (7):
    - test_security_headers_present_by_default
    - test_security_headers_can_be_disabled
    - test_rate_limit_blocks_after_threshold
    - test_rate_limit_off_by_default
    - test_use_installs_plugin
    - test_request_id_plugin_stamps_header
    - test_on_startup_hook_runs
"""
from fastapi.testclient import TestClient

import mango


def test_security_headers_present_by_default():
    """A fresh mango.App has security headers on every response, with no extra setup."""
    app = mango.App(title="t")

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    response = TestClient(app).get("/ping")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_security_headers_can_be_disabled():
    """security_headers=False opts out entirely."""
    app = mango.App(title="t", security_headers=False)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    response = TestClient(app).get("/ping")
    assert "X-Content-Type-Options" not in response.headers


def test_rate_limit_blocks_after_threshold():
    """rate_limit=(N, window) blocks the (N+1)th request within the window with a 429."""
    app = mango.App(title="t", rate_limit=(2, 60))

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200
    blocked = client.get("/ping")
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_rate_limit_off_by_default():
    """Without rate_limit=, there's no limit on repeated requests."""
    app = mango.App(title="t")

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    client = TestClient(app)
    for _ in range(10):
        assert client.get("/ping").status_code == 200


def test_use_installs_plugin():
    """app.use(plugin) calls plugin.install(app)."""
    installed_with = {}

    class _Plugin:
        def install(self, app):
            installed_with["app"] = app

    app = mango.App(title="t")
    app.use(_Plugin())
    assert installed_with["app"] is app


def test_request_id_plugin_stamps_header():
    """RequestIDPlugin adds a unique X-Request-ID to every response."""
    app = mango.App(title="t")
    app.use(mango.RequestIDPlugin())

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    client = TestClient(app)
    first = client.get("/ping")
    second = client.get("/ping")
    assert "X-Request-ID" in first.headers
    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]


def test_on_startup_hook_runs():
    """app.on_startup registers a function that runs when the app starts."""
    ran = {"value": False}
    app = mango.App(title="t")

    @app.on_startup
    async def _mark_ran():
        ran["value"] = True

    with TestClient(app):  # TestClient's context manager triggers startup/shutdown events
        assert ran["value"] is True
