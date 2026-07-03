"""tests/test_cli.py

Tests for the `mango` CLI's argparse-based dispatch: `main()` given
various argv, `--version`, `--help`, subcommand help, and that an
expected failure (target already exists) prints a clean error instead
of a raw traceback.

`modules`/`routes` import a scaffolded project's own `app` package by
dotted name — since every project scaffolds a top-level package
literally named `app`, and Python caches imports by name in
`sys.modules`, running these against two different temp projects in the
same pytest process needs `_reset_app_imports()` between them, or the
second test would silently get the first project's cached `app` module.
This is a test-isolation concern only: real CLI usage is a fresh Python
process per invocation, so no such collision is possible there. The
module registry (`mango.module.get_registry()`) is similarly global and
process-wide, so module names used across these tests are kept unique
(`clitest_*`) rather than reused.

Classes: none — pytest test functions only.

Functions (13):
    - _run: helper — call main() with the given argv, capturing stdout/
      stderr/exit code.
    - _reset_app_imports: drops cached `app`/`app.*` modules between tests.
    - test_version_flag
    - test_no_command_prints_quickstart
    - test_init_scaffolds_project
    - test_new_module_scaffolds_module
    - test_init_migrations_scaffolds_alembic
    - test_existing_target_prints_clean_error_not_traceback
    - test_new_module_auto_detects_project_and_wires_registry
    - test_new_module_explicit_directory_skips_auto_wiring
    - test_init_dot_scaffolds_in_place
    - test_init_migrations_auto_detects_base_import
    - test_remove_module_deletes_and_unwires
    - test_modules_lists_in_mount_order
    - test_routes_lists_mounted_endpoints
    - test_doctor_reports_orphan_module_and_missing_env
    - test_migrate_requires_alembic_ini
"""
import sys

from mango.cli import main


def _run(monkeypatch, argv: list[str]):
    """Call main() with argv, capturing SystemExit's code (None if it didn't exit)."""
    monkeypatch.setattr(sys, "argv", ["mango", *argv])
    try:
        main()
        return None
    except SystemExit as exc:
        return exc.code


def _reset_app_imports():
    """Drop cached `app`/`app.*` modules — see module docstring for why
    this is needed between tests that import different projects' `app`
    packages, all literally named `app`."""
    for mod_name in list(sys.modules):
        if mod_name == "app" or mod_name.startswith("app."):
            del sys.modules[mod_name]


def test_version_flag(monkeypatch, capsys):
    """mango --version prints the version and exits 0."""
    code = _run(monkeypatch, ["--version"])
    assert code == 0
    assert "mango" in capsys.readouterr().out


def test_no_command_prints_quickstart(monkeypatch, capsys):
    """Running `mango` with no subcommand prints a friendly quickstart (not an
    error) and exits 0 — the bare command is a normal entry point for a
    first-time user, not a usage mistake."""
    code = _run(monkeypatch, [])
    assert code is None
    assert "mango init" in capsys.readouterr().out


def test_init_scaffolds_project(monkeypatch, tmp_path, capsys):
    """mango init <name> <dir> scaffolds a project and prints where."""
    code = _run(monkeypatch, ["init", "demo_shop", str(tmp_path)])
    assert code is None
    assert (tmp_path / "demo_shop" / "app" / "main.py").exists()
    assert "created" in capsys.readouterr().out


def test_new_module_scaffolds_module(monkeypatch, tmp_path, capsys):
    """mango new-module <name> <dir> scaffolds a module.py and prints where."""
    code = _run(monkeypatch, ["new-module", "billing", str(tmp_path)])
    assert code is None
    assert (tmp_path / "billing" / "module.py").exists()
    assert "created" in capsys.readouterr().out


def test_init_migrations_scaffolds_alembic(monkeypatch, tmp_path, capsys):
    """mango init-migrations <base_import> <dir> scaffolds alembic.ini + migrations/."""
    code = _run(monkeypatch, ["init-migrations", "app.db:Base", str(tmp_path)])
    assert code is None
    assert (tmp_path / "alembic.ini").exists()
    assert (tmp_path / "migrations" / "env.py").exists()


