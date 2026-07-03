"""mango/module.py

The core of mango: a single `@module` decorator + `MangoModule` base class
that replaces the hand-written `models.py` / `repository.py` / `service.py`
/ `schemas.py` / `router.py` / `__init__.py` quintet-per-module with one
declarative class. A decorated class's attributes ARE the module's public
API — mango derives the equivalent of an aggressive `__init__.py` from
them automatically, so there is nothing separate to keep in sync.

Classes (2):
    - MangoModule: base class every module declaration inherits from.
    - ModuleSpec: frozen record mango builds from a decorated class,
      stored in the registry and consumed by MangoApp at mount time.

Functions (2):
    - module: class decorator — validates and registers a MangoModule
      subclass, returns it unchanged so it stays a normal importable class.
    - get_registry: returns the live module registry (mainly for tests/
      introspection; MangoApp is the normal consumer).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mango.web import Router

_REGISTRY: dict[str, "ModuleSpec"] = {}  # name -> ModuleSpec, populated by @module as modules are imported


@dataclass(frozen=True)
class ModuleSpec:
    """What mango knows about one registered module, derived from its
    MangoModule subclass at decoration time."""

    name: str  # unique module name, e.g. "identity" — also the manifest/ordering key
    cls: type["MangoModule"]  # the decorated class itself
    router: Router | None  # the module's FastAPI router, if it exposes HTTP endpoints
    depends_on: tuple[str, ...] = field(default_factory=tuple)  # names of modules that must mount first
    prefix: str = ""  # extra path prefix applied when MangoApp mounts this module's router


class MangoModule:
    """Base class for a module declaration.

    Subclass this and set class attributes for whichever pieces your
    module actually has — mango only requires `name`; everything else
    (models, repository, service, schemas, router, depends_on, prefix)
    is optional, matching modules like `admin` or `storage` in the
    reference backend that don't own models/a repository at all.
    """

    name: str  # required — unique module identifier used for registry lookup and mount ordering
    models: Any = None  # optional module/namespace holding this module's ORM model classes
    repository: Any = None  # optional module/namespace holding this module's MangoRepository subclass(es)
    service: Any = None  # optional module/namespace holding this module's business-logic class(es)
    schemas: Any = None  # optional module/namespace holding this module's Pydantic schema classes
    router: Router | None = None  # optional FastAPI router this module exposes
    depends_on: tuple[str, ...] = ()  # names of other modules this one imports from, for mount ordering
    prefix: str = ""  # extra path prefix under the app's base prefix, e.g. "/admin"


def module(cls: type[MangoModule]) -> type[MangoModule]:
    """Register a MangoModule subclass. Returns the class unchanged so it
    remains a normal, directly-importable Python class — decoration only
    has the side effect of adding it to the registry.
    """
    if not issubclass(cls, MangoModule):
        raise TypeError(f"@mango.module can only decorate a MangoModule subclass, got {cls!r}")
    name = getattr(cls, "name", None)  # the module's declared unique name
    if not name:
        raise ValueError(f"{cls!r} must set a class attribute `name`")
    if name in _REGISTRY:
        raise ValueError(f"module {name!r} is already registered (duplicate @module name)")

    spec = ModuleSpec(
        name=name,
        cls=cls,
        router=cls.router,
        depends_on=tuple(cls.depends_on),
        prefix=cls.prefix,
    )  # the immutable record mango stores and later consumes
    _REGISTRY[name] = spec
    return cls


def get_registry() -> dict[str, ModuleSpec]:
    """Return the live module registry — one entry per `@module`-decorated class imported so far."""
    return _REGISTRY
