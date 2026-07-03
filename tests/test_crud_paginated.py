"""tests/test_crud_paginated.py

Tests that build_crud_router(paginated=True) returns a mango.Page
envelope instead of a bare list.

Classes: none — pytest test functions only.

Functions (1):
    - test_paginated_list_returns_page_envelope: GET / returns
      {"items": [...], "total": N, "limit": L, "offset": O}.
"""
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

import mango
from examples.hello_module.module import Base, Greeting, GreetingRepository
from tests.test_crud import GreetingCreate, GreetingRead


@pytest.fixture
def _paginated_client():
    """Build a FastAPI app with a paginated mango CRUD router over an in-memory SQLite DB."""
    db = mango.Database(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )  # ephemeral in-memory DB for this test; StaticPool shares one connection across sessions
    router = mango.build_crud_router(
        repository=GreetingRepository,
        read_schema=GreetingRead,
        create_schema=GreetingCreate,
        get_db=db.get_db,
        id_type=uuid.UUID,
        paginated=True,
        prefix="/greetings",
    )  # paginated variant of the generated CRUD router

    app = FastAPI()
    mango.register_error_handlers(app)
    app.include_router(router)

    with TestClient(app) as client:
        import asyncio

        asyncio.run(db.create_all(Base))  # create the greetings table before any request runs
        yield client


def test_paginated_list_returns_page_envelope(_paginated_client: TestClient):
    """GET / returns a Page envelope with items/total/limit/offset, not a bare list."""
    for _ in range(3):
        _paginated_client.post("/greetings/", json={"id": str(uuid.uuid4()), "message": "hi"})

    response = _paginated_client.get("/greetings/?limit=2&offset=0")
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 0
