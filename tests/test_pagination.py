"""tests/test_pagination.py

Tests for mango.Page and MangoRepository.list_page/search_page against
an in-memory SQLite DB.

Classes: none — pytest test functions only.

Functions (3):
    - _seeded_db: pytest fixture with 5 greetings already inserted.
    - test_list_page_returns_total_across_all_pages: total reflects all
      rows, not just the current page's slice.
    - test_search_page_filters_and_counts: search_page's total reflects
      the filtered count, not the unfiltered table count.
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from examples.hello_module.module import Base, Greeting, GreetingRepository


@pytest_asyncio.fixture
async def _seeded_db():
    """In-memory SQLite session with 5 greetings, 2 matching "hello"."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")  # ephemeral in-memory DB
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)  # session factory bound to this engine
    async with session_factory() as session:
        repo = GreetingRepository(session)  # repository used to seed rows
        for message in ["hello world", "hello there", "goodbye", "hi", "yo"]:
            await repo.add(Greeting(id=uuid.uuid4(), message=message))
        yield session


@pytest.mark.asyncio
async def test_list_page_returns_total_across_all_pages(_seeded_db: AsyncSession):
    """total reflects all 5 rows even when limit only returns 2 of them."""
    repo = GreetingRepository(_seeded_db)  # repository under test
    rows, total = await repo.list_page(limit=2, offset=0)
    assert len(rows) == 2
    assert total == 5


@pytest.mark.asyncio
async def test_search_page_filters_and_counts(_seeded_db: AsyncSession):
    """search_page's total reflects the 2 rows matching "hello", not all 5."""
    repo = GreetingRepository(_seeded_db)  # repository under test
    rows, total = await repo.search_page("hello", limit=1, offset=0)
    assert len(rows) == 1  # page size respected
    assert total == 2  # total matches, not total rows in the table
