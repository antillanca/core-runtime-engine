#!/usr/bin/env python3
"""Validate CORE expert conflict pre-resolution artifacts.

Accepts a single JSON file or a directory of JSON files.
Validates all five artifact types based on schema_version dispatch.

Rejection codes
---------------
Structural:
 missing_schema_version          schema_version is missing or empty
 unknown_schema_version          schema_version not recognized

Expert conflict bundle:
 invalid_conflict_bundle         structural validation failed
 missing_preserved_claims        expert outputs have no preserved claims

Pre-resolution protocol:
 unknown_protocol_type           protocol_type not in allowed set
 non_deterministic_protocol      deterministic is not true

Pre-resolution report:
 llm_authority_resolution_rejected  LLM consensus used as authority
 human_required_bypassed             human approval bypassed when required
 unbounded_context_resolution_rejected  unbounded context used to resolve
 invalid_pre_resolution_outcome      outcome not in allowed set
 pre_resolution_executes_action      report claims to execute an action
 core_rejection_overridden           protocol overrides CORE rejection
 missing_preserved_claims            no preserved claims in report

Human escalation decision:
 missing_human_escalation_decision   decision inconsistent with report
 human_required_bypassed             human required but decision says no
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

VALID_FP_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

# --- Rejection codes ---------------------------------------------------

MISSING_SCHEMA_VERSION = "missing_schema_version"
UNKNOWN_SCHEMA_VERSION = "unknown_schema_version"
INVALID_CONFLICT_BUNDLE = "invalid_conflict_bundle"
MISSING_PRESERVED_CLAIMS = "missing_preserved_claims"
UNKNOWN_PROTOCOL_TYPE = "unknown_protocol_type"
NON_DETERMINISTIC_PROTOCOL = "non_deterministic_protocol"
LLM_AUTHORITY_RESOLUTION_REJECTED = "llm_authority_resolution_rejected"
HUMAN_REQUIRED_BYPASSED = "human_required_bypassed"
UNBOUNDED_CONTEXT_RESOLUTION_REJECTED = "unbounded_context_resolution_rejected"
INVALID_PRE_RESOLUTION_OUTCOME = "invalid_pre_resolution_outcome"
MISSING_HUMAN_ESCALATION_DECISION = "missing_human_escalation_decision"
PRE_RESOLUTION_EXECUTES_ACTION = "pre_resolution_executes_action"
CORE_REJECTION_OVERRIDDEN = "core_rejection_overridden"

# --- Valid values ------------------------------------------------------

VALID_PROTOCOL_TYPES = {
    "canonicalization_check",
    "schema_alignment",
    "lawset_check",
    "evidence_completeness_check",
    "bounded_reference_lookup",
    "classification_recheck",
    "template_match_check",
    "replay_check",
    "risk_tier_check",
    "confidence_gap_check",
}

VALID_RISK_TIERS = {"low", "medium", "high", "critical"}

VALID_CLAIM_TYPES = {
    "command_candidate",
    "classification_candidate",
    "evidence_bundle",
    "advisory_review",
}

VALID_EXPERT_DECISIONS = {
    "accepted",
    "rejected",
    "clarification_required",
    "missing_evidence",
}

VALID_STEP_STATUSES = {
    "resolved_equivalent",
    "resolved_by_law",
    "resolved_by_template",
    "resolved_by_evidence",
    "clarification_needed",
    "evidence_missing",
    "no_resolution",
    "law_rejection",
}

VALID_OUTCOMES = {
    "resolved_by_protocol",
    "clarification_required",
    "missing_evidence",
    "human_required",
    "rejected_by_law",
    "unresolved",
}

VALID_ESCALATION_REASONS = {
    "risk_tier_requires_human_approval",
    "profile_requires_human_escalation",
    "unresolved_conflict",
    "missing_evidence_cannot_be_produced_deterministically",
    "execution_would_require_human_approved_gate",
    "advisory_experts_diverge_on_sensitive_action",
    "ambiguity_changes_execution_scope",
    "no_human_override_needed",
    "resolved_by_deterministic_protocol",
    "rejected_by_active_law",
}

# --- Schema dispatch ---------------------------------------------------

SCHEMA_DISPATCH = {
    "core.expert_conflict_bundle.v1": "_validate_conflict_bundle",
    "core.pre_resolution_protocol.v1": "_validate_pre_resolution_protocol",
    "core.pre_resolution_step.v1": "_validate_pre_resolution_step",
    "core.pre_resolution_report.v1": "_validate_pre_resolution_report",
    "core.human_escalation_decision.v1": "_validate_human_escalation_decision",
}

# --- Helpers -----------------------------------------------------------

def _error(code: str, message: str, field: str) -> dict[str, str]:
    return {"code": code, "message": message, "field": field}


def _validate_conflict_bundle(artifact: dict[str, Any], source: str) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    if artifact.get("type", "") != "expert_conflict_bundle":
        errors.append(_error(INVALID_CONFLICT_BUNDLE, "Expected type 'expert_conflict_bundle'.", "type"))

    # conflict_id
    if not artifact.get("conflict_id"):
        errors.append(_error(INVALID_CONFLICT_BUNDLE, "conflict_id is required.", "conflict_id"))

    # input_fingerprint
    fp = artifact.get("input_fingerprint", "")
    if not VALID_FP_RE.match(fp):
        errors.append(_error(INVALID_CONFLICT_BUNDLE, "input_fingerprint must be sha256:hex64.", "input_fingerprint"))

    # expert_outputs
    outputs = artifact.get("expert_outputs", [])
    if not isinstance(outputs, list) or len(outputs) < 2:
        errors.append(_error(INVALID_CONFLICT_BUNDLE, "expert_outputs must have >= 2 entries.", "expert_outputs"))
    else:
        for i, out in enumerate(outputs):
            if not isinstance(out, dict):
                errors.append(_error(INVALID_CONFLICT_BUNDLE, f"expert_outputs[{i}] must be an object.", f"expert_outputs[{i}]"))
                continue
            if not out.get("expert_id"):
                errors.append(_error(INVALID_CONFLICT_BUNDLE, f"expert_outputs[{i}].expert_id is required.", f"expert_outputs[{i}].expert_id"))
            ref = out.get("output_ref", "")
            if not VALID_FP_RE.match(ref):
                errors.append(_error(INVALID_CONFLICT_BUNDLE, f"expert_outputs[{i}].output_ref must be sha256:hex64.", f"expert_outputs[{i}].output_ref"))
            if out.get("claim_type", "") not in VALID_CLAIM_TYPES:
                errors.append(_error(INVALID_CONFLICT_BUNDLE, f"expert_outputs[{i}].claim_type invalid.", f"expert_outputs[{i}].claim_type"))
            if out.get("decision", "") not in VALID_EXPERT_DECISIONS:
                errors.append(_error(INVALID_CONFLICT_BUNDLE, f"expert_outputs[{i}].decision invalid.", f"expert_outputs[{i}].decision"))

    # risk_tier
    rt = artifact.get("risk_tier", "")
    if rt not in VALID_RISK_TIERS:
        errors.append(_error(INVALID_CONFLICT_BUNDLE, f"Invalid risk_tier: {rt!r}.", "risk_tier"))

    # human_required_by_profile
    if "human_required_by_profile" not in artifact:
        errors.append(_error(INVALID_CONFLICT_BUNDLE, "human_required_by_profile is required.", "human_required_by_profile"))

    # Check for LLM authority usage (forbidden)
    if artifact.get("llm_authority_used"):
        errors.append(_error(LLM_AUTHORITY_RESOLUTION_REJECTED, "LLM authority cannot be used in conflict bundle.", "llm_authority_used"))

    artifact_type = "expert_conflict_bundle"
    status = "passed" if not errors else "failed"
    return {"source": source, "artifact_type": artifact_type, "status": status, "errors": errors}


def _validate_pre_resolution_protocol(artifact: dict[str, Any], source: str) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    if not artifact.get("protocol_id"):
        errors.append(_error(UNKNOWN_PROTOCOL_TYPE, "protocol_id is required.", "protocol_id"))

    if not artifact.get("input_conflict_id"):
        errors.append(_error(UNKNOWN_PROTOCOL_TYPE, "input_conflict_id is required.", "input_conflict_id"))

    pt = artifact.get("protocol_type", "")
    if pt not in VALID_PROTOCOL_TYPES:
        errors.append(_error(UNKNOWN_PROTOCOL_TYPE, f"Invalid protocol_type: {pt!r}.", "protocol_type"))

    # Must be deterministic
    if artifact.get("deterministic") is not True:
        errors.append(_error(NON_DETERMINISTIC_PROTOCOL, "deterministic must be true.", "deterministic"))

    # requires_human_approval
    if "requires_human_approval" not in artifact:
        errors.append(_error(HUMAN_REQUIRED_BYPASSED, "requires_human_approval is required.", "requires_human_approval"))

    artifact_type = "pre_resolution_protocol"
    status = "passed" if not errors else "failed"
    return {"source": source, "artifact_type": artifact_type, "status": status, "errors": errors}


def _validate_pre_resolution_step(artifact: dict[str, Any], source: str) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    if not artifact.get("conflict_id"):
        errors.append(_error(INVALID_CONFLICT_BUNDLE, "conflict_id is required.", "conflict_id"))

    if not artifact.get("protocol_id"):
        errors.append(_error(UNKNOWN_PROTOCOL_TYPE, "protocol_id is required.", "protocol_id"))

    st = artifact.get("status", "")
    if st not in VALID_STEP_STATUSES:
        errors.append(_error(INVALID_PRE_RESOLUTION_OUTCOME, f"Invalid step status: {st!r}.", "status"))

    # fingerprint validation if present
    fp = artifact.get("fingerprint", "")
    if fp and not VALID_FP_RE.match(fp):
        errors.append(_error(INVALID_CONFLICT_BUNDLE, "fingerprint must be sha256:hex64.", "fingerprint"))

    artifact_type = "pre_resolution_step"
    status = "passed" if not errors else "failed"
    return {"source": source, "artifact_type": artifact_type, "status": status, "errors": errors}


def _validate_pre_resolution_report(artifact: dict[str, Any], source: str) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    if not artifact.get("conflict_id"):
        errors.append(_error(INVALID_CONFLICT_BUNDLE, "conflict_id is required.", "conflict_id"))

    # steps
    steps = artifact.get("steps", [])
    if not isinstance(steps, list):
        errors.append(_error(INVALID_CONFLICT_BUNDLE, "steps must be an array.", "steps"))
    else:
        for i, s in enumerate(steps):
            if not VALID_FP_RE.match(s):
                errors.append(_error(INVALID_CONFLICT_BUNDLE, f"steps[{i}] must be sha256:hex64.", f"steps[{i}]"))

    # outcome
    outcome = artifact.get("outcome", "")
    if outcome not in VALID_OUTCOMES:
        errors.append(_error(INVALID_PRE_RESOLUTION_OUTCOME, f"Invalid outcome: {outcome!r}.", "outcome"))

    # human_required
    if "human_required" not in artifact:
        errors.append(_error(HUMAN_REQUIRED_BYPASSED, "human_required is required.", "human_required"))

    # preserved_claims — must have at least 1
    claims = artifact.get("preserved_claims", [])
    if not isinstance(claims, list) or len(claims) < 1:
        errors.append(_error(MISSING_PRESERVED_CLAIMS, "preserved_claims must have >= 1 entry.", "preserved_claims"))
    else:
        for i, c in enumerate(claims):
            if not VALID_FP_RE.match(c):
                errors.append(_error(MISSING_PRESERVED_CLAIMS, f"preserved_claims[{i}] must be sha256:hex64.", f"preserved_claims[{i}]"))

    # LLM authority check (forbidden)
    if artifact.get("llm_authority_used"):
        errors.append(_error(LLM_AUTHORITY_RESOLUTION_REJECTED, "LLM authority cannot be used to resolve conflicts.", "llm_authority_used"))

    # Unbounded context check (forbidden)
    if artifact.get("unbounded_context_used"):
        errors.append(_error(UNBOUNDED_CONTEXT_RESOLUTION_REJECTED, "Unbounded context cannot be used to resolve conflicts.", "unbounded_context_used"))

    # Human bypass check: if profile requires human or risk_tier_override is high/critical
    human_by_profile = artifact.get("human_required_by_profile", False)
    risk_override = artifact.get("risk_tier_override", "")
    if human_by_profile and artifact.get("human_required") is False:
        errors.append(_error(HUMAN_REQUIRED_BYPASSED, "human_required is false but profile requires human approval.", "human_required"))
    if risk_override in ("high", "critical") and artifact.get("human_required") is False:
        errors.append(_error(HUMAN_REQUIRED_BYPASSED, f"human_required is false but risk_tier_override is {risk_override!r}.", "human_required"))

    # Executes action check (forbidden)
    if artifact.get("executes_action") is True:
        errors.append(_error(PRE_RESOLUTION_EXECUTES_ACTION, "Pre-resolution report cannot execute actions.", "executes_action"))

    # CORE rejection override check (forbidden)
    if artifact.get("core_rejection_overridden"):
        errors.append(_error(CORE_REJECTION_OVERRIDDEN, "Protocol cannot override CORE rejection.", "core_rejection_overridden"))

    artifact_type = "pre_resolution_report"
    status = "passed" if not errors else "failed"
    return {"source": source, "artifact_type": artifact_type, "status": status, "errors": errors}


def _validate_human_escalation_decision(artifact: dict[str, Any], source: str) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    if not artifact.get("conflict_id"):
        errors.append(_error(INVALID_CONFLICT_BUNDLE, "conflict_id is required.", "conflict_id"))

    # human_required
    if "human_required" not in artifact:
        errors.append(_error(MISSING_HUMAN_ESCALATION_DECISION, "human_required is required.", "human_required"))

    # reason
    reason = artifact.get("reason", "")
    if reason not in VALID_ESCALATION_REASONS:
        errors.append(_error(MISSING_HUMAN_ESCALATION_DECISION, f"Invalid reason: {reason!r}.", "reason"))

    # pre_resolution_outcome
    outcome = artifact.get("pre_resolution_outcome", "")
    if outcome not in VALID_OUTCOMES:
        errors.append(_error(INVALID_PRE_RESOLUTION_OUTCOME, f"Invalid pre_resolution_outcome: {outcome!r}.", "pre_resolution_outcome"))

    # Consistency: if outcome is "human_required" or "unresolved", human_required must be true
    if outcome in ("human_required", "unresolved") and artifact.get("human_required") is False:
        errors.append(_error(HUMAN_REQUIRED_BYPASSED, f"pre_resolution_outcome is '{outcome}' but human_required is false.", "human_required"))

    # Consistency: if reason indicates human required, human_required must be true
    human_reasons = {
        "risk_tier_requires_human_approval",
        "profile_requires_human_escalation",
        "unresolved_conflict",
        "missing_evidence_cannot_be_produced_deterministically",
        "execution_would_require_human_approved_gate",
        "advisory_experts_diverge_on_sensitive_action",
        "ambiguity_changes_execution_scope",
    }
    if reason in human_reasons and artifact.get("human_required") is False:
        errors.append(_error(HUMAN_REQUIRED_BYPASSED, f"reason '{reason}' requires human but human_required is false.", "human_required"))

    artifact_type = "human_escalation_decision"
    status = "passed" if not errors else "failed"
    return {"source": source, "artifact_type": artifact_type, "status": status, "errors": errors}


# --- Dispatch ----------------------------------------------------------

def _validate_one(artifact: dict[str, Any], source: str) -> dict[str, Any]:
    sv = artifact.get("schema_version", "")
    if not sv:
        return {"source": source, "artifact_type": "unknown", "status": "failed",
                "errors": [_error(MISSING_SCHEMA_VERSION, "schema_version is missing or empty.", "schema_version")]}

    handler_name = SCHEMA_DISPATCH.get(sv)
    if not handler_name:
        return {"source": source, "artifact_type": "unknown", "status": "failed",
                "errors": [_error(UNKNOWN_SCHEMA_VERSION, f"Unknown schema_version: {sv!r}", "schema_version")]}

    handler = globals()[handler_name]
    return handler(artifact, source)


# --- Main --------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Validate expert conflict pre-resolution artifacts.")
    parser.add_argument("path", help="JSON file or directory of JSON files")
    args = parser.parse_args()

    target = Path(args.path)
    files: list[Path] = []

    if target.is_dir():
        for p in sorted(target.rglob("*.json")):
            files.append(p)
    elif target.is_file():
        files.append(target)
    else:
        print(json.dumps({
            "schema": "core.expert_conflict_pre_resolution_validation.v1",
            "status": "failed",
            "total_artifacts": 0,
            "passed_count": 0,
            "failed_count": 0,
            "results": [{"source": str(target), "artifact_type": "unknown", "status": "failed",
                         "errors": [_error("path_not_found", f"Path not found: {target}", "path")]}],
        }, indent=2))
        sys.exit(1)

    if not files:
        print(json.dumps({
            "schema": "core.expert_conflict_pre_resolution_validation.v1",
            "status": "failed",
            "total_artifacts": 0,
            "passed_count": 0,
            "failed_count": 0,
            "results": [],
        }, indent=2))
        sys.exit(1)

    results: list[dict[str, Any]] = []
    for f in files:
        try:
            artifact = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            results.append({
                "source": str(f),
                "artifact_type": "unknown",
                "status": "failed",
                "errors": [{"code": "invalid_json", "message": str(exc), "field": "file"}],
            })
            continue
        results.append(_validate_one(artifact, str(f)))

    passed = sum(1 for r in results if r["status"] == "passed")
    failed = sum(1 for r in results if r["status"] == "failed")

    report_fingerprint = "sha256:" + hashlib.sha256(
        json.dumps(results, sort_keys=True).encode("utf-8")
    ).hexdigest()

    report = {
        "schema": "core.expert_conflict_pre_resolution_validation.v1",
        "status": "passed" if failed == 0 else "failed",
        "total_artifacts": len(results),
        "passed_count": passed,
        "failed_count": failed,
        "report_fingerprint": report_fingerprint,
        "results": results,
    }

    print(json.dumps(report, indent=2, sort_keys=False))
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
