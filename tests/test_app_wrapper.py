"""tests/test_app_wrapper.py

Tests for mango.App — the full wrapper that owns its own FastAPI
instance so a consumer never imports fastapi directly — and mango.Schema.

Classes (1):
    - PingRead: mango.Schema used by the ad-hoc route test.

Functions (4):
    - test_app_is_directly_asgi_callable: an App instance works as a
      TestClient target the same way a raw FastAPI app would.
    - test_app_get_registers_adhoc_route: app.get(...) works without a
      full module, mirroring FastAPI's own @app.get.
    - test_app_mounts_registered_modules: App.mount_all() mounts modules
      the same way MangoApp does.
    - test_schema_builds_from_orm_like_object: Schema's from_attributes
      default lets it build from a plain object, not just a dict.
"""
from fastapi.testclient import TestClient

import mango


class PingRead(mango.Schema):
    """Response schema for the ad-hoc /ping route in this test module."""

    status: str  # "ok"


def test_app_is_directly_asgi_callable():
    """An App instance is usable as a TestClient target, same as a raw FastAPI app."""
    app = mango.App(title="test app")

    @app.get("/ping", response_model=PingRead)
    async def ping() -> PingRead:
        return PingRead(status="ok")

    client = TestClient(app)  # App.__call__ delegates to the underlying FastAPI ASGI app
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_app_get_registers_adhoc_route():
    """app.get(...) registers a route without requiring a full mango module."""
    app = mango.App(title="test app")

    @app.get("/direct")
    async def direct() -> dict:
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/direct")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_app_mounts_registered_modules():
    """App.mount_all() mounts every registered mango module, same as MangoApp."""
    from examples.hello_module import module as hello_module  # noqa: F401  (registers HelloModule)

    app = mango.App(title="test app", prefix="/api/v1")
    order = app.mount_all()
    assert "hello" in order

    client = TestClient(app)
    response = client.get("/api/v1/hello")
    assert response.status_code == 200


def test_schema_builds_from_orm_like_object():
    """Schema's default from_attributes=True lets it build from a plain
    object's attributes, not just a dict — the common ORM-row case."""

    class FakeRow:
        """Stands in for an ORM row with a `status` attribute."""

        status = "ok"

    built = PingRead.model_validate(FakeRow())
    assert built.status == "ok"
