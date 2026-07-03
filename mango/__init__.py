"""mango/__init__.py

Public API of the mango framework. Everything a consumer needs is
re-exported here — import `from mango import X`, not from a submodule,
and never `import fastapi` or `import pydantic` directly for the common
cases (routing, request/response schemas, DB sessions, error handling).
`Router`/`Schema`/etc. ARE the underlying FastAPI/Pydantic classes under
mango's own names, not reimplementations — mango gives them one front
door, it doesn't hide their behavior.

Classes (20):
    - App: the full wrapper — owns its FastAPI instance internally,
      directly ASGI-callable, exposes get/post/put/patch/delete/
      add_middleware/mount_all/run. The default starting point for a new
      project — a consumer using only `App` never touches fastapi.
    - MangoApp: thin wrapper around an EXISTING fastapi.FastAPI instance
      — for projects that already own their FastAPI app object.
    - MangoModule: base class a module's declaration inherits from —
      binds together its models, repository, service, schemas, and router.
    - MangoRepository: generic SQLAlchemy repository with get/list/count/
      search/list_page/search_page built in, so simple modules never
      hand-write CRUD queries.
    - ModuleSpec: internal record of one registered module's pieces.
    - Database: one-line async engine + session-factory + get_db
      dependency, plus `.spawn()` for fire-and-forget background work.
    - Auth: pluggable token-verification + user-loading + role/attribute
      guards (require_role/require/current_user), built on FastAPI
      Depends — the "verify JWT -> load user -> check role" pattern every
      real app hand-writes.
    - Schema: pydantic.BaseModel subclass with from_attributes=True by
      default, for request/response schemas.
    - Page: generic paginated-response envelope (items/total/limit/offset).
    - MangoError: base class for mango's domain exceptions.
    - NotFoundError, ConflictError, ForbiddenError, UnauthorizedError,
      BadRequestError: MangoError subclasses, each with a default HTTP
      status code, used by services instead of raising HTTPException
      directly.
    - Router, Depends, Query, Path, Body, Header, Cookie, Form, File,
      UploadFile, Request, Response, JSONResponse, HTTPException: FastAPI
      primitives re-exported under mango's own namespace (HTTPException
      is an escape hatch — prefer mango's own exceptions).
    - SecurityHeadersMiddleware, RateLimitMiddleware: production-
      hardening middleware `App` installs by default (headers) or
      opt-in (rate limiting) — see mango/security.py.
    - Plugin: the protocol a plugin implements (`install(app)`) for
      `App.use(plugin)`.
    - RequestIDPlugin: a built-in reference plugin — stamps a unique
      `X-Request-ID` on every response.

Functions (7):
    - module: class decorator that registers a MangoModule subclass into
      the global registry and validates it declares the required pieces.
    - register_error_handlers: installs mango's exception -> HTTP response
      mapping on a FastAPI app (also available via `MangoApp(...,
      error_handlers=True)`, and on by default with `App`).
    - build_crud_router: generates a full list/get/create/update/delete
      REST router from a MangoRepository + Pydantic schemas.
    - run_in_background: schedules a fire-and-forget coroutine, logging
      (not swallowing) any exception it raises.
    - init_migrations: scaffolds alembic.ini + migrations/ wired to a
      project's declarative Base.
    - init_project: scaffolds a full new project's folder structure
      (see docs/PROJECT_STRUCTURE.md).
    - Field, field_validator, model_validator: pydantic re-exports for
      schema field definitions/validation.
"""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mangoframe")  # installed package version, from build/install metadata
except PackageNotFoundError:  # pragma: no cover — only hit when mango is used from source, unbuilt
    __version__ = "0.0.0+unknown"

from mango.app import App, MangoApp
from mango.auth import Auth
from mango.crud import build_crud_router
from mango.db import Database
from mango.errors import register_error_handlers
from mango.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    MangoError,
    NotFoundError,
    UnauthorizedError,
)
from mango.migrations import init_migrations
from mango.module import MangoModule, ModuleSpec, module
from mango.pagination import Page
from mango.plugins import Plugin, RequestIDPlugin
from mango.project import init_project
from mango.repository import MangoRepository
from mango.schema import ConfigDict, Field, Schema, field_validator, model_validator
from mango.security import RateLimitMiddleware, SecurityHeadersMiddleware
from mango.tasks import run_in_background
from mango.web import (
    Body,
    Cookie,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    JSONResponse,
    Path,
    Query,
    Request,
    Response,
    Router,
    UploadFile,
    status,
)

__all__ = [
    "__version__",
    # app
    "App",
    "MangoApp",
    # modules
    "MangoModule",
    "ModuleSpec",
    "module",
    # data
    "MangoRepository",
    "Database",
    "Page",
    # auth
    "Auth",
    # schema
    "Schema",
    "Field",
    "field_validator",
    "model_validator",
    "ConfigDict",
    # errors
    "MangoError",
    "NotFoundError",
    "ConflictError",
    "ForbiddenError",
    "UnauthorizedError",
    "BadRequestError",
    "register_error_handlers",
    # crud
    "build_crud_router",
    # background tasks
    "run_in_background",
    # migrations
    "init_migrations",
    # project scaffolding
    "init_project",
    # security / hardening
    "SecurityHeadersMiddleware",
    "RateLimitMiddleware",
    # plugins
    "Plugin",
    "RequestIDPlugin",
    # web primitives
    "Router",
    "Depends",
    "Query",
    "Path",
    "Body",
    "Header",
    "Cookie",
    "Form",
    "File",
    "UploadFile",
    "Request",
    "Response",
    "JSONResponse",
    "HTTPException",
    "status",
]
