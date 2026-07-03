"""mango/crud.py

Generates a full REST CRUD router (list/get/create/update/delete) from a
`MangoRepository` + Pydantic schemas — the single biggest source of
copy-pasted boilerplate in a beginner FastAPI project. A module that just
needs plain CRUD can go from ~80 lines of hand-written endpoints to one
`mango.build_crud_router(...)` call; a module with real business rules
still writes its own router (or its own extra routes registered
alongside the generated ones) — this is opt-in per module, not forced.

Classes: none.

Functions (1):
    - build_crud_router: builds and returns an APIRouter with
      GET (list), GET (by id), POST, PATCH, DELETE endpoints wired to a
      MangoRepository.
"""
from collections.abc import Callable
from typing import Any

# Deliberately NOT using `from __future__ import annotations` here: the
# route functions below are built dynamically with closure-local types
# (create_schema/update_schema/read_schema, each a per-call parameter, not
# a module-level name). FastAPI resolves parameter annotations by name
# against the function's module globals — stringified annotations would
# fail to resolve those closure locals and silently misroute `body` as a
# query parameter instead of the request body.

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from mango.exceptions import NotFoundError
from mango.pagination import Page
from mango.repository import MangoRepository
from mango.web import Depends, Query, Router


def build_crud_router(
    *,
    repository: type[MangoRepository],
    read_schema: type[BaseModel],
    get_db: Callable[..., Any],
    create_schema: type[BaseModel] | None = None,
    update_schema: type[BaseModel] | None = None,
    id_type: type = str,
    paginated: bool = False,
    prefix: str = "",
    tags: list[str] | None = None,
) -> Router:
    """Build a CRUD router for one model.

    Args:
        repository: a `MangoRepository` subclass (its `.model` is used).
        read_schema: Pydantic model for responses. Must have
            `model_config = ConfigDict(from_attributes=True)` so it can
            be built directly from an ORM row.
        get_db: the FastAPI dependency that yields an `AsyncSession`
            (e.g. `mango.Database(...).get_db`).
        create_schema: Pydantic model for POST bodies. Omit to disable
            the create endpoint (e.g. for read-only/admin-managed data).
        update_schema: Pydantic model for PATCH bodies, fields optional.
            Omit to disable the update endpoint.
        id_type: the Python type of the model's primary key, e.g.
            `uuid.UUID` or `int`. FastAPI uses this to parse/validate the
            `{item_id}` path segment before it reaches the repository —
            get this wrong (e.g. leave it as `str` for a `uuid.UUID`
            primary key) and lookups will fail at the DB layer instead of
            with a clean 422. Defaults to `str`.
        paginated: if True, `GET /` returns `mango.Page[read_schema]`
            (`{"items": [...], "total": N, "limit": L, "offset": O}`)
            instead of a bare list, so a client knows if more pages exist.
        prefix: path prefix for every route this router declares, e.g. "/things".
        tags: OpenAPI tags; defaults to `[prefix]` if not given.

    Returns:
        An APIRouter with `include_router()`-ready list/get/create/update/
        delete endpoints. GET/DELETE-by-id raise `mango.NotFoundError`
        (404) for a missing id — register `mango.register_error_handlers`
        on your app so that maps to a clean response.
    """
    router = Router(prefix=prefix, tags=tags or [prefix.strip("/") or "items"])  # this CRUD router's routes

    if paginated:
        page_schema = Page[read_schema]  # concrete Page[ThingRead] type for this router's response_model

        @router.get("/", response_model=page_schema)
        async def list_items(
            limit: int = Query(50, le=200),
            offset: int = Query(0, ge=0),
            session: AsyncSession = Depends(get_db),
        ) -> Any:
            """List rows, paginated by limit/offset, with a total count."""
            repo = repository(session)  # repository bound to this request's session
            rows, total = await repo.list_page(limit=limit, offset=offset)  # this page's rows + total count
            return page_schema(items=rows, total=total, limit=limit, offset=offset)

    else:

        @router.get("/", response_model=list[read_schema])
        async def list_items(
            limit: int = Query(50, le=200),
            offset: int = Query(0, ge=0),
            session: AsyncSession = Depends(get_db),
        ) -> list[Any]:
            """List rows, paginated by limit/offset."""
            repo = repository(session)  # repository bound to this request's session
            rows = await repo.list(limit=limit, offset=offset)  # paginated, unfiltered rows
            return rows

    @router.get("/{item_id}", response_model=read_schema)
    async def get_item(item_id: id_type, session: AsyncSession = Depends(get_db)) -> Any:
        """Fetch a single row by id, or 404 if it doesn't exist."""
        repo = repository(session)  # repository bound to this request's session
        row = await repo.get(item_id)  # the matching row, or None
        if row is None:
            raise NotFoundError(f"{repository.model.__name__} {item_id!r} not found")
        return row

    if create_schema is not None:

        @router.post("/", response_model=read_schema, status_code=201)
        async def create_item(body: create_schema, session: AsyncSession = Depends(get_db)) -> Any:
            """Create a new row from the request body."""
            repo = repository(session)  # repository bound to this request's session
            entity = repository.model(**body.model_dump())  # new ORM instance from the validated body
            return await repo.add(entity)

    if update_schema is not None:

        @router.patch("/{item_id}", response_model=read_schema)
        async def update_item(
            item_id: id_type, body: update_schema, session: AsyncSession = Depends(get_db)
        ) -> Any:
            """Apply a partial update to an existing row, or 404 if it doesn't exist."""
            repo = repository(session)  # repository bound to this request's session
            row = await repo.get(item_id)  # the row to update, or None
            if row is None:
                raise NotFoundError(f"{repository.model.__name__} {item_id!r} not found")
            fields = body.model_dump(exclude_unset=True)  # only fields the caller actually sent
            return await repo.update(row, **fields)

    @router.delete("/{item_id}", status_code=204)
    async def delete_item(item_id: id_type, session: AsyncSession = Depends(get_db)) -> None:
        """Delete a row by id, or 404 if it doesn't exist."""
        repo = repository(session)  # repository bound to this request's session
        row = await repo.get(item_id)  # the row to delete, or None
        if row is None:
            raise NotFoundError(f"{repository.model.__name__} {item_id!r} not found")
        await repo.delete(row)

    return router
