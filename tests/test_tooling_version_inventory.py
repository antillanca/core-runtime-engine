"""Tests for core_runtime.tooling.version_inventory."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from core_runtime.tooling.diagnostics import DiagnosticCollection
from core_runtime.tooling.version_inventory import VersionInventory


def create_mock_repo(tmp_path: Path) -> Path:
    """Create a mock repository structure for testing."""
    # Create core_runtime/__version__.py
    core_runtime = tmp_path / "core_runtime"
    core_runtime.mkdir()
    (core_runtime / "__version__.py").write_text(
        '__version__ = "10.5.0"\nCORE_VERSION = "10.5.0"\n',
        encoding="utf-8",
    )
    (core_runtime / "__init__.py").write_text(
        'from core_runtime.__version__ import __version__\n',
        encoding="utf-8",
    )

    # pyproject.toml
    (tmp_path / "pyproject.toml").write_text(
        'version = "10.5.0"\n',
        encoding="utf-8",
    )

    # README.md
    (tmp_path / "README.md").write_text(
        '**Current version**: CORE v10.5.0 | Circuits v2.15.0\n',
        encoding="utf-8",
    )

    # docs/
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "VERSIONING_POLICY.md").write_text(
        '**Current**: v10.5.0\n',
        encoding="utf-8",
    )
    (docs / "CORE_RELEASE_README.md").write_text(
        'CORE: v10.5.0\n',
        encoding="utf-8",
    )
    releases = docs / "releases"
    releases.mkdir()
    (releases / "v10.5.0.md").write_text("# v10.5.0\n", encoding="utf-8")

    # CHANGELOG.md
    (tmp_path / "CHANGELOG.md").write_text(
        '# Changelog\n\n## v10.5.0\n- Release\n',
        encoding="utf-8",
    )

    # scripts/
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for script in ["verify_release.py", "check_version_consistency.py", "bump_version.py", "generate_requirements_lock.py"]:
        (scripts / script).write_text("#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")

    # requirements files
    (tmp_path / "requirements.lock").write_text("numpy==1.24.0\n", encoding="utf-8")
    (tmp_path / "requirements-dev.txt").write_text("pytest\nruff\n", encoding="utf-8")

    # directories
    for d in ["schemas", "examples", "tests"]:
        (tmp_path / d).mkdir()
    # Nested .github/workflows needs parents=True
    (tmp_path / ".github" / "workflows").mkdir(parents=True)

    return tmp_path


class TestVersionInventory:
    def test_discover_all_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            inv = VersionInventory(repo)
            sources = inv.discover()

            # Should find all sources
            names = [s.name for s in sources]
            assert "core_runtime/__version__.py" in names
            assert "pyproject.toml" in names
            assert "core_runtime/__init__.py" in names
            assert "README.md" in names
            assert "docs/VERSIONING_POLICY.md" in names
            assert "CHANGELOG.md" in names
            assert "docs/CORE_RELEASE_README.md" in names

    def test_get_canonical_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            inv = VersionInventory(repo)
            canonical = inv.get_canonical_version()
            assert canonical == "10.5.0"

    def test_check_consistency_all_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            inv = VersionInventory(repo)
            diagnostics = DiagnosticCollection()
            sources = inv.check_consistency(diagnostics)

            # All should be consistent
            assert not diagnostics.has_errors()
            assert not diagnostics.has_blocked()

    def test_check_consistency_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            # Change pyproject.toml version
            (repo / "pyproject.toml").write_text('version = "7.8.0"\n', encoding="utf-8")

            inv = VersionInventory(repo)
            diagnostics = DiagnosticCollection()
            sources = inv.check_consistency(diagnostics)

            # Should detect mismatch
            assert diagnostics.has_errors()
            errors = [d for d in diagnostics.diagnostics if d.severity.value == "error"]
            assert any("core.version.inconsistent" in d.code for d in errors)

    def test_check_consistency_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            # Remove README.md
            (repo / "README.md").unlink()

            inv = VersionInventory(repo)
            diagnostics = DiagnosticCollection()
            sources = inv.check_consistency(diagnostics)

            # Should detect missing
            assert diagnostics.has_errors()
            errors = [d for d in diagnostics.diagnostics if d.severity.value == "error"]
            assert any("core.version.missing" in d.code for d in errors)

    def test_check_changelog_latest_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            inv = VersionInventory(repo)
            diagnostics = DiagnosticCollection()
            inv.check_changelog_latest(diagnostics)

            # Should not error
            assert not diagnostics.has_errors()

    def test_check_changelog_latest_ahead(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            # Change CHANGELOG to have newer version
            (repo / "CHANGELOG.md").write_text(
                '# Changelog\n\n## v11.0.0\n- Future release\n',
                encoding="utf-8",
            )

            inv = VersionInventory(repo)
            diagnostics = DiagnosticCollection()
            inv.check_changelog_latest(diagnostics)

            # Should warn or error
            errors = [d for d in diagnostics.diagnostics if d.severity.value == "error"]
            warnings = [d for d in diagnostics.diagnostics if d.severity.value == "warning"]
            assert any("core.version.changelog_ahead" in d.code for d in errors)

    def test_check_release_note_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            inv = VersionInventory(repo)
            diagnostics = DiagnosticCollection()
            inv.check_release_note(diagnostics)

            # Should not error (release note exists)
            assert not diagnostics.has_errors()

    def test_check_release_note_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            # Remove release note
            (repo / "docs" / "releases" / "v10.5.0.md").unlink()

            inv = VersionInventory(repo)
            diagnostics = DiagnosticCollection()
            inv.check_release_note(diagnostics)

            # Should error
            assert diagnostics.has_errors()
            errors = [d for d in diagnostics.diagnostics if d.severity.value == "error"]
            assert any("core.version.release_note_missing" in d.code for d in errors)

    def test_check_init_reexport(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            inv = VersionInventory(repo)

            # Check correct re-export
            sources = inv.discover()
            init_source = next(s for s in sources if s.name == "core_runtime/__init__.py")
            assert init_source.version == "re-export"

            # Now break it
            (repo / "core_runtime" / "__init__.py").write_text(
                '__version__ = "9.9.9"\n', encoding="utf-8"
            )

            sources = inv.discover()
            init_source = next(s for s in sources if s.name == "core_runtime/__init__.py")
            assert init_source.version != "re-export"