"""Tests for dry-run-first artifact path repair planning."""

from __future__ import annotations

import json
from pathlib import Path

from core_runtime.cli.main import build_parser
from core_runtime.tooling.repair_artifact_paths import ArtifactPathRepairPlanner


def _make_repo(tmp_path: Path) -> Path:
    (tmp_path / "core_runtime" / "data" / "operational_experience").mkdir(parents=True)
    (tmp_path / "core_runtime" / "data" / "paper_figures").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    (tmp_path / "private" / "reports").mkdir(parents=True)
    (tmp_path / "core_runtime" / "data" / "artifact_migration_manifest.json").write_text(
        json.dumps(
            {
                "migrated_files": [
                    {
                        "source": "workspace/operational_experience/family_statistics.json",
                        "destination": "core_runtime/data/operational_experience/family_statistics.json",
                    },
                    {
                        "source": "runtime_release_manifest_v215.json",
                        "destination": "core_runtime/data/runtime_release_manifest_v215.json",
                    },
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_build_parser_includes_repair_artifact_paths_command() -> None:
    parser = build_parser()

    args = parser.parse_args(["repair-artifact-paths", "--dry-run"])
    assert args.command == "repair-artifact-paths"
    assert args.dry_run is True


def test_repair_artifact_paths_plans_mutable_references(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    docs_path = repo / "docs" / "repair_notes.md"
    docs_path.write_text(
        "\n".join(
            [
                "# repair notes",
                "",
                "workspace/operational_experience/family_statistics.json",
                "workspace/operational_experience/",
            ]
        ),
        encoding="utf-8",
    )

    planner = ArtifactPathRepairPlanner(repo)
    report = planner.build_plan(dry_run=True)

    assert report.status == "warning"
    assert report.summary["planned_repairs"] == 2
    assert any(item.path.endswith("repair_notes.md") for item in report.items)
    assert any(d.code == "core.repair_artifact_paths.mutable_reference" for d in report.diagnostics.diagnostics)


def test_repair_artifact_paths_blocks_immutable_evidence(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    evidence_path = repo / "private" / "reports" / "sensitive_evidence.md"
    evidence_path.write_text(
        json.dumps(
            {
                "report_path": "runtime_release_manifest_v215.json",
                "output_dir": "workspace/operational_experience/",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    planner = ArtifactPathRepairPlanner(repo)
    report = planner.build_plan(dry_run=True)

    assert report.status == "blocked"
    assert any(d.code == "core.repair_artifact_paths.immutable_reference" for d in report.diagnostics.diagnostics)


def test_repair_artifact_paths_requires_dry_run(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    planner = ArtifactPathRepairPlanner(repo)

    report = planner.build_plan(dry_run=False)

    assert report.status == "blocked"
    assert any(d.code == "core.repair_artifact_paths.dry_run_required" for d in report.diagnostics.diagnostics)
