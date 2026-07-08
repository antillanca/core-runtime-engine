"""Tests for dry-run-first domain scaffolding."""

from __future__ import annotations

from pathlib import Path

from core_runtime.cli.main import build_parser
from core_runtime.tooling.create_domain import DomainScaffolder


def _make_repo(tmp_path: Path) -> Path:
    (tmp_path / "core_runtime" / "domains").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "examples" / "domains").mkdir(parents=True)
    (tmp_path / "docs" / "domains").mkdir(parents=True)
    return tmp_path


def test_build_parser_includes_create_domain_command() -> None:
    parser = build_parser()

    args = parser.parse_args(["create-domain", "demo_domain", "--dry-run"])
    assert args.command == "create-domain"
    assert args.name == "demo_domain"
    assert args.dry_run is True


def test_create_domain_plan_is_dry_run_only(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    scaffolder = DomainScaffolder(repo)

    report = scaffolder.build_plan("demo_domain", template="readonly-consumer")

    assert report.status == "warning"
    assert report.summary["item_count"] == 13
    assert report.summary["risk_count"] >= 5
    assert report.items[0].path == "core_runtime/domains/demo_domain"
    assert report.items[-1].path == "docs/domains/demo_domain.md"


def test_create_domain_plan_blocks_name_collisions(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    (repo / "core_runtime" / "domains" / "demo_domain").mkdir()
    scaffolder = DomainScaffolder(repo)

    report = scaffolder.build_plan("demo_domain")

    assert report.status == "blocked"
    assert any(d.code == "core.create_domain.collision" for d in report.diagnostics.diagnostics)
