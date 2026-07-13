#!/usr/bin/env python3
"""Validate a frozen release-surface manifest against exact repository bytes."""

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


SCHEMA_VERSION = "core.frozen_release_manifest.v1"
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "core" / "frozen_release_manifest.v1.json"
RELEASE_VERSION = "v11.1.0"
INVENTORY_PROFILE = "core.blockchain_release.v11_1"
CRITICAL_SUBSYSTEMS = (
    "anchoring",
    "contract_deployment",
    "executable_contracts",
    "physical_safety",
)
SELF_REFERENCE_POLICY = "manifest_file_excluded_fingerprint_covers_inventory"

# This is the frozen v11.1 profile, not a live glob. Future repository files must
# not silently change the historical inventory. The manifest file itself is the
# sole intentional exclusion because no finite file can contain its own raw-byte
# hash. Its canonical fingerprint binds this complete, exact inventory instead.
V11_1_REQUIRED_ARTIFACTS_BY_ROLE: dict[str, tuple[str, ...]] = {
    "ci": (
        ".github/workflows/replay-certification.yml",
    ),
    "contract": (
        "contracts/CoreRuleAnchor.abi.json",
        "contracts/CoreRuleAnchor.bin",
        "contracts/CoreRuleAnchor.build.json",
        "contracts/CoreRuleAnchor.runtime.bin",
        "contracts/CoreRuleAnchor.sol",
    ),
    "documentation": (
        "CHANGELOG.md",
        "README.md",
        "docs/CORE_RELEASE_README.md",
        "docs/EXECUTABLE_CONTRACTS_AND_PHYSICAL_SAFETY.md",
        "docs/FROZEN_RULE_ANCHORING.md",
        "docs/PROJECTION_AND_RESPONSIBLE_AGENCY.md",
        "docs/REPRODUCIBILITY.md",
        "docs/VERSIONING_POLICY.md",
        "docs/releases/README.md",
        "docs/releases/v11.1.0.md",
        "examples/anchoring_event/README.md",
    ),
    "example": (
        "examples/anchoring/accepted_freeze_artifact.json",
        "examples/anchoring/accepted_release_manifest.json",
        "examples/anchoring/chain_adapters/arbitrum_one_valid.json",
        "examples/anchoring/chain_adapters/ethereum_sepolia_valid.json",
        "examples/anchoring/chain_adapters/local_devnet_valid.json",
        "examples/anchoring/chain_adapters/polygon_mainnet_valid.json",
        "examples/anchoring/chain_adapters/rejected_fingerprint_mismatch.json",
        "examples/anchoring/chain_adapters/rejected_local_rpc_mainnet.json",
        "examples/anchoring/chain_adapters/rejected_mainnet_low_confirmations.json",
        "examples/anchoring/chain_adapters/rejected_unsupported_family.json",
        "examples/anchoring/rejected_hash_mismatch.json",
        "examples/anchoring/rejected_not_frozen.json",
        "examples/anchoring/rejected_private_data.json",
        "examples/anchoring_event/accepted_freeze_anchor.json",
        "examples/anchoring_event/accepted_profile_anchor.json",
        "examples/anchoring_event/rejected_fingerprint_mismatch.json",
        "examples/anchoring_event/rejected_hash_fp_mismatch.json",
        "examples/anchoring_event/rejected_unknown_chain.json",
        "examples/core_contracts/causal_trace.v1.json",
        "examples/core_contracts/control_decision.v1.json",
        "examples/core_contracts/execution_receipt.v1.json",
        "examples/core_contracts/memory_artifact.v1.json",
        "examples/frozen_rules/general_cooperative_supply.json",
        "examples/frozen_rules/personal_commitment.json",
        "examples/merkle_batch/accepted_batch_manifest.json",
        "examples/merkle_batch/accepted_batch_request.json",
        "examples/merkle_batch/rejected_duplicate_fingerprints.json",
        "examples/merkle_batch/rejected_empty_items.json",
        "examples/merkle_batch/rejected_tampered_path.json",
        "examples/merkle_batch/rejected_tampered_root.json",
        "examples/rule_approvals/general_cooperative_supply.json",
        "examples/rule_approvals/personal_commitment.json",
    ),
    "release_metadata": (
        "core_runtime/__version__.py",
        "core_runtime/cli/__init__.py",
        "pyproject.toml",
        "requirements-dev.txt",
        "requirements.lock",
    ),
    "runtime": (
        "core_runtime/core/__init__.py",
        "core_runtime/core/canonicalization.py",
        "core_runtime/core/contract_evaluator.py",
        "core_runtime/core/contract_executability.py",
        "core_runtime/core/contract_loader.py",
        "core_runtime/core/contract_probes.py",
        "core_runtime/core/rule_anchor.py",
        "core_runtime/tooling/file_inventory.py",
    ),
    "schema": (
        "schemas/anchoring_event.schema.json",
        "schemas/anchoring_submission.schema.json",
        "schemas/chain_adapter.schema.json",
        "schemas/core/causal_trace.v1.json",
        "schemas/core/context_gate.v1.json",
        "schemas/core/context_threshold.v1.json",
        "schemas/core/control_decision.v1.json",
        "schemas/core/effect_result.v1.json",
        "schemas/core/entropy_signal.v1.json",
        "schemas/core/execution_receipt.v1.json",
        "schemas/core/frozen_release_manifest.v1.json",
        "schemas/core/frozen_rule_set.v1.json",
        "schemas/core/memory_artifact.v1.json",
        "schemas/core/memory_generation_result.v1.json",
        "schemas/core/operational_learning_event.v1.json",
        "schemas/core/pattern_candidate.v1.json",
        "schemas/core/physical_safety_assurance_case.v1.json",
        "schemas/core/policy_lifecycle.v1.json",
        "schemas/core/retention_manifest.v1.json",
        "schemas/core/reversibility_policy.v1.json",
        "schemas/core/rule_anchor_batch.v1.json",
        "schemas/core/rule_anchor_chain_evidence.v1.json",
        "schemas/core/rule_approval.v1.json",
        "schemas/core/rule_approval_request.v1.json",
        "schemas/core/state_transition.v1.json",
        "schemas/core/task_closeout.v1.json",
        "schemas/core/template_promotion_candidate.v1.json",
        "schemas/core/unsigned_rule_anchor_deployment.v1.json",
        "schemas/core/unsigned_rule_anchor_transaction.v1.json",
    ),
    "script": (
        "scripts/audit_contract_executability.py",
        "scripts/build_frozen_release_manifest.py",
        "scripts/build_merkle_batch.py",
        "scripts/build_rule_anchor_batch.py",
        "scripts/compile_core_rule_anchor.py",
        "scripts/core_anchor.py",
        "scripts/create_private_rule_commitment.py",
        "scripts/create_rule_approval_request.py",
        "scripts/evaluate_core_contract.py",
        "scripts/finalize_rule_approval.py",
        "scripts/prepare_core_rule_anchor_deployment.py",
        "scripts/prepare_rule_anchor_transaction.py",
        "scripts/submit_anchoring.py",
        "scripts/validate_anchoring_event.py",
        "scripts/validate_anchoring_submission.py",
        "scripts/validate_chain_adapter.py",
        "scripts/validate_frozen_release_manifest.py",
        "scripts/validate_frozen_rule_set.py",
        "scripts/validate_rule_anchor_batch.py",
        "scripts/validate_rule_approval.py",
        "scripts/validate_unsigned_rule_anchor_deployment.py",
        "scripts/validate_unsigned_rule_anchor_transaction.py",
        "scripts/verify_merkle_proof.py",
        "scripts/verify_release.py",
        "scripts/verify_rule_anchor_onchain.py",
    ),
    "test": (
        "tests/test_anchoring_event_validator.py",
        "tests/test_anchoring_submission_validator.py",
        "tests/test_causal_entropy_contracts.py",
        "tests/test_chain_adapter_validator.py",
        "tests/test_control_plane_contracts.py",
        "tests/test_core_contract_examples.py",
        "tests/test_core_generic_contracts.py",
        "tests/test_core_memory_artifact_contract.py",
        "tests/test_core_rule_anchor_contract.py",
        "tests/test_executable_contracts.py",
        "tests/test_frozen_release_manifest.py",
        "tests/test_frozen_rule_set_validator.py",
        "tests/test_operational_learning_contracts.py",
        "tests/test_physical_safety_assurance.py",
        "tests/test_rule_anchor_batch.py",
        "tests/test_rule_anchor_deployment.py",
        "tests/test_rule_anchor_transaction.py",
        "tests/test_rule_approval_validator.py",
        "tests/test_tooling_ci_contract.py",
        "tests/test_tooling_contract_preflight.py",
        "tests/test_tooling_repository_inventory.py",
        "tests/test_verify_release_script.py",
    ),
}


