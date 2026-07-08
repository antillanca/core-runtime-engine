#!/usr/bin/env python3
"""Validate CORE tool invocation proposal artifacts.

Accepts a single JSON file or a directory of JSON files.
Validates the tool_invocation_proposal artifact type.

Rejection codes:
  missing_schema_version, unknown_schema_version, invalid_json,
  invalid_type, missing_proposal_id, invalid_proposal_id_format,
  missing_session_ref, missing_plan_step_ref, missing_tool_logical_name,
  invalid_tool_logical_name_format, missing_tool_version,
  invalid_tool_version_format, invalid_tool_category, invalid_argument_type,
  nested_argument_value, empty_arguments, invalid_risk_tier,
  invalid_side_effects, invalid_reversibility,
  approval_not_required_for_risky_tool,
  approval_not_required_for_side_effects,
  autonomous_execution_allowed, missing_approval_reason,
  invalid_evidence_type, missing_expected_evidence,
  missing_evidence_description, timeout_out_of_range,
  max_retries_out_of_range, private_path_detected,
  missing_expected_evidence_description
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "core.tool_invocation_proposal_validation.v1"
ARTIFACT_TYPE = "tool_invocation_proposal"
SCHEMA_VERSION_PATTERN = "core.tool_invocation_proposal.v1"
PROPOSAL_ID_RE = re.compile(
    r"^tool_invocation_proposal:[a-z][a-z0-9_.-]*\.[a-z][a-z0-9_.-]*\.v[0-9]+$"
)
TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
TOOL_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
PRIVATE_PATH_RE = re.compile(r"(?:^|[/\\])(?:home|etc|var|usr|tmp|opt|root|Users)[/\\]")

VALID_TOOL_CATEGORIES = {"read_only", "write", "external_call", "approval_gate", "notification"}
VALID_RISK_TIERS = {"none", "low", "medium", "high"}
VALID_SIDE_EFFECTS = {"none", "read_only", "writes_state", "external_side_effect"}
VALID_REVERSIBILITIES = {"reversible", "partially_reversible", "irreversible"}
VALID_EVIDENCE_TYPES = {"output_summary", "confirmation_record", "error_record", "audit_log_entry"}


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _error(code: str, message: str, field: str, **extra: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {"code": code, "message": message, "field": field}
    entry.update(extra)
    return entry


def _has_private_path(value: Any) -> bool:
    if isinstance(value, str):
        return bool(PRIVATE_PATH_RE.search(value))
    if isinstance(value, dict):
        return any(_has_private_path(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_private_path(v) for v in value)
    return False


def validate_proposal(data: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []

    # schema_version
    sv = data.get("schema_version")
    if not sv:
        errors.append(_error("missing_schema_version", "schema_version is required.", "schema_version"))
        return errors
    if sv != SCHEMA_VERSION_PATTERN:
        errors.append(_error("unknown_schema_version", f"Expected '{SCHEMA_VERSION_PATTERN}', got '{sv}'.", "schema_version"))
        return errors

    # type
    t = data.get("type")
    if t != ARTIFACT_TYPE:
        errors.append(_error("invalid_type", f"Expected '{ARTIFACT_TYPE}', got '{t}'.", "type"))

    # proposal_id
    pid = data.get("proposal_id", "")
    if not pid:
        errors.append(_error("missing_proposal_id", "proposal_id is required.", "proposal_id"))
    elif not PROPOSAL_ID_RE.match(pid):
        errors.append(_error("invalid_proposal_id_format", "proposal_id must match pattern tool_invocation_proposal:<name>.<suffix>.vN", "proposal_id"))

    # session_ref
    sr = data.get("session_ref", "")
    if not sr:
        errors.append(_error("missing_session_ref", "session_ref is required.", "session_ref"))

    # plan_step_ref
    psr = data.get("plan_step_ref", "")
    if not psr:
        errors.append(_error("missing_plan_step_ref", "plan_step_ref is required.", "plan_step_ref"))

    # tool
    tool = data.get("tool", {})
    logical_name = tool.get("logical_name", "")
    if not logical_name:
        errors.append(_error("missing_tool_logical_name", "tool.logical_name is required.", "tool.logical_name"))
    elif not TOOL_NAME_RE.match(logical_name):
        errors.append(_error("invalid_tool_logical_name_format", "tool.logical_name must match ^[a-z][a-z0-9_]*$", "tool.logical_name"))

    version = tool.get("version", "")
    if not version:
        errors.append(_error("missing_tool_version", "tool.version is required.", "tool.version"))
    elif not TOOL_VERSION_RE.match(version):
        errors.append(_error("invalid_tool_version_format", "tool.version must be semver.", "tool.version"))

    category = tool.get("category", "")
    if category not in VALID_TOOL_CATEGORIES:
        errors.append(_error("invalid_tool_category", f"tool.category must be one of {sorted(VALID_TOOL_CATEGORIES)}.", "tool.category"))

    # arguments
    args = data.get("arguments")
    if args is None or not isinstance(args, dict) or len(args) == 0:
        errors.append(_error("empty_arguments", "arguments must be a non-empty object.", "arguments"))
    elif isinstance(args, dict):
        for key, val in args.items():
            if isinstance(val, (dict, list)):
                errors.append(_error("nested_argument_value", f"Argument '{key}' has nested value of type {type(val).__name__}. Values must be flat.", f"arguments.{key}"))
            elif not isinstance(val, (str, int, float, bool)) and val is not None:
                errors.append(_error("invalid_argument_type", f"Argument '{key}' has invalid type {type(val).__name__}.", f"arguments.{key}"))

    # risk
    risk = data.get("risk", {})
    risk_tier = risk.get("risk_tier", "")
    if risk_tier not in VALID_RISK_TIERS:
        errors.append(_error("invalid_risk_tier", f"risk.risk_tier must be one of {sorted(VALID_RISK_TIERS)}.", "risk.risk_tier"))

    side_effects = risk.get("side_effects", "")
    if side_effects not in VALID_SIDE_EFFECTS:
        errors.append(_error("invalid_side_effects", f"risk.side_effects must be one of {sorted(VALID_SIDE_EFFECTS)}.", "risk.side_effects"))

    reversibility = risk.get("reversibility", "")
    if reversibility not in VALID_REVERSIBILITIES:
        errors.append(_error("invalid_reversibility", f"risk.reversibility must be one of {sorted(VALID_REVERSIBILITIES)}.", "risk.reversibility"))

    # approval
    approval = data.get("approval", {})
    requires_approval = approval.get("requires_human_approval")
    approval_reason = approval.get("approval_reason", "")

    if requires_approval is None:
        errors.append(_error("missing_requires_human_approval", "approval.requires_human_approval is required.", "approval.requires_human_approval"))
    elif requires_approval is False:
        if risk_tier and risk_tier != "none":
            errors.append(_error("approval_not_required_for_risky_tool", f"requires_human_approval must be true when risk_tier='{risk_tier}'.", "approval.requires_human_approval"))
        if side_effects and side_effects != "none" and side_effects != "read_only":
            errors.append(_error("approval_not_required_for_side_effects", f"requires_human_approval must be true when side_effects='{side_effects}'.", "approval.requires_human_approval"))

    if not approval_reason:
        errors.append(_error("missing_approval_reason", "approval.approval_reason is required.", "approval.approval_reason"))

    # expected_evidence
    evidence = data.get("expected_evidence")
    if not evidence or not isinstance(evidence, dict):
        errors.append(_error("missing_expected_evidence", "expected_evidence is required.", "expected_evidence"))
    else:
        et = evidence.get("evidence_type", "")
        if et not in VALID_EVIDENCE_TYPES:
            errors.append(_error("invalid_evidence_type", f"expected_evidence.evidence_type must be one of {sorted(VALID_EVIDENCE_TYPES)}.", "expected_evidence.evidence_type"))
        ed = evidence.get("description", "")
        if not ed:
            errors.append(_error("missing_evidence_description", "expected_evidence.description is required.", "expected_evidence.description"))

    # safety
    safety = data.get("safety", {})
    fae = safety.get("forbids_autonomous_execution")
    if fae is not True:
        errors.append(_error("autonomous_execution_allowed", "safety.forbids_autonomous_execution must be true.", "safety.forbids_autonomous_execution"))

    timeout = safety.get("timeout_seconds")
    if timeout is None or not isinstance(timeout, int) or timeout < 1 or timeout > 3600:
        errors.append(_error("timeout_out_of_range", "safety.timeout_seconds must be integer in 1..3600.", "safety.timeout_seconds"))

    retries = safety.get("max_retries")
    if retries is None or not isinstance(retries, int) or retries < 0 or retries > 3:
        errors.append(_error("max_retries_out_of_range", "safety.max_retries must be integer in 0..3.", "safety.max_retries"))

    # private path check
    if _has_private_path(data):
        errors.append(_error("private_path_detected", "Absolute private path detected in artifact.", "artifact"))

    return errors


def validate_file(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return {
            "source": str(path),
            "artifact_type": ARTIFACT_TYPE,
            "status": "failed",
            "errors": [_error("invalid_json", f"JSON parse error: {exc}", "file")],
        }

    if not isinstance(data, dict):
        return {
            "source": str(path),
            "artifact_type": ARTIFACT_TYPE,
            "status": "failed",
            "errors": [_error("invalid_json", "Top-level value must be a JSON object.", "file")],
        }

    errors = validate_proposal(data)
    status = "passed" if not errors else "failed"

    return {
        "source": str(path),
        "artifact_type": ARTIFACT_TYPE,
        "status": status,
        "errors": errors,
    }


def validate_path(target: Path) -> dict[str, Any]:
    if target.is_dir():
        files = sorted(target.glob("*.json"))
    else:
        files = [target]

    results = [validate_file(f) for f in files]
    passed = sum(1 for r in results if r["status"] == "passed")
    failed = sum(1 for r in results if r["status"] == "failed")

    report: dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "status": "passed" if failed == 0 else "failed",
        "total_artifacts": len(results),
        "passed_count": passed,
        "failed_count": failed,
        "results": results,
    }

    canonical = _canonical_json(report)
    report["report_fingerprint"] = f"sha256:{_sha256_text(canonical)}"
    return report


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <file_or_dir>", file=sys.stderr)
        sys.exit(2)

    target = Path(sys.argv[1])
    if not target.exists():
        print(f"Error: {target} not found.", file=sys.stderr)
        sys.exit(2)

    report = validate_path(target)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
