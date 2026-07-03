# Changelog

All notable changes to mango are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning
follows [Semantic Versioning](https://semver.org/) — while the major
version is `0`, any release may contain breaking changes, but they'll
always be listed under "Changed"/"Removed" below, never silent.

## [Unreleased]

## [0.9.0]

### Added
- `MangoRepository.get()`/`.exists()`/`.get_or_404()` now support
  composite primary keys — pass `id_` as a tuple in
  `model.__mapper__.primary_key` order (the same shape SQLAlchemy's own
  `Session.get()` already expects), instead of only a single-column
  scalar. A pure join-table model (e.g. a many-to-many association row)
  is the common case: a composite `(a_id, b_id)` primary key needs no
  surrogate id column, and previously `exists()`/`get(options=...)`
  raised `ValueError` unconditionally for any composite-PK model.
  `get()` without `options=` already worked via `Session.get()`'s own
  tuple-identity support; the fix is in the `options=`/`exists()` path,
  which built its own WHERE clause assuming a single column. Fixes #4.

## [0.8.0]

### Added
- `mango doctor` now detects when a DIFFERENT mango project's `app`
  package is already importable instead of this project's own — every
  mango project's top-level package is named `app` (see
  `mango init`'s scaffold), so two projects `pip install -e .`'d
  editable into the same environment silently collide: `import app`
  resolves to whichever one Python's import system finds, with no
  error, and other mango commands (`modules`/`routes`) then quietly run
  the WRONG project's code. Fixes #3.

## [0.7.0]

### Fixed
- `App.routes()` (and therefore `mango routes`) silently returned only
  ad-hoc/framework routes (`/healthz`, `/docs`, `/openapi.json`, ...) —
  every route mounted via a registered module was missing. Newer FastAPI
  wraps an `include_router()`'d router in a lazy `_IncludedRouter` proxy
  instead of eagerly copying its routes with the prefix baked in; that
  proxy has no `.path` of its own; its real routes live on
  `.original_router.routes`, still relative to
  `.include_context.prefix`. `App.routes()` assumed every route has a
  `.path` directly and silently produced nothing for anything reached
  through such a wrapper — which, via `MangoApp.mount_all()`'s
  `include_router()` call, is every module route in every project.
  Added `App._flatten_route()`, recursing into arbitrarily many levels
  of this wrapping (a module additionally doing its own
  `router.include_router(...)` before being mounted is a second level of
  the same shape). Found building an end-to-end multi-tenant SaaS
  project — `App.routes()` had no test coverage before this fix, since
  the existing dev environment's older installed FastAPI never hit this
  code path; added both a real-environment integration test and a
  synthetic-stub unit test (independent of which FastAPI version is
  installed) so this can't silently regress again. Fixes #2.

## [0.6.0]

### Fixed
- `mango init-migrations`/`mango.init_migrations` produced empty
  migrations — `env.py` only imported `base_import` (e.g. `app.db:Base`),
  which never imports any model module, so `Base.metadata` was empty at
  `alembic revision --autogenerate` time. Added `models_import` (a
  dotted module path to import for its model-registration side effect,
  e.g. a project's `registry` module) to `init_migrations`; the CLI now
  auto-fills it from `project.mango`'s `registry` field, even when
  `base_import`/`directory` are given explicitly. Found via an
  end-to-end mangoframe project build (a full-scale e-commerce API) —
  the first migration silently generated `pass`/`pass` for both
  `upgrade()`/`downgrade()` until this was fixed.

## [0.5.0]

### Added
- `mango modules` — lists every registered module in dependency-
  respecting mount order (name, prefix, `depends_on`), by importing the
  project's `registry.py` and reusing `App`'s own topological sort.
- `mango routes` — lists every currently-mounted HTTP route (method,
  path, name), by importing the project's `app_import` (`app.main:app`
  by default, per `project.mango`) — no need to boot the server and
  click through `/docs`. `mango.App` gained a public `.routes()` method
  for this.
- `mango remove-module <name>` — the inverse of `new-module`: deletes
  the module's directory and un-wires its import from `registry.py`
  (auto-detected via `project.mango`, same as `new-module`).
- `mango doctor` — sanity-checks an existing project for drift that
  hand-editing can introduce: a module folder created without updating
  `registry.py` (orphan), a `registry.py` import pointing at a deleted
  module folder (stale), a missing `.env`, or a `pyproject.toml` that
  lost its `mangoframe` dependency. Exits 1 if any check fails.
- `mango migrate "<message>"` — wraps the two-command Alembic loop
  (`revision --autogenerate -m "<message>"` + `upgrade head`) every
  model change requires, via `python -m alembic` so it always resolves
  to the current virtualenv's Alembic. Requires `mango init-migrations`
  to have run already.
- `project.mango`'s manifest gained an `app_import` field (default
  `"app.main:app"`), used by `mango routes`.

## [0.4.0]

