"""Repository audit proving that public contracts have executable semantics."""

from __future__ import annotations

import copy
import importlib
import json
from importlib.resources import files
from typing import Any

from core_runtime.core.canonicalization import canonical_json_hash
from core_runtime.core.contract_evaluator import (
    SEMANTIC_RULE_IDS,
    evaluate_contract_payload,
    executable_contract_versions,
    validate_contract_structure,
)
from core_runtime.core.contract_loader import SCHEMA_ROOT, available_contracts, load_contract_schema
from core_runtime.core.contract_probes import executable_contract_probes



STANDALONE_EXECUTABLE_CONTRACTS: dict[str, tuple[str, str]] = {
    "core.frozen_release_manifest.v1": (
        "scripts.validate_frozen_release_manifest",
        "validate_frozen_release_manifest",
    ),
    "core.frozen_release_manifest.v2": (
        "scripts.validate_frozen_release_manifest_v11_2",
        "validate_v11_2_release_manifest",
    ),
    "core.frozen_release_manifest.v3": (
        "scripts.validate_frozen_release_manifest_v11_2_frozen",
        "validate_v11_2_frozen_release_manifest",
    ),
    "core.frozen_release_manifest.v4": (
        "scripts.validate_frozen_release_manifest_v11_3",
        "validate_v11_3_release_manifest",
    ),
    "core.frozen_release_manifest.v5": (
        "scripts.validate_frozen_release_manifest_v11_3_frozen",
        "validate_v11_3_frozen_release_manifest",
    ),
    "core.frozen_release_manifest.v6": (
        "scripts.validate_frozen_release_manifest_v11_4",
        "validate_v11_4_release_manifest",
    ),
    "core.frozen_release_manifest.v7": (
        "scripts.validate_frozen_release_manifest_v11_5",
        "validate_v11_5_release_manifest",
    ),
    "core.frozen_release_manifest.v8": (
        "scripts.validate_frozen_release_manifest_v11_5_1",
        "validate_v11_5_1_release_manifest",
    ),
    "core.frozen_release_manifest.v9": (
        "scripts.validate_frozen_release_manifest_v11_6",
        "validate_v11_6_release_manifest",
    ),
    "core.dsk.v3": (
        "core_runtime.core.dsk_v3",
        "evaluate_dsk_v3",
    ),
    "core.contract_program.v2": (
        "core_runtime.core.contract_program_v2",
        "evaluate_contract_v2",
    ),
    "core.frozen_rule_set.v1": (
        "scripts.validate_frozen_rule_set",
        "validate_frozen_rule_set",
    ),
    "core.rule_anchor_batch.v1": (
        "scripts.validate_rule_anchor_batch",
        "validate_rule_anchor_batch",
    ),
    "core.rule_anchor_chain_evidence.v1": (
        "core_runtime.core.rule_anchor",
        "validate_rule_anchor_chain_evidence_payload",
    ),
    "core.rule_approval.v1": (
        "scripts.validate_rule_approval",
        "validate_rule_approval",
    ),
    "core.rule_approval_request.v1": (
        "core_runtime.core.rule_anchor",
        "validate_approval_request_payload",
    ),
    "core.unsigned_rule_anchor_transaction.v1": (
        "scripts.validate_unsigned_rule_anchor_transaction",
        "validate_unsigned_transaction",
    ),
    "core.unsigned_rule_anchor_deployment.v1": (
        "scripts.validate_unsigned_rule_anchor_deployment",
        "validate_unsigned_deployment",
    ),
}


def _entry(code: str, message: str, field: str = "$", **extra: Any) -> dict[str, Any]:
    item: dict[str, Any] = {"code": code, "message": message, "field": field}
    item.update(extra)
    return item


def _schema_version(schema: dict[str, Any]) -> str | None:
    value = schema.get("properties", {}).get("schema_version", {}).get("const")
    return value if isinstance(value, str) else None


def _open_object_paths(schema: Any, field: str = "$", seen: set[int] | None = None) -> list[str]:
    if seen is None:
        seen = set()
    if not isinstance(schema, dict) or id(schema) in seen:
        return []
    seen.add(id(schema))
    paths: list[str] = []
    if schema.get("type") == "object" and isinstance(schema.get("properties"), dict):
        if schema.get("additionalProperties") is not False:
            paths.append(field)
    for key in ("properties", "definitions", "$defs"):
        children = schema.get(key)
        if isinstance(children, dict):
            for child_name, child in children.items():
                paths.extend(_open_object_paths(child, f"{field}.{key}.{child_name}", seen))
    items = schema.get("items")
    if isinstance(items, dict):
        paths.extend(_open_object_paths(items, f"{field}.items", seen))
    for key in ("oneOf", "anyOf", "allOf"):
        branches = schema.get(key)
        if isinstance(branches, list):
            for index, branch in enumerate(branches):
                paths.extend(_open_object_paths(branch, f"{field}.{key}[{index}]", seen))
    return paths


