#!/usr/bin/env python3
"""Validate the exact public CORE v11.6.0 stabilization manifest."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core_runtime.core.rule_anchor import artifact_fingerprint, error  # noqa: E402
from scripts.validate_frozen_release_manifest_v11_5_1 import required_v11_5_1_candidate_artifacts  # noqa: E402

SCHEMA_VERSION = "core.frozen_release_manifest.v9"
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "core" / "frozen_release_manifest.v9.json"
RELEASE_VERSION = "v11.6.0"
INVENTORY_PROFILE = "core.stabilization_release.v11_6_0_candidate"
CRITICAL_SUBSYSTEMS = ("dsk_v3", "contract_program_v2", "executable_contracts", "release_integrity")
SELF_REFERENCE_POLICY = "manifest_file_excluded_fingerprint_covers_inventory"


def required_v11_6_candidate_artifacts() -> dict[str, str]:
    # A stabilization release inherits the complete public inventory of the
    # previous candidate line.  This keeps historical v11.5.1 artifacts
    # addressable while adding the v11.6 release and hardening surfaces.
    expected = required_v11_5_1_candidate_artifacts()
    expected.update({
        "CHANGELOG.md": "release_metadata",
        "LICENSE": "release_metadata",
        "pyproject.toml": "release_metadata",
        "core_runtime/__version__.py": "release_metadata",
        "core_runtime/core/__init__.py": "runtime",
        "core_runtime/core/contract_executability.py": "runtime",
        "core_runtime/core/dsk_v3.py": "runtime",
        "schemas/core/dsk.v3.json": "schema",
        "schemas/core/frozen_release_manifest.v9.json": "schema",
        "scripts/validate_dsk_v3.py": "script",
        "scripts/build_frozen_release_manifest_v11_6.py": "script",
        "scripts/validate_frozen_release_manifest_v11_6.py": "script",
        "docs/releases/v11.6.0.md": "documentation",
        "tests/test_dsk_v3.py": "test",
        "tests/test_frozen_release_manifest_v11_6.py": "test",
        "core_runtime/cli/main.py": "runtime",
        "core_runtime/core/audit_event.py": "runtime",
        "core_runtime/tooling/bump_version.py": "runtime",
        "scripts/validate_classification_candidate.py": "script",
        "scripts/validate_private_domain_candidate.py": "script",
        "scripts/pypi_preflight.py": "script",
        "scripts/replay_certification.py": "script",
        "scripts/expert_router_common.py": "script",
        "scripts/validate_expert_router.py": "script",
        "scripts/evaluate_expert_router.py": "script",
        "scripts/report_expert_router.py": "script",
        "scripts/certify_router_replay.py": "script",
        ".github/workflows/publish-v11-6.yml": "ci",
        "tests/test_audit_event_schema.py": "test",
        "tests/test_classification_candidate_validator.py": "test",
        "tests/test_private_domain_integration.py": "test",
        "tests/test_tooling_bump_version.py": "test",
        "tests/test_pypi_preflight.py": "test",
        "tests/test_replay_certification.py": "test",
        "tests/test_expert_router_scripts.py": "test",
        "tests/test_executable_contracts.py": "test",
        "tests/test_causal_entropy_contracts.py": "test",
        "tests/test_core_generic_contracts.py": "test",
        "examples/dsk_v3/accepted_basic.json": "example",
        "examples/dsk_v3/rejected_schema_unknown_field.json": "example",
        "examples/dsk_v3/rejected_insufficient_data.json": "example",
        "examples/dsk_v3/rejected_blocked_threshold.json": "example",
        "examples/dsk_v3/rejected_authority_amplification.json": "example",
        "examples/dsk_v3/rejected_scale_violation.json": "example",
        "examples/expert_router/routing_fixtures/minimal_routing.json": "example",
    })
    return expected


def _timezone_timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def build_v11_6_candidate_manifest(created_at: str) -> dict[str, Any]:
    if not _timezone_timestamp(created_at):
        raise ValueError("created_at must include an explicit timezone")
    expected = required_v11_6_candidate_artifacts()
    artifacts = []
    for relative_path, role in sorted(expected.items()):
        path = PROJECT_ROOT / relative_path
        if not path.is_file():
            raise FileNotFoundError(relative_path)
        artifacts.append({"path": relative_path, "role": role, "file_sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()})
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "type": "frozen_release_manifest",
        "release_version": RELEASE_VERSION,
        "status": "candidate",
        "scope": "deterministic_scale_kernel_v3",
        "inventory_profile": INVENTORY_PROFILE,
        "critical_subsystems": list(CRITICAL_SUBSYSTEMS),
        "self_reference_policy": SELF_REFERENCE_POLICY,
        "canonicalization": "core.canonical_json.v1",
        "hash_algorithm": "sha256",
        "created_at": created_at,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }
    payload["fingerprint"] = artifact_fingerprint(payload)
    return payload


def validate_v11_6_release_manifest(path: Path, *, verify_live_artifacts: bool = False) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        payload = {}
        errors = [error("file_not_found", "Release candidate manifest does not exist.", "path")]
    except (json.JSONDecodeError, OSError) as exc:
        payload = {}
        errors = [error("invalid_manifest", exc.__class__.__name__, "path")]
    else:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        errors = [error("schema_validation_error", item.message, ".".join(map(str, item.absolute_path)) or "$") for item in sorted(Draft7Validator(schema).iter_errors(payload), key=lambda item: list(item.absolute_path))]
        artifacts = payload.get("artifacts") if isinstance(payload, dict) else None
        expected = required_v11_6_candidate_artifacts()
        if isinstance(artifacts, list):
            paths = [item.get("path") for item in artifacts if isinstance(item, dict)]
            actual = {item["path"]: item.get("role") for item in artifacts if isinstance(item, dict) and isinstance(item.get("path"), str)}
            if paths != sorted(paths):
                errors.append(error("noncanonical_artifact_order", "Artifacts must be sorted by path.", "artifacts"))
            if len(paths) != len(set(paths)):
                errors.append(error("duplicate_artifact_path", "Artifact paths must be unique.", "artifacts"))
            if payload.get("artifact_count") != len(artifacts):
                errors.append(error("artifact_count_mismatch", "artifact_count must equal artifacts length.", "artifact_count"))
            missing = sorted(set(expected) - set(actual))
            unexpected = sorted(set(actual) - set(expected))
            if missing or unexpected:
                errors.append(error("artifact_inventory_mismatch", "Paths must equal the v11.6 stabilization inventory.", "artifacts", missing=missing, unexpected=unexpected))
            for relative_path, role in expected.items():
                if relative_path in actual and actual[relative_path] != role:
                    errors.append(error("artifact_role_mismatch", "Artifact role differs from candidate inventory.", relative_path))
            for item in artifacts:
                if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                    continue
                resolved = (PROJECT_ROOT / item["path"]).resolve()
                try:
                    resolved.relative_to(PROJECT_ROOT.resolve())
                except ValueError:
                    errors.append(error("unsafe_artifact_path", "Artifact path escapes the repository.", item["path"]))
                    continue
                if not resolved.is_file():
                    errors.append(error("artifact_missing", "Candidate artifact file is missing.", item["path"]))
                elif verify_live_artifacts:
                    computed = "sha256:" + hashlib.sha256(resolved.read_bytes()).hexdigest()
                    if item.get("file_sha256") != computed:
                        errors.append(error("artifact_hash_mismatch", "Candidate artifact bytes do not match file_sha256.", item["path"], computed=computed))
        if not _timezone_timestamp(payload.get("created_at")):
            errors.append(error("invalid_created_at", "created_at must include an explicit timezone.", "created_at"))
        if payload.get("fingerprint") != artifact_fingerprint(payload):
            errors.append(error("fingerprint_mismatch", "Candidate fingerprint does not match canonical content.", "fingerprint"))
    return {"schema": "core.frozen_release_manifest_validation.v2", "status": "passed" if not errors else "failed", "errors": errors, "release_version": payload.get("release_version"), "inventory_profile": payload.get("inventory_profile"), "artifact_count": payload.get("artifact_count"), "live_artifacts_verified": verify_live_artifacts, "manifest_valid": not errors}


def main() -> int:
    if len(sys.argv) not in {2, 3} or (len(sys.argv) == 3 and sys.argv[2] != "--verify-live-artifacts"):
        print("Usage: validate_frozen_release_manifest_v11_6.py <path> [--verify-live-artifacts]", file=sys.stderr)
        return 2
    result = validate_v11_6_release_manifest(Path(sys.argv[1]), verify_live_artifacts=len(sys.argv) == 3)
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
