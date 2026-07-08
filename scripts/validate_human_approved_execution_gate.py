#!/usr/bin/env python3
"""Validate CORE human-approved execution gate artifacts.

Accepts a single JSON file or a directory of JSON files.
Validates all seven artifact types based on schema_version dispatch.

Rejection codes
---------------
Structural:
 missing_schema_version        schema_version is missing or empty
 unknown_schema_version        schema_version not recognized
 invalid_type                  type field does not match schema

Execution proposal:
 missing_proposal_id           proposal_id is missing or empty
 missing_sandbox_required      sandbox_required is missing
 invalid_execution_proposal    structural validation failed

Advisory review:
 llm_authority_rejected        authority is not 'advisory_only'
 advisory_consensus_not_authority advisory reviews cannot authorize execution

Multi-expert bundle:
 expert_divergence_requires_human  divergence without human review flag
 missing_divergence_summary        partial agreement without divergence summary

Human approval:
 missing_human_approval        requires_human_approval is false
 core_rejection_cannot_be_overridden human cannot override CORE rejection

Sandbox execution:
 missing_sandbox_profile       sandbox_profile is missing or empty

Scope:
 scope_expansion_detected      declared_scope contains escape patterns

Skill promotion:
 skill_auto_activation_rejected activation_default is not 'disabled'
 missing_execution_evidence    source_execution_id is missing
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
INVALID_TYPE = "invalid_type"
MISSING_PROPOSAL_ID = "missing_proposal_id"
MISSING_SANDBOX_REQUIRED = "missing_sandbox_required"
INVALID_EXECUTION_PROPOSAL = "invalid_execution_proposal"
LLM_AUTHORITY_REJECTED = "llm_authority_rejected"
ADVISORY_CONSENSUS_NOT_AUTHORITY = "advisory_consensus_not_authority"
EXPERT_DIVERGENCE_REQUIRES_HUMAN = "expert_divergence_requires_human"
MISSING_DIVERGENCE_SUMMARY = "missing_divergence_summary"
MISSING_HUMAN_APPROVAL = "missing_human_approval"
CORE_REJECTION_CANNOT_BE_OVERRIDDEN = "core_rejection_cannot_be_overridden"
MISSING_SANDBOX_PROFILE = "missing_sandbox_profile"
SCOPE_EXPANSION_DETECTED = "scope_expansion_detected"
SKILL_AUTO_ACTIVATION_REJECTED = "skill_auto_activation_rejected"
MISSING_EXECUTION_EVIDENCE = "missing_execution_evidence"
AMBIGUITY_REQUIRES_RESOLUTION = "ambiguity_requires_resolution"

VALID_RISK_TIERS = {"low", "medium", "high", "critical"}
VALID_ACTION_TYPES = {"run_script", "apply_patch", "generate_artifact", "read_only_check"}
VALID_PRODUCER_KINDS = {"private_assistant", "development_agent", "skill_runner", "human_operator"}
VALID_ADVISORY_VERDICTS = {"approve", "approve_with_conditions", "clarification_requested", "reject"}
VALID_AGREEMENT_LEVELS = {"unanimous_approval", "partial", "unanimous_rejection"}
VALID_HUMAN_DECISIONS = {"approved_for_sandbox_execution", "rejected", "clarification_required"}
VALID_AMBIGUITY_TYPES = {"scope_interpretation", "risk_tier_ambiguity", "output_format_ambiguity", "authorization_boundary"}

# --- Helpers -----------------------------------------------------------

def _error(code: str, message: str, field: str) -> dict[str, str]:
    return {"code": code, "message": message, "field": field}


def _validate_execution_proposal(artifact: dict[str, Any], source: str) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    if artifact.get("type", "") != "execution_proposal":
        errors.append(_error(INVALID_TYPE, "Expected type 'execution_proposal'.", "type"))

    pid = artifact.get("proposal_id", "")
    if not pid:
        errors.append(_error(MISSING_PROPOSAL_ID, "proposal_id is required.", "proposal_id"))

    producer = artifact.get("producer", {})
    if not isinstance(producer, dict) or not producer.get("id") or not producer.get("kind"):
        errors.append(_error(INVALID_EXECUTION_PROPOSAL, "producer must have id and kind.", "producer"))
    elif producer.get("kind", "") not in VALID_PRODUCER_KINDS:
        errors.append(_error(INVALID_EXECUTION_PROPOSAL, f"Invalid producer kind: {producer['kind']!r}.", "producer.kind"))

    action = artifact.get("requested_action", {})
    if not isinstance(action, dict):
        errors.append(_error(INVALID_EXECUTION_PROPOSAL, "requested_action must be an object.", "requested_action"))
    else:
        if action.get("action_type", "") not in VALID_ACTION_TYPES:
            errors.append(_error(INVALID_EXECUTION_PROPOSAL, f"Invalid action_type: {action.get('action_type')!r}.", "requested_action.action_type"))
        if "sandbox_required" not in action:
            errors.append(_error(MISSING_SANDBOX_REQUIRED, "sandbox_required is missing.", "requested_action.sandbox_required"))

    rt = artifact.get("risk_tier", "")
    if rt and rt not in VALID_RISK_TIERS:
        errors.append(_error(INVALID_EXECUTION_PROPOSAL, f"Invalid risk_tier: {rt!r}.", "risk_tier"))

    # Scope expansion check
    scope = artifact.get("declared_scope", [])
    if isinstance(scope, list):
        for i, s in enumerate(scope):
            if isinstance(s, str):
                if s.startswith("/") or ".." in s.split("/"):
                    errors.append(_error(SCOPE_EXPANSION_DETECTED, f"Scope escape detected: {s!r}.", f"declared_scope[{i}]"))

    # Human approval required
    if artifact.get("requires_human_approval") is False:
        errors.append(_error(MISSING_HUMAN_APPROVAL, "requires_human_approval must be true. No execution without human approval.", "requires_human_approval"))

    status = "passed" if not errors else "failed"
    result: dict[str, Any] = {
        "source": source,
        "artifact_type": "execution_proposal",
        "status": status,
        "errors": errors,
    }
    if pid:
        result["proposal_id"] = pid
    return result


def _validate_advisory_review(artifact: dict[str, Any], source: str) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    if artifact.get("type", "") != "advisory_review":
        errors.append(_error(INVALID_TYPE, "Expected type 'advisory_review'.", "type"))

    # Authority must be advisory_only
    authority = artifact.get("authority", "")
    if authority != "advisory_only":
        if authority in ("execution_authority", "authorizing", "binding"):
            errors.append(_error(LLM_AUTHORITY_REJECTED, f"LLM cannot authorize execution. authority={authority!r}.", "authority"))
        else:
            errors.append(_error(LLM_AUTHORITY_REJECTED, f"authority must be 'advisory_only', got {authority!r}.", "authority"))

    verdict = artifact.get("verdict", "")
    if verdict and verdict not in VALID_ADVISORY_VERDICTS:
        errors.append(_error(INVALID_TYPE, f"Invalid verdict: {verdict!r}.", "verdict"))

    # Even unanimous approval is not authority
    if verdict == "approve" and authority == "advisory_only":
        pass  # Valid but still not authorizing

    pid = artifact.get("proposal_id", "")
    status = "passed" if not errors else "failed"
    result: dict[str, Any] = {
        "source": source,
        "artifact_type": "advisory_review",
        "status": status,
        "errors": errors,
    }
    if pid:
        result["proposal_id"] = pid
    return result


def _validate_multi_expert_review_bundle(artifact: dict[str, Any], source: str) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    if artifact.get("type", "") != "multi_expert_review_bundle":
        errors.append(_error(INVALID_TYPE, "Expected type 'multi_expert_review_bundle'.", "type"))

    agreement = artifact.get("agreement", "")
    if agreement and agreement not in VALID_AGREEMENT_LEVELS:
        errors.append(_error(INVALID_TYPE, f"Invalid agreement: {agreement!r}.", "agreement"))

    # requires_human_review must be True
    if artifact.get("requires_human_review") is not True:
        errors.append(_error(EXPERT_DIVERGENCE_REQUIRES_HUMAN, "requires_human_review must be true.", "requires_human_review"))

    # If agreement is partial, divergence_summary is required
    if agreement == "partial" and not artifact.get("divergence_summary"):
        errors.append(_error(MISSING_DIVERGENCE_SUMMARY, "divergence_summary is required when agreement is partial.", "divergence_summary"))

    # Even unanimous approval requires human review
    if agreement == "unanimous_approval" and artifact.get("requires_human_review") is not True:
        errors.append(_error(ADVISORY_CONSENSUS_NOT_AUTHORITY, "Unanimous advisory approval still requires human review.", "requires_human_review"))

    pid = artifact.get("proposal_id", "")
    status = "passed" if not errors else "failed"
    result: dict[str, Any] = {
        "source": source,
        "artifact_type": "multi_expert_review_bundle",
        "status": status,
        "errors": errors,
    }
    if pid:
        result["proposal_id"] = pid
    return result


def _validate_human_approval_record(artifact: dict[str, Any], source: str) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    if artifact.get("type", "") != "human_approval_record":
        errors.append(_error(INVALID_TYPE, "Expected type 'human_approval_record'.", "type"))

    decision = artifact.get("decision", "")
    if decision and decision not in VALID_HUMAN_DECISIONS:
        errors.append(_error(INVALID_TYPE, f"Invalid decision: {decision!r}.", "decision"))

    fp = artifact.get("approval_fingerprint", "")
    if fp and not VALID_FP_RE.match(fp):
        errors.append(_error(INVALID_TYPE, f"Invalid fingerprint: {fp!r}.", "approval_fingerprint"))

    pid = artifact.get("proposal_id", "")
    status = "passed" if not errors else "failed"
    result: dict[str, Any] = {
        "source": source,
        "artifact_type": "human_approval_record",
        "status": status,
        "errors": errors,
    }
    if pid:
        result["proposal_id"] = pid
    return result


def _validate_sandbox_execution_record(artifact: dict[str, Any], source: str) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    if artifact.get("type", "") != "sandbox_execution_record":
        errors.append(_error(INVALID_TYPE, "Expected type 'sandbox_execution_record'.", "type"))

    # sandbox_profile must be explicit
    sp = artifact.get("sandbox_profile", "")
    if not sp:
        errors.append(_error(MISSING_SANDBOX_PROFILE, "sandbox_profile is required.", "sandbox_profile"))

    pid = artifact.get("proposal_id", "")
    status = "passed" if not errors else "failed"
    result: dict[str, Any] = {
        "source": source,
        "artifact_type": "sandbox_execution_record",
        "status": status,
        "errors": errors,
    }
    if pid:
        result["proposal_id"] = pid
    return result


def _validate_skill_promotion_candidate(artifact: dict[str, Any], source: str) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    if artifact.get("type", "") != "skill_promotion_candidate":
        errors.append(_error(INVALID_TYPE, "Expected type 'skill_promotion_candidate'.", "type"))

    # activation_default must be 'disabled'
    ad = artifact.get("activation_default", "")
    if ad != "disabled":
        errors.append(_error(SKILL_AUTO_ACTIVATION_REJECTED, f"activation_default must be 'disabled', got {ad!r}. Skills never auto-activate.", "activation_default"))

    # requires_human_approval must be True
    if artifact.get("requires_human_approval") is not True:
        errors.append(_error(MISSING_HUMAN_APPROVAL, "requires_human_approval must be true for skill promotion.", "requires_human_approval"))

    # source_execution_id is required (evidence)
    sei = artifact.get("source_execution_id", "")
    if not sei:
        errors.append(_error(MISSING_EXECUTION_EVIDENCE, "source_execution_id is required. Skill promotion requires frozen evidence.", "source_execution_id"))

    status = "passed" if not errors else "failed"
    result: dict[str, Any] = {
        "source": source,
        "artifact_type": "skill_promotion_candidate",
        "status": status,
        "errors": errors,
    }
    if sei:
        result["source_execution_id"] = sei
    return result


def _validate_ambiguity_resolution_record(artifact: dict[str, Any], source: str) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    if artifact.get("type", "") != "ambiguity_resolution_record":
        errors.append(_error(INVALID_TYPE, "Expected type 'ambiguity_resolution_record'.", "type"))

    at = artifact.get("ambiguity_type", "")
    if at and at not in VALID_AMBIGUITY_TYPES:
        errors.append(_error(INVALID_TYPE, f"Invalid ambiguity_type: {at!r}.", "ambiguity_type"))

    # interpretations must have at least 2 entries
    interpretations = artifact.get("interpretations", [])
    if not isinstance(interpretations, list) or len(interpretations) < 2:
        errors.append(_error(AMBIGUITY_REQUIRES_RESOLUTION, "interpretations must have at least 2 entries.", "interpretations"))

    # If no resolution, ambiguity is unresolved -> cannot proceed to execution
    resolution = artifact.get("resolution", "")
    if not resolution:
        errors.append(_error(AMBIGUITY_REQUIRES_RESOLUTION, "Ambiguity must be resolved before execution. resolution is missing.", "resolution"))

    pid = artifact.get("proposal_id", "")
    status = "passed" if not errors else "failed"
    result: dict[str, Any] = {
        "source": source,
        "artifact_type": "ambiguity_resolution_record",
        "status": status,
        "errors": errors,
    }
    if pid:
        result["proposal_id"] = pid
    return result


# --- Dispatch ----------------------------------------------------------

SCHEMA_DISPATCH = {
    "core.execution_proposal.v1": _validate_execution_proposal,
    "core.advisory_review.v1": _validate_advisory_review,
    "core.multi_expert_review_bundle.v1": _validate_multi_expert_review_bundle,
    "core.human_approval_record.v1": _validate_human_approval_record,
    "core.sandbox_execution_record.v1": _validate_sandbox_execution_record,
    "core.skill_promotion_candidate.v1": _validate_skill_promotion_candidate,
    "core.ambiguity_resolution_record.v1": _validate_ambiguity_resolution_record,
}

TYPE_DISPATCH = {
    "execution_proposal": _validate_execution_proposal,
    "advisory_review": _validate_advisory_review,
    "multi_expert_review_bundle": _validate_multi_expert_review_bundle,
    "human_approval_record": _validate_human_approval_record,
    "sandbox_execution_record": _validate_sandbox_execution_record,
    "skill_promotion_candidate": _validate_skill_promotion_candidate,
    "ambiguity_resolution_record": _validate_ambiguity_resolution_record,
}


def _validate_one(artifact: dict[str, Any], source: str) -> dict[str, Any]:
    sv = artifact.get("schema_version", "")
    if not sv or not isinstance(sv, str):
        inferred = artifact.get("type", "")
        validator = TYPE_DISPATCH.get(inferred)
        if validator:
            return validator(artifact, source)
        return {
            "source": source,
            "artifact_type": "unknown",
            "status": "failed",
            "errors": [_error(MISSING_SCHEMA_VERSION, "Missing or invalid schema_version.", "schema_version")],
        }

    validator = SCHEMA_DISPATCH.get(sv)
    if validator:
        return validator(artifact, source)

    return {
        "source": source,
        "artifact_type": "unknown",
        "status": "failed",
        "errors": [_error(UNKNOWN_SCHEMA_VERSION, f"Unknown schema_version: {sv!r}.", "schema_version")],
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Validate human-approved execution gate artifacts.")
    parser.add_argument("path", help="JSON file or directory to validate.")
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
            "schema": "core.human_approved_execution_gate_validation.v1",
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
            "schema": "core.human_approved_execution_gate_validation.v1",
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
        "schema": "core.human_approved_execution_gate_validation.v1",
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