def _public_schema_inventory() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    generic_versions = set(executable_contract_versions())
    for path in sorted((item for item in SCHEMA_ROOT.iterdir() if item.name.endswith(".json")), key=lambda item: item.name):
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(_entry("schema_unreadable", exc.__class__.__name__, f"core_runtime/data/schemas/core/{path.name}"))
            continue
        version = _schema_version(schema)
        if version in generic_versions:
            mechanism = "generic_semantic_evaluator"
        elif version in STANDALONE_EXECUTABLE_CONTRACTS:
            mechanism = "standalone_semantic_validator"
        else:
            mechanism = "unclassified"
            errors.append(
                _entry(
                    "unclassified_public_contract",
                    "Every public schema requires an executable semantic mechanism.",
                    f"core_runtime/data/schemas/core/{path.name}",
                    schema_version=version,
                )
            )
        open_paths = _open_object_paths(schema)
        rows.append(
            {
                "schema_version": version,
                "schema_path": f"core_runtime/data/schemas/core/{path.name}",
                "mechanism": mechanism,
                "shape_profile": "closed_native" if not open_paths else "legacy_open_closed_by_strict_evaluator",
                "open_object_count": len(open_paths),
            }
        )
    return rows, errors


def _standalone_mechanism_errors() -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for version, (module_name, symbol_name) in sorted(STANDALONE_EXECUTABLE_CONTRACTS.items()):
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            errors.append(_entry("validator_import_failed", exc.__class__.__name__, version))
            continue
        if not callable(getattr(module, symbol_name, None)):
            errors.append(
                _entry(
                    "validator_symbol_missing",
                    "Declared standalone semantic validator is not callable.",
                    version,
                    module=module_name,
                    symbol=symbol_name,
                )
            )
    return errors


def audit_contract_executability() -> dict[str, Any]:
    """Execute positive and schema-valid negative probes for every contract."""

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    probes = executable_contract_probes()
    probe_versions = {probe.schema_version for probe in probes}
    evaluator_versions = set(executable_contract_versions())
    loader_versions = {
        _schema_version(load_contract_schema(contract_name))
        for contract_name in available_contracts()
    }
    loader_versions.discard(None)

    if probe_versions != evaluator_versions or evaluator_versions != loader_versions:
        errors.append(
            _entry(
                "contract_registry_drift",
                "Loader, evaluator, and executable-probe registries must contain the same contracts.",
                "registry",
                loader_only=sorted(loader_versions - evaluator_versions),
                evaluator_without_probe=sorted(evaluator_versions - probe_versions),
                probe_without_loader=sorted(probe_versions - loader_versions),
            )
        )

    for probe in sorted(probes, key=lambda item: item.schema_version):
        accepted_structure = validate_contract_structure(probe.accepted)
        accepted_first = evaluate_contract_payload(probe.accepted)
        accepted_second = evaluate_contract_payload(probe.accepted)
        negative = copy.deepcopy(probe.accepted)
        probe.mutate(negative)
        negative_structure = validate_contract_structure(negative)
        negative_result = evaluate_contract_payload(negative)
        negative_codes = {item["code"] for item in negative_result["errors"]}

        probe_errors: list[str] = []
        if accepted_structure:
            probe_errors.append("accepted_probe_schema_failed")
        if accepted_first["status"] != "passed":
            probe_errors.append("accepted_probe_semantics_failed")
        if accepted_first != accepted_second:
            probe_errors.append("nondeterministic_result")
        if negative_structure:
            probe_errors.append("negative_probe_not_schema_valid")
        if negative_result["status"] != "failed":
            probe_errors.append("semantic_negative_probe_accepted")
        if probe.expected_error not in negative_codes:
            probe_errors.append("expected_semantic_error_missing")
        if not SEMANTIC_RULE_IDS.get(probe.schema_version):
            probe_errors.append("semantic_rule_inventory_missing")
        if accepted_first.get("execution_authorized") is not False:
            probe_errors.append("execution_authority_leak")
        if accepted_first.get("deployment_authorized") is not False:
            probe_errors.append("deployment_authority_leak")

        result = {
            "schema_version": probe.schema_version,
            "status": "passed" if not probe_errors else "failed",
            "accepted_input_fingerprint": accepted_first["input_fingerprint"],
            "accepted_report_fingerprint": accepted_first["report_fingerprint"],
            "semantic_rule_count": len(SEMANTIC_RULE_IDS.get(probe.schema_version, ())),
            "negative_probe_schema_valid": not negative_structure,
            "expected_rejection_code": probe.expected_error,
            "observed_rejection_codes": sorted(negative_codes),
            "probe_errors": probe_errors,
        }
        results.append(result)
        for code in probe_errors:
            errors.append(
                _entry(
                    code,
                    "Contract executability probe failed.",
                    probe.schema_version,
                )
            )

    inventory, inventory_errors = _public_schema_inventory()
    errors.extend(inventory_errors)
    errors.extend(_standalone_mechanism_errors())
    for row in inventory:
        if row["open_object_count"]:
            warnings.append(
                _entry(
                    "legacy_open_schema",
                    "Published compatibility schema remains open; strict executable evaluation closes declared object shapes without rewriting history.",
                    row["schema_path"],
                    open_object_count=row["open_object_count"],
                )
            )

    report: dict[str, Any] = {
        "schema": "core.contract_executability_audit.v1",
        "status": "passed" if not errors else "failed",
        "authority": "validation_only",
        "truth_claimed": False,
        "execution_authorized": False,
        "contract_count": len(results),
        "passed_count": sum(result["status"] == "passed" for result in results),
        "failed_count": sum(result["status"] == "failed" for result in results),
        "public_schema_count": len(inventory),
        "results": results,
        "public_schema_inventory": inventory,
        "errors": errors,
        "warnings": warnings,
    }
    report["report_fingerprint"] = f"sha256:{canonical_json_hash(report)}"
    return report
