"""mango/project.py

Scaffolds a new mango project's folder structure — `app/main.py`,
`app/registry.py`, `app/db.py`, `app/modules/`, `tests/`, plus the usual
project-root files (`pyproject.toml`, `.env.example`, `.gitignore`,
`README.md`). This is the structural counterpart to `new_module()`
(mango/cli.py): that scaffolds one module, this scaffolds the project
those modules live in. See docs/PROJECT_STRUCTURE.md for the full
convention and rationale.

Also writes `project.mango` at the project root — a small TOML manifest
(see `_PROJECT_MANGO` below) that marks a directory as a mango project
and records where its modules/registry live, the way `tsconfig.json`
marks a TypeScript project. `mango new-module`/`init-migrations`
(mango/cli.py) look for it so they can default their own arguments
instead of asking the user to repeat `app/modules` on every invocation.

Classes: none.

Functions (1):
    - init_project: writes a complete starter project, either into a new
      `directory/name/` subdirectory, or in place into `directory` itself
      when `name` is `"."` (e.g. an already-`cd`'d-into, already-`git
      init`'d empty folder that should become the project root, not gain
      a redundant nested copy of itself).
"""
from __future__ import annotations

from pathlib import Path

MANIFEST_FILENAME = "project.mango"  # marks a directory as a mango project root

_PROJECT_MANGO = """\
# project.mango — marks this directory as a mango project root; read by
# the `mango` CLI (new-module/init-migrations/routes/modules/doctor/
# migrate) to default its own arguments instead of asking you to repeat
# them on every invocation.
name = "{slug}"
modules_dir = "app/modules"
registry = "app/registry.py"
base_import = "app.db:Base"
app_import = "app.main:app"
"""

_PYPROJECT = """\
[project]
name = "{slug}"
version = "0.1.0"
description = "A mango project."
requires-python = ">=3.11"
dependencies = [
    "mangoframe",
    "asyncpg",
    "aiosqlite",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app"]
"""

_ENV_EXAMPLE = """\
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/{slug}
"""

_GITIGNORE = """\
__pycache__/
*.pyc
.venv/
.pytest_cache/
*.egg-info/
.env
"""

_README = """\
# {name}

A mango project. See `app/` for the code, `mango`'s own
[docs/GUIDE.md](https://github.com/) for the framework itself, and
`docs/PROJECT_STRUCTURE.md` in the mango repo for why this layout looks
the way it does.

## Run it

```bash
pip install -e ".[dev]"
export DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/{slug}
python -m app.main
```

## Add a module

```bash
mango new-module <name>
```

Run from anywhere inside this project — `project.mango` tells `mango`
where `modules_dir`/`registry.py` are, so the module is created under
`app/modules/` and wired into `app/registry.py` automatically.

## Migrations

```bash
mango init-migrations
alembic revision --autogenerate -m "..."
alembic upgrade head
```
"""

_APP_INIT = ""  # app/__init__.py — empty, just makes `app` a package

_DB_PY = '''"""app/db.py

The project's single shared Database instance and declarative Base.
Every module's models.py imports `Base` from here (never creates its
own) so they all land in the same `Base.metadata` — required for
`mango init-migrations` autogenerate to see every table.

Classes: none — this file only instantiates shared objects.

Functions: none.
"""
import os

from sqlalchemy.orm import DeclarativeBase

import mango


class Base(DeclarativeBase):
    """Shared declarative base — every module's ORM models subclass this."""


db = mango.Database(os.environ["DATABASE_URL"])  # the project's one Database instance
'''

_REGISTRY_PY = '''"""app/registry.py

Imports every module's module.py for its @mango.module registration side
effect. This is the ONLY file that needs to know every module exists —
app/main.py just imports this file and calls app.mount_all(). Add a line
here whenever `mango new-module` creates a new one.

Classes: none.

Functions: none.
"""
# import app.modules.<name>.module  # noqa: F401  (uncomment/add as modules are created)
'''