def test_existing_target_prints_clean_error_not_traceback(monkeypatch, tmp_path, capsys):
    """Scaffolding into an already-existing target prints `error: ...` and exits 1, no traceback."""
    _run(monkeypatch, ["init", "demo_shop", str(tmp_path)])  # first call succeeds
    code = _run(monkeypatch, ["init", "demo_shop", str(tmp_path)])  # second call collides
    assert code == 1
    assert capsys.readouterr().err.startswith("error:")


def test_new_module_auto_detects_project_and_wires_registry(monkeypatch, tmp_path, capsys):
    """Running `mango new-module <name>` with no directory, from inside a
    project scaffolded by `mango init`, auto-detects modules_dir from
    project.mango and auto-wires the import into registry.py."""
    _run(monkeypatch, ["init", "demo_shop", str(tmp_path)])
    project_root = tmp_path / "demo_shop"
    assert (project_root / "project.mango").exists()

    monkeypatch.chdir(project_root / "app")  # run from a subdirectory, not the root
    code = _run(monkeypatch, ["new-module", "billing"])
    assert code is None

    module_file = project_root / "app" / "modules" / "billing" / "module.py"
    assert module_file.exists()

    registry_text = (project_root / "app" / "registry.py").read_text(encoding="utf-8")
    assert "import app.modules.billing.module" in registry_text
    assert "wired into registry.py automatically" in capsys.readouterr().out


def test_new_module_explicit_directory_skips_auto_wiring(monkeypatch, tmp_path, capsys):
    """Passing an explicit directory bypasses manifest auto-detection entirely,
    same as before project.mango existed."""
    code = _run(monkeypatch, ["new-module", "billing", str(tmp_path)])
    assert code is None
    assert (tmp_path / "billing" / "module.py").exists()
    assert "next step: wire it up" in capsys.readouterr().out


def test_init_dot_scaffolds_in_place(monkeypatch, tmp_path, capsys):
    """mango init . scaffolds the given directory itself, no nested
    subfolder, and skips the (now meaningless) `cd` next-step."""
    target = tmp_path / "my_cool_app"
    target.mkdir()

    code = _run(monkeypatch, ["init", ".", str(target)])
    assert code is None
    assert (target / "app" / "main.py").exists()
    assert (target / "project.mango").exists()
    out = capsys.readouterr().out
    assert "created" in out
    assert "cd " not in out


def test_init_migrations_auto_detects_base_import(monkeypatch, tmp_path):
    """Running `mango init-migrations` with no args, from inside a project
    scaffolded by `mango init`, reads base_import and the project root from
    project.mango."""
    _run(monkeypatch, ["init", "demo_shop", str(tmp_path)])
    project_root = tmp_path / "demo_shop"

    monkeypatch.chdir(project_root)
    code = _run(monkeypatch, ["init-migrations"])
    assert code is None
    assert (project_root / "alembic.ini").exists()
    assert (project_root / "migrations" / "env.py").exists()


def test_init_migrations_auto_wires_models_import_from_manifest(monkeypatch, tmp_path):
    """mango init-migrations, run inside a project, also imports the
    project's registry.py in env.py — without this, every model module
    stays unimported and `alembic revision --autogenerate` silently
    diffs against an empty Base.metadata, producing an empty migration."""
    _run(monkeypatch, ["init", "demo_shop", str(tmp_path)])
    project_root = tmp_path / "demo_shop"

    monkeypatch.chdir(project_root)
    code = _run(monkeypatch, ["init-migrations"])
    assert code is None

    env_contents = (project_root / "migrations" / "env.py").read_text(encoding="utf-8")
    assert "import app.registry" in env_contents


def test_remove_module_deletes_and_unwires(monkeypatch, tmp_path, capsys):
    """mango remove-module <name> deletes the module's directory and
    removes its import from registry.py — the inverse of new-module."""
    _run(monkeypatch, ["init", "demo_shop", str(tmp_path)])
    project_root = tmp_path / "demo_shop"
    monkeypatch.chdir(project_root)
    _run(monkeypatch, ["new-module", "clitest_gone"])
    module_dir = project_root / "app" / "modules" / "clitest_gone"
    assert module_dir.exists()

    code = _run(monkeypatch, ["remove-module", "clitest_gone"])
    assert code is None
    assert not module_dir.exists()

    registry_text = (project_root / "app" / "registry.py").read_text(encoding="utf-8")
    assert "clitest_gone" not in registry_text
    assert "un-wired from registry.py automatically" in capsys.readouterr().out


