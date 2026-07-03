"""mango/db.py

One-line async SQLAlchemy setup: engine + session factory + a FastAPI
dependency, instead of the ~15 lines of boilerplate (create_async_engine,
async_sessionmaker, a get_db() generator with try/commit/except/rollback)
every hand-rolled FastAPI project rewrites from scratch. Also owns
`spawn()`, the fire-and-forget-background-work-with-its-own-session
pattern (see mango/tasks.py for why a background task can't reuse the
request's session).

Classes (1):
    - Database: holds the engine/session factory for one database and
      exposes the FastAPI dependency to use in routes/services, plus
      `spawn()` for background work needing its own session.

Functions: none — all behavior lives on Database's methods.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from mango.tasks import run_in_background


class Database:
    """Owns one async engine + session factory. Create one instance at
    startup and reuse its `.get_db` dependency across every route:

        db = mango.Database("postgresql+asyncpg://...")

        @router.get("/things")
        async def list_things(session: AsyncSession = Depends(db.get_db)):
            ...

    Commits automatically on a clean request, rolls back on any
    exception — the same commit-once-per-request pattern a hand-written
    `get_db()` generator implements, without writing it by hand.
    """

    def __init__(self, url: str, *, echo: bool = False, **engine_kwargs) -> None:
        """Create the engine and session factory for the given connection URL.

        `**engine_kwargs` is forwarded to `create_async_engine` verbatim —
        e.g. pass `poolclass=StaticPool, connect_args={"check_same_thread": False}`
        for an in-memory SQLite DB in tests, so every session shares the
        same connection instead of each getting its own empty database.
        """
        self.engine: AsyncEngine = create_async_engine(url, echo=echo, **engine_kwargs)  # the underlying async engine
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)  # produces request-scoped sessions

    async def get_db(self) -> AsyncIterator[AsyncSession]:
        """FastAPI dependency: yields a session, commits on success, rolls
        back and re-raises on any exception."""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()  # commit once, at the end of a successful request
            except Exception:
                await session.rollback()  # undo any partial writes before propagating the error
                raise

    async def create_all(self, base) -> None:
        """Create every table registered on `base.metadata` — convenience
        for local dev/tests; real projects use Alembic migrations instead.
        """
        async with self.engine.begin() as conn:
            await conn.run_sync(base.metadata.create_all)

    async def dispose(self) -> None:
        """Close the engine's connection pool — call on app shutdown."""
        await self.engine.dispose()

    def spawn(
        self, fn: Callable[[AsyncSession], Awaitable[None]], *, name: str | None = None
    ) -> asyncio.Task:
        """Run `fn(session)` as a fire-and-forget background task with its
        own fresh session (never the request's — that session closes when
        the response is sent, long before a background task would finish).
        Commits on success, rolls back on any exception, and logs (does
        not silently swallow) failures via `mango.tasks.run_in_background`.

            async def send_welcome_email(session: AsyncSession) -> None:
                ...

            db.spawn(send_welcome_email)
        """

        async def _run() -> None:
            """Open a fresh session, run fn against it, commit or roll back."""
            async with self.session_factory() as session:
                try:
                    await fn(session)
                    await session.commit()  # commit once, at the end of a successful run
                except Exception:
                    await session.rollback()  # undo any partial writes before propagating the error
                    raise

        return run_in_background(_run(), name=name or getattr(fn, "__name__", None))
