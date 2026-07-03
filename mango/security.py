"""mango/security.py

Production-hardening middleware `mango.App` wires in by default — the
things a hand-rolled `FastAPI()` doesn't set up on its own and a
beginner reliably forgets until a security review flags them: missing
security headers, and no limit on how fast one client can hit the API.

Classes (2):
    - SecurityHeadersMiddleware: sets X-Content-Type-Options,
      X-Frame-Options, Referrer-Policy, and (over HTTPS) HSTS on every
      response.
    - RateLimitMiddleware: in-memory sliding-window rate limit per
      client IP. Explicitly NOT a substitute for a real rate limiter
      (Redis-backed, multi-process-aware) in a horizontally-scaled
      deployment — see its docstring for exactly where it stops being
      enough.

Functions: none — all behavior lives on the middleware classes.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Sets baseline security headers on every response.

    - `X-Content-Type-Options: nosniff` — stops a browser from
      MIME-sniffing a response into executing as something it isn't.
    - `X-Frame-Options: DENY` — blocks the API's responses from being
      framed (clickjacking defense; irrelevant for a pure JSON API, but
      free and standard).
    - `Referrer-Policy: strict-origin-when-cross-origin` — avoids
      leaking full URLs (which may contain query-string secrets) to
      third-party referrers.
    - `Strict-Transport-Security` — only set when the request itself
      arrived over HTTPS (checking `request.url.scheme`), since sending
      HSTS over plain HTTP is meaningless and can be actively wrong
      behind a misconfigured proxy that terminates TLS upstream.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Run the request, then stamp security headers onto the response."""
        response = await call_next(request)  # the response from the rest of the app
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-memory sliding-window rate limit, keyed by client IP.

    `RateLimitMiddleware(app, max_requests=100, window_seconds=60)`
    allows at most `max_requests` per `window_seconds` per IP, returning
    429 with a `Retry-After` header once exceeded.

    **This is single-process, in-memory state.** It resets on restart
    and does NOT coordinate across multiple worker processes or
    replicas — running 4 uvicorn workers means each one enforces the
    limit independently, so the *effective* limit is `max_requests * 4`.
    Fine for a single-instance deployment or as a basic abuse guard;
    replace with a Redis-backed limiter (or your load balancer/API
    gateway's own rate limiting) before relying on this for a
    horizontally-scaled, security-critical limit.
    """

    def __init__(self, app, *, max_requests: int = 100, window_seconds: float = 60.0) -> None:
        """Configure the limit: `max_requests` per `window_seconds`, per client IP."""
        super().__init__(app)
        self.max_requests = max_requests  # requests allowed per window, per IP
        self.window_seconds = window_seconds  # the sliding window's length in seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)  # client IP -> timestamps of recent requests

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Reject with 429 if this client has exceeded the limit; otherwise proceed."""
        client_ip = request.client.host if request.client else "unknown"  # best-effort client identifier
        now = time.monotonic()  # current time, for the sliding window
        hits = self._hits[client_ip]  # this client's recent request timestamps

        while hits and hits[0] <= now - self.window_seconds:
            hits.popleft()  # drop timestamps that have aged out of the window

        if len(hits) >= self.max_requests:
            retry_after = self.window_seconds - (now - hits[0])  # seconds until the oldest hit ages out
            return JSONResponse(
                status_code=429,
                content={"detail": "rate limit exceeded"},
                headers={"Retry-After": str(max(1, int(retry_after)))},
            )

        hits.append(now)
        return await call_next(request)
