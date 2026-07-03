# mango project structure

This is the convention `mango init <name>` scaffolds and the rest of
mango (module registration, `App.mount_all()`, `init_migrations`)
assumes. It isn't enforced by the framework — nothing breaks if you lay
a project out differently — but following it is what makes the rest of
mango's boilerplate-cutting actually work: `mount_all()` only mounts
modules that got *imported*, `init_migrations` only sees tables whose
models share one `Base`, and so on. Deviating from this loses those
guarantees one at a time.

## The layout

```
demo_shop/
├── pyproject.toml
├── .env.example
├── .gitignore
├── README.md
├── alembic.ini              # after `mango init-migrations`
├── app/
│   ├── __init__.py
│   ├── main.py               # owns the mango.App instance — the ONLY file that does
│   ├── registry.py            # imports every module for its @mango.module side effect
│   ├── db.py                   # the ONE mango.Database instance + the shared declarative Base
│   ├── auth.py                  # the ONE mango.Auth instance, IF the project has auth
│   └── modules/
│       ├── __init__.py
│       ├── items/
│       │   └── module.py         # simple module: everything in one file
│       └── orders/                # a module that outgrew one file
│           ├── module.py           # MangoModule declaration + router only
│           ├── models.py
│           ├── repository.py
│           ├── schemas.py
│           └── service.py
├── migrations/               # after `mango init-migrations`
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
└── tests/
    ├── __init__.py
    └── modules/
        ├── items/
        │   └── test_module.py
        └── orders/
            └── test_module.py
```

Generate the skeleton (everything above `app/modules/`) with:

```bash
mango init demo_shop
```

Add a module with:

```bash
mango new-module items app/modules
```

## The rules, and why each one exists

**One module = one directory under `app/modules/`.** This is the same
vertical-slice convention `collabfluenz.backend` converged on after
starting horizontally layered (`app/models/`, `app/services/`,
`app/routers/`) and finding that every real change touched 4+
directories for one feature. A module directory is self-contained: you
can delete it, and nothing outside `app/registry.py`'s one import line
needs to change.

**Every module starts as a single `module.py`.** `mango new-module`
generates exactly one file: a router, a `@mango.module` declaration, and
nothing else. Don't pre-split into `models.py`/`repository.py`/etc.
before a module actually needs it — a module with one endpoint and no
DB model doesn't need five empty files. Split only when the single file
gets genuinely hard to scan (a rough rule of thumb: once `module.py`
crosses ~150 lines, or once it has both a model *and* enough router
logic that they're fighting for attention in the same file). When you
do split, keep `module.py` as the "table of contents" — just the
`@mango.module` declaration and imports from the sibling files — never
delete it, since it's the one file `app/registry.py` needs to import.

**`app/registry.py` is the only file that knows every module exists.**
Not `app/main.py`, not any other module. This is what makes adding a
module a one-line change (`import app.modules.new_thing.module`) instead
of touching a router-mounting block, an `__init__.py`, and a settings
file. It's also, not incidentally, the exact fix for the
"`__init__.py`-eagerly-imports-router causes a circular import" class of
bug: `registry.py` importing every module means Python resolves the
whole import graph once, at a predictable point, rather than lazily and
unpredictably whenever two modules happen to reference each other.

**`app/db.py` owns exactly one `Database` instance and one `Base`.**
Every module's `models.py` imports `Base` from here — never defines its
own. This isn't a style preference: `init_migrations`'s autogenerate
only sees tables registered on the `Base.metadata` it was pointed at
(`app.db:Base`), so a second `Base` anywhere means a table that silently
never gets a migration. One `Database` instance also means one
connection pool, not one per module competing for connections.

**`app/auth.py` owns exactly one `Auth` instance, if the project has
auth at all.** Same reasoning as `db.py` — a project shouldn't have two
different opinions about how a token gets verified. Modules import
`auth` from here and call `auth.require_role(...)` etc. in their
`module.py`/`router.py`.

**`app/main.py` is the only file that imports `mango.App` (or touches
`fastapi` directly at all, if you drop to the escape hatch).** Every
other file — modules, `db.py`, `auth.py` — only ever needs `mango.`
names. This is what makes "never import fastapi/pydantic directly" true
project-wide rather than just true of `main.py`.

**`tests/` mirrors `app/modules/` one-to-one.** `tests/modules/items/`
for `app/modules/items/`. When a module is deleted, its test directory
goes with it in the same commit — nothing is left over to eventually
confuse someone about what still exists.

## When a module needs sub-modules of its own

Some domains are big enough that "one module" is itself made of related
pieces (e.g. `orders` might reasonably contain `orders/refunds.py`
alongside `orders/service.py`). That's fine — the rule is about the
*directory* boundary (`app/modules/orders/` is one unit, imported by one
line in `registry.py`), not about forcing everything inside it into a
fixed five-file shape. `models.py`/`repository.py`/`schemas.py`/
`service.py`/`module.py` is a strong default, not a hard requirement.

## What doesn't fit this shape

A handful of things are legitimately cross-cutting and don't belong
inside any one module:

- **Shared constants/enums used by more than one module's schemas** (an
  allowed-values list, a shared status enum) — put these in
  `app/shared.py` (or `app/shared/` if there end up being several).
  Keep this file small and genuinely shared; if only one module uses
  something, it belongs in that module, not here.
- **Background job entry points that don't belong to any single
  module's HTTP surface** (a nightly digest that reads from three
  modules) — `app/tasks.py`, using `mango.run_in_background`/
  `db.spawn` the same way a request handler would.

Resist the urge to grow either of these into a dumping ground — the
same instinct that keeps `app/shared/` in `collabfluenz.backend` to four
small files (constants, ORM base, generic repository, validators)
applies here.
