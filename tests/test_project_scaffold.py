"""tests/test_project_scaffold.py

Tests for mango.init_project — the project-folder-structure scaffolder.
Doesn't install/boot the generated project (that's covered manually,
see docs/PROJECT_STRUCTURE.md's worked example) — just verifies the
expected files exist and contain the expected wiring.

Classes: none — pytest test functions only.

Functions (5):
    - test_init_project_scaffolds_expected_files
    - test_init_project_rejects_existing_directory
    - test_scaffolded_main_imports_registry_and_mounts
    - test_init_project_in_place_infers_name_from_directory
    - test_init_project_in_place_rejects_conflicting_files
"""
import pytest

import mango


def test_init_project_scaffolds_expected_files(tmp_path):
    """init_project writes the full expected file set."""
    root = mango.init_project("demo_shop", str(tmp_path))

    assert root == tmp_path / "demo_shop"
    assert (root / "pyproject.toml").exists()
    assert (root / ".env.example").exists()
    assert (root / ".gitignore").exists()
    assert (root / "README.md").exists()
    assert (root / "app" / "__init__.py").exists()
    assert (root / "app" / "main.py").exists()
    assert (root / "app" / "registry.py").exists()
    assert (root / "app" / "db.py").exists()
    assert (root / "app" / "modules" / "__init__.py").exists()
    assert (root / "tests" / "__init__.py").exists()


def test_init_project_rejects_existing_directory(tmp_path):
    """Scaffolding into a directory that already exists raises, rather than silently overwriting."""
    mango.init_project("demo_shop", str(tmp_path))
    with pytest.raises(FileExistsError):
        mango.init_project("demo_shop", str(tmp_path))


def test_scaffolded_main_imports_registry_and_mounts(tmp_path):
    """The generated app/main.py imports app/registry.py and calls app.mount_all()."""
    root = mango.init_project("demo_shop", str(tmp_path))

    main_contents = (root / "app" / "main.py").read_text(encoding="utf-8")
    assert "from app import registry" in main_contents
    assert "app.mount_all()" in main_contents
    assert "mango.App(" in main_contents

    db_contents = (root / "app" / "db.py").read_text(encoding="utf-8")
    assert "class Base(DeclarativeBase)" in db_contents
    assert "mango.Database(" in db_contents


def test_init_project_in_place_infers_name_from_directory(tmp_path):
    """init_project(".", directory) scaffolds directory itself (no nested
    subfolder), taking the project name from the directory's own name."""
    target = tmp_path / "my_cool_app"
    target.mkdir()

    root = mango.init_project(".", str(target))

    assert root == target.resolve()
    assert (root / "pyproject.toml").exists()
    assert (root / "app" / "main.py").exists()
    assert (root / "project.mango").exists()
    assert 'name = "my-cool-app"' in (root / "pyproject.toml").read_text(encoding="utf-8")
    assert "# my_cool_app" in (root / "README.md").read_text(encoding="utf-8")


def test_init_project_in_place_rejects_conflicting_files(tmp_path):
    """Re-running init_project(".", ...) against a directory that already
    has scaffolded files raises, naming the conflicts, rather than
    silently overwriting them."""
    target = tmp_path / "my_cool_app"
    target.mkdir()
    mango.init_project(".", str(target))

    with pytest.raises(FileExistsError, match="pyproject.toml"):
        mango.init_project(".", str(target))