_MAIN_PY = '''"""app/main.py

The project's entry point. Owns the mango.App instance — nothing else in
this project should import fastapi directly.

Classes: none.

Functions (1):
    - create_app: builds the app and mounts every registered module.
"""
import mango
from app import registry  # noqa: F401  (imports every module for its registration side effect)


def create_app() -> mango.App:
    """Build the app and mount every module registered in app/registry.py."""
    app = mango.App(title="{name}", prefix="/api/v1")
    mount_order = app.mount_all()
    print(f"mounted modules: {{mount_order}}")

    @app.get("/healthz")
    async def healthz() -> dict:
        """Liveness-check route."""
        return {{"status": "ok"}}

    return app


app = create_app()  # ASGI-callable — `uvicorn app.main:app`

if __name__ == "__main__":
    app.run()
'''

_MODULES_INIT = ""  # app/modules/__init__.py — empty, just makes app.modules a package

_TESTS_INIT = ""  # tests/__init__.py — empty


def init_project(name: str, directory: str = ".") -> Path:
    """Scaffold a new mango project.

    Normally scaffolds into a new `directory/name/` subdirectory. Pass
    `name="."` to instead scaffold in place into `directory` itself (the
    project's name is then taken from that directory's own name) — for
    the common case of an already-created, already-`cd`'d-into empty
    folder (e.g. one `git init` already ran in) that should become the
    project root directly, not gain a redundant nested copy of itself.

    Writes: pyproject.toml, .env.example, .gitignore, README.md,
    app/__init__.py, app/main.py, app/registry.py, app/db.py,
    app/modules/__init__.py, tests/__init__.py, project.mango.

    Raises:
        FileExistsError: if `directory/name/` already exists (normal
            mode), or if any file this would write already exists in
            `directory` (in-place mode) — named in the error, so an
            accidental re-run against a non-empty folder doesn't
            silently overwrite anything.
    """
    in_place = name == "."
    if in_place:
        root = Path(directory).resolve()  # the existing directory becomes the project root, unchanged
        project_name = root.name or "project"  # derived from the folder's own name, not chosen by the caller
        if root.exists() and not root.is_dir():
            raise FileExistsError(f"{root} is not a directory")
    else:
        root = Path(directory) / name  # the new project's root directory, to be created
        project_name = name
        if root.exists():
            raise FileExistsError(f"{root} already exists")

    slug = project_name.lower().replace(" ", "-").replace("_", "-")  # normalized package name for pyproject.toml

    targets = {
        root / "pyproject.toml": _PYPROJECT.format(slug=slug),
        root / ".env.example": _ENV_EXAMPLE.format(slug=slug),
        root / ".gitignore": _GITIGNORE,
        root / "README.md": _README.format(name=project_name, slug=slug),
        root / "app" / "__init__.py": _APP_INIT,
        root / "app" / "db.py": _DB_PY,
        root / "app" / "registry.py": _REGISTRY_PY,
        root / "app" / "main.py": _MAIN_PY.format(name=project_name),
        root / "app" / "modules" / "__init__.py": _MODULES_INIT,
        root / "tests" / "__init__.py": _TESTS_INIT,
        root / MANIFEST_FILENAME: _PROJECT_MANGO.format(slug=slug),
    }  # every file this scaffolds, mapped to its rendered content

    if in_place:
        conflicts = [path for path in targets if path.exists()]  # files that would be silently overwritten
        if conflicts:
            listed = ", ".join(str(path.relative_to(root)) for path in conflicts)
            raise FileExistsError(f"{root} already contains: {listed}")

    (root / "app" / "modules").mkdir(parents=True, exist_ok=in_place)
    (root / "tests").mkdir(parents=True, exist_ok=in_place)

    for path, content in targets.items():
        path.write_text(content, encoding="utf-8")

    return root
