---
name: mangoframe
description: "Use when creating, scaffolding, or working inside a mangoframe project (a thin FastAPI + SQLAlchemy convention layer, pip package name 'mangoframe', import name 'mango'). Covers project/module scaffolding via the `mango` CLI, the project.mango manifest, and mango's own primitives (App, MangoModule, MangoRepository, Auth, build_crud_router, Database, error handling). Trigger on: mangoframe, `import mango`, project.mango, `mango init`/`new-module`/`modules`/`routes`/`doctor`/`migrate`/`remove-module`, or a repo containing a project.mango file."
---

# mangoframe

A thin convention-and-scaffolding layer over FastAPI + SQLAlchemy + Pydantic. `mango.Router`/`mango.Schema` ARE `fastapi.APIRouter`/`pydantic.BaseModel` — mango adds no lock-in, only removes the boilerplate every hand-rolled FastAPI project repeats (module wiring, CRUD repositories, DB setup, auth guards, error mapping, pagination, background jobs, migrations).

Install: `pip install mangoframe` (PyPI name `mangoframe`; import name is always `mango`).

## Detecting a mangoframe project

A directory is a mango project root if it has a `project.mango` file (plain TOML, like `tsconfig.json` marks a TypeScript project):

```toml
name = "my_shop"
modules_dir = "app/modules"
registry = "app/registry.py"
base_import = "app.db:Base"
app_import = "app.main:app"
```

Every `mango` subcommand below (except `init`) auto-detects this by walking upward from the cwd — run them from anywhere inside the project, no directory argument needed, unless you want to target a different project explicitly.

## CLI commands (the whole workflow)

```bash
mango init my_shop          # scaffold a new project into ./my_shop
mango init .                # scaffold THIS directory in place (name inferred from the folder), for an
                             # already-created/already-cd'd-into (maybe already git-init'd) empty folder
mango new-module items       # scaffold a module under modules_dir, auto-wired into registry.py
mango remove-module items     # inverse: deletes the module dir, un-wires the registry import
mango modules                # list registered modules in mount order (name, prefix, depends_on)
mango routes                 # list every mounted HTTP route — no need to boot the server / check /docs
mango doctor                  # sanity-check: orphan/stale registry imports, missing .env, dependency drift
mango init-migrations         # scaffold alembic.ini + migrations/, wired to base_import
mango migrate "message"       # alembic revision --autogenerate + upgrade head, in one step
```

Run `mango <command> --help` for details/examples on any of these; bare `mango` prints a quickstart.

## Project layout `mango init` produces

```
my_shop/
  project.mango       # the manifest above
  pyproject.toml       # depends on "mangoframe" (not "mango-api" — that name doesn't exist on PyPI)
  .env.example / .env  # DATABASE_URL=postgresql+asyncpg://... or sqlite+aiosqlite:///...
  app/
    db.py              # shared `Base` (DeclarativeBase) + `db = mango.Database(DATABASE_URL)`
    registry.py         # imports every module.py for its @mango.module registration side effect
    main.py              # `app = mango.App(...)`; `app.mount_all()`; ASGI entrypoint
    modules/
      <name>/module.py   # one module = one file: router + @mango.module class
  tests/
```

**Never create a module's `__init__.py`/router-mounting by hand** — always `mango new-module <name>`, then let it auto-wire `registry.py`. If a module folder ever gets created or deleted by hand, run `mango doctor` to catch the drift (orphan module not wired in, or a stale import pointing at a deleted module).

## Writing a module (`app/modules/<name>/module.py`)

```python
import mango

router = mango.Router()

@router.get("/items/ping")
async def ping() -> dict:
    return {"status": "ok"}

@mango.module
class ItemsModule(mango.MangoModule):
    name = "items"
    router = router
    depends_on = ()   # other module names that must mount first (topological order, cycle-checked)
    prefix = ""        # extra path prefix under the app's own prefix
```

`MangoModule` fields are all optional except `name` — set only what the module actually has (`models`, `repository`, `service`, `schemas`, `router`).

## Core primitives (all under `import mango`, never `import fastapi`/`import pydantic` directly)

