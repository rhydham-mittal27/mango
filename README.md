<div align="center">

# 🥭 mango

**FastAPI + SQLAlchemy, without the boilerplate.**

`mango.Router` *is* `fastapi.APIRouter`. `mango.Schema` *is* `pydantic.BaseModel`.
mango doesn't reimplement your stack — it gives it one front door, then
removes everything you'd otherwise hand-write around it: module wiring,
CRUD repositories, DB setup, auth guards, error mapping, pagination,
background jobs, migrations, and security middleware.

[![PyPI](https://img.shields.io/pypi/v/mangoframe?color=6E4A2E&label=pypi)](https://pypi.org/project/mangoframe/)
[![CI](https://github.com/rhydham-mittal27/mango/actions/workflows/ci.yml/badge.svg)](https://github.com/rhydham-mittal27/mango/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-6E4A2E)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-6E4A2E)](LICENSE)

[Quickstart](#-quickstart) · [Why mango](#-why-mango) · [Full guide](docs/GUIDE.md) · [Project structure](docs/PROJECT_STRUCTURE.md) · [Contributing](CONTRIBUTING.md)

</div>

---

## The pitch, in code

**Without mango** — a plain-CRUD module is a router, a repository, a
schema file, engine/session setup, and manual error handling:

```python
# ~80+ lines across models.py / repository.py / schemas.py / router.py / main.py
```

**With mango** — the same module, in full:

```python
import uuid
from mango import Router, Schema, MangoRepository, build_crud_router, Database

class Thing(Base):
    __tablename__ = "things"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    name: Mapped[str]

class ThingRepository(MangoRepository[Thing]):
    model = Thing

class ThingRead(Schema):
    id: uuid.UUID
    name: str

router = build_crud_router(
    repository=ThingRepository, read_schema=ThingRead,
    get_db=db.get_db, id_type=uuid.UUID, prefix="/things",
)
```

That's a full `GET /things/`, `GET /things/{id}`, `DELETE /things/{id}`
REST endpoint set — 404s, pagination, error handling, all included. No
`import fastapi`. No `import pydantic`. No hand-wired `main.py`.

---

## 🚀 Quickstart

```bash
pip install mangoframe
mango init demo_shop
cd demo_shop
mango new-module items app/modules
```

```python
# app/main.py — generated for you, shown here for reference
import mango
from app import registry  # imports every module for its registration side effect

app = mango.App(title="demo_shop")
app.mount_all()
```

```bash
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/demo_shop uvicorn app.main:app --reload
```

`pip install` name is **`mangoframe`** (`mango` and `mango-framework`
were already taken on PyPI) — the import name is always `mango`.

---

## 🥭 Why mango

FastAPI and SQLAlchemy are both excellent at what they do. What they
don't give you is a *convention* — every team ends up hand-rolling the
same `models.py`/`repository.py`/`service.py`/`schemas.py`/`router.py`/
`__init__.py` shape, the same `main.py` router-mounting list, the same
generic CRUD repository, the same `try/except HTTPException` translation
at every error site. mango is that convention, packaged:

| You'd hand-write | mango gives you |
|---|---|
| `__init__.py` re-exports per module | `@mango.module` — derived, not maintained |
| `main.py` router-mounting list | `app.mount_all()` |
| A generic repository base class | `MangoRepository` — get/add/update/delete/list/count/search, plus `get_or_404`, batch ops, eager-loading |
| `create_async_engine` + `get_db()` boilerplate | `mango.Database(url)` |
| Domain-error → HTTP status `try/except` | `raise mango.NotFoundError(...)` |
| A full CRUD router | `mango.build_crud_router(...)` — optionally paginated |
| verify-token → load-user → check-role chain | `mango.Auth` — pluggable, not opinionated about your token provider |
| Security headers / rate limiting | On by default in `mango.App`, or one kwarg |
| `alembic.ini` + async `env.py` | `mango init-migrations app.db:Base` |
| A new project's folder skeleton | `mango init <name>` |

A module with real, non-generic business logic still writes that logic
by hand — mango only removes the boilerplate *around* it. See
[the size table](#-what-it-actually-cuts) below for the receipts.

**No magic, no lock-in.** `mango.Router`/`mango.Schema`/etc. are the
literal FastAPI/Pydantic classes — anything written for FastAPI
directly (a raw `APIRouter`, a third-party plugin, an app you're
migrating incrementally) works alongside mango without conversion.

---

## What's inside

- **`App`** — owns its FastAPI instance, ASGI-callable, wires in
  security headers by default and opt-in CORS/rate-limiting, exposes a
  `Plugin` extension point and `on_startup`/`on_shutdown` hooks.
- **`MangoModule` + `@mango.module`** — declare a module as one class;
  mango derives its public API instead of a hand-written `__init__.py`.
- **`MangoRepository`** — generic async CRUD, `get_or_404`, `exists`,
  `add_many`/`delete_many`, `filter_by(**equals)`, eager-loading via
  `options=`, and `list_page`/`search_page` for pagination.
- **`Auth`** — pluggable token verification + user loading +
  `require_role`/`require`/`current_user` FastAPI dependencies.
- **`MangoError` + subclasses + `register_error_handlers`** — domain
  exceptions that map straight to clean HTTP responses, plus a
  catch-all so an unhandled bug returns a generic 500, never a leaked
  traceback.
- **`build_crud_router`** — a full list/get/create/update/delete router
  from a repository + schemas, one call.
- **`run_in_background` / `Database.spawn`** — fire-and-forget work with
  its own session and a logged (not swallowed) exception on failure.
- **`init_migrations` / `init_project`** — scaffold Alembic and a whole
  new project's folder structure, via the `mango` CLI.

Full tour with examples: **[docs/GUIDE.md](docs/GUIDE.md)**.
Folder-structure convention and the reasoning behind it:
**[docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)**.

---

## 📏 What it actually cuts

Every piece exists to measurably shorten a project's code — not to add
abstraction for its own sake. Per module, roughly:

| What you'd hand-write | Lines | With mango |
|---|---|---|
| `__init__.py` re-exports | 15–30 | 0 |
| `main.py` router mounting | 1–2/module | 0 |
| Generic repository CRUD | 30–50 | 0 |
| DB engine/session/`get_db()` | ~15 | 3 |
| Plain-CRUD router | 60–90 | ~10 |
| Domain-error → HTTP mapping | 5–10/site | 0 |
| Auth guard | 20–40 | ~10 |
| Background task + own session | 10–15 | 1 |
| Alembic `env.py` | ~100 | 0 |
| Security headers middleware | ~15 | 0 |
| New project skeleton | ~80 | 0 |

---

## Development

```bash
git clone https://github.com/rhydham-mittal27/mango.git
cd mango
pip install -e ".[dev]"
pytest -q
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the ground rules (every
change ships with a test and a changelog entry, no exceptions).

## Status

Module registry, generic repository, pagination, mount ordering, DB
setup, background tasks, auth guards, error mapping, generated CRUD
routers, Alembic + project scaffolding, production hardening, a plugin
system, and a full FastAPI/Pydantic re-export surface are all in place
— a project can be built end to end importing only `mango`. CI runs the
full suite across Python 3.11/3.12/3.13 on every push.

**Honestly:** this is a young project. No production mileage beyond one
real integration, a small test suite, a single maintainer. If you use
it and something breaks, that's expected — [open an issue](../../issues)
or a PR. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) — use it for anything, including in production, at your
own judgment given the "Status" section above.
