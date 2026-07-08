"""Tests for read-only structural validation commands."""

from __future__ import annotations

import json
from pathlib import Path

from core_runtime.cli.main import build_parser
from core_runtime.tooling.validation import RepositoryValidation


def _make_repo(tmp_path: Path) -> Path:
    core_runtime = tmp_path / "core_runtime"
    core_runtime.mkdir()
    domains = core_runtime / "domains"
    domains.mkdir()
    circuits = domains / "circuits"
    circuits.mkdir()
    (circuits / "__init__.py").write_text("from . import adapters\n", encoding="utf-8")
    (circuits / "adapters.py").write_text("ADAPTER = True\n", encoding="utf-8")
    (circuits / "manifest.json").write_text(
        json.dumps({"schema_version": "core.domain_manifest.v1", "source_documents": ["docs/a.md"]}, indent=2),
        encoding="utf-8",
    )

    schemas = tmp_path / "schemas" / "core"
    schemas.mkdir(parents=True)
    (schemas / "task_closeout.v1.json").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "title": "TaskCloseout.v1",
                "type": "object",
                "additionalProperties": False,
                "properties": {"schema_version": {"const": "core.task_closeout.v1"}},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    examples = tmp_path / "examples" / "accepted" / "sample"
    examples.mkdir(parents=True)
    (examples / "manifest.json").write_text(
        json.dumps(
            {
                "schema": "core.example_manifest.v1",
                "source_documents": ["docs/reference.md"],
                "notes": ["offline-only"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    rejected = tmp_path / "examples" / "rejected_case" / "invalid_sample"
    rejected.mkdir(parents=True)
    (rejected / "manifest.json").write_text("{}", encoding="utf-8")

    contracts = tmp_path / "contracts"
    contracts.mkdir()
    (contracts / "CoreAnchor.sol").write_text("pragma solidity ^0.8.0;\ncontract CoreAnchor {}\n", encoding="utf-8")
    docs_contracts = tmp_path / "docs" / "contracts"
    docs_contracts.mkdir(parents=True)
    (docs_contracts / "gaia_pipeline_manifest_schema.json").write_text(
        json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "title": "Pipeline", "type": "object"}, indent=2),
        encoding="utf-8",
    )

    (tmp_path / "README.md").write_text("CORE v10.5.0\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('version = "10.5.0"\n', encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("## v10.5.0\n", encoding="utf-8")
    docs = tmp_path / "docs"
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
    (tmp_path / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_build_parser_includes_validate_command() -> None:
    parser = build_parser()

    args = parser.parse_args(["validate", "domain", "circuits"])
    assert args.command == "validate"
    assert args.kind == "domain"
    assert args.name == "circuits"


def test_validate_reports_pass_for_clean_repo(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    validator = RepositoryValidation(repo)

    schema_report = validator.build_report("schemas")
    example_report = validator.build_report("examples")
    manifest_report = validator.build_report("manifests")
    contract_report = validator.build_report("contracts")
    domain_report = validator.build_report("domain", "circuits")

    assert schema_report.status == "pass"
    assert example_report.status == "pass"
    assert manifest_report.status == "pass"
    assert contract_report.status == "pass"
    assert domain_report.status == "pass"


def test_validate_rejects_absolute_manifest_paths(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    manifest_path = repo / "examples" / "accepted" / "sample" / "manifest.json"
    manifest_path.write_text(
        json.dumps({"schema": "core.example_manifest.v1", "source_documents": ["/tmp/bad.md"]}, indent=2),
        encoding="utf-8",
    )

    validator = RepositoryValidation(repo)
    report = validator.build_report("manifests")

    assert report.status == "error"
    assert any(d.code == "core.validate.manifest_path_invalid" for d in report.diagnostics.diagnostics)

