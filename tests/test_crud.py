"""tests/test_crud.py

End-to-end test of mango.Database + mango.build_crud_router: a full
list/get/create/update/delete REST API built from a MangoRepository and
two Pydantic schemas, with no hand-written route bodies.

Classes (2):
    - GreetingCreate: request schema for POST.
    - GreetingRead: response schema for all endpoints.

Functions (2):
    - _client: pytest fixture building the app under test.
    - test_crud_lifecycle: create, read, list, update, delete — in order,
      against a single running app.
"""
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict
from sqlalchemy.pool import StaticPool

import mango
from examples.hello_module.module import Base, Greeting, GreetingRepository


class GreetingCreate(BaseModel):
    """POST body for creating a Greeting."""

    id: uuid.UUID  # caller-supplied id (a real app would usually generate this server-side)
    message: str  # the greeting text


class GreetingUpdate(BaseModel):
    """PATCH body for updating a Greeting — all fields optional."""

    message: str | None = None  # new greeting text, if changing it


class GreetingRead(BaseModel):
    """Response schema for a Greeting."""

    model_config = ConfigDict(from_attributes=True)  # required so it can be built directly from an ORM row

    id: uuid.UUID
    message: str


@pytest.fixture
def _client():
    """Build a FastAPI app with a mango CRUD router over an in-memory SQLite DB."""
    db = mango.Database(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )  # ephemeral in-memory DB for this test; StaticPool shares one connection across sessions
    router = mango.build_crud_router(
        repository=GreetingRepository,
        read_schema=GreetingRead,
        create_schema=GreetingCreate,
        update_schema=GreetingUpdate,
        get_db=db.get_db,
        id_type=uuid.UUID,
        prefix="/greetings",
    )  # fully generated CRUD router, no hand-written endpoint bodies

    app = FastAPI()
    mango.register_error_handlers(app)  # so a missing id maps to a clean 404
    app.include_router(router)

    with TestClient(app) as client:
        import asyncio

        asyncio.run(db.create_all(Base))  # create the greetings table before any request runs
        yield client


def test_crud_lifecycle(_client: TestClient):
    """Create, read, list, update, and delete a row through the generated router."""
    greeting_id = str(uuid.uuid4())  # id for the row this test creates

    create_response = _client.post(
        "/greetings/", json={"id": greeting_id, "message": "hi"}
    )
    assert create_response.status_code == 201
    assert create_response.json() == {"id": greeting_id, "message": "hi"}

    get_response = _client.get(f"/greetings/{greeting_id}")
    assert get_response.status_code == 200
    assert get_response.json()["message"] == "hi"

    list_response = _client.get("/greetings/")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    update_response = _client.patch(f"/greetings/{greeting_id}", json={"message": "hello"})
    assert update_response.status_code == 200
    assert update_response.json()["message"] == "hello"

    delete_response = _client.delete(f"/greetings/{greeting_id}")
    assert delete_response.status_code == 204

    missing_response = _client.get(f"/greetings/{greeting_id}")
    assert missing_response.status_code == 404
