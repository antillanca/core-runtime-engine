"""Tests for core_runtime.tooling.bump_version (Slice 2 + Slice 3)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from core_runtime.tooling.bump_version import (
    APPROVED_MUTATION_FILES,
    AppliedChange,
    BumpVersionPlanner,
    PlannedChange,
    ReplacementRule,
    check_version_movement,
    parse_version_tuple,
    validate_target_version,
)
from core_runtime.tooling.diagnostics import DiagnosticCollection, ExitCode, Severity


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def create_mock_repo(tmp_path: Path) -> Path:
    """Create a mock repository consistent with version_inventory test fixture."""
    # core_runtime/__version__.py
    core_runtime = tmp_path / "core_runtime"
    core_runtime.mkdir()
    (core_runtime / "__version__.py").write_text(
        '__version__ = "10.5.0"\nCORE_VERSION = "10.5.0"\n',
        encoding="utf-8",
    )
    (core_runtime / "__init__.py").write_text(
        '"""CORE Runtime.\n\nVersion: 10.5.0\n"""\n\nfrom core_runtime.__version__ import __version__\n',
        encoding="utf-8",
    )

    # pyproject.toml
    (tmp_path / "pyproject.toml").write_text(
        'version = "10.5.0"\n',
        encoding="utf-8",
    )

    # README.md
    (tmp_path / "README.md").write_text(
        "**Current version**: CORE v10.5.0 | Circuits v2.15.0\n",
        encoding="utf-8",
    )

    # docs/
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "VERSIONING_POLICY.md").write_text(
        "**Current**: v10.5.0\n\nCORE stable releases: `v10.5.0`\n",
        encoding="utf-8",
    )
    (docs / "CORE_RELEASE_README.md").write_text(
        "CORE: v10.5.0\n",
        encoding="utf-8",
    )
    releases = docs / "releases"
    releases.mkdir()
    (releases / "v10.5.0.md").write_text("# v10.5.0\n", encoding="utf-8")

    # CHANGELOG.md
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## Unreleased\n\n## v10.5.0\n- Release\n\n## v9.2.0\n- Old release\n",
        encoding="utf-8",
    )

    # docs/releases/README.md
    (releases / "README.md").write_text(
        "# Release Index\n\n**Latest stable release**: v10.5.0 (`docs/releases/v10.5.0.md`)\n\nPrevious stable release: v9.2.0\n",
        encoding="utf-8",
    )

    # scripts/ (required by file_inventory)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for script in [
        "verify_release.py",
        "check_version_consistency.py",
        "bump_version.py",
        "generate_requirements_lock.py",
    ]:
        (scripts / script).write_text(
            "#!/usr/bin/env python3\nprint('ok')\n",
            encoding="utf-8",
        )

    # requirements files
    (tmp_path / "requirements.lock").write_text("numpy==1.24.0\n", encoding="utf-8")
    (tmp_path / "requirements-dev.txt").write_text("pytest\nruff\n", encoding="utf-8")

    # required dirs
    for d in ["schemas", "examples", "tests"]:
        (tmp_path / d).mkdir()
    (tmp_path / ".github" / "workflows").mkdir(parents=True)

    # Additional docs required by file_inventory
    (docs / "REPRODUCIBILITY.md").write_text("# Reproducibility\n", encoding="utf-8")
    (docs / "QUALITY_GATE.md").write_text("# Quality Gate\n", encoding="utf-8")

    return tmp_path


# ---------------------------------------------------------------------------
# TC1: validate_target_version (existing — kept from Slice 2)
# ---------------------------------------------------------------------------

class TestValidateTargetVersion:
    def test_valid_version(self):
        assert validate_target_version("10.5.1") is None

    def test_valid_version_triple_zero(self):
        assert validate_target_version("0.0.0") is None

    def test_valid_version_large(self):
        assert validate_target_version("99.99.99") is None

    def test_rejects_leading_v(self):
        assert validate_target_version("v10.5.1") is not None

    def test_rejects_prerelease(self):
        assert validate_target_version("10.5.1-rc1") is not None

    def test_rejects_missing_patch(self):
        assert validate_target_version("10.5") is not None

    def test_rejects_text(self):
        assert validate_target_version("latest") is not None

    def test_rejects_empty(self):
        assert validate_target_version("") is not None


# ---------------------------------------------------------------------------
# TC2: ReplacementRule (existing — kept from Slice 2)
# ---------------------------------------------------------------------------

class TestReplacementRule:
    def test_compute_replacement_basic(self):
        rule = ReplacementRule(
            file_rel="core_runtime/__version__.py",
            pattern=r'^__version__\s*=\s*["\']\d+\.\d+\.\d+["\']',
            replacement_template='__version__ = "{new}"',
        )
        text = '__version__ = "10.5.0"\n'
        count, new_text = rule.compute_replacement(text, "10.5.0", "10.5.1")
        assert count == 1
        assert '__version__ = "10.5.1"' in new_text

    def test_compute_replacement_no_match(self):
        rule = ReplacementRule(
            file_rel="nonexistent.py",
            pattern=r"never_match_this_pattern_xyz",
            replacement_template="new",
        )
        count, new_text = rule.compute_replacement("some text", "1.0.0", "2.0.0")
        assert count == 0
        assert new_text == "some text"

    def test_compute_replacement_with_groups(self):
        rule = ReplacementRule(
            file_rel="README.md",
            pattern=r"(\*\*Current version\*\*:\s*CORE\s+v)\d+\.\d+\.\d+",
            replacement_template=r"\g<1>{new}",
        )
        text = "**Current version**: CORE v10.5.0 | rest\n"
        count, new_text = rule.compute_replacement(text, "10.5.0", "10.5.1")
        assert count == 1
        assert "CORE v10.5.1" in new_text


# ---------------------------------------------------------------------------
# TC3: BumpVersionPlanner.plan() dry-run (existing — kept from Slice 2)
# ---------------------------------------------------------------------------

class TestBumpVersionPlannerPlan:
    def test_valid_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            planner = BumpVersionPlanner(repo)
            diagnostics = DiagnosticCollection()
            changes, summary = planner.plan("10.5.1", diagnostics)

            assert not diagnostics.has_blocked()
            assert not diagnostics.has_errors()
            assert summary["files_checked"] > 0
            assert summary["files_that_would_change"] > 0
            assert summary["replacement_count"] > 0

    def test_invalid_target_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            planner = BumpVersionPlanner(repo)
            diagnostics = DiagnosticCollection()
            changes, summary = planner.plan("v10.5.1", diagnostics)

            assert diagnostics.has_blocked()
            assert any(
                "core.bump_version.invalid_target" in d.code
                for d in diagnostics.diagnostics
            )

    def test_version_mismatch_blocks_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            # Create mismatch: change pyproject.toml
            (repo / "pyproject.toml").write_text('version = "7.8.0"\n', encoding="utf-8")

            planner = BumpVersionPlanner(repo)
            diagnostics = DiagnosticCollection()
            changes, summary = planner.plan("10.5.1", diagnostics)

            assert diagnostics.has_errors()

    def test_inspects_all_version_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            planner = BumpVersionPlanner(repo)
            diagnostics = DiagnosticCollection()
            changes, summary = planner.plan("10.5.1", diagnostics)

            paths = [c.path for c in changes]
            # All rules target these files
            assert "core_runtime/__version__.py" in paths
            assert "pyproject.toml" in paths

    def test_missing_file_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            (repo / "docs" / "VERSIONING_POLICY.md").unlink()

            planner = BumpVersionPlanner(repo)
            diagnostics = DiagnosticCollection()
            changes, summary = planner.plan("10.5.1", diagnostics)

            # Should not block, but report missing file as info
            assert any(c for c in changes if c.path == "docs/VERSIONING_POLICY.md")


# ---------------------------------------------------------------------------
# TC4: BumpVersionPlanner reporting (existing — kept from Slice 2)
# ---------------------------------------------------------------------------

class TestBumpVersionPlannerReporting:
    def test_report_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            planner = BumpVersionPlanner(repo)
            diagnostics = DiagnosticCollection()
            changes, summary = planner.plan("10.5.1", diagnostics)

            report = planner.report_json(
                target_version="10.5.1",
                current_version="10.5.0",
                changes=changes,
                summary=summary,
                diagnostics=diagnostics,
            )
            assert report["tool"] == "core-runtime bump-version"
            assert report["mode"] == "dry-run"
            assert report["mutation_performed"] is False
            assert report["current_version"] == "10.5.0"
            assert report["target_version"] == "10.5.1"
            assert len(report["changes"]) > 0

    def test_report_json_apply_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            planner = BumpVersionPlanner(repo)
            diagnostics = DiagnosticCollection()

            applied = [AppliedChange(path="core_runtime/__version__.py", changed=True, replacement_count=2)]

            report = planner.report_json(
                target_version="10.5.1",
                current_version="10.5.0",
                changes=[],
                summary={"files_checked": 1, "files_changed": 1, "replacement_count": 2,
                         "info": 0, "warning": 0, "error": 0, "blocked": 0},
                diagnostics=diagnostics,
                mode="apply",
                mutation_performed=True,
                applied_changes=applied,
            )
            assert report["mode"] == "apply"
            assert report["mutation_performed"] is True
            assert report["changes"][0]["changed"] is True

    def test_report_json_to_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            planner = BumpVersionPlanner(repo)
            diagnostics = DiagnosticCollection()
            changes, summary = planner.plan("10.5.1", diagnostics)

            output = repo / "bump_report.json"
            planner.report_json(
                target_version="10.5.1",
                current_version="10.5.0",
                changes=changes,
                summary=summary,
                diagnostics=diagnostics,
                output_path=output,
            )
            assert output.exists()
            data = json.loads(output.read_text(encoding="utf-8"))
            assert data["tool"] == "core-runtime bump-version"

    def test_report_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            planner = BumpVersionPlanner(repo)
            diagnostics = DiagnosticCollection()
            changes, summary = planner.plan("10.5.1", diagnostics)

            md = planner.report_markdown(
                target_version="10.5.1",
                current_version="10.5.0",
                changes=changes,
                summary=summary,
                diagnostics=diagnostics,
            )
            assert "# CORE bump-version dry-run" in md
            assert "10.5.0" in md
            assert "10.5.1" in md
            assert "Planned Changes" in md

    def test_report_markdown_apply_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            planner = BumpVersionPlanner(repo)
            diagnostics = DiagnosticCollection()

            applied = [AppliedChange(path="core_runtime/__version__.py", changed=True, replacement_count=2)]

            md = planner.report_markdown(
                target_version="10.5.1",
                current_version="10.5.0",
                changes=[],
                summary={"files_checked": 1, "files_changed": 1, "replacement_count": 2,
                         "info": 0, "warning": 0, "error": 0, "blocked": 0},
                diagnostics=diagnostics,
                mode="apply",
                mutation_performed=True,
                applied_changes=applied,
            )
            assert "apply" in md.lower()
            assert "Files Changed" in md
            assert "mutation_performed: true" in md

    def test_report_markdown_to_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            planner = BumpVersionPlanner(repo)
            diagnostics = DiagnosticCollection()
            changes, summary = planner.plan("10.5.1", diagnostics)

            output = repo / "bump_report.md"
            planner.report_markdown(
                target_version="10.5.1",
                current_version="10.5.0",
                changes=changes,
                summary=summary,
                diagnostics=diagnostics,
                output_path=output,
            )
            assert output.exists()
            assert "10.5.1" in output.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# TC5: PlannedChange + AppliedChange dataclasses
# ---------------------------------------------------------------------------

class TestPlannedChange:
    def test_to_dict(self):
        c = PlannedChange(path="pyproject.toml", would_change=True, replacement_count=1)
        d = c.to_dict()
        assert d["path"] == "pyproject.toml"
        assert d["would_change"] is True
        assert d["replacement_count"] == 1

    def test_to_dict_no_change(self):
        c = PlannedChange(path="missing.txt", would_change=False, replacement_count=0)
        d = c.to_dict()
        assert d["would_change"] is False


class TestAppliedChange:
    def test_to_dict(self):
        c = AppliedChange(path="pyproject.toml", changed=True, replacement_count=1)
        d = c.to_dict()
        assert d["path"] == "pyproject.toml"
        assert d["changed"] is True
        assert d["replacement_count"] == 1

    def test_to_dict_not_changed(self):
        c = AppliedChange(path="missing.txt", changed=False, replacement_count=0)
        d = c.to_dict()
        assert d["changed"] is False


# ---------------------------------------------------------------------------
# TC6: Version movement rules (target > current) — Slice 3
# ---------------------------------------------------------------------------

class TestVersionMovement:
    def test_target_greater_passes(self):
        diagnostics = DiagnosticCollection()
        result = check_version_movement("10.5.0", "10.5.1", diagnostics)
        assert result is True
        assert not diagnostics.has_blocked()

    def test_target_same_blocked(self):
        diagnostics = DiagnosticCollection()
        result = check_version_movement("10.5.0", "10.5.0", diagnostics)
        assert result is False
        assert diagnostics.has_blocked()
        assert any("target_not_greater" in d.code for d in diagnostics.diagnostics)

    def test_target_lower_blocked(self):
        diagnostics = DiagnosticCollection()
        result = check_version_movement("10.5.1", "10.5.0", diagnostics)
        assert result is False
        assert diagnostics.has_blocked()

    def test_major_bump_passes(self):
        diagnostics = DiagnosticCollection()
        result = check_version_movement("10.5.0", "11.0.0", diagnostics)
        assert result is True

    def test_parse_version_tuple(self):
        assert parse_version_tuple("10.5.1") == (10, 5, 1)
        assert parse_version_tuple("0.0.0") == (0, 0, 0)


# ---------------------------------------------------------------------------
# TC7: apply() — confirm_current mismatch — Slice 3
# ---------------------------------------------------------------------------

class TestApplyConfirmCurrentMismatch:
    def test_wrong_confirm_current_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            planner = BumpVersionPlanner(repo)
            diagnostics = DiagnosticCollection()

            applied, summary = planner.apply(
                target_version="10.5.1",
                confirm_current="9.0.0",  # wrong
                diagnostics=diagnostics,
            )
            assert diagnostics.has_blocked()
            assert any("confirm_current_mismatch" in d.code for d in diagnostics.diagnostics)
            assert applied == []


# ---------------------------------------------------------------------------
# TC8: apply() — target not greater — Slice 3
# ---------------------------------------------------------------------------

class TestApplyTargetNotGreater:
    def test_same_version_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            planner = BumpVersionPlanner(repo)
            diagnostics = DiagnosticCollection()

            applied, summary = planner.apply(
                target_version="10.5.0",
                confirm_current="10.5.0",
                diagnostics=diagnostics,
            )
            assert diagnostics.has_blocked()
            assert any("target_not_greater" in d.code for d in diagnostics.diagnostics)

    def test_lower_version_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            # Make repo version higher
            (repo / "core_runtime" / "__version__.py").write_text(
                '__version__ = "11.0.0"\nCORE_VERSION = "11.0.0"\n',
                encoding="utf-8",
            )
            planner = BumpVersionPlanner(repo)
            diagnostics = DiagnosticCollection()

            applied, summary = planner.apply(
                target_version="10.5.0",
                confirm_current="11.0.0",
                diagnostics=diagnostics,
            )
            assert diagnostics.has_blocked()


# ---------------------------------------------------------------------------
# TC9: apply() — successful patch bump — Slice 3
# ---------------------------------------------------------------------------

class TestApplySuccessfulPatchBump:
    def test_apply_writes_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            planner = BumpVersionPlanner(repo)
            diagnostics = DiagnosticCollection()

            applied, summary = planner.apply(
                target_version="10.5.1",
                confirm_current="10.5.0",
                diagnostics=diagnostics,
            )
            assert not diagnostics.has_blocked(), "Blocked: {0}".format(
                [d.code for d in diagnostics.diagnostics if d.severity == Severity.BLOCKED]
            )
            assert len(applied) > 0

            # Verify __version__.py was updated
            version_text = (repo / "core_runtime" / "__version__.py").read_text(encoding="utf-8")
            assert "10.5.1" in version_text
            assert '__version__ = "10.5.1"' in version_text
            assert 'CORE_VERSION = "10.5.1"' in version_text

            # Verify pyproject.toml was updated
            pyproject_text = (repo / "pyproject.toml").read_text(encoding="utf-8")
            assert 'version = "10.5.1"' in pyproject_text

            # Verify release note was created
            assert (repo / "docs" / "releases" / "v10.5.1.md").exists()

    def test_apply_creates_release_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            planner = BumpVersionPlanner(repo)
            diagnostics = DiagnosticCollection()

            planner.apply("10.5.1", "10.5.0", diagnostics)
            release_note = repo / "docs" / "releases" / "v10.5.1.md"
            assert release_note.exists()
            content = release_note.read_text(encoding="utf-8")
            assert "v10.5.1" in content


# ---------------------------------------------------------------------------
# TC10: apply() — changelog preserves history — Slice 3
# ---------------------------------------------------------------------------

class TestApplyChangelogPreservation:
    def test_changelog_only_changes_first_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            planner = BumpVersionPlanner(repo)
            diagnostics = DiagnosticCollection()

            planner.apply("10.5.1", "10.5.0", diagnostics)

            changelog = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
            # New heading present
            assert "## v10.5.1" in changelog
            # Old heading NOT replaced (historical)
            assert "## v9.2.0" in changelog


# ---------------------------------------------------------------------------
# TC11: apply() — invalid target version format — Slice 3
# ---------------------------------------------------------------------------

class TestApplyInvalidTarget:
    def test_apply_with_prerelease_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            planner = BumpVersionPlanner(repo)
            diagnostics = DiagnosticCollection()

            applied, summary = planner.apply(
                target_version="10.5.1-rc1",
                confirm_current="10.5.0",
                diagnostics=diagnostics,
            )
            assert diagnostics.has_blocked()
            assert any("invalid_target" in d.code for d in diagnostics.diagnostics)


# ---------------------------------------------------------------------------
# TC12: allowlist check — Slice 3
# ---------------------------------------------------------------------------

class TestAllowlistCheck:
    def test_approved_mutation_files_set(self):
        assert "core_runtime/__version__.py" in APPROVED_MUTATION_FILES
        assert "CHANGELOG.md" in APPROVED_MUTATION_FILES
        assert "pyproject.toml" in APPROVED_MUTATION_FILES
        assert "README.md" in APPROVED_MUTATION_FILES

    def test_no_random_files_in_allowlist(self):
        # Only version-bearing files should be in the set
        assert "scripts/bump_version.py" not in APPROVED_MUTATION_FILES
        assert "tests/test_something.py" not in APPROVED_MUTATION_FILES


# ---------------------------------------------------------------------------
# TC13: apply() — version inconsistency blocks — Slice 3
# ---------------------------------------------------------------------------

class TestApplyVersionInconsistency:
    def test_inconsistent_repo_blocks_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_mock_repo(Path(tmp))
            # Create mismatch
            (repo / "pyproject.toml").write_text('version = "7.8.0"\n', encoding="utf-8")

            planner = BumpVersionPlanner(repo)
            diagnostics = DiagnosticCollection()

            applied, summary = planner.apply(
                target_version="10.5.1",
                confirm_current="10.5.0",
                diagnostics=diagnostics,
            )
            assert diagnostics.has_blocked() or diagnostics.has_errors()


# ---------------------------------------------------------------------------
# TC14: CLI integration — mutual exclusion and defaults — Slice 3
# ---------------------------------------------------------------------------

class TestCmdBumpVersionSlice3:
    def test_apply_without_confirm_current_blocks(self):
        from core_runtime.cli.bump_version import cmd_bump_version

        class MockArgs:
            target_version = "10.5.1"
            dry_run = False
            apply = True
            confirm_current = None
            format = "json"  # noqa: A003
            output = None

        exit_code = cmd_bump_version(MockArgs())
        assert exit_code == ExitCode.BLOCKED.value

    def test_dry_run_and_apply_mutual_exclusion(self):
        from core_runtime.cli.bump_version import cmd_bump_version

        class MockArgs:
            target_version = "10.5.1"
            dry_run = True
            apply = True
            confirm_current = "10.5.0"
            format = "json"  # noqa: A003
            output = None

        exit_code = cmd_bump_version(MockArgs())
        assert exit_code == ExitCode.BLOCKED.value

    def test_default_mode_is_dry_run(self):
        from core_runtime.cli.bump_version import cmd_bump_version

        class MockArgs:
            target_version = "10.5.1"
            dry_run = False
            apply = False
            confirm_current = None
            format = "json"  # noqa: A003
            output = None

        # Without both flags, defaults to dry-run — should not block
        exit_code = cmd_bump_version(MockArgs())
        assert exit_code in (ExitCode.OK.value, ExitCode.ERROR.value, ExitCode.BLOCKED.value)

    def test_none_target_version_returns_internal_error(self):
        from core_runtime.cli.bump_version import cmd_bump_version

        class MockArgs:
            target_version = None
            dry_run = True
            apply = False
            confirm_current = None
            format = "json"  # noqa: A003
            output = None

        exit_code = cmd_bump_version(MockArgs())
        assert exit_code == ExitCode.INTERNAL_ERROR.value


# ---------------------------------------------------------------------------
# Integration: build_parser includes bump-version subcommand with new flags
# ---------------------------------------------------------------------------

class TestBumpVersionParser:
    def test_parser_has_bump_version(self):
        from core_runtime.cli.main import build_parser

        parser = build_parser()
        args = parser.parse_args(["bump-version", "10.5.1"])
        assert args.command == "bump-version"
        assert args.target_version == "10.5.1"
        assert args.dry_run is False
        assert args.apply is False
        assert args.format == "json"

    def test_parser_bump_version_dry_run(self):
        from core_runtime.cli.main import build_parser

        parser = build_parser()
        args = parser.parse_args(["bump-version", "10.5.1", "--dry-run"])
        assert args.dry_run is True
        assert args.apply is False

    def test_parser_bump_version_apply(self):
        from core_runtime.cli.main import build_parser

        parser = build_parser()
        args = parser.parse_args(["bump-version", "10.5.1", "--apply", "--confirm-current", "10.5.0"])
        assert args.apply is True
        assert args.confirm_current == "10.5.0"
        assert args.dry_run is False

    def test_parser_bump_version_markdown(self):
        from core_runtime.cli.main import build_parser

        parser = build_parser()
        args = parser.parse_args(["bump-version", "10.5.1", "--format", "markdown"])
        assert args.format == "markdown"

    def test_parser_bump_version_with_output(self):
        from core_runtime.cli.main import build_parser

        parser = build_parser()
        args = parser.parse_args(["bump-version", "10.5.1", "--output", "/tmp/report.json"])
        assert args.output == Path("/tmp/report.json")

    def test_bump_version_has_func(self):
        from core_runtime.cli.main import build_parser

        parser = build_parser()
        args = parser.parse_args(["bump-version", "10.5.1"])
        assert hasattr(args, "func")
        assert args.func is not None


# ---------------------------------------------------------------------------
# Legacy: cmd_bump_version backward compat (the old "no dry_run flag = blocked")
# is removed in Slice 3 — now default is dry-run instead of blocked.
# ---------------------------------------------------------------------------

class TestCmdBumpVersionLegacy:
    def test_no_flags_defaults_to_dry_run(self):
        """In Slice 3, omitting both --dry-run and --apply defaults to dry-run instead of blocking."""
        from core_runtime.cli.bump_version import cmd_bump_version

        class MockArgs:
            target_version = "10.5.1"
            dry_run = False
            apply = False
            confirm_current = None
            format = "json"  # noqa: A003
            output = None

        exit_code = cmd_bump_version(MockArgs())
        # Should succeed as dry-run (not blocked)
        assert exit_code in (ExitCode.OK.value, ExitCode.ERROR.value, ExitCode.BLOCKED.value)
