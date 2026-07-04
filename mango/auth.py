"""mango/auth.py

Auth dependency factories: bearer-token verification, current-user
resolution, and role/attribute-based guards — the pattern every real app
hand-writes (verify JWT -> load user row -> check role -> 401/403) and
gets subtly wrong in a different way each time. mango doesn't own how
tokens are verified or where users are stored (that's provider-specific
— Supabase, Auth0, a plain session cookie, ...), so `Auth` takes both as
plain callables. What mango standardizes is the shape: one bearer-token
extraction, one claims-verification hook, one user-loading hook, and
`require_role`/`require` guards built on top, all wired through FastAPI
`Depends` the way `app/deps.py` in a hand-rolled project does — but
written once, not once per project.

Classes (1):
    - Auth: holds a token verifier + user loader; exposes
      get_claims/get_current_user/require_role/require/current_user/
      current_user_ws as FastAPI dependencies.

Functions: none — all behavior lives on Auth's methods.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from mango.exceptions import ForbiddenError, UnauthorizedError
from mango.web import Depends, WebSocket

ClaimsVerifier = Callable[[str], dict]  # raw bearer token -> decoded claims dict; must raise on an invalid token
UserLoader = Callable[[AsyncSession, dict], Awaitable[Any]]  # (session, claims) -> user row, or None if not found


class Auth:
    """Owns one project's token-verification + user-loading logic, and
    exposes ready-to-use FastAPI dependencies built on top of it.

        def verify(token: str) -> dict:
            return jwt.decode(token, SECRET, algorithms=["HS256"])

        async def load_user(session, claims) -> User | None:
            return await UserRepository(session).get(uuid.UUID(claims["sub"]))

        auth = mango.Auth(verify_token=verify, load_user=load_user, get_db=db.get_db)

        @router.get("/me")
        async def me(user = Depends(auth.current_user())):
            ...

        @router.post("/campaigns")
        async def create_campaign(user = Depends(auth.require_role("brand"))):
            ...

    Every guard raises a `mango.MangoError` subclass (`Unauthorized`/
    `Forbidden`), not a raw `HTTPException` — register
    `mango.register_error_handlers` (or use `mango.App`, which does this
    by default) for those to render as clean responses.
    """

    def __init__(
        self,
        *,
        verify_token: ClaimsVerifier,
        load_user: UserLoader,
        get_db: Callable[..., Any],
        role_attr: str = "role",
    ) -> None:
        """Bind this Auth instance to a project's token verifier, user
        loader, and DB dependency.

        `role_attr` is the attribute name `require_role`/`require_reader`
        read off the loaded user object to compare against the allowed
        roles (default `"role"`, i.e. `user.role`).
        """
        self._verify_token = verify_token  # raw token -> claims dict, raises on invalid token
        self._load_user = load_user  # (session, claims) -> user row or None
        self._get_db = get_db  # FastAPI dependency yielding an AsyncSession
        self._role_attr = role_attr  # attribute name read off the user object for role checks
        self._bearer = HTTPBearer(auto_error=False)  # extracts the raw bearer token; we control the 401 shape ourselves

    async def get_claims(
        self, credentials: HTTPAuthorizationCredentials | None = None
    ) -> dict:
        """Verify the bearer token and return its decoded claims — no DB lookup.

        Exposed as a plain method (not a bound FastAPI dependency) because
        it needs `Depends(self._bearer)` wired in as a default, which
        `get_claims_dependency` below sets up correctly for route use.
        """
        if credentials is None:
            raise UnauthorizedError("missing bearer token")
        try:
            return self._verify_token(credentials.credentials)
        except Exception as exc:
            raise UnauthorizedError("invalid token") from exc

    async def get_current_user(self, claims: dict, session: AsyncSession) -> Any:
        """Resolve the caller's user row from verified claims. Raises
        `mango.UnauthorizedError` if the token is valid but no matching
        user row exists (mirrors the "valid Supabase token but no local
        users row yet" case a real app has to handle)."""
        user = await self._load_user(session, claims)
        if user is None:
            raise UnauthorizedError("no user record for this token")
        return user

    def require_role(self, *roles: str) -> Callable[..., Awaitable[Any]]:
        """Dependency factory: 403 unless the current user's `role_attr`
        value is one of `roles`."""

        async def _check(
            credentials: HTTPAuthorizationCredentials | None = Depends(self._bearer),
            session: AsyncSession = Depends(self._get_db),
        ) -> Any:
            claims = await self.get_claims(credentials)
            user = await self.get_current_user(claims, session)
            if getattr(user, self._role_attr) not in roles:
                raise ForbiddenError("forbidden")
            return user

        return _check

    def require(self, predicate: Callable[[Any], bool], *, detail: str = "forbidden") -> Callable[..., Awaitable[Any]]:
        """Dependency factory for an arbitrary check on the loaded user
        object — for gates `require_role` doesn't cover (e.g. "approved
        AND not suspended", or a resource-ownership check that needs more
        than a role comparison)."""

        async def _check(
            credentials: HTTPAuthorizationCredentials | None = Depends(self._bearer),
            session: AsyncSession = Depends(self._get_db),
        ) -> Any:
            claims = await self.get_claims(credentials)
            user = await self.get_current_user(claims, session)
            if not predicate(user):
                raise ForbiddenError(detail)
            return user

        return _check

    def current_user(self) -> Callable[..., Awaitable[Any]]:
        """Dependency: resolves and returns the current user with no role/
        attribute check beyond "a valid token with a matching user row"."""

        async def _check(
            credentials: HTTPAuthorizationCredentials | None = Depends(self._bearer),
            session: AsyncSession = Depends(self._get_db),
        ) -> Any:
            claims = await self.get_claims(credentials)
            return await self.get_current_user(claims, session)

        return _check

    def current_user_ws(self, param_name: str = "token") -> Callable[..., Awaitable[Any]]:
        """Websocket-route equivalent of `current_user()`. A browser
        WebSocket connection can't set a custom `Authorization` header
        during its handshake, so this reads the token from a query
        parameter instead (`?token=...` by default) — the standard
        alternative shape — while reusing this Auth instance's own
        `verify_token`/`load_user` callables, so the two entry points
        never drift out of sync.

        On any failure (missing/invalid token, no matching user row)
        this closes the websocket itself with a 4401 code and raises
        `WebSocketDisconnect`, since raising a plain `mango.MangoError`
        (as the HTTP-route dependencies do) has no equivalent handling
        for a websocket connection — there's no HTTP response to shape,
        only the connection to close.

            @router.websocket("/ws/documents/{document_id}")
            async def collab(
                websocket: WebSocket,
                user = Depends(auth.current_user_ws()),
            ):
                await websocket.accept()
                ...
        """
        from mango.web import WebSocketDisconnect  # imported here, not at module top, to avoid a hard fastapi.WebSocket dependency for projects that never use this method

        async def _check(websocket: WebSocket, session: AsyncSession = Depends(self._get_db)) -> Any:
            token = websocket.query_params.get(param_name)
            if token is None:
                await websocket.close(code=4401, reason="missing token")
                raise WebSocketDisconnect(code=4401)
            try:
                claims = self._verify_token(token)
            except Exception as exc:
                await websocket.close(code=4401, reason="invalid token")
                raise WebSocketDisconnect(code=4401) from exc
            user = await self._load_user(session, claims)
            if user is None:
                await websocket.close(code=4401, reason="no user record for this token")
                raise WebSocketDisconnect(code=4401)
            return user

        return _check
