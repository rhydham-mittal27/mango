# mango — usage guide

mango is a thin convention-and-scaffolding layer over FastAPI + SQLAlchemy.
It does not reimplement either — `mango.Router` IS `fastapi.APIRouter`,
`mango.Schema` IS a `pydantic.BaseModel` subclass — but a project built
with mango never needs `import fastapi` or `import pydantic` for the
common cases. Everything you'd otherwise reach into those packages for
(routing, request/response schemas, dependency injection, the app
instance itself, DB sessions, error handling) has a `mango.` name.
Beyond that single front door, mango removes the repetitive plumbing
every FastAPI project rewrites: the `models.py` / `repository.py` /
`service.py` / `schemas.py` / `router.py` / `__init__.py` quintet a
vertical-slice module normally needs, the hand-maintained `main.py`
router-mounting list, generic CRUD repositories, DB session setup, and
domain-exception-to-HTTP-status mapping.

This guide covers everything needed to use mango in a new project.
For the framework's own design notes see [../README.md](../README.md).

**Why hide FastAPI/Pydantic at all, instead of just using them
alongside mango?** One import surface is easier to teach and easier to
search-and-replace later if the underlying framework ever needs to
change. It's a convenience, not a wall — `mango.Router` objects are real
`fastapi.APIRouter` instances, so anything written for FastAPI directly
(a raw `fastapi.APIRouter`, a third-party FastAPI plugin, an existing
app you're migrating incrementally) still works alongside mango without
conversion. Nothing about mango's internals forbids reaching past it
when you need to.

---

## 1. Install

From a built wheel (recommended once you have one):

```bash
pip install /path/to/mango_api-0.1.0-py3-none-any.whl
```

From source, editable (while iterating on mango itself):

```bash
pip install -e /path/to/mango
# or, with uv, from inside your project:
uv add --editable /path/to/mango
```

The distribution name is `mango-api` (see [naming note](#naming-note)
below), but the import name is always `mango`:

```python
import mango
```

---

## 2. Core concepts

mango has sixteen pieces. Use whichever help — nothing requires the others.

| Piece | Replaces | When to use it |
|---|---|---|
| `mango.App` | `fastapi.FastAPI()` itself, plus the `include_router(...)` block in `main.py` | Starting a new project — the default entry point. |
| `mango.MangoApp` | just the `include_router(...)` block | Wiring mango's mounting into a FastAPI app you already own (e.g. an incremental migration). |
| `mango.Router` / `mango.Depends` / `mango.Query` / etc. | `fastapi.APIRouter` / `fastapi.Depends` / ... | Every route file — these ARE the FastAPI classes, just under `mango.` |
| `mango.Schema` | `pydantic.BaseModel` (+ remembering `ConfigDict(from_attributes=True)`) | Every request/response schema. |
| `mango.MangoModule` + `@mango.module` | hand-written `__init__.py` re-exports + `main.py` router wiring | Always — this is mango's main structural value. |
| `mango.MangoRepository` | a hand-written generic CRUD repository base class | Any module with an ORM model. Skip it for admin/composition modules with no model of their own. |
| `mango.Page` + `list_page`/`search_page` | a hand-rolled `{"items": ..., "total": ...}` envelope | Any list endpoint where the client needs to know if more pages exist. |
| `mango.Database` | hand-written `create_async_engine` + `async_sessionmaker` + `get_db()` generator | Any project managing its own DB connection. |
| `mango.Auth` | hand-written verify-token / load-user / check-role dependency chain | Any project with authenticated, role-gated endpoints. |
| `mango.MangoError` + subclasses + `register_error_handlers` | per-router `try/except` blocks translating domain errors into `HTTPException` | Services that raise domain errors (not found, conflict, forbidden, ...). |
| `mango.build_crud_router` | ~80 lines of hand-written list/get/create/update/delete endpoints | Any module whose API is plain CRUD with no extra business rules. |
| `mango.run_in_background` / `Database.spawn` | hand-rolled `asyncio.create_task` + its own session + swallowed exceptions | Fire-and-forget work a request handler kicks off without blocking the response. |
| `mango.init_migrations` | hand-written `alembic.ini` + async `env.py` | Once, when setting up a new project's migrations. |
| `mango.init_project` | hand-copying an existing project's skeleton | Once, when starting a brand new project. |
| `App`'s `security_headers`/`cors_origins`/`rate_limit` | hand-written security-header/CORS/rate-limit middleware | Every project — headers are on by default; CORS/rate-limiting are opt-in. |
| `mango.Plugin` + `App.use(...)` | ad hoc "add this middleware in main.py" copy-pasted across projects | Reusable cross-cutting behavior (observability, internal auth bundles). |

A minimal but complete, production-shaped app using every piece is
about 40 lines total, none of it `import fastapi` or `import pydantic`
— see [§11](#11-a-complete-minimal-app).

---

## 3. Declaring a module

A module is one class. Set only the attributes your module actually has
— `name` is the only required one.

```python
# app/modules/greeting/module.py
import mango

router = mango.Router()

@router.get("/hello")
async def hello() -> dict:
    return {"message": "hello"}

@mango.module
class GreetingModule(mango.MangoModule):
    """Says hello."""

    name = "greeting"       # required, unique across the app
    router = router           # optional — omit for modules with no HTTP surface
    models = None              # optional — point at your ORM model(s)
    repository = None          # optional — point at your MangoRepository subclass(es)
    service = None             # optional — point at your business-logic class(es)
    schemas = None              # optional — point at your Pydantic schema(s)
    depends_on = ()              # optional — see "Mount ordering" below
    prefix = ""                   # optional — extra path prefix under the app's base prefix
```

`@mango.module`:
- validates the class is a `MangoModule` subclass with a non-empty `name`,
- rejects a duplicate `name` immediately (`ValueError`, not a silent overwrite),
- registers the class into mango's global registry,
- returns the class **unchanged** — it's still a normal, directly
  importable Python class. Decoration is purely a registration side
  effect.

**Import the module file for its side effect.** Registration only
happens when Python executes the `@mango.module` decorator, which only
happens when the file is imported. A common pattern is one file per
app that imports every module file just to trigger registration (see
[`app/mango_registry.py`](#5-wiring-into-mainpy) below).

---

## 4. Generic repositories

If a module has an ORM model, give it a repository:

```python
# app/modules/greeting/repository.py
import mango
from .models import Greeting

class GreetingRepository(mango.MangoRepository[Greeting]):
    model = Greeting
    search_fields = ("message",)   # optional — enables .search()
```

You get, for free:

```python
repo = GreetingRepository(session)
await repo.get(id_)                 # single row by PK, or None
await repo.get_or_404(id_)          # single row, or raises mango.NotFoundError
await repo.exists(id_)              # bool, without loading the row
await repo.add(entity)              # insert + flush
await repo.add_many([e1, e2])       # batch insert + flush
await repo.update(entity, field=x)  # set fields + flush
await repo.delete(entity)           # delete + flush
await repo.delete_many([e1, e2])    # batch delete + flush
await repo.list(limit=50, offset=0)              # paginated, unfiltered
await repo.filter_by(status="active", owner_id=user.id)  # exact-match AND filter
await repo.count()                                # COUNT(*)
await repo.search("query", limit=50, offset=0)      # ILIKE across search_fields, OR-combined
await repo.list_page(limit=50, offset=0)              # (rows, total) — see §12 Pagination
await repo.search_page("query", limit=50, offset=0)    # (rows, total), filtered
```

`search()`/`search_page()` raise `ValueError` if `search_fields` isn't
set — a deliberate fail-fast rather than silently returning `list()`'s
unfiltered results. `get_or_404` is the common case where a missing row
IS the error — use it in a router/service instead of `get()` + a manual
`if row is None: raise ...` every time.

`filter_by(**equals)` is exact-match, AND-combined equality only — the
one pattern ("get all X where column == value", possibly on several
columns at once) that's genuinely repetitive across modules. Anything
beyond that (OR conditions, ranges, joins) is a custom method, same as
always — this isn't a general query builder.

### Eager-loading relationships

`get()` and `list()` both take `options=` — SQLAlchemy loader options,
for relationships you need populated before the session closes (async
SQLAlchemy can't do an implicit lazy load once a session is gone, so
skipping this is a common source of `MissingGreenlet`/detached-instance
errors):

```python
from sqlalchemy.orm import selectinload

await repo.get(order_id, options=[selectinload(Order.line_items)])
await repo.list(options=[selectinload(Order.line_items)])
```

Left empty by default — not every model has relationships worth
eager-loading on every fetch, and mango isn't going to guess which ones
matter for a given call site.

**Write custom query methods as normal subclass methods** for anything
domain-specific — mango does not try to generate arbitrary filtered
queries. A repository with 6 custom methods and 4 inherited ones is
normal and expected:

```python
class GreetingRepository(mango.MangoRepository[Greeting]):
    model = Greeting

    async def get_by_author(self, author_id: uuid.UUID) -> Sequence[Greeting]:
        stmt = select(Greeting).where(Greeting.author_id == author_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()
```

### If you already have a repository base class

You don't have to replace it — you can build it on top of mango instead,
keeping your existing overrides:

```python
class BaseRepository(mango.MangoRepository[ModelType]):
    # only override what's actually different from mango's default,
    # e.g. if your app calls session.refresh() after writes:
    async def add(self, obj):
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj
```

Everything you don't override (`get`, `list`, `count`, `search`) is
inherited from mango as-is.

---

## 5. Database setup

`mango.Database` replaces the usual ~15 lines of `create_async_engine` +
`async_sessionmaker` + a hand-written `get_db()` generator:

```python
import mango

db = mango.Database("postgresql+asyncpg://user:pass@localhost/mydb")
```

Use `db.get_db` anywhere FastAPI expects a session dependency:

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

@router.get("/things")
async def list_things(session: AsyncSession = Depends(db.get_db)):
    ...
```

It commits once at the end of a clean request and rolls back on any
exception — the same pattern a hand-written `get_db()` implements.
`db.create_all(Base)` is a dev/test convenience for creating tables
directly from your models; real projects still use Alembic (or
equivalent) migrations for anything beyond local iteration.

Extra keyword arguments are forwarded straight to
`create_async_engine` — e.g. for an in-memory SQLite DB in tests:

```python
from sqlalchemy.pool import StaticPool

db = mango.Database(
    "sqlite+aiosqlite:///:memory:",
    poolclass=StaticPool,
    connect_args={"check_same_thread": False},
)
```

---

## 6. Error handling

Raise a domain exception from a service; mango turns it into the right
HTTP response — no per-router `try/except HTTPException` translation:

```python
import mango

class CreatorService:
    async def get(self, creator_id):
        creator = await self.repo.get(creator_id)
        if creator is None:
            raise mango.NotFoundError(f"creator {creator_id} not found")
        return creator
```

Register the handlers once, in your app factory:

```python
app = FastAPI()
mango.register_error_handlers(app)
# or, if you're also using MangoApp:
mango_app = mango.MangoApp(app, error_handlers=True)
```

Built-in exceptions and their status codes:

| Exception | Status | Typical use |
|---|---|---|
| `mango.BadRequestError` | 400 | malformed input FastAPI's own validation wouldn't catch |
| `mango.UnauthorizedError` | 401 | missing/invalid credentials |
| `mango.ForbiddenError` | 403 | authenticated, but not allowed |
| `mango.NotFoundError` | 404 | resource doesn't exist |
| `mango.ConflictError` | 409 | duplicate, already-decided, immutable field |

Any exception that *isn't* a `mango.MangoError` is caught by a
catch-all handler, logged server-side with its full traceback, and
turned into a generic `{"detail": "internal server error"}` 500 — so a
bug in your code never leaks a stack trace, a DB connection string, or
any other internal detail to a client. This is one of the most common
mistakes in a hand-rolled FastAPI app; mango gives it to you for free.

Need a custom exception with its own status code? Subclass `MangoError`
directly:

```python
class PaymentDeclinedError(mango.MangoError):
    status_code = 402
    default_detail = "payment declined"
```

---

## 7. Instant CRUD

For a module whose API is plain create/read/update/delete with no extra
business rules, `mango.build_crud_router` generates the whole router:

```python
import uuid
from pydantic import BaseModel, ConfigDict
import mango

class ThingCreate(BaseModel):
    name: str

class ThingUpdate(BaseModel):
    name: str | None = None

class ThingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # required — builds directly from the ORM row
    id: uuid.UUID
    name: str

router = mango.build_crud_router(
    repository=ThingRepository,      # a MangoRepository subclass
    read_schema=ThingRead,
    create_schema=ThingCreate,       # omit to disable POST
    update_schema=ThingUpdate,       # omit to disable PATCH
    get_db=db.get_db,
    id_type=uuid.UUID,               # the model's primary-key type — get this right, see below
    prefix="/things",
)
```

This produces `GET /things/`, `GET /things/{id}`, `POST /things/`,
`PATCH /things/{id}`, `DELETE /things/{id}` — a missing id 404s via
`mango.NotFoundError` automatically (register error handlers as in
[§6](#6-error-handling) for that to render cleanly).

**`id_type` matters.** It tells FastAPI how to parse the `{item_id}` URL
segment *before* it reaches your repository. Get it wrong — e.g. leave
the default `str` for a model with a `uuid.UUID` primary key — and a
lookup fails at the database layer with an opaque type-mismatch error
instead of a clean 422. Set it to match your model's actual primary-key
type (`uuid.UUID`, `int`, etc.).

**When not to use this:** the moment an endpoint needs real business
logic (authorization scoping, state-machine transitions, side effects),
write that endpoint by hand instead of trying to bend the generated
router to fit — mix a `build_crud_router()` for the boring parts of a
module with a few hand-written routes on the same `APIRouter`-derived
object, or on a second router mounted at the same prefix, for the parts
that aren't boring.

---

## 8. Wiring into `main.py`

Instead of a hand-maintained `include_router(...)` block, create one file
that imports every module (registering them) and let `mango.App` mount
them all:

```python
# app/mango_registry.py — import every module file for its registration side effect
import app.modules.greeting.module  # noqa: F401
import app.modules.other_thing.module  # noqa: F401
```

```python
# app/main.py
import mango
from app import mango_registry  # noqa: F401  (registers every module)

def create_app() -> mango.App:
    app = mango.App(title="My API", prefix="/api/v1")
    mount_order = app.mount_all()   # -> ["greeting", "other_thing", ...]
    return app

app = create_app()   # ASGI-callable — this is what `uvicorn app.main:app` points at
```

`mount_all()` includes each module's router (skipping modules with
`router = None`) under `prefix + module.prefix`, and returns the mount
order for logging.

**Already have a FastAPI instance you don't want to give up?** Use
`mango.MangoApp` instead — same `mount_all()`, but it wraps an app you
already created and own, rather than creating one for you:

```python
from fastapi import FastAPI
import mango

app = FastAPI()  # your existing app, untouched otherwise
mango.MangoApp(app, prefix="/api/v1").mount_all()
```

This is the right choice when adopting mango incrementally into an
existing FastAPI project — see `collabfluenz.backend`'s
`app/mango_registry.py` + `app/main.py` for exactly this pattern.

---

## 9. Mount ordering (`depends_on`)

`depends_on` is optional and only affects **mount order** (which
`include_router` call happens first) — it does not affect Python's own
import resolution, which happens independently the moment your module
files are imported.

```python
@mango.module
class OrdersModule(mango.MangoModule):
    name = "orders"
    depends_on = ("customers",)   # customers must be mounted before orders
```

If two modules' `depends_on` form a cycle, `MangoApp.mount_all()` (via
`mango.app._topological_order`) raises immediately with the exact
cycle traced out:

```
ValueError: circular module dependency: orders -> customers -> orders
```

This is deliberately more actionable than Python's own
`ImportError: cannot import name 'X' from partially initialized module
'Y' (most likely due to a circular import)`.

**Important:** most apps don't need `depends_on` at all. Router mount
order almost never matters functionally (FastAPI's routing doesn't
depend on include order except for overlapping path patterns). Leave it
empty unless you have a concrete reason to enforce ordering — declaring
a full "who imports whom" graph here will often be *stricter* than what
Python itself requires, because two modules can legitimately import each
other's services reciprocally (module A's service imports a class from
module B, and vice versa) as long as neither triggers the other's
`__init__`/router chain at the wrong moment. Don't fight that; just leave
`depends_on` off unless mounting genuinely requires an order.

---

## 10. Scaffolding a new project or module

Starting a brand new project:

```bash
mango init demo_shop
# -> created demo_shop/  (pyproject.toml, app/main.py, app/registry.py,
#    app/db.py, app/modules/, tests/, ...)
```

See [docs/PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) for the full
layout `mango init` produces and why each file exists — it's the
convention the rest of mango (module registration, `App.mount_all()`,
`init_migrations`) assumes.

Adding a module to an existing project:

```bash
mango new-module billing app/modules
# -> created app/modules/billing/module.py
```

This writes a starter file with the `@mango.module` boilerplate already
filled in — edit it to add your router endpoints, models, etc. Then add
one import line to `app/registry.py` so it actually gets mounted (see
[§8](#8-wiring-into-mainpy)) — `mango new-module` doesn't do this for
you, since it doesn't know which `registry.py` (if any) your project
uses.

---

## 11. A complete minimal app

Everything above, in one file — a full, runnable CRUD API with error
handling, in well under 40 lines, with no `import fastapi` or
`import pydantic` anywhere (the ORM model still uses plain SQLAlchemy —
see the note in [§2](#2-core-concepts) on why mango doesn't wrap that
layer):

```python
import uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import UUID
import mango

class Base(DeclarativeBase):
    pass

class Thing(Base):
    __tablename__ = "things"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)

class ThingRepository(mango.MangoRepository[Thing]):
    model = Thing
    search_fields = ("name",)

class ThingCreate(mango.Schema):
    id: uuid.UUID
    name: str

class ThingRead(mango.Schema):
    id: uuid.UUID
    name: str

db = mango.Database("postgresql+asyncpg://user:pass@localhost/mydb")

app = mango.App(title="Things API")
app.include_router(mango.build_crud_router(
    repository=ThingRepository,
    read_schema=ThingRead,
    create_schema=ThingCreate,
    get_db=db.get_db,
    id_type=uuid.UUID,
    prefix="/things",
))

if __name__ == "__main__":
    app.run()   # or: uvicorn mymodule:app
```

`mango.App` installs error handlers by default, so `ThingRepository`'s
generated 404s already render cleanly — no separate
`register_error_handlers` call needed (that's only for `MangoApp`
wrapping an existing FastAPI instance, where it defaults to off).

This is the honest ceiling of what mango collapses for a *simple*
module. A module with real business logic (auth scoping, workflows,
side effects) still writes its service/router by hand — mango just
keeps that code from being buried under boilerplate.

---

## 12. Pagination

`GET /` on a hand-rolled list endpoint usually returns a bare list —
which means a client has no way to know if there's a second page. Use
`mango.Page` instead of reinventing `{"items": ..., "total": ...}` per
project:

```python
class ThingList(mango.Page[ThingRead]):
    pass

@router.get("/things", response_model=mango.Page[ThingRead])
async def list_things(
    limit: int = 50, offset: int = 0, session=Depends(db.get_db)
):
    repo = ThingRepository(session)
    rows, total = await repo.list_page(limit=limit, offset=offset)
    return mango.Page(items=rows, total=total, limit=limit, offset=offset)
```

`MangoRepository.search_page(query, ...)` is the filtered counterpart —
`total` reflects the *filtered* count, not the whole table.

`build_crud_router(..., paginated=True)` does this automatically for
generated CRUD routers — see [§7](#7-instant-crud).

---

## 13. Background tasks

A request handler that needs to kick off work without blocking the
response (send an email, trigger a scoring job) can't reuse the
request's own DB session — that session closes when the response is
sent, often before the background work finishes. `Database.spawn`
handles opening a fresh session, committing/rolling back around it, and
logging (not silently swallowing) any exception:

```python
async def send_welcome_email(session: AsyncSession) -> None:
    user = await UserRepository(session).get(user_id)
    await email_client.send(user.email, "Welcome!")

@router.post("/signup")
async def signup(body: SignupRequest, session=Depends(db.get_db)):
    user = await create_user(session, body)
    db.spawn(send_welcome_email)   # fires, doesn't block the response
    return user
```

For background work that doesn't need a DB session at all, use
`mango.run_in_background(coro)` directly — same exception-logging
behavior, no session management.

---

## 14. Auth guards

`mango.Auth` is the "verify token -> load user -> check role" chain
every real app hand-writes, minus the provider-specific parts (how a
token is verified, where users are stored) — those stay plain callables
you provide, since they vary too much to bake in a default:

```python
import jwt
import mango

def verify_token(token: str) -> dict:
    return jwt.decode(token, SECRET, algorithms=["HS256"])

async def load_user(session, claims: dict):
    return await UserRepository(session).get(uuid.UUID(claims["sub"]))

auth = mango.Auth(verify_token=verify_token, load_user=load_user, get_db=db.get_db)
```

Three dependency factories built on top:

```python
# any authenticated user, no role check
@router.get("/me")
async def me(user=mango.Depends(auth.current_user())):
    ...

# only these roles
@router.post("/campaigns")
async def create_campaign(user=mango.Depends(auth.require_role("brand"))):
    ...

# an arbitrary check on the loaded user object
@router.post("/apply")
async def apply(user=mango.Depends(auth.require(lambda u: u.approved and not u.suspended))):
    ...
```

Every guard raises `mango.UnauthorizedError` (401, missing/invalid
token or no matching user row) or `mango.ForbiddenError` (403, wrong
role or failed predicate) — register error handlers (on by default with
`mango.App`) for those to render as clean responses instead of raw
Python exceptions.

`role_attr` (default `"role"`) controls which attribute `require_role`
reads off the loaded user object — pass `role_attr="user_type"` etc. if
your model names it differently.

---

## 15. Migrations

`mango.init_migrations` scaffolds a working, async-aware Alembic setup
— the ~100 lines of `env.py` boilerplate (async engine, offline/online
mode branching, metadata wiring) every project rewrites once and then
never looks at again:

```bash
mango init-migrations app.db:Base .
# -> created alembic.ini and migrations/
```

`app.db:Base` is `"module.path:AttributeName"` pointing at your
declarative Base — `migrations/env.py` imports it and diffs Alembic's
autogenerate against `Base.metadata`. The generated `env.py` reads the
DB connection string from the `DATABASE_URL` environment variable by
default (pass `database_url_env=` to `init_migrations` for a different
name) — keep it in sync with whatever you pass to `mango.Database(...)`.

From there, it's plain Alembic:

```bash
alembic revision --autogenerate -m "create things table"
alembic upgrade head
```

mango scaffolds the setup; it doesn't replace Alembic's own workflow —
autogenerate still needs a human review pass (it misses enum value
changes, index types, and anything RLS-adjacent, the same caveats as a
hand-written Alembic setup).

---

## 16. Production hardening

`mango.App` wires in baseline security by default, and offers two more
as opt-in flags:

```python
app = mango.App(
    title="My API",
    security_headers=True,           # default — see below
    cors_origins=["https://example.com"],   # default: no CORS middleware at all
    rate_limit=(100, 60),                    # default: no limit — (max_requests, window_seconds)
)
```

- **`security_headers`** (default `True`) adds
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: strict-origin-when-cross-origin`, and (only over
  HTTPS) `Strict-Transport-Security` to every response.
- **`cors_origins`** adds FastAPI's own `CORSMiddleware`, scoped to
  exactly the origins you list — never pass `["*"]` if the API needs
  cookies/Authorization headers from a browser, since a wildcard origin
  with credentials is a real vulnerability, not just a lint warning.
- **`rate_limit=(max_requests, window_seconds)`** adds an in-memory
  sliding-window limiter, 429ing with `Retry-After` once a client (by
  IP) exceeds the limit. **Read `mango.RateLimitMiddleware`'s docstring
  before relying on this**: it's single-process, in-memory state — it
  does NOT coordinate across multiple uvicorn workers or replicas (4
  workers means the *effective* limit is 4x what you configured), and it
  resets on restart. Fine as a basic abuse guard on a single instance;
  replace with a Redis-backed limiter or your load balancer's own
  rate limiting before depending on it for a horizontally-scaled,
  security-critical limit.

Need custom middleware beyond these three? `app.add_middleware(...)`
works exactly like FastAPI's own `app.add_middleware(...)` (because it
is — see [§18](#18-plugins) for the extension-point version of the same
idea, if you're packaging the middleware for reuse across projects).

---

## 17. App lifecycle hooks

```python
@app.on_startup
async def warm_cache():
    ...

@app.on_shutdown
async def close_connections():
    await db.dispose()
```

Built on FastAPI's `lifespan` context manager, not the deprecated
`add_event_handler("startup"/"shutdown", ...)` API — newer FastAPI/
Starlette versions removed that entirely, so if you've seen it in older
tutorials, don't reach for it. Multiple `@app.on_startup`/`@app.on_shutdown`
calls all run, in registration order.

---

## 18. Plugins

For code that wants to extend `App` itself — add middleware, register
routes, hook lifecycle events — without `App` needing to know about it
in advance, implement `install(app)`:

```python
class RequestLoggingPlugin:
    def install(self, app: mango.App) -> None:
        app.add_middleware(SomeLoggingMiddleware)
        app.on_startup(lambda: print("logging plugin active"))

app = mango.App(title="My API")
app.use(RequestLoggingPlugin())
```

`app.use(plugin)` just calls `plugin.install(app)` — the mechanism is
deliberately that thin. `mango.RequestIDPlugin` (stamps a unique
`X-Request-ID` on every response, available in handlers as
`request.state.request_id`) is a working, complete example:

```python
app.use(mango.RequestIDPlugin())
```

Use this for anything reusable across projects (an internal
observability plugin, a project's own auth-adjacent middleware bundle)
— for something specific to one project, just call `app.add_middleware`/
`app.on_startup` directly in `main.py`, no plugin needed.

---

## 19. Common pitfalls

**"My module's router never got mounted."**
Check that its file is actually imported somewhere before
`mango_app.mount_all()` runs. Decoration only fires on import — a module
file that's never imported never registers, and `MangoApp` has no way to
discover files it hasn't seen.

**"ValueError: module 'X' is already registered."**
Two different classes declared the same `name`, or the same file got
imported twice under two different module paths (e.g. once as
`app.modules.x.module` and once as a top-level `x.module` — pick one
import path convention and stick to it).

**"ValueError: circular module dependency: a -> b -> a"**
You declared `depends_on` in both directions. Remove it from at least
one side — see [§9](#9-mount-ordering-depends_on).

**"ValueError: X has no search_fields declared"**
Called `.search()` on a `MangoRepository` subclass that didn't set
`search_fields`. Either add it or write a custom search method.

**"A 404/409/etc. I raised isn't rendering as JSON, it's a 500."**
You raised a `mango.MangoError` subclass but never called
`mango.register_error_handlers(app)` (or `MangoApp(..., error_handlers=True)`).
Without it, mango's exceptions are just plain Python exceptions as far
as FastAPI is concerned.

**"POST/PATCH on a generated CRUD route 422s with `body` missing from query."**
This is a mango-internal gotcha, not something you'd hit as a consumer
— noted here in case you're extending `mango/crud.py` itself: its route
functions are built dynamically with closure-local schema types, so the
file must NOT use `from __future__ import annotations` (stringified
annotations can't resolve a closure-local name).

**"Looking up a UUID-keyed row 500s with an opaque type-mismatch error."**
`build_crud_router`'s `id_type` defaults to `str`. Set it to your
model's actual primary-key type (`id_type=uuid.UUID`, `id_type=int`,
...) — see [§7](#7-instant-crud).

**"Every request to an auth-guarded route is a 401, even with a valid token."**
`Auth.get_db` must be the same kind of dependency you'd pass to
`Depends(...)` elsewhere (e.g. `mango.Database(...).get_db`) — if
`load_user` raises or the session it receives can't run the query your
loader issues, that surfaces as a 401 ("no user record for this token"),
not a 500, since `Auth` treats a failed lookup as "not authenticated"
rather than propagating the underlying error. Check `load_user` works
in isolation first.

**"A background task silently never seems to run."**
Something is dropping the last reference to the returned `asyncio.Task`
before the event loop gets a chance to run it, OR the process exited
before the task finished (background tasks don't survive process
shutdown — `run_in_background`/`Database.spawn` don't persist work
across a restart, they're in-process only). For anything that must
survive a crash or restart, use a real task queue, not this.

**"AttributeError: 'FastAPI' object has no attribute 'add_event_handler'."**
You're calling FastAPI's deprecated event API directly instead of
`app.on_startup`/`app.on_shutdown` — newer FastAPI/Starlette versions
removed `add_event_handler` entirely in favor of the `lifespan` context
manager, which is what `App.on_startup`/`on_shutdown` are built on. Use
those instead of reaching for the old API.

**"Rate limiting isn't actually limiting anything in production."**
You're running more than one uvicorn worker or replica.
`mango.RateLimitMiddleware` is in-memory and per-process — each worker
enforces the limit independently, so N workers means an effective limit
of N times what you configured. See [§16](#16-production-hardening).

---

## Naming note

The framework's import name is `mango` (`import mango`). Because the
plain name `mango` and `mango-framework` were already taken on PyPI when
this was published, the **distribution** name is `mango-api`
(`pip install mango-api`). This is the same pattern as e.g.
`beautifulsoup4` installing as `bs4`.

---

## Reference: full public API

```python
import mango

# app
mango.App                     # owns its own FastAPI instance; ASGI-callable; the default entry point
mango.MangoApp                 # wraps an EXISTING FastAPI app; .mount_all() mounts every registered module

# modules
mango.MangoModule           # base class for a module declaration
mango.module                 # @mango.module decorator, registers a MangoModule subclass
mango.ModuleSpec              # frozen record mango builds from a decorated class (introspection only)

# data
mango.MangoRepository           # generic async repository: get/add/update/delete/list/count/search/list_page/search_page
mango.Database                   # one-line async engine + session factory + get_db dependency + spawn()
mango.Page                        # generic paginated-response schema: items/total/limit/offset

# auth
mango.Auth                          # pluggable token verification + user loading + require_role/require/current_user

# schema (pydantic re-exports)
mango.Schema                       # BaseModel subclass, from_attributes=True by default
mango.Field                         # pydantic.Field
mango.field_validator                 # pydantic.field_validator
mango.model_validator                   # pydantic.model_validator
mango.ConfigDict                          # pydantic.ConfigDict

# errors
mango.register_error_handlers      # installs MangoError -> HTTP response mapping on a FastAPI app
mango.MangoError                       # base class for mango's domain exceptions
mango.NotFoundError                     # 404
mango.ConflictError                      # 409
mango.ForbiddenError                      # 403
mango.UnauthorizedError                    # 401
mango.BadRequestError                       # 400

# crud
mango.build_crud_router              # generates a full list/get/create/update/delete router, optionally paginated

# background tasks
mango.run_in_background              # schedules a fire-and-forget coroutine, logs its exception if it fails

# migrations
mango.init_migrations                # scaffolds alembic.ini + async migrations/env.py wired to a declarative Base

# project scaffolding
mango.init_project                     # scaffolds a full project's folder structure (docs/PROJECT_STRUCTURE.md)

# production hardening
mango.SecurityHeadersMiddleware          # on by default in App: X-Content-Type-Options, X-Frame-Options, etc.
mango.RateLimitMiddleware                 # opt-in via App(rate_limit=(max_requests, window_seconds))

# plugins
mango.Plugin                                # protocol: install(app) — the interface App.use() expects
mango.RequestIDPlugin                        # reference plugin: stamps a unique X-Request-ID per response

# web (fastapi re-exports)
mango.Router                    # fastapi.APIRouter
mango.Depends                    # fastapi.Depends
mango.Query, mango.Path, mango.Body, mango.Header, mango.Cookie, mango.Form, mango.UploadFile
mango.Request, mango.Response, mango.JSONResponse, mango.status
mango.HTTPException              # escape hatch — prefer mango's own exceptions where applicable
```

See [`examples/hello_module/`](../examples/hello_module/) for a complete,
runnable minimal module, and
[`examples/main.py`](../examples/main.py) for the app wiring.
