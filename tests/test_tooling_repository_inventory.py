"""Tests for read-only repository inventory navigation."""

from __future__ import annotations

import json
from pathlib import Path

from core_runtime.cli.main import build_parser
from core_runtime.tooling.repository_inventory import RepositoryInventory


def _make_repo(tmp_path: Path) -> Path:
    core_runtime = tmp_path / "core_runtime"
    core_runtime.mkdir()
    domains = core_runtime / "domains"
    domains.mkdir()
    circuits = domains / "circuits"
    circuits.mkdir()
    (circuits / "__init__.py").write_text("from . import adapters\n", encoding="utf-8")
    (circuits / "adapters.py").write_text("ADAPTER = True\n", encoding="utf-8")

    schemas = tmp_path / "schemas" / "core"
    schemas.mkdir(parents=True)
    (schemas / "task_closeout.v1.json").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "https://core-runtime-engine.local/schemas/core/task_closeout.v1.json",
                "title": "TaskCloseout.v1",
                "type": "object",
                "properties": {"schema_version": {"const": "core.task_closeout.v1"}},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    contracts = tmp_path / "contracts"
    contracts.mkdir()
    (contracts / "CoreAnchor.sol").write_text("contract CoreAnchor {}\n", encoding="utf-8")

    adapters = tmp_path / "examples" / "adapters" / "minimal_sensor_adapter"
    adapters.mkdir(parents=True)
    (adapters / "README.md").write_text("# Minimal Adapter\n", encoding="utf-8")
    (adapters / "generate_fixture.py").write_text("print('ok')\n", encoding="utf-8")
    (adapters / "fixtures").mkdir()
    (adapters / "fixtures" / "manifest.json").write_text("{}", encoding="utf-8")

    (tmp_path / "README.md").write_text("CORE v10.5.0\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('version = "10.5.0"\n', encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("## v10.5.0\n", encoding="utf-8")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "VERSIONING_POLICY.md").write_text("Current: v10.5.0\n", encoding="utf-8")
    (docs / "CORE_RELEASE_README.md").write_text("CORE: v10.5.0\n", encoding="utf-8")
    (docs / "REPRODUCIBILITY.md").write_text("# Reproducibility\n", encoding="utf-8")
    (docs / "QUALITY_GATE.md").write_text("# Quality Gate\n", encoding="utf-8")
    (docs / "releases").mkdir()
    (docs / "releases" / "README.md").write_text("# Releases\n", encoding="utf-8")

    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for script in ["verify_release.py", "check_version_consistency.py", "bump_version.py", "generate_requirements_lock.py"]:
        (scripts / script).write_text("#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")

    (tmp_path / "requirements.lock").write_text("pytest\n", encoding="utf-8")
    (tmp_path / "requirements-dev.txt").write_text("pytest\n", encoding="utf-8")
    (tmp_path / "schemas").mkdir(exist_ok=True)
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_build_parser_includes_list_and_info_commands() -> None:
    parser = build_parser()

    list_args = parser.parse_args(["list", "schemas"])
    assert list_args.command == "list"
    assert list_args.kind == "schemas"

    info_alias_args = parser.parse_args(["info", "schema", "TaskCloseout.v1"])
    assert info_alias_args.command == "info"
    assert info_alias_args.kind == "schema"
    assert info_alias_args.name == "TaskCloseout.v1"

    info_args = parser.parse_args(["info", "schemas", "TaskCloseout.v1"])
    assert info_args.command == "info"
    assert info_args.kind == "schemas"
    assert info_args.name == "TaskCloseout.v1"


def test_repository_inventory_lists_and_infos_items(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    inventory = RepositoryInventory(repo)

    schemas = inventory.list_items("schemas")
    contracts = inventory.list_items("contracts")
    domains = inventory.list_items("domains")
    adapters = inventory.list_items("adapters")

    assert any(item.name == "TaskCloseout.v1" for item in schemas)
    assert any(item.path.endswith("CoreAnchor.sol") for item in contracts)
    assert any(item.name == "circuits" for item in domains)
    assert any(item.name == "minimal_sensor_adapter" for item in adapters)

    schema_info = inventory.build_info_report(kind="schemas", name="TaskCloseout.v1")
    assert schema_info.status == "pass"
    assert schema_info.items[0].title == "TaskCloseout.v1"

    domain_info = inventory.build_info_report(kind="domains", name="circuits")
    assert domain_info.status == "pass"
    assert domain_info.items[0].name == "circuits"


def test_inventory_reports_block_on_unknown_kind(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    inventory = RepositoryInventory(repo)

    report = inventory.build_list_report("unknown-kind")
    assert report.status == "blocked"
    assert any(d.code == "core.inventory.kind_unknown" for d in report.diagnostics.diagnostics)


def test_inventory_report_dicts_are_stable(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    inventory = RepositoryInventory(repo)

    list_report = inventory.build_list_report("schemas")
    assert list_report.to_dict()["tool"] == "core-runtime list"
    assert list_report.to_dict()["summary"]["item_count"] == 1

    info_report = inventory.build_info_report(kind="schemas", name="TaskCloseout.v1")
    payload = info_report.to_dict()
    assert payload["tool"] == "core-runtime info"
    assert payload["selection"]["kind"] == "schemas"
    assert payload["items"][0]["title"] == "TaskCloseout.v1"


def test_general_info_is_summary_only(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    inventory = RepositoryInventory(repo)

    report = inventory.build_info_report()
    payload = report.to_dict()
    assert payload["summary"]["item_count"] == 0
    assert payload["items"] == []
    assert payload["summary"]["schema_count"] == 1