def required_v11_1_artifacts() -> dict[str, str]:
    """Return the exact path-to-role inventory frozen for v11.1."""

    return {
        path: role
        for role, paths in V11_1_REQUIRED_ARTIFACTS_BY_ROLE.items()
        for path in paths
    }


def _timezone_timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def build_v11_1_manifest(frozen_at: str) -> dict[str, Any]:
    """Build the canonical v11.1 manifest from exact repository bytes."""

    if not _timezone_timestamp(frozen_at):
        raise ValueError("frozen_at must include an explicit timezone")
    expected = required_v11_1_artifacts()
    expected_total = sum(len(paths) for paths in V11_1_REQUIRED_ARTIFACTS_BY_ROLE.values())
    if len(expected) != expected_total:
        raise ValueError("v11.1 artifact inventory contains duplicate paths")

    artifacts: list[dict[str, str]] = []
    for relative_path, role in sorted(expected.items()):
        path = PROJECT_ROOT / relative_path
        if not path.is_file():
            raise FileNotFoundError(relative_path)
        artifacts.append(
            {
                "path": relative_path,
                "role": role,
                "file_sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "type": "frozen_release_manifest",
        "release_version": RELEASE_VERSION,
        "status": "frozen",
        "scope": "blockchain_release_critical_surface",
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


def validate_frozen_release_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors = [error("file_not_found", "Frozen release manifest does not exist.", "path")]
        payload = {}
    except json.JSONDecodeError:
        errors = [error("invalid_json", "Frozen release manifest is not valid JSON.", "path")]
        payload = {}
    except OSError as exc:
        errors = [error("file_read_error", exc.__class__.__name__, "path")]
        payload = {}
    else:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        errors = []
        for item in sorted(
            Draft7Validator(schema).iter_errors(payload),
            key=lambda entry: list(entry.absolute_path),
        ):
            field = ".".join(str(part) for part in item.absolute_path) or "$"
            errors.append(error("schema_validation_error", item.message, field))

        if isinstance(payload, dict):
            artifacts = payload.get("artifacts")
            if isinstance(artifacts, list):
                paths = [
                    item.get("path") for item in artifacts if isinstance(item, dict)
                ]
                if paths != sorted(paths):
                    errors.append(
                        error(
                            "noncanonical_artifact_order",
                            "Manifest artifacts must be sorted by path.",
                            "artifacts",
                        )
                    )
                if len(paths) != len(set(paths)):
                    errors.append(
                        error(
                            "duplicate_artifact_path",
                            "Manifest artifact paths must be unique.",
                            "artifacts",
                        )
                    )
                if payload.get("artifact_count") != len(artifacts):
                    errors.append(
                        error(
                            "artifact_count_mismatch",
                            "artifact_count must equal the artifacts length.",
                            "artifact_count",
                        )
                    )

                for index, item in enumerate(artifacts):
                    if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                        continue
                    relative = Path(item["path"])
                    if relative.is_absolute() or ".." in relative.parts:
                        errors.append(
                            error(
                                "unsafe_artifact_path",
                                "Artifact path must remain repository-relative.",
                                f"artifacts.{index}.path",
                            )
                        )
                        continue
                    resolved = (PROJECT_ROOT / relative).resolve()
                    try:
                        resolved.relative_to(PROJECT_ROOT.resolve())
                    except ValueError:
                        errors.append(
                            error(
                                "unsafe_artifact_path",
                                "Artifact path escapes the repository.",
                                f"artifacts.{index}.path",
                            )
                        )
                        continue
                    if not resolved.is_file():
                        errors.append(
                            error(
                                "artifact_missing",
                                "Frozen artifact file is missing.",
                                f"artifacts.{index}.path",
                            )
                        )
                        continue
                    computed = "sha256:" + hashlib.sha256(resolved.read_bytes()).hexdigest()
                    if item.get("file_sha256") != computed:
                        errors.append(
                            error(
                                "artifact_hash_mismatch",
                                "Frozen artifact bytes do not match file_sha256.",
                                f"artifacts.{index}.file_sha256",
                                computed=computed,
                            )
                        )

                expected = required_v11_1_artifacts()
                actual = {
                    item["path"]: item.get("role")
                    for item in artifacts
                    if isinstance(item, dict) and isinstance(item.get("path"), str)
                }
                missing = sorted(set(expected) - set(actual))
                unexpected = sorted(set(actual) - set(expected))
                if missing or unexpected:
                    errors.append(
                        error(
                            "artifact_inventory_mismatch",
                            "Manifest paths must equal the frozen v11.1 inventory.",
                            "artifacts",
                            missing=missing,
                            unexpected=unexpected,
                        )
                    )
                for relative_path in sorted(set(expected) & set(actual)):
                    if actual[relative_path] != expected[relative_path]:
                        errors.append(
                            error(
                                "artifact_role_mismatch",
                                "Artifact role differs from the frozen v11.1 inventory.",
                                relative_path,
                                expected=expected[relative_path],
                                actual=actual[relative_path],
                            )
                        )

            if payload.get("release_version") != RELEASE_VERSION:
                errors.append(
                    error(
                        "release_profile_mismatch",
                        "This inventory profile is frozen for release v11.1.0.",
                        "release_version",
                        expected=RELEASE_VERSION,
                    )
                )
            if payload.get("inventory_profile") != INVENTORY_PROFILE:
                errors.append(
                    error(
                        "release_profile_mismatch",
                        "Unknown or incompatible frozen inventory profile.",
                        "inventory_profile",
                        expected=INVENTORY_PROFILE,
                    )
                )

            if not _timezone_timestamp(payload.get("frozen_at")):
                errors.append(
                    error(
                        "invalid_frozen_at",
                        "frozen_at must include an explicit timezone.",
                        "frozen_at",
                    )
                )
            declared = payload.get("fingerprint")
            if isinstance(declared, str):
                computed = artifact_fingerprint(payload)
                if declared != computed:
                    errors.append(
                        error(
                            "fingerprint_mismatch",
                            "Manifest fingerprint does not match canonical content.",
                            "fingerprint",
                            computed=computed,
                        )
                    )

    return {
        "schema": SCHEMA_VERSION,
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "release_version": payload.get("release_version") if isinstance(payload, dict) else None,
        "artifact_count": payload.get("artifact_count") if isinstance(payload, dict) else None,
        "manifest_valid": not errors,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: validate_frozen_release_manifest.py <path>", file=sys.stderr)
        return 2
    result = validate_frozen_release_manifest(Path(sys.argv[1]))
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