### Added
- `mango init .` — scaffolds the given directory (default: current
  directory) in place instead of creating a new `directory/name/`
  subdirectory, inferring the project's name from the directory's own
  name. Covers the common case of an already-created, already-`cd`'d-
  into (perhaps already-`git init`'d) empty folder that should become
  the project root directly. Re-running it against a directory that
  already has scaffolded files raises, naming every conflicting file,
  rather than silently overwriting anything.

## [0.3.0]

### Added
- `project.mango` — a small TOML manifest `mango init` now writes at the
  project root (name/modules_dir/registry/base_import), the way
  `tsconfig.json` marks a TypeScript project. `mango new-module`/
  `init-migrations` walk upward from the current directory to find it:
  `new-module <name>` (no directory) creates the module under the
  manifest's `modules_dir` and auto-appends its import to `registry.py`;
  `init-migrations` (no args) reads `base_import` and the project root
  from it. Passing an explicit directory/base_import still overrides the
  manifest entirely, so nothing changes for a project scaffolded before
  this existed.

## [0.2.0]

### Added
- `mango` (no subcommand) now prints a quickstart with concrete next
  commands instead of dumping argparse help and exiting 1 — the bare
  command is a first-time-user entry point, not a usage error.
- Every `mango init` / `new-module` / `init-migrations` run now prints
  the concrete next step (cd/install/env/run, the registry import line
  to add, the alembic commands to run) instead of a bare `created X`.
- `mango init` / `mango new-module` validate the given name up front
  (lowercase snake_case) with an actionable error and suggested fix,
  instead of failing deep inside file scaffolding or module import.
- Every CLI subcommand's `--help` now includes copy-pasteable examples.

### Fixed
- Projects scaffolded by `mango init` depended on `mango-api` in the
  generated `pyproject.toml`, a name that doesn't exist on PyPI (the
  real distribution is `mangoframe`, per the [0.1.1] rename below) —
  every project scaffolded before this fix has a broken dependency list
  and needs `mango-api` replaced with `mangoframe` by hand.

## [0.1.1]

### Changed
- Distribution name on PyPI changed from `mango-api` to `mangoframe` —
  `mango-api` was rejected by PyPI as "too similar to an existing
  project" (the unrelated `mango` package). Import name is unaffected
  (`import mango`).
- `mango --version` / `mango.__version__` added, read from installed
  package metadata via `importlib.metadata`.
- `mango/cli.py` rewritten on `argparse` instead of hand-rolled
  `sys.argv` parsing — real `--help` at the top level and per
  subcommand, `--version`, and expected failures (target already
  exists, malformed `base_import`) now print a clean `error: ...` line
  instead of a raw traceback.

### Fixed
- `pyproject.toml`'s `license = { file = "LICENSE" }` made hatchling
  dump the entire license *text* into the classic `License:` metadata
  field, which PyPI's upload validation silently rejects with a bare
  `400 Bad Request` past a length limit — switched to the PEP 639 SPDX
  form (`license = "MIT"` + `license-files = ["LICENSE"]`), which
  produces a short `License-Expression: MIT` field instead.

## [0.1.0] — first published release

### Added
- `mango.SecurityHeadersMiddleware`, on by default in `App` — sets
  `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and
  (over HTTPS) `Strict-Transport-Security`.
- `mango.RateLimitMiddleware` + `App(rate_limit=(max_requests,
  window_seconds))` — opt-in in-memory sliding-window rate limiting.
- `App(cors_origins=[...])` — opt-in CORS wiring.
- `mango.Plugin` protocol + `App.use(plugin)` — third-party/project-local
  extension point.
- `mango.RequestIDPlugin` — reference plugin, stamps `X-Request-ID`.
- `App.on_startup` / `App.on_shutdown` decorators, built on FastAPI's
  `lifespan` context manager (not the deprecated `add_event_handler`
  API, which newer FastAPI/Starlette versions removed entirely).
- `MangoRepository.get_or_404`, `.exists`, `.add_many`, `.delete_many`,
  `.filter_by`, and `options=` (SQLAlchemy loader options, for
  eager-loading relationships) on `.get()`/`.list()`.
- `mango.init_project` / `mango init <name>` — scaffolds a full project's
  folder structure. See `docs/PROJECT_STRUCTURE.md`.
- `mango.Auth` — pluggable token-verification + user-loading +
  `require_role`/`require`/`current_user` FastAPI dependency factories.
- `mango.Page` + `MangoRepository.list_page`/`.search_page` — paginated-
  response envelope; `build_crud_router(paginated=True)`.
- `mango.run_in_background` + `Database.spawn` — fire-and-forget
  background work with its own session and logged (not swallowed)
  exceptions.
- `mango.init_migrations` / `mango init-migrations` — scaffolds an
  async-aware Alembic setup wired to a declarative Base.
- Full FastAPI/Pydantic re-export surface: `mango.App`, `mango.Router`,
  `mango.Schema`, `mango.Depends`, and the rest of `mango.web`/
  `mango.schema` — a project built with mango never needs
  `import fastapi` or `import pydantic`.
- `mango.MangoRepository`, `mango.Database`, `mango.MangoError` +
  subclasses, `mango.register_error_handlers`, `mango.build_crud_router`.
- `mango.MangoModule` + `@mango.module` + `mango.MangoApp` — the original
  module-registration/mounting core.

### Fixed
- `App.on_startup`/`on_shutdown` initially used
  `FastAPI.add_event_handler`, which newer FastAPI versions (0.139+
  tested) removed — rewritten on top of the `lifespan` context manager.
- `mango/crud.py`'s dynamically-built route functions initially broke
  under `from __future__ import annotations` (FastAPI couldn't resolve
  closure-local schema types as string annotations) — removed the
  future-import in that file specifically.
- `build_crud_router`'s `id_type` defaulted to `str`, which broke lookups
  against `uuid.UUID`-keyed models with an opaque DB-layer type error
  instead of a clean 422 — made `id_type` an explicit, documented param.
