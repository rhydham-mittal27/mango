"""mango/errors.py

Wires MangoError subclasses into FastAPI's exception-handler system, so a
service can raise a domain exception directly and get a correctly-shaped
HTTP response with no per-router try/except. Also installs a catch-all
handler for genuinely unexpected exceptions, so a bug never leaks a raw
traceback to a client — this is one of the most common beginner mistakes
in a hand-rolled FastAPI app (a 500 that dumps internal details).

Classes: none.

Functions (1):
    - register_error_handlers: installs mango's exception handlers on a
      FastAPI app. Call this once, in your app factory.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from mango.exceptions import MangoError

logger = logging.getLogger("mango.errors")  # logger for unexpected (non-MangoError) exceptions


def register_error_handlers(app: FastAPI) -> None:
    """Install mango's exception handlers on `app`.

    After calling this, any `raise mango.NotFoundError(...)` (or any other
    MangoError subclass) anywhere in a request's call stack becomes the
    correctly-shaped JSON error response automatically — routers and
    services don't need their own try/except HTTPException translation.
    """

    @app.exception_handler(MangoError)
    async def _handle_mango_error(request: Request, exc: MangoError) -> JSONResponse:
        """Convert any MangoError subclass into its declared HTTP status + detail."""
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        """Catch-all for anything that isn't a MangoError: log the real
        exception server-side, return a generic 500 to the client so
        internals (stack traces, DB errors, etc.) never leak over HTTP.
        """
        logger.exception("unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "internal server error"})
