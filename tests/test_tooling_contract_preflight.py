"""Tests for advisory-only contract preflight."""

from __future__ import annotations

import json
from pathlib import Path

from core_runtime.cli.main import build_parser
from core_runtime.tooling.contract_preflight import RepositoryContractPreflight


def _make_repo(tmp_path: Path) -> Path:
    schemas = tmp_path / "schemas" / "core"
    schemas.mkdir(parents=True)

    for name, title, required in [
        ("task_closeout.v1.json", "TaskCloseout.v1", ["schema_version", "status", "source_type"]),
        ("effect_result.v1.json", "EffectResult.v1", ["schema_version", "status", "effect_type"]),
    ]:
        (schemas / name).write_text(
            json.dumps(
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "title": title,
                    "type": "object",
                    "required": required,
                    "properties": {
                        "schema_version": {"const": f"core.{title[:-3].lower()}"},
                        "status": {"type": "string"},
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    return tmp_path


def test_build_parser_includes_contract_preflight_command() -> None:
    parser = build_parser()

    candidate_args = parser.parse_args(["contract-preflight", "--candidate", "TaskCloseout.v1"])
    assert candidate_args.command == "contract-preflight"
    assert candidate_args.candidate == "TaskCloseout.v1"

    compare_args = parser.parse_args(["contract-preflight", "--compare", "TaskCloseout.v1", "EffectResult.v1"])
    assert compare_args.command == "contract-preflight"
    assert compare_args.compare == ["TaskCloseout.v1", "EffectResult.v1"]


def test_contract_preflight_candidate_and_compare(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    preflight = RepositoryContractPreflight(repo)

    candidate_report = preflight.build_candidate_report("TaskCloseout.v1")
    compare_report = preflight.build_compare_report("TaskCloseout.v1", "EffectResult.v1")

    assert candidate_report.status == "pass"
    assert candidate_report.items[0].name == "TaskCloseout.v1"
    assert candidate_report.items[0].details["required_fields"] == [
        "schema_version",
        "source_type",
        "status",
    ]

    assert compare_report.status == "warning"
    assert compare_report.summary["item_count"] == 2
    assert compare_report.summary["shared_required_fields"] == 2
    assert compare_report.summary["left_only_required_fields"] == 1
    assert compare_report.summary["right_only_required_fields"] == 1
    assert compare_report.summary["same_schema_version"] is False


def test_contract_preflight_blocks_unknown_candidate(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    preflight = RepositoryContractPreflight(repo)

    report = preflight.build_candidate_report("UnknownContract.v1")

    assert report.status == "blocked"
    assert any(d.code == "core.contract_preflight.contract_unknown" for d in report.diagnostics.diagnostics)
