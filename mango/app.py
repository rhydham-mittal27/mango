"""mango/app.py

Wraps a plain FastAPI app and auto-mounts every registered module's
router — replacing the hand-maintained list of
`from app.modules.X.router import router as X_router` +
`app.include_router(X_router, ...)` lines in a conventional FastAPI
`main.py`. Mount order is derived from each module's `depends_on`
declaration via topological sort, with an explicit cycle error instead
of the confusing `ImportError: cannot import name ... (most likely due
to a circular import)` traceback a plain FastAPI/Python setup produces.
`App` also wires in production-hardening middleware by default
(security headers; optional rate limiting; optional CORS) and exposes
`use(plugin)` as an extension point for third-party/project-local code.

Classes (2):
    - MangoApp: thin wrapper around an EXISTING fastapi.FastAPI instance
      that mounts modules — for projects that already own their FastAPI
      app object and just want mango's mounting on top of it.
    - App: the full wrapper — creates and owns the FastAPI instance
      itself, is directly ASGI-callable (`uvicorn mymodule:app`), and
      exposes get/post/put/patch/delete/add_middleware/use/on_startup/
      on_shutdown/mount_all/routes/run — so a consumer never needs
      `from fastapi import FastAPI` at all. `routes()` lists every
      currently-mounted endpoint (path/methods/name); `mango routes`
      (mango/cli.py) uses it for CLI introspection.

Functions (1):
    - _topological_order: internal — orders module names so every
      module's dependencies are mounted before it, raising on cycles.
"""
from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mango.errors import register_error_handlers
from mango.module import ModuleSpec, get_registry
from mango.plugins import Plugin
from mango.security import RateLimitMiddleware, SecurityHeadersMiddleware


def _topological_order(specs: dict[str, ModuleSpec]) -> list[str]:
    """Return module names ordered so each module's `depends_on` entries
    come before it. Raises ValueError naming the exact cycle if one exists
    — deliberately more actionable than a Python ImportError traceback.
    """
    visited: set[str] = set()  # names fully placed into `order`
    visiting: set[str] = set()  # names currently on the recursion stack (cycle detection)
    order: list[str] = []  # the resulting mount order, built up via DFS post-order

    def visit(name: str, path: list[str]) -> None:
        """DFS helper: visit `name`'s dependencies first, then append `name`."""
        if name in visited:
            return
        if name in visiting:
            cycle = " -> ".join(path + [name])  # human-readable cycle trace for the error message
            raise ValueError(f"circular module dependency: {cycle}")
        if name not in specs:
            raise ValueError(f"module {name!r} is declared as a dependency but never registered")

        visiting.add(name)
        for dep in specs[name].depends_on:
            visit(dep, path + [name])
        visiting.discard(name)
        visited.add(name)
        order.append(name)

    for module_name in specs:
        visit(module_name, [])
    return order


class MangoApp:
    """Wraps a FastAPI app; `mount_all()` includes every registered
    module's router in dependency order, under a shared base prefix."""

    def __init__(
        self, fastapi_app: FastAPI, *, prefix: str = "", error_handlers: bool = False
    ) -> None:
        """Bind mango to an existing FastAPI app instance.

        `error_handlers=True` additionally calls
        `mango.register_error_handlers(fastapi_app)`, so MangoError
        subclasses map to clean HTTP responses without a separate call.
        Defaults to False so adopting MangoApp in a project that already
        has its own exception handlers doesn't silently override them —
        opt in explicitly once you're using mango's exceptions.
        """
        self.app = fastapi_app  # the underlying FastAPI app being configured
        self.prefix = prefix  # base path prefix applied in front of each module's own prefix
        if error_handlers:
            register_error_handlers(fastapi_app)

    def mount_all(self) -> list[str]:
        """Include every registered module's router, in dependency order.
        Returns the mount order (module names) for logging/introspection.
        """
        specs = get_registry()  # all modules registered so far via @mango.module
        order = _topological_order(specs)  # dependency-respecting mount order

        for module_name in order:
            spec = specs[module_name]  # this module's registered pieces
            if spec.router is None:
                continue  # modules with no router (e.g. pure model/schema packages) have nothing to mount
            full_prefix = f"{self.prefix}{spec.prefix}"  # base prefix + this module's own prefix
            self.app.include_router(spec.router, prefix=full_prefix, tags=[module_name])

        return order


