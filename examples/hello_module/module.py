"""examples/hello_module/module.py

A minimal end-to-end mango module: one ORM model, one MangoRepository
(no custom queries needed), a mango.Schema response model, and one
router endpoint — showing what mango collapses a conventional 5-file
module into, and that nothing here imports fastapi or pydantic directly.
(The ORM model itself still uses plain SQLAlchemy — mango wraps the web
and schema layers, not the ORM, since SQLAlchemy's declarative mapping
isn't boilerplate mango can meaningfully compress.)

Classes (4):
    - Greeting: ORM model, one row per stored greeting.
    - GreetingRepository: MangoRepository[Greeting] — no custom methods
      needed, get/add/list/search all come from the base class.
    - GreetingRead: mango.Schema response model for the /hello endpoint.
    - HelloModule: the module declaration tying it together.

Functions: none — this file only declares the module's pieces.
"""
import uuid

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

import mango


class Base(DeclarativeBase):
    """Declarative base for this example — a real app reuses one shared Base."""


class Greeting(Base):
    """A single stored greeting message."""

    __tablename__ = "greetings"  # physical table name

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)  # row id
    message: Mapped[str] = mapped_column(Text, nullable=False)  # the greeting text


class GreetingRepository(mango.MangoRepository[Greeting]):
    """Data access for Greeting — entirely inherited, no custom queries needed."""

    model = Greeting  # tells MangoRepository which ORM class this repository targets
    search_fields = ("message",)  # columns `search()` matches against


class GreetingRead(mango.Schema):
    """Response schema for the /hello endpoint."""

    message: str  # the greeting text


router = mango.Router()  # this module's HTTP endpoints


@router.get("/hello", response_model=GreetingRead)
async def hello() -> GreetingRead:
    """Trivial example endpoint — no DB access, just proves router mounting works."""
    return GreetingRead(message="hello from mango")


@mango.module
class HelloModule(mango.MangoModule):
    """Example module: a greeting model, its repository, and one endpoint."""

    name = "hello"  # unique module name, used for mount ordering and logging
    models = Greeting  # this module's ORM model(s)
    repository = GreetingRepository  # this module's repository class
    schemas = GreetingRead  # this module's Pydantic schema(s)
    router = router  # this module's FastAPI router
    depends_on = ()  # no dependencies on other modules
