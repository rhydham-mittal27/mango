"""mango/repository.py

Generic SQLAlchemy repository. Collapses the common get/add/update/list/
count/search methods that every hand-written repository in the reference
backend repeats — a module only needs custom query methods for logic
that's genuinely specific to it (e.g. "accepted applications older than
a cutoff").

Classes (1):
    - MangoRepository: generic async repository over a single ORM model.

Functions: none — all behavior lives on MangoRepository's methods.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mango.exceptions import NotFoundError

ModelT = TypeVar("ModelT")  # the ORM model type a given MangoRepository subclass operates on


class MangoRepository(Generic[ModelT]):
    """Generic async repository over a single ORM model.

    Subclasses set `model` and, optionally, `search_fields` (column names
    eligible for the `search()` method's free-text filter). Everything
    else — get/add/update/delete/list/count — works out of the box.
    """

    model: type[ModelT]  # required — the ORM model class this repository targets
    search_fields: tuple[str, ...] = ()  # column names `search()` matches against with ILIKE

    def __init__(self, session: AsyncSession) -> None:
        """Bind this repository to a request-scoped async session."""
        self.session = session  # the active DB session for this request/unit of work

    async def get(self, id_: object, *, options: Sequence[Any] = ()) -> ModelT | None:
        """Fetch a single row by primary key, or None if it doesn't exist.

        `options` takes SQLAlchemy loader options (e.g.
        `selectinload(Model.children)`) for eager-loading relationships
        — without them, accessing a lazy relationship on the returned
        row outside an active session raises `DetachedInstanceError` /
        triggers an implicit (and, in async SQLAlchemy, invalid) lazy
        load. Left empty by default since not every model has
        relationships worth eager-loading on every fetch.
        """
        if options:
            stmt = select(self.model).where(self._pk_column() == id_).options(*options)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        return await self.session.get(self.model, id_)

    async def get_or_404(self, id_: object, *, options: Sequence[Any] = ()) -> ModelT:
        """Like `get()`, but raises `mango.NotFoundError` instead of
        returning None — for the common case where a missing row IS the
        error, not a value the caller has to remember to check."""
        entity = await self.get(id_, options=options)
        if entity is None:
            raise NotFoundError(f"{self.model.__name__} {id_!r} not found")
        return entity

    async def exists(self, id_: object) -> bool:
        """Whether a row with this primary key exists, without loading it."""
        stmt = select(func.count()).select_from(self.model).where(self._pk_column() == id_)
        result = await self.session.execute(stmt)
        return result.scalar_one() > 0

    async def add(self, entity: ModelT) -> ModelT:
        """Insert a new row and flush it so generated defaults (id, timestamps) are populated."""
        self.session.add(entity)  # stage the new row for insertion
        await self.session.flush()  # force the INSERT so server-generated columns are populated
        return entity

    async def add_many(self, entities: Sequence[ModelT]) -> Sequence[ModelT]:
        """Insert several new rows in one flush — cheaper than calling
        `add()` in a loop when the caller already has the full batch."""
        self.session.add_all(entities)  # stage all new rows for insertion
        await self.session.flush()  # force the INSERTs so server-generated columns are populated
        return entities

    async def update(self, entity: ModelT, **fields: object) -> ModelT:
        """Apply the given field updates to an existing row and flush them."""
        for field_name, value in fields.items():
            setattr(entity, field_name, value)  # apply one field update at a time
        await self.session.flush()  # push the updates to the DB
        return entity

    async def delete(self, entity: ModelT) -> None:
        """Delete a row."""
        await self.session.delete(entity)
        await self.session.flush()  # push the deletion to the DB

    async def delete_many(self, entities: Sequence[ModelT]) -> None:
        """Delete several rows in one flush."""
        for entity in entities:
            await self.session.delete(entity)
        await self.session.flush()  # push all the deletions to the DB in one round trip

    async def list(
        self, *, limit: int = 50, offset: int = 0, options: Sequence[Any] = ()
    ) -> Sequence[ModelT]:
        """List rows with simple offset/limit pagination, no filtering.
        `options` — see `get()`'s docstring for eager-loading relationships."""
        stmt = select(self.model).limit(limit).offset(offset)  # unfiltered, paginated query
        if options:
            stmt = stmt.options(*options)
        result = await self.session.execute(stmt)  # execute against the current session
        return result.scalars().all()

    async def filter_by(
        self, *, limit: int = 50, offset: int = 0, **equals: object
    ) -> Sequence[ModelT]:
        """List rows matching an exact-value filter on one or more
        columns — the common "get all X where column == value" query
        that doesn't need a full custom repository method.

            await repo.filter_by(status="active", owner_id=user.id)

        For anything beyond exact-match AND-combined equality (OR
        conditions, ranges, joins), write a custom method — this isn't a
        general query builder, just the boilerplate for the one pattern
        that's genuinely repetitive.
        """
        stmt = select(self.model)  # base query before filtering
        for column_name, value in equals.items():
            stmt = stmt.where(getattr(self.model, column_name) == value)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count(self) -> int:
        """Count all rows for this model."""
        stmt = select(func.count()).select_from(self.model)  # COUNT(*) over the whole table
        result = await self.session.execute(stmt)  # execute against the current session
        return result.scalar_one()

    def _pk_column(self):
        """Resolve this model's single primary-key column, for exists()/get() with options()."""
        pk_columns = list(self.model.__mapper__.primary_key)  # this model's primary-key column(s)
        if len(pk_columns) != 1:
            raise ValueError(
                f"{self.model.__name__} has a composite or missing primary key; "
                "exists()/get(options=...) only support a single-column primary key"
            )
        return pk_columns[0]

    async def search(
        self, query: str | None = None, *, limit: int = 50, offset: int = 0
    ) -> Sequence[ModelT]:
        """Free-text search across `search_fields` (ILIKE, OR-combined), paginated.

        Raises ValueError if called without `search_fields` declared — this
        is a deliberate fail-fast rather than silently returning an
        unfiltered `list()`.
        """
        stmt = self._search_statement(query)  # the (possibly filtered) base query, unpaginated
        stmt = stmt.limit(limit).offset(offset)  # paginate the (possibly filtered) query
        result = await self.session.execute(stmt)  # execute against the current session
        return result.scalars().all()

    async def list_page(self, *, limit: int = 50, offset: int = 0) -> tuple[Sequence[ModelT], int]:
        """Like `list()`, but also returns the total row count — feeds a
        `mango.Page` response so a client knows if more pages exist."""
        rows = await self.list(limit=limit, offset=offset)  # this page's rows
        total = await self.count()  # total rows across all pages
        return rows, total

    async def search_page(
        self, query: str | None = None, *, limit: int = 50, offset: int = 0
    ) -> tuple[Sequence[ModelT], int]:
        """Like `search()`, but also returns the total matching row count
        (not just this page's count) — feeds a `mango.Page` response."""
        stmt = self._search_statement(query)  # the (possibly filtered) base query, unpaginated
        count_stmt = select(func.count()).select_from(stmt.subquery())  # COUNT(*) over the filtered query
        total = (await self.session.execute(count_stmt)).scalar_one()  # total matching rows

        page_stmt = stmt.limit(limit).offset(offset)  # this page's slice of the filtered query
        rows = (await self.session.execute(page_stmt)).scalars().all()  # this page's rows
        return rows, total

    def _search_statement(self, query: str | None):
        """Build the (unpaginated) filtered SELECT statement search()/search_page() share."""
        if not self.search_fields:
            raise ValueError(f"{type(self).__name__} has no search_fields declared")
        stmt = select(self.model)  # base query before optional filtering
        if query:
            columns = [getattr(self.model, name) for name in self.search_fields]  # resolved column objects
            conditions = [column.ilike(f"%{query}%") for column in columns]  # one ILIKE per searchable column
            clause = conditions[0]  # accumulator for the OR-combined filter, seeded with the first condition
            for condition in conditions[1:]:
                clause = clause | condition  # OR each remaining condition into the accumulator
            stmt = stmt.where(clause)
        return stmt
