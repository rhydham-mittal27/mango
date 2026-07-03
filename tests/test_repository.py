"""tests/test_repository.py

Tests for MangoRepository's built-in CRUD/search against an in-memory
SQLite database — proves the generic base class works without any
module writing its own query methods.

Classes: none — pytest test functions only.

Functions (4):
    - _session: pytest fixture providing an in-memory SQLite async session.
    - test_add_and_get: a row added via the repository can be fetched back.
    - test_search_matches_ilike: search() filters on the declared field.
    - test_search_without_fields_raises: search() without search_fields
      declared fails fast rather than silently returning everything.
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from examples.hello_module.module import Base, Greeting, GreetingRepository


@pytest_asyncio.fixture
async def _session():
    """In-memory SQLite async session, schema created fresh per test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")  # ephemeral in-memory DB
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)  # create the Greeting table
    session_factory = async_sessionmaker(engine, expire_on_commit=False)  # session factory bound to this engine
    async with session_factory() as session:
        yield session


@pytest.mark.asyncio
async def test_add_and_get(_session: AsyncSession):
    """A row added via the repository can be fetched back by id."""
    repo = GreetingRepository(_session)  # repository under test
    greeting = Greeting(id=uuid.uuid4(), message="hi there")  # new row to insert
    await repo.add(greeting)

    fetched = await repo.get(greeting.id)  # round-tripped row
    assert fetched is not None
    assert fetched.message == "hi there"


@pytest.mark.asyncio
async def test_search_matches_ilike(_session: AsyncSession):
    """search() filters rows via a case-insensitive partial match on search_fields."""
    repo = GreetingRepository(_session)  # repository under test
    await repo.add(Greeting(id=uuid.uuid4(), message="hello world"))
    await repo.add(Greeting(id=uuid.uuid4(), message="goodbye"))

    results = await repo.search("HELLO")  # case-insensitive partial match
    assert len(results) == 1
    assert results[0].message == "hello world"


@pytest.mark.asyncio
async def test_search_without_fields_raises(_session: AsyncSession):
    """search() without search_fields declared fails fast instead of silently listing everything."""

    class _NoFieldsRepo(GreetingRepository):
        """Same model, but with search_fields cleared to prove the guard fires."""

        search_fields = ()

    repo = _NoFieldsRepo(_session)  # repository under test, deliberately missing search_fields
    with pytest.raises(ValueError, match="no search_fields declared"):
        await repo.search("anything")
