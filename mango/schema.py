"""mango/schema.py

Request/response schema base, re-exported under mango's own name so a
consumer never needs `import pydantic` directly for the common case.
`Schema` IS a `pydantic.BaseModel` subclass — not a reimplementation —
with one default applied (`from_attributes=True`) since it's the setting
every response schema in a DB-backed app needs anyway (building the
schema straight from an ORM row) and beginners reliably forget it.

Classes (1):
    - Schema: BaseModel subclass with from_attributes=True by default.

Functions: none.
"""
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = ["Schema", "Field", "field_validator", "model_validator", "ConfigDict"]


class Schema(BaseModel):
    """Base class for request/response schemas.

    `from_attributes=True` is on by default so a response schema can be
    built directly from an ORM row (`ThingRead.model_validate(row)`, or
    implicitly via `response_model=` / `mango.build_crud_router`) without
    every schema having to remember to set it. A request-body schema that
    never receives ORM rows is unaffected — the setting only matters when
    validating from a non-dict object.

    Override `model_config` on a subclass as normal if a given schema
    needs different behavior (e.g. `extra="forbid"`).
    """

    model_config = ConfigDict(from_attributes=True)  # build directly from ORM rows without extra config