def test_remove_module_missing_raises(monkeypatch, tmp_path):
    """Removing a module that doesn't exist prints a clean error, not a traceback."""
    _run(monkeypatch, ["init", "demo_shop", str(tmp_path)])
    project_root = tmp_path / "demo_shop"
    monkeypatch.chdir(project_root)

    code = _run(monkeypatch, ["remove-module", "does_not_exist"])
    assert code == 1


def test_modules_lists_in_mount_order(monkeypatch, tmp_path, capsys):
    """mango modules imports the project's registry.py (registering every
    module) and lists them in dependency-respecting mount order."""
    _run(monkeypatch, ["init", "demo_shop", str(tmp_path)])
    project_root = tmp_path / "demo_shop"
    monkeypatch.chdir(project_root)
    _run(monkeypatch, ["new-module", "clitest_alpha"])
    _run(monkeypatch, ["new-module", "clitest_beta"])

    _reset_app_imports()
    code = _run(monkeypatch, ["modules"])
    assert code is None
    out = capsys.readouterr().out
    assert "clitest_alpha" in out
    assert "clitest_beta" in out


def test_routes_lists_mounted_endpoints(monkeypatch, tmp_path, capsys):
    """mango routes imports the project's app_import (app.main:app) and
    lists every route actually mounted, including the module's own
    generated ping endpoint and the app's own /healthz."""
    _run(monkeypatch, ["init", "demo_shop", str(tmp_path)])
    project_root = tmp_path / "demo_shop"
    monkeypatch.chdir(project_root)
    _run(monkeypatch, ["new-module", "clitest_widgets"])
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

    _reset_app_imports()
    code = _run(monkeypatch, ["routes"])
    assert code is None
    out = capsys.readouterr().out
    assert "/api/v1/clitest_widgets/ping" in out
    assert "/healthz" in out


def test_doctor_reports_orphan_module_and_missing_env(monkeypatch, tmp_path, capsys):
    """mango doctor flags a module folder created by hand (never wired
    into registry.py) and a missing .env, exiting 1 when any check fails."""
    _run(monkeypatch, ["init", "demo_shop", str(tmp_path)])
    project_root = tmp_path / "demo_shop"
    orphan_dir = project_root / "app" / "modules" / "clitest_orphan"
    orphan_dir.mkdir(parents=True)
    (orphan_dir / "module.py").write_text("# stub, never wired into registry.py\n", encoding="utf-8")

    monkeypatch.chdir(project_root)
    code = _run(monkeypatch, ["doctor"])
    assert code == 1
    out = capsys.readouterr().out
    assert "FAIL" in out
    assert "clitest_orphan" in out
    assert ".env" in out


def test_doctor_all_checks_pass_for_healthy_project(monkeypatch, tmp_path, capsys):
    """mango doctor exits 0 and reports all-clear for a freshly scaffolded,
    correctly-wired project with its .env in place."""
    _run(monkeypatch, ["init", "demo_shop", str(tmp_path)])
    project_root = tmp_path / "demo_shop"
    monkeypatch.chdir(project_root)
    _run(monkeypatch, ["new-module", "clitest_healthy"])
    (project_root / ".env").write_text("DATABASE_URL=sqlite+aiosqlite:///./demo.db\n", encoding="utf-8")

    code = _run(monkeypatch, ["doctor"])
    assert code is None
    assert "all checks passed" in capsys.readouterr().out


def test_migrate_requires_alembic_ini(monkeypatch, tmp_path):
    """mango migrate prints a clean error (not a traceback) if
    `mango init-migrations` hasn't been run yet."""
    _run(monkeypatch, ["init", "demo_shop", str(tmp_path)])
    project_root = tmp_path / "demo_shop"
    monkeypatch.chdir(project_root)

    code = _run(monkeypatch, ["migrate", "add things"])
    assert code == 1
