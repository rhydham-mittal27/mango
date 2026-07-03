# Changelog

All notable changes to mango are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning
follows [Semantic Versioning](https://semver.org/) — while the major
version is `0`, any release may contain breaking changes, but they'll
always be listed under "Changed"/"Removed" below, never silent.

## [Unreleased]

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
