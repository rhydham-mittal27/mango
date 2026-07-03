"""tests/test_cli.py

Tests for the `mango` CLI's argparse-based dispatch: `main()` given
various argv, `--version`, `--help`, subcommand help, and that an
expected failure (target already exists) prints a clean error instead
of a raw traceback.

Classes: none — pytest test functions only.

Functions (7):
    - _run: helper — call main() with the given argv, capturing stdout/
      stderr/exit code.
    - test_version_flag
    - test_no_command_prints_help_and_exits_1
    - test_init_scaffolds_project
    - test_new_module_scaffolds_module
    - test_init_migrations_scaffolds_alembic
    - test_existing_target_prints_clean_error_not_traceback
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


def test_version_flag(monkeypatch, capsys):
    """mango --version prints the version and exits 0."""
    code = _run(monkeypatch, ["--version"])
    assert code == 0
    assert "mango" in capsys.readouterr().out


def test_no_command_prints_help_and_exits_1(monkeypatch, capsys):
    """Running `mango` with no subcommand prints help and exits 1, not a traceback."""
    code = _run(monkeypatch, [])
    assert code == 1
    assert "usage: mango" in capsys.readouterr().out


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
