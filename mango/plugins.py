"""mango/plugins.py

An extension point for third-party or project-local code to hook into a
`mango.App` without `App` needing to know about it in advance — the
thing a "real" framework has and a bare convenience layer doesn't.
`App.use(plugin)` calls `plugin.install(app)`, handing the plugin the
same `App` instance a project's own `main.py` has, so a plugin can add
middleware, routes, startup/shutdown hooks, or anything else `App`
itself exposes.

Classes (2):
    - Plugin: the protocol a plugin implements — just one method,
      `install(app)`.
    - RequestIDPlugin: a built-in reference plugin (adds a unique
      `X-Request-ID` response header per request) — proves the
      mechanism works and doubles as a template for writing your own.

Functions: none.
"""
from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


@runtime_checkable
class Plugin(Protocol):
    """The interface `App.use(...)` expects. Implement `install(app)` and
    do whatever setup your plugin needs — add middleware, register
    routes, hook startup/shutdown, read/write attributes on `app` for
    other plugins to find later.

        class MyPlugin:
            def install(self, app: mango.App) -> None:
                app.add_middleware(MyMiddleware)

        app.use(MyPlugin())
    """

    def install(self, app: "object") -> None:
        """Wire this plugin into `app`. `app` is a `mango.App` instance;
        typed as `object` here only to avoid a circular import between
        mango/plugins.py and mango/app.py."""
        ...


class _RequestIDMiddleware(BaseHTTPMiddleware):
    """Stamps a unique `X-Request-ID` on every response — for
    correlating a client-reported issue with server logs."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Generate a request id, run the request, stamp the id onto the response."""
        request_id = str(uuid.uuid4())  # unique id for this request
        request.state.request_id = request_id  # available to route handlers via request.state
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class RequestIDPlugin:
    """Reference plugin: adds a unique `X-Request-ID` header to every
    response, and makes it available to handlers as
    `request.state.request_id`.

        app.use(mango.RequestIDPlugin())
    """

    def install(self, app: "object") -> None:
        """Add the request-id middleware to `app`."""
        app.add_middleware(_RequestIDMiddleware)  # type: ignore[attr-defined]
