"""tests/test_app_wrapper.py

Tests for mango.App — the full wrapper that owns its own FastAPI
instance so a consumer never imports fastapi directly — and mango.Schema.

Classes (1):
    - PingRead: mango.Schema used by the ad-hoc route test.

Functions (7):
    - test_app_is_directly_asgi_callable: an App instance works as a
      TestClient target the same way a raw FastAPI app would.
    - test_app_get_registers_adhoc_route: app.get(...) works without a
      full module, mirroring FastAPI's own @app.get.
    - test_app_mounts_registered_modules: App.mount_all() mounts modules
      the same way MangoApp does.
    - test_schema_builds_from_orm_like_object: Schema's from_attributes
      default lets it build from a plain object, not just a dict.
    - test_routes_lists_adhoc_and_mounted_routes: App.routes() against
      whatever FastAPI version is actually installed.
    - test_flatten_route_handles_lazy_included_router: App._flatten_route
      against a synthetic stub of newer FastAPI's lazy `_IncludedRouter`
      wrapper (real routes on `.original_router.routes`, prefix on
      `.include_context.prefix`, not baked into each route's own `.path`)
      — verified independent of which FastAPI version happens to be
      installed, since that shape isn't reachable with every version.
    - test_flatten_route_handles_plain_route: the older/simpler shape
      (a route with `.path` already fully resolved) still works.
"""
from fastapi.testclient import TestClient

import mango
from mango.app import App


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


def test_routes_lists_adhoc_and_mounted_routes():
    """App.routes() lists both an ad-hoc app.get(...) route and a route
    mounted via a full module, against whatever FastAPI version is
    actually installed in this environment."""
    from examples.hello_module import module as hello_module  # noqa: F401  (registers HelloModule)

    app = mango.App(title="test app", prefix="/api/v1")
    app.mount_all()

    @app.get("/direct")
    async def direct() -> dict:
        return {"ok": True}

    paths = {r["path"] for r in app.routes()}
    assert "/direct" in paths
    assert "/api/v1/hello" in paths


class _FakeLeafRoute:
    """Stands in for a Starlette Route/APIRoute/APIWebSocketRoute — the
    real thing has `.path`/`.methods`/`.name`, which is all `_flatten_route`
    reads."""

    def __init__(self, path: str, methods: set[str] | None = None, name: str = "") -> None:
        self.path = path
        self.methods = methods
        self.name = name


class _FakeIncludeContext:
    """Stands in for newer FastAPI's `_IncludedRouter.include_context` —
    only its `.prefix` is read."""

    def __init__(self, prefix: str) -> None:
        self.prefix = prefix


class _FakeOriginalRouter:
    """Stands in for `_IncludedRouter.original_router` — only `.routes` is read."""

    def __init__(self, routes: list) -> None:
        self.routes = routes


class _FakeIncludedRouter:
    """Stands in for newer FastAPI's `_IncludedRouter`: no `.path` of its
    own, real routes live on `.original_router.routes` with paths still
    relative to `.include_context.prefix` — the exact shape that broke
    App.routes() until _flatten_route was written to recurse into it."""

    def __init__(self, prefix: str, routes: list) -> None:
        self.original_router = _FakeOriginalRouter(routes)
        self.include_context = _FakeIncludeContext(prefix)


def test_flatten_route_handles_lazy_included_router():
    """A route reachable only through a lazy `_IncludedRouter`-shaped
    wrapper is still found, with its prefix correctly prepended — this
    is the exact bug: before this fix, App.routes() only checked for a
    top-level `.path` and silently produced nothing for routes nested
    this way (real-world impact: `mango routes` printed only /healthz
    and the OpenAPI routes, every actual module route missing)."""
    leaf = _FakeLeafRoute("/me", methods={"GET"}, name="me")
    wrapper = _FakeIncludedRouter(prefix="/api/v1/users", routes=[leaf])

    result = App._flatten_route(wrapper, prefix="")

    assert result == [{"path": "/api/v1/users/me", "methods": ["GET"], "name": "me"}]


def test_flatten_route_handles_nested_included_routers():
    """Two levels of lazy wrapping (a module's own router.include_router()
    of an admin sub-router, itself included into the FastAPI app) resolve
    prefixes cumulatively — the ecom_api categories/products pattern."""
    leaf = _FakeLeafRoute("/{item_id}", methods={"DELETE"}, name="delete_item")
    inner = _FakeIncludedRouter(prefix="", routes=[leaf])  # router.include_router(admin_router) — no extra prefix
    outer = _FakeIncludedRouter(prefix="/api/v1/products", routes=[inner])  # app.include_router(router, prefix=...)

    result = App._flatten_route(outer, prefix="")

    assert result == [{"path": "/api/v1/products/{item_id}", "methods": ["DELETE"], "name": "delete_item"}]


def test_flatten_route_handles_plain_route():
    """A route with its own fully-resolved `.path` (older FastAPI's flat
    shape, or a top-level route never wrapped at all) is returned as-is,
    with no recursion needed."""
    leaf = _FakeLeafRoute("/healthz", methods={"GET"}, name="healthz")

    result = App._flatten_route(leaf, prefix="")

    assert result == [{"path": "/healthz", "methods": ["GET"], "name": "healthz"}]


def test_schema_builds_from_orm_like_object():
    """Schema's default from_attributes=True lets it build from a plain
    object's attributes, not just a dict — the common ORM-row case."""

    class FakeRow:
        """Stands in for an ORM row with a `status` attribute."""

        status = "ok"

    built = PingRead.model_validate(FakeRow())
    assert built.status == "ok"
