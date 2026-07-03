# Contributing to mango

## Setup

```bash
cd mango
pip install -e ".[dev]"
pytest -q
```

## Ground rules

- **Every change ships with a test.** No exceptions for "it's obviously
  correct" — the `App.on_startup`/`on_shutdown` bug in this changelog
  (looked correct, broke on a newer FastAPI version, only caught because
  a test exercised it) is exactly why.
- **Every new public symbol gets exported from `mango/__init__.py`** and
  added to its module docstring's Classes/Functions inventory. Nothing
  is "internal but technically importable" — either it's in
  `mango.__all__` or it's prefixed `_` and genuinely private.
- **Update `CHANGELOG.md` under `[Unreleased]`** in the same PR/commit as
  the change. A change without a changelog entry is the number one way
  this project's history becomes useless to someone (including future
  you) trying to understand why something works the way it does.
- **Update `docs/GUIDE.md`** if the change is user-facing — a new piece
  isn't done until it has a worked example, not just a docstring.
- **Don't reimplement FastAPI/Pydantic/SQLAlchemy behavior.** mango's
  entire value proposition is being a thin layer — if something can be a
  re-export (`mango/web.py`, `mango/schema.py`) instead of a wrapper
  class, make it a re-export. Only wrap when there's real behavior to
  add (error mapping, mounting, generic CRUD) — not for the sake of
  having a `mango.` name.
- **Don't force an opinion where the answer is genuinely
  project-specific.** `mango.Auth` takes `verify_token`/`load_user` as
  plain callables rather than assuming a JWT library or a specific ORM
  shape, on purpose — that's the line between "convention" and
  "someone else's opinion imposed on your project."

## Before opening a PR

1. `pytest -q` — all tests pass.
2. `python -c "import mango"` — no import-time errors (this catches
   circular imports between `mango/*.py` files immediately).
3. If you touched `mango/crud.py`: re-read the comment at the top of
   that file about why it can't use `from __future__ import
   annotations` — this exact mistake has broken it once already (see
   CHANGELOG's Fixed section) and is easy to reintroduce without
   realizing why it matters.
4. If you added a CLI subcommand: update the `_USAGE` string in
   `mango/cli.py` and add a test in `tests/`.

## Versioning

While mango is `0.x`, breaking changes are allowed but must be called
out explicitly in `CHANGELOG.md`'s `[Unreleased]` section under
"Changed"/"Removed" — never silently. Once mango reaches `1.0`, it
follows standard [SemVer](https://semver.org/): breaking changes require
a major version bump.

## Design philosophy, in one sentence

mango exists to make a FastAPI + SQLAlchemy project's code shorter and
more uniform, never to add abstraction for its own sake — if an addition
doesn't measurably cut boilerplate a real project would otherwise write,
it doesn't belong in mango. See `README.md`'s "The size goal" section
for the concrete standard.