- **`mango.MangoRepository[Model]`** — generic async repository: `get`, `get_or_404`, `exists`, `add`/`add_many`, `update(**fields)`, `delete`/`delete_many`, `list`, `filter_by(**equals)`, `count`, `list_page`/`search_page` (paginated, with total count). Subclass sets `model` and optionally `search_fields` for `.search()`'s ILIKE filter.
- **`mango.build_crud_router(repository=, read_schema=, get_db=, create_schema=None, update_schema=None, id_type=str, paginated=False, prefix="")`** — full list/get/create/update/delete router in one call for plain-CRUD modules. Get `id_type` right (e.g. `uuid.UUID`) or lookups fail at the DB layer instead of a clean 422.
- **`mango.Auth(verify_token=, load_user=, get_db=, role_attr="role")`** — provider-agnostic (Supabase/Auth0/custom JWT all fine): `verify_token` decodes a raw bearer token to claims (raises on invalid), `load_user(session, claims)` resolves the user row. Exposes `.current_user()`, `.require_role(*roles)`, `.require(predicate)` as `Depends(...)`-ready dependencies. For per-resource ownership/role checks beyond a flat `user.role`, write a small `Depends`-factory function (resolve-the-resource + check-role-on-it in one dependency) rather than repeating the fetch+check in every route body.
- **`mango.Database(url, **engine_kwargs)`** — `.get_db` (commit-on-success/rollback-on-exception session dependency), `.create_all(base)` (dev/test only — use Alembic for real migrations), `.spawn(fn)` (fire-and-forget background work with its own session, never the request's).
- **`mango.MangoError` subclasses** (`NotFoundError`, `UnauthorizedError`, `ForbiddenError`, ...) + `mango.register_error_handlers(app)` — raise domain errors, never raw `HTTPException`, for them to map to clean responses (default 500 on anything unhandled, no leaked traceback). `mango.App` wires this in by default.
- **`mango.App(title=, prefix=, security_headers=True, cors_origins=None, rate_limit=None)`** — owns the FastAPI instance; `.mount_all()` mounts every registered module in dependency order; `.routes()` lists every mounted route programmatically (what `mango routes` uses); `.on_startup`/`.on_shutdown` hooks; `.use(plugin)` extension point. `RateLimitMiddleware` is in-memory/single-process only — not sufficient alone for a horizontally-scaled deployment.

## Compacting hand-written routes (custom logic beyond plain CRUD)

When a route needs real business logic `build_crud_router` doesn't cover, still lean on mango + these patterns rather than reinventing FastAPI boilerplate:

- **Auth**: one `mango.Auth(...)` instance for the whole app/module, reused via `Depends(auth.current_user())` — never a per-route hand-rolled `OAuth2PasswordBearer` + user-loading function.
- **Repeated "fetch resource + check permission on it"**: fold into a `Depends`-factory (e.g. `require_project(*roles)` returning a dependency that 404s/403s and returns the resolved row) so the route signature itself states the precondition — the body then holds only the route's actual logic.
- **Repeated small shapes** (a `setattr`-loop partial update, an OR-of-ILIKEs search filter, a `COUNT(*)` subquery) — name them as one-line helpers (`apply(obj, patch)`, `matches(term, *cols)`, `count_of(session, stmt)`) instead of inlining the SQLAlchemy idiom at every call site.
- Prefer `mango.Depends`/`mango.Query`/`mango.Router` over separate `fastapi` imports, so the file stays consistent with the rest of the project.

## Common mistakes to catch

- A generated project's `pyproject.toml` must depend on `"mangoframe"`, never `"mango-api"` (a nonexistent package name from an old naming attempt) — if you see `mango-api` in a dependency list, it's a bug, fix it.
- Modules created/deleted by hand instead of via `mango new-module`/`remove-module` — run `mango doctor` to catch orphan or stale `registry.py` imports.
- `id_type` on `build_crud_router` defaulting to `str` for a `uuid.UUID`-keyed model — set it explicitly.
- Rolling a custom rate limiter or JWT verifier from scratch — use `mango.RateLimitMiddleware`/`mango.Auth`'s pluggable hooks instead.
