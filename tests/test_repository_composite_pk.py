"""tests/test_repository_composite_pk.py

Tests for MangoRepository's composite-primary-key support: get()/
exists()/get_or_404() accepting a tuple id_ for a model whose primary
key spans more than one column — the common shape for a pure join-table
model (e.g. a many-to-many association row), which has no reason for a
surrogate id column.

Classes: none — pytest test functions only.

Functions (7):
    - _session: pytest fixture, in-memory SQLite with a composite-PK
      Membership model.
    - test_get_with_composite_tuple_returns_row
    - test_get_with_composite_tuple_returns_none_when_missing
    - test_get_with_options_and_composite_tuple
    - test_exists_with_composite_tuple
    - test_get_or_404_with_composite_tuple
    - test_composite_pk_rejects_scalar_id
    - test_composite_pk_rejects_wrong_length_tuple
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import ForeignKey, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, selectinload

import mango


class _Base(DeclarativeBase):
    """Local declarative base for this test module only."""


class _Group(_Base):
    __tablename__ = "test_groups"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))


class _Membership(_Base):
    """A pure join-table row — composite (group_id, user_id) primary key,
    no surrogate id column, the natural modeling choice this feature targets."""

    __tablename__ = "test_memberships"

    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("test_groups.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(50), default="member")
    group: Mapped[_Group] = relationship()


class _MembershipRepository(mango.MangoRepository[_Membership]):
    model = _Membership


@pytest_asyncio.fixture
async def _session():
    """In-memory SQLite async session, schema created fresh per test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.mark.asyncio
async def test_get_with_composite_tuple_returns_row(_session: AsyncSession):
    """get() accepts a tuple id_ (group_id, user_id) for a composite-PK model."""
    group_id, user_id = uuid.uuid4(), uuid.uuid4()
    repo = _MembershipRepository(_session)
    await repo.add(_Membership(group_id=group_id, user_id=user_id, role="owner"))

    found = await repo.get((group_id, user_id))
    assert found is not None
    assert found.role == "owner"


@pytest.mark.asyncio
async def test_get_with_composite_tuple_returns_none_when_missing(_session: AsyncSession):
    """get() returns None (not an error) for a well-formed but non-matching composite tuple."""
    repo = _MembershipRepository(_session)
    found = await repo.get((uuid.uuid4(), uuid.uuid4()))
    assert found is None


@pytest.mark.asyncio
async def test_get_with_options_and_composite_tuple(_session: AsyncSession):
    """get(id_, options=...) — the path that used to hard-fail on any
    composite key at all — now builds a matching WHERE clause and honors
    eager-loading options together."""
    group_id, user_id = uuid.uuid4(), uuid.uuid4()
    group_repo = mango.MangoRepository(_session)
    group_repo.model = _Group
    await group_repo.add(_Group(id=group_id, name="Engineering"))

    repo = _MembershipRepository(_session)
    await repo.add(_Membership(group_id=group_id, user_id=user_id))

    found = await repo.get((group_id, user_id), options=(selectinload(_Membership.group),))
    assert found is not None
    assert found.group.name == "Engineering"  # no DetachedInstanceError/lazy-load needed


@pytest.mark.asyncio
async def test_exists_with_composite_tuple(_session: AsyncSession):
    """exists() works the same way as get() for a composite id_."""
    group_id, user_id = uuid.uuid4(), uuid.uuid4()
    repo = _MembershipRepository(_session)
    await repo.add(_Membership(group_id=group_id, user_id=user_id))

    assert await repo.exists((group_id, user_id)) is True
    assert await repo.exists((uuid.uuid4(), uuid.uuid4())) is False


@pytest.mark.asyncio
async def test_get_or_404_with_composite_tuple(_session: AsyncSession):
    """get_or_404 raises NotFoundError for a missing composite id_, same as the single-column case."""
    repo = _MembershipRepository(_session)
    with pytest.raises(mango.NotFoundError):
        await repo.get_or_404((uuid.uuid4(), uuid.uuid4()))


@pytest.mark.asyncio
async def test_composite_pk_rejects_scalar_id(_session: AsyncSession):
    """A scalar id_ against a composite-PK model raises a clear ValueError
    (not a confusing SQLAlchemy error), only on the options= path — the
    no-options path already delegates to Session.get(), which raises its
    own clear error for a mismatched identity."""
    repo = _MembershipRepository(_session)
    with pytest.raises(ValueError, match="composite primary key"):
        await repo.get(uuid.uuid4(), options=(selectinload(_Membership.group),))


@pytest.mark.asyncio
async def test_composite_pk_rejects_wrong_length_tuple(_session: AsyncSession):
    """A tuple of the wrong length against a composite-PK model raises,
    rather than silently building a clause that matches nothing."""
    repo = _MembershipRepository(_session)
    with pytest.raises(ValueError, match="composite primary key"):
        await repo.exists((uuid.uuid4(),))
