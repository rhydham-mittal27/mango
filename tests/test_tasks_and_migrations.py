"""tests/test_tasks_and_migrations.py

Tests for mango.run_in_background / Database.spawn (fire-and-forget
background work) and mango.init_migrations (Alembic scaffolding).

Classes: none — pytest test functions only.

Functions (4):
    - test_run_in_background_runs_and_is_awaitable_via_task
    - test_run_in_background_logs_exception_without_raising: a failing
      background task's exception is logged, not raised into the caller.
    - test_database_spawn_commits_on_success: db.spawn's session commits
      a row that a fresh session can then read back.
    - test_init_migrations_scaffolds_expected_files
"""
import asyncio
import uuid

import pytest

import mango
from examples.hello_module.module import Base, Greeting, GreetingRepository


@pytest.mark.asyncio
async def test_run_in_background_runs_and_is_awaitable_via_task():
    """A scheduled coroutine actually runs and its result is retrievable via the returned Task."""
    ran = {"value": False}  # mutated by the background coroutine to prove it ran

    async def _work():
        ran["value"] = True

    task = mango.run_in_background(_work())
    await task
    assert ran["value"] is True


@pytest.mark.asyncio
async def test_run_in_background_logs_exception_without_raising(caplog):
    """A background task's exception is logged, not propagated to the caller."""

    async def _boom():
        raise RuntimeError("background failure")

    task = mango.run_in_background(_boom(), name="boom-task")
    with caplog.at_level("ERROR", logger="mango.tasks"):
        await asyncio.sleep(0)  # let the task run and its done-callback fire
        await asyncio.gather(task, return_exceptions=True)  # drain the task without re-raising in this test
        await asyncio.sleep(0)  # let the done-callback log after the task actually completes

    assert any("boom-task" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_database_spawn_commits_on_success():
    """db.spawn(fn) opens its own session, runs fn, and commits — a fresh
    session afterward can read back what fn wrote."""
    db = mango.Database("sqlite+aiosqlite:///:memory:")  # ephemeral in-memory DB for this test
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    greeting_id = uuid.uuid4()  # id of the row the background task writes

    async def _write(session):
        await GreetingRepository(session).add(Greeting(id=greeting_id, message="from background"))

    task = db.spawn(_write)
    await task  # wait for the background task to finish for this test's assertion

    async with db.session_factory() as verify_session:
        row = await GreetingRepository(verify_session).get(greeting_id)
        assert row is not None
        assert row.message == "from background"


def test_init_migrations_scaffolds_expected_files(tmp_path):
    """init_migrations writes alembic.ini + migrations/env.py + script.py.mako + versions/."""
    ini_path = mango.init_migrations(str(tmp_path), base_import="app.db:Base")

    assert ini_path.exists()
    assert (tmp_path / "migrations" / "env.py").exists()
    assert (tmp_path / "migrations" / "script.py.mako").exists()
    assert (tmp_path / "migrations" / "versions").is_dir()

    env_contents = (tmp_path / "migrations" / "env.py").read_text(encoding="utf-8")
    assert "from app.db import Base" in env_contents
    assert 'os.environ["DATABASE_URL"]' in env_contents