class App:
    """The full mango wrapper: owns its own FastAPI instance internally so
    a consumer never has to `import fastapi`. Directly ASGI-callable, so
    the instance itself is what you point uvicorn at:

        # myproject/main.py
        import mango
        app = mango.App(title="My API", prefix="/api/v1")
        app.mount_all()

        # uvicorn myproject.main:app

    For projects that already have their own FastAPI instance and only
    want mango's mounting on top of it, use `MangoApp` instead — `App` is
    for starting a project entirely through mango.
    """

    def __init__(
        self,
        *,
        title: str = "mango app",
        prefix: str = "",
        error_handlers: bool = True,
        security_headers: bool = True,
        cors_origins: list[str] | None = None,
        rate_limit: tuple[int, float] | None = None,
        **fastapi_kwargs: Any,
    ) -> None:
        """Create the underlying FastAPI app and bind mango's mounting to it.

        `error_handlers` defaults to True here (unlike `MangoApp`) — `App`
        owns the whole FastAPI instance, so there's no pre-existing error
        handling it could silently override.

        `security_headers` (default True) adds
        `mango.security.SecurityHeadersMiddleware` — baseline headers a
        hand-rolled `FastAPI()` doesn't set.

        `cors_origins`, if given, adds FastAPI's own CORSMiddleware
        scoped to exactly those origins (never a wildcard with
        credentials — pass explicit origins, not `["*"]`, if the API
        needs cookies/Authorization headers from a browser).

        `rate_limit`, if given, is `(max_requests, window_seconds)` and
        adds `mango.security.RateLimitMiddleware` — see that class's
        docstring for what it does and doesn't protect against
        (in-memory, single-process; not a substitute for a real limiter
        in a horizontally-scaled deployment).
        """
        self._startup_hooks: list[Callable[[], Any]] = []  # functions on_startup() registers, run in order at startup
        self._shutdown_hooks: list[Callable[[], Any]] = []  # functions on_shutdown() registers, run in order at shutdown

        self._fastapi = FastAPI(
            title=title, lifespan=self._lifespan, **fastapi_kwargs
        )  # the underlying FastAPI app, owned entirely by this wrapper
        self._mango_app = MangoApp(self._fastapi, prefix=prefix, error_handlers=error_handlers)  # delegate for mounting

        if security_headers:
            self._fastapi.add_middleware(SecurityHeadersMiddleware)
        if cors_origins:
            self._fastapi.add_middleware(
                CORSMiddleware,
                allow_origins=cors_origins,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        if rate_limit is not None:
            max_requests, window_seconds = rate_limit  # unpack the (count, window) tuple
            self._fastapi.add_middleware(
                RateLimitMiddleware, max_requests=max_requests, window_seconds=window_seconds
            )

    @asynccontextmanager
    async def _lifespan(self, fastapi_app: FastAPI) -> AsyncIterator[None]:
        """FastAPI's modern lifespan hook — runs every registered startup
        hook (in order) before yielding control to the running app, then
        every shutdown hook (in order) after the app stops accepting
        requests. Built as a lifespan rather than the deprecated
        `add_event_handler("startup"/"shutdown", ...)` API, which newer
        FastAPI/Starlette versions have removed entirely.
        """
        for hook in self._startup_hooks:
            result = hook()
            if inspect.isawaitable(result):
                await result
        yield
        for hook in self._shutdown_hooks:
            result = hook()
            if inspect.isawaitable(result):
                await result

    def mount_all(self) -> list[str]:
        """Include every registered module's router, in dependency order. See MangoApp.mount_all()."""
        return self._mango_app.mount_all()

    def routes(self) -> list[dict[str, Any]]:
        """Every currently-mounted HTTP route, as `{"path", "methods", "name"}`
        dicts — call after `mount_all()` for the full picture. Used by
        `mango routes` for CLI introspection; also handy in a startup hook
        for logging what actually got mounted.

        Walks `self._fastapi.routes` recursively rather than assuming a
        flat list of leaf routes: newer FastAPI/Starlette versions wrap an
        `include_router()`'d router in a lazy `_IncludedRouter` proxy
        instead of eagerly copying its routes with the prefix already
        baked into each one — that proxy has no `.path` of its own, its
        real routes live on `.original_router.routes` with paths still
        relative to `.include_context.prefix`. Older versions (a flat
        list of routes with `.path` already fully resolved) still work
        the same way, since a route with its own `.path` is yielded
        immediately without needing to recurse.
        """
        result: list[dict[str, Any]] = []
        for route in self._fastapi.routes:
            result.extend(self._flatten_route(route, prefix=""))
        return result

    @staticmethod
    def _flatten_route(route: Any, *, prefix: str) -> list[dict[str, Any]]:
        """Yield one dict per leaf HTTP/websocket route reachable from
        `route`, resolving `prefix` against any nested `_IncludedRouter`-
        style wrapper. See `routes()`'s docstring for why this recursion
        exists."""
        path = getattr(route, "path", None)
        if path is not None:
            methods = sorted(getattr(route, "methods", None) or []) or (
                ["WS"] if "WebSocket" in type(route).__name__ else []
            )
            return [{"path": prefix + path, "methods": methods, "name": getattr(route, "name", "")}]

        original_router = getattr(route, "original_router", None)
        if original_router is None:
            return []  # not a route and not a recognized wrapper — nothing to report

        include_context = getattr(route, "include_context", None)
        nested_prefix = prefix + (getattr(include_context, "prefix", "") or "")
        result: list[dict[str, Any]] = []
        for sub_route in original_router.routes:
            result.extend(App._flatten_route(sub_route, prefix=nested_prefix))
        return result

    def add_middleware(self, middleware_cls: type, **options: Any) -> None:
        """Add ASGI middleware to the underlying FastAPI app."""
        self._fastapi.add_middleware(middleware_cls, **options)

    def use(self, plugin: Plugin) -> None:
        """Install a plugin: calls `plugin.install(self)`, handing the
        plugin this App instance to add middleware/routes/hooks to.
        See mango.plugins.Plugin for the interface a plugin implements."""
        plugin.install(self)

    def on_startup(self, fn: Callable[[], Any]) -> Callable[[], Any]:
        """Decorator: register `fn` to run once, on app startup.

            @app.on_startup
            async def warm_cache():
                ...
        """
        self._startup_hooks.append(fn)
        return fn

    def on_shutdown(self, fn: Callable[[], Any]) -> Callable[[], Any]:
        """Decorator: register `fn` to run once, on app shutdown.

            @app.on_shutdown
            async def close_connections():
                await db.dispose()
        """
        self._shutdown_hooks.append(fn)
        return fn

    def include_router(self, router: Any, **options: Any) -> None:
        """Escape hatch: include a router that isn't registered as a mango module."""
        self._fastapi.include_router(router, **options)

    def get(self, path: str, **options: Any):
        """Register a one-off GET route directly on the app (e.g. a /healthz check),
        without needing a full module for it. Same signature as FastAPI's own `@app.get`."""
        return self._fastapi.get(path, **options)

    def post(self, path: str, **options: Any):
        """Register a one-off POST route directly on the app. Same signature as FastAPI's `@app.post`."""
        return self._fastapi.post(path, **options)

    def put(self, path: str, **options: Any):
        """Register a one-off PUT route directly on the app. Same signature as FastAPI's `@app.put`."""
        return self._fastapi.put(path, **options)

    def patch(self, path: str, **options: Any):
        """Register a one-off PATCH route directly on the app. Same signature as FastAPI's `@app.patch`."""
        return self._fastapi.patch(path, **options)

    def delete(self, path: str, **options: Any):
        """Register a one-off DELETE route directly on the app. Same signature as FastAPI's `@app.delete`."""
        return self._fastapi.delete(path, **options)

    def run(self, *, host: str = "127.0.0.1", port: int = 8000, **uvicorn_kwargs: Any) -> None:
        """Run the app with uvicorn — `python main.py` instead of a separate
        `uvicorn module:app` command. Requires uvicorn to be installed
        (it's a dependency of mango itself via FastAPI's own ecosystem in
        most projects, but imported lazily here in case it isn't).
        """
        import uvicorn

        uvicorn.run(self._fastapi, host=host, port=port, **uvicorn_kwargs)

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        """ASGI entrypoint — delegates to the underlying FastAPI app, so
        `App` instances are directly usable as `uvicorn module:app`."""
        await self._fastapi(scope, receive, send)
