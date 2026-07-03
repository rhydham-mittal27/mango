"""tests/test_module_registry.py

Tests for mango's module registry and dependency-ordered mounting: that
`@mango.module` registers correctly, duplicate names are rejected,
mount order respects `depends_on`, and cycles raise a clear error
instead of Python's confusing circular-import traceback.

Classes: none — pytest test functions only.

Functions (5):
    - test_module_registers: a decorated class appears in the registry.
    - test_duplicate_name_rejected: registering the same name twice raises.
    - test_topological_order_respects_dependencies: a depends on b implies
      b is mounted before a.
    - test_cycle_raises_clear_error: a circular depends_on chain raises
      ValueError naming the cycle.
    - test_example_app_mounts_hello_module: the example app's /hello
      endpoint is reachable end-to-end through MangoApp.
"""
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

import mango
from mango.module import _REGISTRY  # test-only access to reset registry state between tests


@pytest.fixture(autouse=True)
def _isolate_registry():
    """Roll the registry back to its pre-test contents afterward, rather than
    wiping it outright — modules registered once via module-level import
    side effects (e.g. the hello_module example, imported by other test
    files) don't re-register on a second import, so a hard clear would
    permanently lose them for the rest of the session.
    """
    snapshot = dict(_REGISTRY)  # entries that existed before this test ran
    yield
    _REGISTRY.clear()
    _REGISTRY.update(snapshot)  # restore to the pre-test snapshot, dropping anything this test added


def test_module_registers():
    """A decorated class appears in the registry under its declared name."""
    empty_router = APIRouter()  # no endpoints needed for this test; named to avoid
    # shadowing inside the class body below (Python class bodies can't see an
    # enclosing function's locals through a same-named assignment target).

    @mango.module
    class Foo(mango.MangoModule):
        """Minimal module with no router endpoints."""

        name = "foo"
        router = empty_router

    from mango.module import get_registry

    assert "foo" in get_registry()
    assert get_registry()["foo"].cls is Foo


def test_duplicate_name_rejected():
    """Registering two modules under the same name raises ValueError."""
    router_a = APIRouter()  # first module's router
    router_b = APIRouter()  # second module's router, same name as the first

    @mango.module
    class First(mango.MangoModule):
        name = "dup"
        router = router_a

    with pytest.raises(ValueError, match="already registered"):

        @mango.module
        class Second(mango.MangoModule):
            name = "dup"
            router = router_b


def test_topological_order_respects_dependencies():
    """A module's dependencies are always mounted before it."""
    from mango.app import _topological_order
    from mango.module import get_registry

    @mango.module
    class B(mango.MangoModule):
        name = "b"
        router = APIRouter()

    @mango.module
    class A(mango.MangoModule):
        name = "a"
        router = APIRouter()
        depends_on = ("b",)

    order = _topological_order(get_registry())  # computed mount order
    assert order.index("b") < order.index("a")


def test_cycle_raises_clear_error():
    """A circular depends_on chain raises ValueError naming the cycle, not a Python ImportError."""
    from mango.app import _topological_order
    from mango.module import get_registry

    @mango.module
    class X(mango.MangoModule):
        name = "x"
        router = APIRouter()
        depends_on = ("y",)

    @mango.module
    class Y(mango.MangoModule):
        name = "y"
        router = APIRouter()
        depends_on = ("x",)

    with pytest.raises(ValueError, match="circular module dependency"):
        _topological_order(get_registry())


def test_example_app_mounts_hello_module():
    """The example app's /hello endpoint is reachable end-to-end through MangoApp."""
    from examples.hello_module import module as hello_module  # noqa: F401  (registers HelloModule)

    fastapi_app = FastAPI()  # fresh app for this test
    mango_app = mango.MangoApp(fastapi_app, prefix="/api/v1")  # mango wrapper under test
    order = mango_app.mount_all()  # mount order returned by MangoApp
    assert "hello" in order

    client = TestClient(fastapi_app)  # test client against the mounted app
    response = client.get("/api/v1/hello")  # the example module's one endpoint
    assert response.status_code == 200
    assert response.json() == {"message": "hello from mango"}
