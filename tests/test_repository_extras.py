"""tests/test_repository_extras.py

Tests for MangoRepository's deeper ORM helpers: get_or_404, exists,
add_many, delete_many, filter_by.

Classes: none — pytest test functions only.

Functions (6):
    - _session: pytest fixture, in-memory SQLite.
    - test_get_or_404_raises_when_missing
    - test_get_or_404_returns_row_when_present
    - test_exists
    - test_add_many_and_delete_many
    - test_filter_by_matches_exact_values
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import mango
from examples.hello_module.module import Base, Greeting, GreetingRepository


@pytest_asyncio.fixture
async def _session():
    """In-memory SQLite async session, schema created fresh per test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")  # ephemeral in-memory DB
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)  # session factory bound to this engine
    async with session_factory() as session:
        yield session


@pytest.mark.asyncio
async def test_get_or_404_raises_when_missing(_session: AsyncSession):
    """get_or_404 raises mango.NotFoundError for a missing row, not None."""
    repo = GreetingRepository(_session)
    with pytest.raises(mango.NotFoundError):
        await repo.get_or_404(uuid.uuid4())


@pytest.mark.asyncio
async def test_get_or_404_returns_row_when_present(_session: AsyncSession):
    """get_or_404 returns the row directly (not wrapped) when it exists."""
    repo = GreetingRepository(_session)
    greeting = await repo.add(Greeting(id=uuid.uuid4(), message="hi"))
    found = await repo.get_or_404(greeting.id)
    assert found.id == greeting.id


@pytest.mark.asyncio
async def test_exists(_session: AsyncSession):
    """exists() is True for a real id and False for a random one, without loading the row."""
    repo = GreetingRepository(_session)
    greeting = await repo.add(Greeting(id=uuid.uuid4(), message="hi"))
    assert await repo.exists(greeting.id) is True
    assert await repo.exists(uuid.uuid4()) is False


@pytest.mark.asyncio
async def test_add_many_and_delete_many(_session: AsyncSession):
    """add_many inserts a batch in one flush; delete_many removes a batch in one flush."""
    repo = GreetingRepository(_session)
    rows = [Greeting(id=uuid.uuid4(), message=f"msg-{i}") for i in range(3)]
    await repo.add_many(rows)
    assert await repo.count() == 3

    await repo.delete_many(rows)
    assert await repo.count() == 0


@pytest.mark.asyncio
async def test_filter_by_matches_exact_values(_session: AsyncSession):
    """filter_by(**equals) returns only rows matching every given column exactly."""
    repo = GreetingRepository(_session)
    await repo.add(Greeting(id=uuid.uuid4(), message="hello"))
    await repo.add(Greeting(id=uuid.uuid4(), message="hello"))
    await repo.add(Greeting(id=uuid.uuid4(), message="goodbye"))

    matches = await repo.filter_by(message="hello")
    assert len(matches) == 2
    assert all(row.message == "hello" for row in matches)
