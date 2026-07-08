#!/usr/bin/env python3
"""Validate CORE downstream bridge adapter artifacts.

Accepts a single JSON file or a directory of JSON files.
Validates downstream_bridge_adapter artifacts based on schema_version dispatch.

Rejection codes
---------------
Structural:
 missing_schema_version        schema_version is missing or empty
 unknown_schema_version        schema_version not recognized
 invalid_json                  file is not valid JSON

Identity:
 missing_adapter_id            adapter_id is missing or empty
 invalid_adapter_id_format     adapter_id does not match pattern
 duplicate_core_schema_consumed  core_schemas_consumed has duplicates

Content:
 empty_core_schemas_consumed   core_schemas_consumed is empty
 unknown_core_schema_referenced schema name not in CORE registry
 empty_translation_invariants  translation_invariants is empty
 duplicate_invariant_id        two invariants share the same invariant_id
 invariant_missing_core_ref    invariant core_artifact_ref is empty
 invariant_missing_verification invariant verification_method is empty

Governance:
 autonomous_execution_allowed   forbids_autonomous_execution is false
 private_namespace_leak_not_forbidden  forbids_private_namespace_leak is false
 fail_closed_not_set            fail_closed is false in strict mode
 human_override_without_emergency  human_override_allowed true but level not emergency
 enforcement_level_invalid      enforcement_level not in allowed enum

Integrity:
 adapter_fingerprint_mismatch  fingerprint does not match computed
 consumed_schema_not_in_core_registry  schema name not found in CORE
 verification_method_not_declared  invariant has empty verification_method
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

# CORE schema registry — schemas that exist in the schemas/ directory
CORE_SCHEMA_REGISTRY: set[str] = {
    "agent_session",
    "agent_task",
    "agent_context_budget",
    "agent_decision_trace",
    "agent_plan",
    "agent_plan_step",
    "agent_plan_dependency",
    "agent_plan_result",
    "tool_invocation_proposal",
    "downstream_bridge_adapter",
    "bounded_reference_index",
    "bounded_read_window",
    "classification_candidate",
    "execution_proposal",
    "human_approval_record",
    "human_escalation_decision",
    "ambiguity_resolution_record",
    "pre_resolution_protocol",
    "pre_resolution_step",
    "pre_resolution_report",
    "expert_conflict_bundle",
    "multi_expert_review_bundle",
    "advisory_review",
    "business_event",
    "parametric_template",
    "parametric_cache_entry",
    "processed_reference_cache",
    "variable_binding",
    "state_watcher",
    "skill_promotion_candidate",
    "sandbox_execution_record",
}

ADAPTER_ID_PATTERN = re.compile(r"^bridge_[a-z][a-z0-9]*_v[0-9]+$")
INVARIANT_ID_PATTERN = re.compile(r"^inv_[a-z][a-z0-9_]*$")
FINGERPRINT_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")
VERSION_REF_PATTERN = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")
ENFORCEMENT_LEVELS = {"strict", "degraded", "emergency"}


def _err(code: str, field: str = "", message: str = "", **extra: Any) -> dict:
    return {"code": code, "field": field, "message": message, **extra}


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _compute_adapter_fingerprint(adapter: dict) -> str:
    payload = {k: v for k, v in adapter.items() if k != "audit"}
    if "audit" in adapter:
        audit_payload = {k: v for k, v in adapter["audit"].items() if k != "adapter_fingerprint"}
        payload["audit"] = audit_payload
    return f"sha256:{hashlib.sha256(_canonical_json(payload).encode()).hexdigest()}"


def validate_adapter(data: dict) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []

    # Structural
    sv = data.get("schema_version")
    if not sv:
        errors.append(_err("missing_schema_version", "schema_version", "schema_version is missing or empty"))
        return {"status": "failed", "errors": errors, "warnings": warnings, "adapter_fingerprint": ""}
    if sv != "v1":
        errors.append(_err("unknown_schema_version", "schema_version", f"schema_version '{sv}' not recognized"))

    tp = data.get("type")
    if tp != "downstream_bridge_adapter":
        errors.append(_err("invalid_type", "type", f"type must be 'downstream_bridge_adapter', got '{tp}'"))

    # Identity
    aid = data.get("adapter_id", "")
    if not aid:
        errors.append(_err("missing_adapter_id", "adapter_id", "adapter_id is missing or empty"))
    elif not ADAPTER_ID_PATTERN.match(aid):
        errors.append(_err("invalid_adapter_id_format", "adapter_id", f"adapter_id '{aid}' does not match pattern bridge_{{domain}}_v{{n}}"))

    # Core schemas consumed
    consumed = data.get("core_schemas_consumed", [])
    if not consumed:
        errors.append(_err("empty_core_schemas_consumed", "core_schemas_consumed", "core_schemas_consumed must not be empty"))
    else:
        seen: set[str] = set()
        for s in consumed:
            if s in seen:
                errors.append(_err("duplicate_core_schema_consumed", "core_schemas_consumed", f"duplicate schema '{s}'"))
            seen.add(s)
            if s not in CORE_SCHEMA_REGISTRY:
                errors.append(_err("unknown_core_schema_referenced", "core_schemas_consumed", f"schema '{s}' not in CORE registry"))

    # Translation invariants
    invariants = data.get("translation_invariants", [])
    if not invariants:
        errors.append(_err("empty_translation_invariants", "translation_invariants", "translation_invariants must not be empty"))
    else:
        inv_ids: set[str] = set()
        for inv in invariants:
            iid = inv.get("invariant_id", "")
            if iid in inv_ids:
                errors.append(_err("duplicate_invariant_id", "translation_invariants", f"duplicate invariant_id '{iid}'"))
            inv_ids.add(iid)

            if not inv.get("core_artifact_ref"):
                errors.append(_err("invariant_missing_core_ref", "translation_invariants", f"invariant '{iid}' missing core_artifact_ref"))
            if not inv.get("verification_method"):
                errors.append(_err("verification_method_not_declared", "translation_invariants", f"invariant '{iid}' missing verification_method"))

    # Governance
    if data.get("forbids_autonomous_execution") is not True:
        errors.append(_err("autonomous_execution_allowed", "forbids_autonomous_execution", "forbids_autonomous_execution must be true"))

    if data.get("forbids_private_namespace_leak") is not True:
        errors.append(_err("private_namespace_leak_not_forbidden", "forbids_private_namespace_leak", "forbids_private_namespace_leak must be true"))

    # Runtime enforcement policy
    policy = data.get("runtime_enforcement_policy", {})
    level = policy.get("enforcement_level", "")
    if level not in ENFORCEMENT_LEVELS:
        errors.append(_err("enforcement_level_invalid", "runtime_enforcement_policy.enforcement_level", f"enforcement_level '{level}' not in {ENFORCEMENT_LEVELS}"))

    fail_closed = policy.get("fail_closed")
    if level == "strict" and fail_closed is not True:
        errors.append(_err("fail_closed_not_set", "runtime_enforcement_policy.fail_closed", "fail_closed must be true when enforcement_level is 'strict'"))

    human_override = policy.get("human_override_allowed")
    if human_override is True and level != "emergency":
        errors.append(_err("human_override_without_emergency", "runtime_enforcement_policy.human_override_allowed", "human_override_allowed requires enforcement_level 'emergency'"))

    # Integrity — fingerprint
    computed_fp = _compute_adapter_fingerprint(data)
    stored_fp = data.get("audit", {}).get("adapter_fingerprint", "")
    if stored_fp and stored_fp != computed_fp:
        errors.append(_err(
            "adapter_fingerprint_mismatch",
            "audit.adapter_fingerprint",
            "adapter_fingerprint does not match computed fingerprint",
            actual=stored_fp,
            expected=computed_fp,
        ))

    # Core release ref format
    release_ref = data.get("audit", {}).get("core_release_ref", "")
    if release_ref and not VERSION_REF_PATTERN.match(release_ref):
        errors.append(_err("invalid_core_release_ref", "audit.core_release_ref", f"core_release_ref '{release_ref}' does not match version pattern"))

    status = "passed" if not errors else "failed"
    return {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "adapter_fingerprint": computed_fp,
    }


def validate_file(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"status": "failed", "errors": [_err("invalid_json", "", str(exc))], "warnings": [], "adapter_fingerprint": ""}
    return validate_adapter(data)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: validate_downstream_bridge_adapter.py <file_or_dir>", file=sys.stderr)
        sys.exit(2)

    target = Path(sys.argv[1])
    if target.is_dir():
        results = {}
        for f in sorted(target.glob("*.json")):
            results[f.name] = validate_file(f)
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(validate_file(target), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
