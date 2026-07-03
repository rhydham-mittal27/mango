"""mango/exceptions.py

Domain exceptions with a built-in HTTP status mapping, so a service can
`raise mango.NotFoundError("creator not found")` instead of every router
hand-writing a try/except block that translates a domain error into an
`HTTPException`. Paired with `mango.errors.register_error_handlers`,
which is what actually converts these into HTTP responses.

Classes (6):
    - MangoError: base class for all mango domain exceptions.
    - NotFoundError: 404 — the requested resource doesn't exist.
    - ConflictError: 409 — the request conflicts with current state
      (duplicate, already-decided, immutable field, etc.).
    - ForbiddenError: 403 — authenticated, but not allowed to do this.
    - UnauthorizedError: 401 — missing/invalid credentials.
    - BadRequestError: 400 — malformed/invalid input the framework's own
      422 validation wouldn't have already caught.

Functions: none — all behavior lives on MangoError's constructor.
"""
from __future__ import annotations


class MangoError(Exception):
    """Base class for every mango domain exception.

    Subclasses set a class-level `status_code`; `register_error_handlers`
    reads it to build the HTTP response, so raising the right subclass is
    enough — no router needs its own try/except mapping.
    """

    status_code: int = 500  # HTTP status this exception maps to; overridden by subclasses
    default_detail: str = "an error occurred"  # used if no message is passed to the constructor

    def __init__(self, detail: str | None = None) -> None:
        """Store the detail message shown in the error response (falls back to default_detail)."""
        self.detail = detail or self.default_detail  # the message returned in the JSON error body
        super().__init__(self.detail)


class NotFoundError(MangoError):
    """The requested resource doesn't exist. Maps to 404."""

    status_code = 404
    default_detail = "not found"


class ConflictError(MangoError):
    """The request conflicts with current state (duplicate, already-decided,
    immutable field, etc.). Maps to 409."""

    status_code = 409
    default_detail = "conflict"


class ForbiddenError(MangoError):
    """Authenticated, but not allowed to perform this action. Maps to 403."""

    status_code = 403
    default_detail = "forbidden"


class UnauthorizedError(MangoError):
    """Missing or invalid credentials. Maps to 401."""

    status_code = 401
    default_detail = "unauthorized"


class BadRequestError(MangoError):
    """Malformed/invalid input not already caught by FastAPI's own request
    validation. Maps to 400."""

    status_code = 400
    default_detail = "bad request"
