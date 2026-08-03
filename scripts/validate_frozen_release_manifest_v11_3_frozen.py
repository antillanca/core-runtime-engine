#!/usr/bin/env python3
"""Validate the frozen CORE v11.3.0 ContractProgram release surface."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core_runtime.core.rule_anchor import artifact_fingerprint, error  # noqa: E402
from scripts.validate_frozen_release_manifest_v11_3 import (  # noqa: E402
    _timezone_timestamp,
    required_v11_3_candidate_artifacts,
)

SCHEMA_VERSION = "core.frozen_release_manifest.v5"
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "core" / "frozen_release_manifest.v5.json"
RELEASE_VERSION = "v11.3.0"
INVENTORY_PROFILE = "core.contract_program_release.v11_3"
CRITICAL_SUBSYSTEMS = ("contract_program", "executable_contracts", "release_integrity")
SELF_REFERENCE_POLICY = "manifest_file_excluded_fingerprint_covers_inventory"


def required_v11_3_frozen_artifacts() -> dict[str, str]:
    expected = required_v11_3_candidate_artifacts()
    expected.update(
        {
            "examples/frozen_release_manifest/accepted_v11_3_0_candidate.json": "example",
            "schemas/core/frozen_release_manifest.v5.json": "schema",
            "scripts/build_frozen_release_manifest_v11_3_frozen.py": "script",
            "scripts/validate_frozen_release_manifest_v11_3_frozen.py": "script",
            "docs/releases/v11.3.0.md": "documentation",
            "tests/test_frozen_release_manifest_v11_3_frozen.py": "test",
        }
    )
    return expected


def build_v11_3_frozen_manifest(frozen_at: str) -> dict[str, Any]:
    if not _timezone_timestamp(frozen_at):
        raise ValueError("frozen_at must include an explicit timezone")
    expected = required_v11_3_frozen_artifacts()
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
        "status": "frozen",
        "scope": "deterministic_contract_program_surface",
        "inventory_profile": INVENTORY_PROFILE,
        "critical_subsystems": list(CRITICAL_SUBSYSTEMS),
        "self_reference_policy": SELF_REFERENCE_POLICY,
        "canonicalization": "core.canonical_json.v1",
        "hash_algorithm": "sha256",
        "frozen_at": frozen_at,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }
    payload["fingerprint"] = artifact_fingerprint(payload)
    return payload


def validate_v11_3_frozen_release_manifest(path: Path, *, verify_live_artifacts: bool = False) -> dict[str, Any]:
    """Validate historical evidence, optionally against the live worktree."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors = [error("file_not_found", "Frozen v11.3 release manifest does not exist.", "path")]
        payload = {}
    except json.JSONDecodeError:
        errors = [error("invalid_json", "Frozen v11.3 release manifest is not valid JSON.", "path")]
        payload = {}
    except OSError as exc:
        errors = [error("file_read_error", exc.__class__.__name__, "path")]
        payload = {}
    else:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        errors = [
            error("schema_validation_error", item.message, ".".join(map(str, item.absolute_path)) or "$")
            for item in sorted(Draft7Validator(schema).iter_errors(payload), key=lambda entry: list(entry.absolute_path))
        ]
        if isinstance(payload, dict):
            artifacts = payload.get("artifacts")
            if isinstance(artifacts, list):
                paths = [item.get("path") for item in artifacts if isinstance(item, dict)]
                if paths != sorted(paths):
                    errors.append(error("noncanonical_artifact_order", "Artifacts must be sorted by path.", "artifacts"))
                if len(paths) != len(set(paths)):
                    errors.append(error("duplicate_artifact_path", "Artifact paths must be unique.", "artifacts"))
                if payload.get("artifact_count") != len(artifacts):
                    errors.append(error("artifact_count_mismatch", "artifact_count must equal artifacts length.", "artifact_count"))
                expected = required_v11_3_frozen_artifacts()
                actual = {item["path"]: item.get("role") for item in artifacts if isinstance(item, dict) and isinstance(item.get("path"), str)}
                missing = sorted(set(expected) - set(actual))
                unexpected = sorted(set(actual) - set(expected))
                if missing or unexpected:
                    errors.append(error("artifact_inventory_mismatch", "Paths must equal the frozen v11.3 inventory.", "artifacts", missing=missing, unexpected=unexpected))
                for relative_path in sorted(set(expected) & set(actual)):
                    if actual[relative_path] != expected[relative_path]:
                        errors.append(error("artifact_role_mismatch", "Artifact role differs from frozen inventory.", relative_path, expected=expected[relative_path], actual=actual[relative_path]))
                for index, item in enumerate(artifacts):
                    if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                        continue
                    relative = Path(item["path"])
                    resolved = (PROJECT_ROOT / relative).resolve()
                    try:
                        resolved.relative_to(PROJECT_ROOT.resolve())
                    except ValueError:
                        errors.append(error("unsafe_artifact_path", "Artifact path escapes the repository.", f"artifacts.{index}.path"))
                        continue
                    if not resolved.is_file():
                        errors.append(error("artifact_missing", "Frozen artifact file is missing.", f"artifacts.{index}.path"))
                        continue
                    if verify_live_artifacts:
                        computed = "sha256:" + hashlib.sha256(resolved.read_bytes()).hexdigest()
                        if item.get("file_sha256") != computed:
                            errors.append(error("artifact_hash_mismatch", "Frozen artifact bytes do not match file_sha256.", f"artifacts.{index}.file_sha256", computed=computed))
            if not _timezone_timestamp(payload.get("frozen_at")):
                errors.append(error("invalid_frozen_at", "frozen_at must include an explicit timezone.", "frozen_at"))
            declared = payload.get("fingerprint")
            if isinstance(declared, str) and declared != artifact_fingerprint(payload):
                errors.append(error("fingerprint_mismatch", "Frozen fingerprint does not match canonical content.", "fingerprint", computed=artifact_fingerprint(payload)))

    return {"schema": "core.frozen_release_manifest_validation.v3", "status": "passed" if not errors else "failed", "errors": errors, "release_version": payload.get("release_version") if isinstance(payload, dict) else None, "inventory_profile": payload.get("inventory_profile") if isinstance(payload, dict) else None, "artifact_count": payload.get("artifact_count") if isinstance(payload, dict) else None, "live_artifacts_verified": verify_live_artifacts, "manifest_valid": not errors}


def main() -> int:
    if len(sys.argv) not in {2, 3} or (len(sys.argv) == 3 and sys.argv[2] != "--verify-live-artifacts"):
        print("Usage: validate_frozen_release_manifest_v11_3_frozen.py <path> [--verify-live-artifacts]", file=sys.stderr)
        return 2
    result = validate_v11_3_frozen_release_manifest(Path(sys.argv[1]), verify_live_artifacts=len(sys.argv) == 3)
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
