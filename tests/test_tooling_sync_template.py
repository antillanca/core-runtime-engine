"""Tests for dry-run template synchronization planning."""

from __future__ import annotations

from pathlib import Path

from core_runtime.cli.main import build_parser
from core_runtime.tooling.sync_template import TemplateSyncPlanner


def _make_repo(tmp_path: Path) -> Path:
    domain = tmp_path / "core_runtime" / "domains" / "demo_domain"
    domain.mkdir(parents=True)
    (domain / "__init__.py").write_text("from . import task\n", encoding="utf-8")
    (domain / "task.py").write_text("TASK = True\n", encoding="utf-8")
    (domain / "custom.py").write_text("CUSTOM = True\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "examples" / "domains").mkdir(parents=True)
    (tmp_path / "docs" / "domains").mkdir(parents=True)
    return tmp_path


def test_build_parser_includes_sync_template_command() -> None:
    parser = build_parser()

    args = parser.parse_args(["sync-template", "--domain", "demo_domain", "--dry-run"])
    assert args.command == "sync-template"
    assert args.domain == "demo_domain"
    assert args.dry_run is True

    all_args = parser.parse_args(["sync-template", "--all", "--dry-run"])
    assert all_args.command == "sync-template"
    assert all_args.all is True


def test_sync_template_plans_preserve_custom_files_and_missing_scaffold(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    planner = TemplateSyncPlanner(repo)

    report = planner.build_plan(domain="demo_domain", template="generic")

    assert report.status == "warning"
    assert report.summary["planned_additions"] > 0
    assert report.summary["preserved_custom"] >= 3
    assert any(item.kind == "custom_file" and item.path.endswith("custom.py") for item in report.items)
    assert any(item.status == "planned_addition" for item in report.items)


def test_sync_template_blocks_missing_domain(tmp_path: Path) -> None:
    repo = tmp_path
    (repo / "core_runtime" / "domains").mkdir(parents=True)
    planner = TemplateSyncPlanner(repo)

    report = planner.build_plan(domain="missing_domain", template="generic")

    assert report.status == "blocked"
    assert any(d.code == "core.sync_template.domain_missing" for d in report.diagnostics.diagnostics)
