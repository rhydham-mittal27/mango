"""mango/project.py

Scaffolds a new mango project's folder structure — `app/main.py`,
`app/registry.py`, `app/db.py`, `app/modules/`, `tests/`, plus the usual
project-root files (`pyproject.toml`, `.env.example`, `.gitignore`,
`README.md`). This is the structural counterpart to `new_module()`
(mango/cli.py): that scaffolds one module, this scaffolds the project
those modules live in. See docs/PROJECT_STRUCTURE.md for the full
convention and rationale.

Classes: none.

Functions (1):
    - init_project: writes a complete starter project into a new
      directory named after the project.
"""
from __future__ import annotations

from pathlib import Path

_PYPROJECT = """\
[project]
name = "{slug}"
version = "0.1.0"
description = "A mango project."
requires-python = ">=3.11"
dependencies = [
    "mango-api",
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
mango new-module <name> app/modules
```

Then add a line for it to `app/registry.py` so it actually gets mounted.

## Migrations

```bash
mango init-migrations app.db:Base
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
    """Scaffold a new mango project named `name` into `directory/name/`.

    Writes: pyproject.toml, .env.example, .gitignore, README.md,
    app/__init__.py, app/main.py, app/registry.py, app/db.py,
    app/modules/__init__.py, tests/__init__.py.

    Raises:
        FileExistsError: if `directory/name/` already exists.
    """
    slug = name.lower().replace(" ", "-").replace("_", "-")  # normalized project/package name for pyproject.toml
    root = Path(directory) / name  # the new project's root directory
    if root.exists():
        raise FileExistsError(f"{root} already exists")

    (root / "app" / "modules").mkdir(parents=True)
    (root / "tests").mkdir(parents=True)

    (root / "pyproject.toml").write_text(_PYPROJECT.format(slug=slug), encoding="utf-8")
    (root / ".env.example").write_text(_ENV_EXAMPLE.format(slug=slug), encoding="utf-8")
    (root / ".gitignore").write_text(_GITIGNORE, encoding="utf-8")
    (root / "README.md").write_text(_README.format(name=name, slug=slug), encoding="utf-8")

    (root / "app" / "__init__.py").write_text(_APP_INIT, encoding="utf-8")
    (root / "app" / "db.py").write_text(_DB_PY, encoding="utf-8")
    (root / "app" / "registry.py").write_text(_REGISTRY_PY, encoding="utf-8")
    (root / "app" / "main.py").write_text(_MAIN_PY.format(name=name), encoding="utf-8")
    (root / "app" / "modules" / "__init__.py").write_text(_MODULES_INIT, encoding="utf-8")
    (root / "tests" / "__init__.py").write_text(_TESTS_INIT, encoding="utf-8")

    return root
