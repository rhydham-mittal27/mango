"""tests/test_errors.py

Tests that MangoError subclasses map to the right HTTP status/body via
register_error_handlers, and that an unrelated unhandled exception maps
to a generic 500 instead of leaking its details.

Classes: none — pytest test functions only.

Functions (3):
    - test_not_found_maps_to_404: NotFoundError -> 404 with its detail.
    - test_custom_message_used: a custom detail message is passed through.
    - test_unexpected_exception_maps_to_generic_500: a plain exception
      doesn't leak internals, just a generic message.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

import mango


def _make_app() -> TestClient:
    """Build a minimal app with mango's error handlers and one route per test case."""
    app = FastAPI()
    mango.register_error_handlers(app)

    @app.get("/not-found")
    async def not_found():
        raise mango.NotFoundError()

    @app.get("/not-found-custom")
    async def not_found_custom():
        raise mango.NotFoundError("widget 42 not found")

    @app.get("/boom")
    async def boom():
        raise RuntimeError("something sensitive: db password is hunter2")

    return TestClient(app, raise_server_exceptions=False)


def test_not_found_maps_to_404():
    """NotFoundError becomes a 404 with its default detail."""
    client = _make_app()
    response = client.get("/not-found")
    assert response.status_code == 404
    assert response.json() == {"detail": "not found"}


def test_custom_message_used():
    """A custom detail message passed to the constructor is used verbatim."""
    client = _make_app()
    response = client.get("/not-found-custom")
    assert response.status_code == 404
    assert response.json() == {"detail": "widget 42 not found"}


def test_unexpected_exception_maps_to_generic_500():
    """A plain, unhandled exception never leaks its message to the client."""
    client = _make_app()
    response = client.get("/boom")
    assert response.status_code == 500
    assert response.json() == {"detail": "internal server error"}
    assert "hunter2" not in response.text
