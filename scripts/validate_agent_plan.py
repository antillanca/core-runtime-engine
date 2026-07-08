#!/usr/bin/env python3
"""Validate CORE agent plan artifacts.

Accepts a single JSON file or a directory of JSON files.
Validates all four artifact types based on schema_version dispatch.

Rejection codes
---------------
Structural:
 missing_schema_version   schema_version is missing or empty
 unknown_schema_version   schema_version not recognized
 invalid_json             file is not valid JSON

Agent plan:
 invalid_type                        type is not agent_plan
 missing_plan_id                     plan_id is missing or empty
 invalid_plan_id_format              plan_id does not match pattern
 missing_session_ref                 session_ref is missing or empty
 empty_steps                         steps list is empty
 max_steps_exceeded                  len(steps) > safety.max_steps
 plan_approval_not_required          requires_step_approval is false
 plan_parallel_execution_with_side_effects  parallel allowed with side-effect steps
 circular_dependency                 dependency graph has a cycle
 invalid_depends_on                  depends_on references non-existent step_index
 step_index_out_of_range             step_index >= len(steps)
 duplicate_step_index                two steps share the same step_index
 missing_step_intent                 step intent is empty
 step_approval_not_required          step with tool_proposal_ref has requires_human_approval=false
 step_autonomous_execution_allowed   step forbids_autonomous_execution=false
 invalid_risk_tier                   risk_tier not in allowed enum
 invalid_expected_result_type        result_type not in allowed enum
 missing_expected_result             step lacks expected_result
 private_path_detected               field contains absolute private path

Agent plan step:
 invalid_step_type          type is not agent_plan_step
 missing_step_id            step_id is missing or empty
 invalid_step_id_format     step_id does not match pattern
 missing_plan_ref           plan_ref is missing or empty

Agent plan dependency:
 invalid_dep_type           type is not agent_plan_dependency
 missing_dependency_id      dependency_id is missing or empty
 invalid_dependency_id_format dependency_id does not match pattern
 self_dependency            from_step == to_step
 invalid_dependency_type    dependency_type not in allowed enum

Agent plan result:
 invalid_result_type        type is not agent_plan_result
 missing_result_id          result_id is missing or empty
 invalid_result_id_format   result_id does not match pattern
 empty_step_results         step_results list is empty
 invalid_overall_status     overall_status not in allowed enum
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

VALID_FP_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
PLAN_ID_RE = re.compile(r"^agent_plan:[a-z0-9_]+\.[a-z0-9_]+\.v1$")
STEP_ID_RE = re.compile(r"^agent_plan_step:[a-z0-9_]+\.[a-z0-9_]+\.v1$")
DEP_ID_RE = re.compile(r"^agent_plan_dependency:[a-z0-9_]+\.[a-z0-9_]+\.[a-z0-9_]+\.v1$")
RESULT_ID_RE = re.compile(r"^agent_plan_result:[a-z0-9_]+\.[a-z0-9_]+\.v1$")

PRIVATE_PATH_RE = re.compile(r"(?:/home/|/etc/|/var/|/root/|/Users/|C:\\\\|D:\\\\)")

# --- Rejection codes ---------------------------------------------------

MISSING_SCHEMA_VERSION = "missing_schema_version"
UNKNOWN_SCHEMA_VERSION = "unknown_schema_version"
INVALID_JSON = "invalid_json"
INVALID_TYPE = "invalid_type"
MISSING_PLAN_ID = "missing_plan_id"
INVALID_PLAN_ID_FORMAT = "invalid_plan_id_format"
MISSING_SESSION_REF = "missing_session_ref"
EMPTY_STEPS = "empty_steps"
MAX_STEPS_EXCEEDED = "max_steps_exceeded"
PLAN_APPROVAL_NOT_REQUIRED = "plan_approval_not_required"
PLAN_PARALLEL_WITH_SIDE_EFFECTS = "plan_parallel_execution_with_side_effects"
CIRCULAR_DEPENDENCY = "circular_dependency"
INVALID_DEPENDS_ON = "invalid_depends_on"
STEP_INDEX_OUT_OF_RANGE = "step_index_out_of_range"
DUPLICATE_STEP_INDEX = "duplicate_step_index"
MISSING_STEP_INTENT = "missing_step_intent"
STEP_APPROVAL_NOT_REQUIRED = "step_approval_not_required"
STEP_AUTONOMOUS_ALLOWED = "step_autonomous_execution_allowed"
INVALID_RISK_TIER = "invalid_risk_tier"
INVALID_RESULT_TYPE = "invalid_expected_result_type"
MISSING_EXPECTED_RESULT = "missing_expected_result"
PRIVATE_PATH_DETECTED = "private_path_detected"
INVALID_STEP_TYPE = "invalid_step_type"
MISSING_STEP_ID = "missing_step_id"
INVALID_STEP_ID_FORMAT = "invalid_step_id_format"
MISSING_PLAN_REF = "missing_plan_ref"
INVALID_DEP_TYPE = "invalid_dep_type"
MISSING_DEP_ID = "missing_dependency_id"
INVALID_DEP_ID_FORMAT = "invalid_dependency_id_format"
SELF_DEPENDENCY = "self_dependency"
INVALID_DEP_TYPE_VAL = "invalid_dependency_type"
INVALID_RESULT_TYPE_ARTIFACT = "invalid_result_type"
MISSING_RESULT_ID = "missing_result_id"
INVALID_RESULT_ID_FORMAT = "invalid_result_id_format"
EMPTY_STEP_RESULTS = "empty_step_results"
INVALID_OVERALL_STATUS = "invalid_overall_status"

# --- Valid values ------------------------------------------------------

VALID_RISK_TIERS = {"none", "low", "medium", "high"}
VALID_RESULT_TYPES = {"proposal_only", "read_result", "approval_record", "escalation_record"}
VALID_STEP_STATUSES = {"planned", "approved", "rejected", "skipped", "completed"}
VALID_DEP_TYPES = {"sequential", "data_flow", "approval_required"}
VALID_OVERALL_STATUSES = {"completed", "partial", "rejected", "escalated"}

# Side-effect steps: those with tool_proposal_ref or risk_tier > none
SIDE_EFFECT_RISK_TIERS = {"low", "medium", "high"}

# --- Schema dispatch ---------------------------------------------------

DISPATCH = {
    "core.agent_plan.v1": "validate_agent_plan",
    "core.agent_plan_step.v1": "validate_agent_plan_step",
    "core.agent_plan_dependency.v1": "validate_agent_plan_dependency",
    "core.agent_plan_result.v1": "validate_agent_plan_result",
}


# --- Helpers -----------------------------------------------------------

def _check_private_paths(obj: Any, path: str, errors: list[dict]) -> None:
    if isinstance(obj, str):
        if PRIVATE_PATH_RE.search(obj):
            errors.append({
                "code": PRIVATE_PATH_DETECTED,
                "message": f"Absolute private path found in {path}",
                "field": path,
            })
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _check_private_paths(v, f"{path}.{k}", errors)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _check_private_paths(v, f"{path}[{i}]", errors)


def _topological_sort(steps: list[dict]) -> bool:
    """Return True if the dependency graph is a DAG (no cycles)."""
    n = len(steps)
    adj: dict[int, list[int]] = {i: [] for i in range(n)}
    in_degree: dict[int, int] = {i: 0 for i in range(n)}
    for step in steps:
        si = step["step_index"]
        for dep in step.get("depends_on", []):
            if 0 <= dep < n and dep != si:
                adj[dep].append(si)
                in_degree[si] += 1
    queue = [i for i in range(n) if in_degree[i] == 0]
    visited = 0
    while queue:
        node = queue.pop(0)
        visited += 1
        for nb in adj[node]:
            in_degree[nb] -= 1
            if in_degree[nb] == 0:
                queue.append(nb)
    return visited == n


# --- Validators --------------------------------------------------------

def validate_agent_plan(artifact: dict) -> list[dict]:
    errors: list[dict] = []

    # Type check
    if artifact.get("type") != "agent_plan":
        errors.append({"code": INVALID_TYPE, "message": "type is not agent_plan", "field": "type"})

    # plan_id
    pid = artifact.get("plan_id", "")
    if not pid:
        errors.append({"code": MISSING_PLAN_ID, "message": "plan_id is missing or empty", "field": "plan_id"})
    elif not PLAN_ID_RE.match(pid):
        errors.append({"code": INVALID_PLAN_ID_FORMAT, "message": "plan_id does not match pattern", "field": "plan_id"})

    # session_ref
    sref = artifact.get("session_ref", "")
    if not sref:
        errors.append({"code": MISSING_SESSION_REF, "message": "session_ref is missing or empty", "field": "session_ref"})

    # steps
    steps = artifact.get("steps", [])
    if not steps:
        errors.append({"code": EMPTY_STEPS, "message": "steps list is empty", "field": "steps"})
        return errors  # nothing more to check

    safety = artifact.get("safety", {})
    max_steps = safety.get("max_steps", 64)

    if len(steps) > max_steps:
        errors.append({"code": MAX_STEPS_EXCEEDED, "message": f"len(steps)={len(steps)} > max_steps={max_steps}", "field": "steps"})

    # Plan safety
    if not safety.get("requires_step_approval", False):
        errors.append({"code": PLAN_APPROVAL_NOT_REQUIRED, "message": "requires_step_approval is false", "field": "safety.requires_step_approval"})

    # Check parallel execution with side effects
    if not safety.get("forbids_parallel_execution", True):
        has_side_effects = any(
            s.get("tool_proposal_ref") is not None
            or s.get("safety", {}).get("risk_tier") in SIDE_EFFECT_RISK_TIERS
            for s in steps
        )
        if has_side_effects:
            errors.append({
                "code": PLAN_PARALLEL_WITH_SIDE_EFFECTS,
                "message": "Parallel execution allowed with side-effect steps",
                "field": "safety.forbids_parallel_execution",
            })

    # Step indices
    indices = [s.get("step_index", -1) for s in steps]
    n = len(steps)

    # Contiguity check
    expected = list(range(n))
    if sorted(indices) != expected:
        # Check for duplicates
        seen = set()
        for idx in indices:
            if idx in seen:
                errors.append({"code": DUPLICATE_STEP_INDEX, "message": f"Duplicate step_index {idx}", "field": "steps"})
            seen.add(idx)

    # Per-step validation
    step_index_set = set(indices)
    for step in steps:
        si = step.get("step_index", -1)
        if si < 0 or si >= n:
            errors.append({"code": STEP_INDEX_OUT_OF_RANGE, "message": f"step_index {si} out of range [0,{n-1}]", "field": f"steps[{si}].step_index"})

        # Intent
        if not step.get("intent", ""):
            errors.append({"code": MISSING_STEP_INTENT, "message": f"Step {si} intent is empty", "field": f"steps[{si}].intent"})

        # Safety
        step_safety = step.get("safety", {})
        if step.get("tool_proposal_ref") is not None and not step_safety.get("requires_human_approval", False):
            errors.append({
                "code": STEP_APPROVAL_NOT_REQUIRED,
                "message": f"Step {si} has tool_proposal_ref but requires_human_approval=false",
                "field": f"steps[{si}].safety.requires_human_approval",
            })
        if not step_safety.get("forbids_autonomous_execution", False):
            errors.append({
                "code": STEP_AUTONOMOUS_ALLOWED,
                "message": f"Step {si} forbids_autonomous_execution=false",
                "field": f"steps[{si}].safety.forbids_autonomous_execution",
            })

        risk = step_safety.get("risk_tier", "")
        if risk and risk not in VALID_RISK_TIERS:
            errors.append({"code": INVALID_RISK_TIER, "message": f"Invalid risk_tier '{risk}'", "field": f"steps[{si}].safety.risk_tier"})

        # Expected result
        er = step.get("expected_result", {})
        if not er:
            errors.append({"code": MISSING_EXPECTED_RESULT, "message": f"Step {si} lacks expected_result", "field": f"steps[{si}].expected_result"})
        elif er.get("result_type", "") not in VALID_RESULT_TYPES:
            errors.append({
                "code": INVALID_RESULT_TYPE,
                "message": f"Invalid result_type '{er.get('result_type', '')}'",
                "field": f"steps[{si}].expected_result.result_type",
            })

        # depends_on references
        for dep in step.get("depends_on", []):
            if dep not in step_index_set:
                errors.append({
                    "code": INVALID_DEPENDS_ON,
                    "message": f"Step {si} depends_on {dep} not in step indices",
                    "field": f"steps[{si}].depends_on",
                })

    # Circular dependency check
    if not _topological_sort(steps):
        errors.append({"code": CIRCULAR_DEPENDENCY, "message": "Dependency graph has a cycle", "field": "steps"})

    # Private path scan
    _check_private_paths(artifact, "$", errors)

    return errors


def validate_agent_plan_step(artifact: dict) -> list[dict]:
    errors: list[dict] = []

    if artifact.get("type") != "agent_plan_step":
        errors.append({"code": INVALID_STEP_TYPE, "message": "type is not agent_plan_step", "field": "type"})

    sid = artifact.get("step_id", "")
    if not sid:
        errors.append({"code": MISSING_STEP_ID, "message": "step_id is missing or empty", "field": "step_id"})
    elif not STEP_ID_RE.match(sid):
        errors.append({"code": INVALID_STEP_ID_FORMAT, "message": "step_id does not match pattern", "field": "step_id"})

    pref = artifact.get("plan_ref", "")
    if not pref:
        errors.append({"code": MISSING_PLAN_REF, "message": "plan_ref is missing or empty", "field": "plan_ref"})

    # Safety invariants
    safety = artifact.get("safety", {})
    if artifact.get("tool_proposal_ref") is not None and not safety.get("requires_human_approval", False):
        errors.append({"code": STEP_APPROVAL_NOT_REQUIRED, "message": "Step with tool_proposal_ref requires approval", "field": "safety.requires_human_approval"})
    if not safety.get("forbids_autonomous_execution", False):
        errors.append({"code": STEP_AUTONOMOUS_ALLOWED, "message": "forbids_autonomous_execution is false", "field": "safety.forbids_autonomous_execution"})

    risk = safety.get("risk_tier", "")
    if risk and risk not in VALID_RISK_TIERS:
        errors.append({"code": INVALID_RISK_TIER, "message": f"Invalid risk_tier '{risk}'", "field": "safety.risk_tier"})

    # Expected result
    er = artifact.get("expected_result", {})
    if not er:
        errors.append({"code": MISSING_EXPECTED_RESULT, "message": "Missing expected_result", "field": "expected_result"})
    elif er.get("result_type", "") not in VALID_RESULT_TYPES:
        errors.append({"code": INVALID_RESULT_TYPE, "message": f"Invalid result_type '{er.get('result_type', '')}'", "field": "expected_result.result_type"})

    _check_private_paths(artifact, "$", errors)
    return errors


def validate_agent_plan_dependency(artifact: dict) -> list[dict]:
    errors: list[dict] = []

    if artifact.get("type") != "agent_plan_dependency":
        errors.append({"code": INVALID_DEP_TYPE, "message": "type is not agent_plan_dependency", "field": "type"})

    did = artifact.get("dependency_id", "")
    if not did:
        errors.append({"code": MISSING_DEP_ID, "message": "dependency_id is missing or empty", "field": "dependency_id"})
    elif not DEP_ID_RE.match(did):
        errors.append({"code": INVALID_DEP_ID_FORMAT, "message": "dependency_id does not match pattern", "field": "dependency_id"})

    pref = artifact.get("plan_ref", "")
    if not pref:
        errors.append({"code": MISSING_PLAN_REF, "message": "plan_ref is missing or empty", "field": "plan_ref"})

    fs = artifact.get("from_step", -1)
    ts = artifact.get("to_step", -1)
    if fs == ts:
        errors.append({"code": SELF_DEPENDENCY, "message": f"from_step == to_step == {fs}", "field": "from_step/to_step"})

    dt = artifact.get("dependency_type", "")
    if dt and dt not in VALID_DEP_TYPES:
        errors.append({"code": INVALID_DEP_TYPE_VAL, "message": f"Invalid dependency_type '{dt}'", "field": "dependency_type"})

    _check_private_paths(artifact, "$", errors)
    return errors


def validate_agent_plan_result(artifact: dict) -> list[dict]:
    errors: list[dict] = []

    if artifact.get("type") != "agent_plan_result":
        errors.append({"code": INVALID_RESULT_TYPE_ARTIFACT, "message": "type is not agent_plan_result", "field": "type"})

    rid = artifact.get("result_id", "")
    if not rid:
        errors.append({"code": MISSING_RESULT_ID, "message": "result_id is missing or empty", "field": "result_id"})
    elif not RESULT_ID_RE.match(rid):
        errors.append({"code": INVALID_RESULT_ID_FORMAT, "message": "result_id does not match pattern", "field": "result_id"})

    pref = artifact.get("plan_ref", "")
    if not pref:
        errors.append({"code": MISSING_PLAN_REF, "message": "plan_ref is missing or empty", "field": "plan_ref"})

    sref = artifact.get("session_ref", "")
    if not sref:
        errors.append({"code": MISSING_SESSION_REF, "message": "session_ref is missing or empty", "field": "session_ref"})

    os = artifact.get("overall_status", "")
    if os and os not in VALID_OVERALL_STATUSES:
        errors.append({"code": INVALID_OVERALL_STATUS, "message": f"Invalid overall_status '{os}'", "field": "overall_status"})

    sr = artifact.get("step_results", [])
    if not sr:
        errors.append({"code": EMPTY_STEP_RESULTS, "message": "step_results list is empty", "field": "step_results"})

    for i, entry in enumerate(sr):
        fp = entry.get("outcome_fingerprint", "")
        if fp and not VALID_FP_RE.match(fp):
            errors.append({"code": "invalid_outcome_fingerprint", "message": f"Step result {i} has invalid fingerprint", "field": f"step_results[{i}].outcome_fingerprint"})

    for fp_field in ("plan_fingerprint", "validation_fingerprint"):
        fp = artifact.get(fp_field, "")
        if fp and not VALID_FP_RE.match(fp):
            errors.append({"code": "invalid_fingerprint", "message": f"{fp_field} is not a valid sha256 fingerprint", "field": fp_field})

    _check_private_paths(artifact, "$", errors)
    return errors


# --- Main dispatch -----------------------------------------------------

def validate_single(artifact: dict) -> list[dict]:
    sv = artifact.get("schema_version", "")
    if not sv:
        return [{"code": MISSING_SCHEMA_VERSION, "message": "schema_version is missing or empty", "field": "schema_version"}]
    handler = DISPATCH.get(sv)
    if handler is None:
        return [{"code": UNKNOWN_SCHEMA_VERSION, "message": f"Unknown schema_version '{sv}'", "field": "schema_version"}]
    fn = globals()[handler]
    return fn(artifact)


def validate_file(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
        artifact = json.loads(text)
    except json.JSONDecodeError as exc:
        return {"source": str(path), "status": "failed", "errors": [{"code": INVALID_JSON, "message": str(exc), "field": ""}]}
    if not isinstance(artifact, dict):
        return {"source": str(path), "status": "failed", "errors": [{"code": INVALID_JSON, "message": "Root is not a JSON object", "field": ""}]}

    errors = validate_single(artifact)
    atype = artifact.get("type", "unknown")
    status = "passed" if not errors else "failed"

    return {"source": str(path), "status": status, "artifact_type": atype, "errors": errors}


def validate_directory(dir_path: Path) -> dict:
    results = []
    for p in sorted(dir_path.glob("*.json")):
        results.append(validate_file(p))
    passed = sum(1 for r in results if r["status"] == "passed")
    failed = sum(1 for r in results if r["status"] == "failed")
    report = {
        "total_artifacts": len(results),
        "passed_count": passed,
        "failed_count": failed,
        "results": results,
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_fingerprint"] = f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"
    report["status"] = "passed" if failed == 0 else "failed"
    return report


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: validate_agent_plan.py <file_or_dir>", file=sys.stderr)
        sys.exit(2)

    target = Path(sys.argv[1])
    if target.is_dir():
        report = validate_directory(target)
    else:
        r = validate_file(target)
        report = r
        report["report_fingerprint"] = "sha256:" + hashlib.sha256(
            json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        report["status"] = r["status"]

    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    print()


if __name__ == "__main__":
    main()
