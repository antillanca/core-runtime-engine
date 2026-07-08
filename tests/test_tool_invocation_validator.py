#!/usr/bin/env python3
"""Tests for validate_tool_invocation.py — CORE v8.2 Tool Invocation Proposal."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path("scripts/validate_tool_invocation.py")
FIXTURE_DIR = Path("examples/tool_invocations")

ACCEPTED = [
    "accepted_read_tool.json",
    "accepted_notification_tool.json",
]

REJECTED = [
    "rejected_autonomous_write.json",
    "rejected_risky_no_approval.json",
    "rejected_nested_arguments.json",
    "rejected_private_path.json",
    "rejected_invalid_safety.json",
]


def _run(target: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), target],
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _validate(data: dict) -> list:
    """Import and call the validator directly."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("validator", str(SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.validate_proposal(data)


# ── Structural tests ──────────────────────────────────────────────

def test_missing_schema_version():
    errors = _validate({})
    codes = [e["code"] for e in errors]
    assert "missing_schema_version" in codes


def test_unknown_schema_version():
    errors = _validate({"schema_version": "core.tool_invocation_proposal.v99"})
    codes = [e["code"] for e in errors]
    assert "unknown_schema_version" in codes


def test_invalid_type():
    errors = _validate({"schema_version": "core.tool_invocation_proposal.v1", "type": "wrong"})
    codes = [e["code"] for e in errors]
    assert "invalid_type" in codes


# ── Proposal ID tests ─────────────────────────────────────────────

def test_missing_proposal_id():
    errors = _validate({"schema_version": "core.tool_invocation_proposal.v1"})
    codes = [e["code"] for e in errors]
    assert "missing_proposal_id" in codes


def test_invalid_proposal_id_format():
    errors = _validate({"schema_version": "core.tool_invocation_proposal.v1", "proposal_id": "bad-id"})
    codes = [e["code"] for e in errors]
    assert "invalid_proposal_id_format" in codes


# ── Reference tests ───────────────────────────────────────────────

def test_missing_session_ref():
    errors = _validate({"schema_version": "core.tool_invocation_proposal.v1", "proposal_id": "tool_invocation_proposal:x.y.v1"})
    codes = [e["code"] for e in errors]
    assert "missing_session_ref" in codes


def test_missing_plan_step_ref():
    errors = _validate({"schema_version": "core.tool_invocation_proposal.v1", "proposal_id": "tool_invocation_proposal:x.y.v1", "session_ref": "s"})
    codes = [e["code"] for e in errors]
    assert "missing_plan_step_ref" in codes


# ── Tool tests ────────────────────────────────────────────────────

def test_missing_tool_logical_name():
    base = {"schema_version": "core.tool_invocation_proposal.v1", "proposal_id": "tool_invocation_proposal:x.y.v1", "session_ref": "s", "plan_step_ref": "p"}
    errors = _validate({**base, "tool": {"version": "1.0.0", "category": "read_only"}})
    codes = [e["code"] for e in errors]
    assert "missing_tool_logical_name" in codes


def test_invalid_tool_logical_name_format():
    base = {"schema_version": "core.tool_invocation_proposal.v1", "proposal_id": "tool_invocation_proposal:x.y.v1", "session_ref": "s", "plan_step_ref": "p"}
    errors = _validate({**base, "tool": {"logical_name": "Bad-Name", "version": "1.0.0", "category": "read_only"}})
    codes = [e["code"] for e in errors]
    assert "invalid_tool_logical_name_format" in codes


def test_invalid_tool_version_format():
    base = {"schema_version": "core.tool_invocation_proposal.v1", "proposal_id": "tool_invocation_proposal:x.y.v1", "session_ref": "s", "plan_step_ref": "p"}
    errors = _validate({**base, "tool": {"logical_name": "reader", "version": "v1", "category": "read_only"}})
    codes = [e["code"] for e in errors]
    assert "invalid_tool_version_format" in codes


def test_invalid_tool_category():
    base = {"schema_version": "core.tool_invocation_proposal.v1", "proposal_id": "tool_invocation_proposal:x.y.v1", "session_ref": "s", "plan_step_ref": "p"}
    errors = _validate({**base, "tool": {"logical_name": "reader", "version": "1.0.0", "category": "dangerous"}})
    codes = [e["code"] for e in errors]
    assert "invalid_tool_category" in codes


# ── Arguments tests ───────────────────────────────────────────────

def test_empty_arguments():
    base = {"schema_version": "core.tool_invocation_proposal.v1", "proposal_id": "tool_invocation_proposal:x.y.v1", "session_ref": "s", "plan_step_ref": "p"}
    errors = _validate({**base, "arguments": {}})
    codes = [e["code"] for e in errors]
    assert "empty_arguments" in codes


def test_nested_argument_value():
    base = {"schema_version": "core.tool_invocation_proposal.v1", "proposal_id": "tool_invocation_proposal:x.y.v1", "session_ref": "s", "plan_step_ref": "p"}
    errors = _validate({**base, "arguments": {"config": {"nested": True}}})
    codes = [e["code"] for e in errors]
    assert "nested_argument_value" in codes


def test_array_argument_value():
    base = {"schema_version": "core.tool_invocation_proposal.v1", "proposal_id": "tool_invocation_proposal:x.y.v1", "session_ref": "s", "plan_step_ref": "p"}
    errors = _validate({**base, "arguments": {"items": [1, 2, 3]}})
    codes = [e["code"] for e in errors]
    assert "nested_argument_value" in codes


# ── Risk tests ────────────────────────────────────────────────────

def test_invalid_risk_tier():
    base = {"schema_version": "core.tool_invocation_proposal.v1", "proposal_id": "tool_invocation_proposal:x.y.v1", "session_ref": "s", "plan_step_ref": "p"}
    errors = _validate({**base, "risk": {"risk_tier": "extreme", "side_effects": "none", "reversibility": "reversible"}})
    codes = [e["code"] for e in errors]
    assert "invalid_risk_tier" in codes


def test_invalid_side_effects():
    base = {"schema_version": "core.tool_invocation_proposal.v1", "proposal_id": "tool_invocation_proposal:x.y.v1", "session_ref": "s", "plan_step_ref": "p"}
    errors = _validate({**base, "risk": {"risk_tier": "none", "side_effects": "destroys", "reversibility": "reversible"}})
    codes = [e["code"] for e in errors]
    assert "invalid_side_effects" in codes


def test_invalid_reversibility():
    base = {"schema_version": "core.tool_invocation_proposal.v1", "proposal_id": "tool_invocation_proposal:x.y.v1", "session_ref": "s", "plan_step_ref": "p"}
    errors = _validate({**base, "risk": {"risk_tier": "none", "side_effects": "none", "reversibility": "magical"}})
    codes = [e["code"] for e in errors]
    assert "invalid_reversibility" in codes


# ── Approval tests ────────────────────────────────────────────────

def test_approval_not_required_for_risky_tool():
    data = {
        "schema_version": "core.tool_invocation_proposal.v1",
        "type": "tool_invocation_proposal",
        "proposal_id": "tool_invocation_proposal:x.y.v1",
        "session_ref": "s",
        "plan_step_ref": "p",
        "tool": {"logical_name": "t", "version": "1.0.0", "category": "write"},
        "arguments": {"k": "v"},
        "risk": {"risk_tier": "high", "side_effects": "none", "reversibility": "reversible"},
        "approval": {"requires_human_approval": False, "approval_reason": "no"},
        "expected_evidence": {"evidence_type": "output_summary", "description": "x"},
        "safety": {"forbids_autonomous_execution": True, "timeout_seconds": 10, "max_retries": 0},
    }
    errors = _validate(data)
    codes = [e["code"] for e in errors]
    assert "approval_not_required_for_risky_tool" in codes


def test_approval_not_required_for_side_effects():
    data = {
        "schema_version": "core.tool_invocation_proposal.v1",
        "type": "tool_invocation_proposal",
        "proposal_id": "tool_invocation_proposal:x.y.v1",
        "session_ref": "s",
        "plan_step_ref": "p",
        "tool": {"logical_name": "t", "version": "1.0.0", "category": "external_call"},
        "arguments": {"k": "v"},
        "risk": {"risk_tier": "none", "side_effects": "external_side_effect", "reversibility": "irreversible"},
        "approval": {"requires_human_approval": False, "approval_reason": "no"},
        "expected_evidence": {"evidence_type": "output_summary", "description": "x"},
        "safety": {"forbids_autonomous_execution": True, "timeout_seconds": 10, "max_retries": 0},
    }
    errors = _validate(data)
    codes = [e["code"] for e in errors]
    assert "approval_not_required_for_side_effects" in codes


def test_autonomous_execution_allowed():
    data = {
        "schema_version": "core.tool_invocation_proposal.v1",
        "type": "tool_invocation_proposal",
        "proposal_id": "tool_invocation_proposal:x.y.v1",
        "session_ref": "s",
        "plan_step_ref": "p",
        "tool": {"logical_name": "t", "version": "1.0.0", "category": "read_only"},
        "arguments": {"k": "v"},
        "risk": {"risk_tier": "none", "side_effects": "none", "reversibility": "reversible"},
        "approval": {"requires_human_approval": True, "approval_reason": "policy"},
        "expected_evidence": {"evidence_type": "output_summary", "description": "x"},
        "safety": {"forbids_autonomous_execution": False, "timeout_seconds": 10, "max_retries": 0},
    }
    errors = _validate(data)
    codes = [e["code"] for e in errors]
    assert "autonomous_execution_allowed" in codes


def test_missing_approval_reason():
    data = {
        "schema_version": "core.tool_invocation_proposal.v1",
        "type": "tool_invocation_proposal",
        "proposal_id": "tool_invocation_proposal:x.y.v1",
        "session_ref": "s",
        "plan_step_ref": "p",
        "tool": {"logical_name": "t", "version": "1.0.0", "category": "read_only"},
        "arguments": {"k": "v"},
        "risk": {"risk_tier": "none", "side_effects": "none", "reversibility": "reversible"},
        "approval": {"requires_human_approval": True, "approval_reason": ""},
        "expected_evidence": {"evidence_type": "output_summary", "description": "x"},
        "safety": {"forbids_autonomous_execution": True, "timeout_seconds": 10, "max_retries": 0},
    }
    errors = _validate(data)
    codes = [e["code"] for e in errors]
    assert "missing_approval_reason" in codes


# ── Evidence tests ────────────────────────────────────────────────

def test_invalid_evidence_type():
    data = {
        "schema_version": "core.tool_invocation_proposal.v1",
        "type": "tool_invocation_proposal",
        "proposal_id": "tool_invocation_proposal:x.y.v1",
        "session_ref": "s",
        "plan_step_ref": "p",
        "tool": {"logical_name": "t", "version": "1.0.0", "category": "read_only"},
        "arguments": {"k": "v"},
        "risk": {"risk_tier": "none", "side_effects": "none", "reversibility": "reversible"},
        "approval": {"requires_human_approval": True, "approval_reason": "ok"},
        "expected_evidence": {"evidence_type": "screenshot", "description": "x"},
        "safety": {"forbids_autonomous_execution": True, "timeout_seconds": 10, "max_retries": 0},
    }
    errors = _validate(data)
    codes = [e["code"] for e in errors]
    assert "invalid_evidence_type" in codes


def test_missing_evidence_description():
    data = {
        "schema_version": "core.tool_invocation_proposal.v1",
        "type": "tool_invocation_proposal",
        "proposal_id": "tool_invocation_proposal:x.y.v1",
        "session_ref": "s",
        "plan_step_ref": "p",
        "tool": {"logical_name": "t", "version": "1.0.0", "category": "read_only"},
        "arguments": {"k": "v"},
        "risk": {"risk_tier": "none", "side_effects": "none", "reversibility": "reversible"},
        "approval": {"requires_human_approval": True, "approval_reason": "ok"},
        "expected_evidence": {"evidence_type": "output_summary", "description": ""},
        "safety": {"forbids_autonomous_execution": True, "timeout_seconds": 10, "max_retries": 0},
    }
    errors = _validate(data)
    codes = [e["code"] for e in errors]
    assert "missing_evidence_description" in codes


# ── Safety tests ──────────────────────────────────────────────────

def test_timeout_out_of_range():
    data = {
        "schema_version": "core.tool_invocation_proposal.v1",
        "type": "tool_invocation_proposal",
        "proposal_id": "tool_invocation_proposal:x.y.v1",
        "session_ref": "s",
        "plan_step_ref": "p",
        "tool": {"logical_name": "t", "version": "1.0.0", "category": "read_only"},
        "arguments": {"k": "v"},
        "risk": {"risk_tier": "none", "side_effects": "none", "reversibility": "reversible"},
        "approval": {"requires_human_approval": True, "approval_reason": "ok"},
        "expected_evidence": {"evidence_type": "output_summary", "description": "x"},
        "safety": {"forbids_autonomous_execution": True, "timeout_seconds": 0, "max_retries": 0},
    }
    errors = _validate(data)
    codes = [e["code"] for e in errors]
    assert "timeout_out_of_range" in codes


def test_max_retries_out_of_range():
    data = {
        "schema_version": "core.tool_invocation_proposal.v1",
        "type": "tool_invocation_proposal",
        "proposal_id": "tool_invocation_proposal:x.y.v1",
        "session_ref": "s",
        "plan_step_ref": "p",
        "tool": {"logical_name": "t", "version": "1.0.0", "category": "read_only"},
        "arguments": {"k": "v"},
        "risk": {"risk_tier": "none", "side_effects": "none", "reversibility": "reversible"},
        "approval": {"requires_human_approval": True, "approval_reason": "ok"},
        "expected_evidence": {"evidence_type": "output_summary", "description": "x"},
        "safety": {"forbids_autonomous_execution": True, "timeout_seconds": 10, "max_retries": 5},
    }
    errors = _validate(data)
    codes = [e["code"] for e in errors]
    assert "max_retries_out_of_range" in codes


# ── Private path tests ────────────────────────────────────────────

def test_private_path_in_arguments():
    data = {
        "schema_version": "core.tool_invocation_proposal.v1",
        "type": "tool_invocation_proposal",
        "proposal_id": "tool_invocation_proposal:x.y.v1",
        "session_ref": "s",
        "plan_step_ref": "p",
        "tool": {"logical_name": "t", "version": "1.0.0", "category": "read_only"},
        "arguments": {"path": "/etc/secret/config.yaml"},
        "risk": {"risk_tier": "none", "side_effects": "none", "reversibility": "reversible"},
        "approval": {"requires_human_approval": True, "approval_reason": "ok"},
        "expected_evidence": {"evidence_type": "output_summary", "description": "x"},
        "safety": {"forbids_autonomous_execution": True, "timeout_seconds": 10, "max_retries": 0},
    }
    errors = _validate(data)
    codes = [e["code"] for e in errors]
    assert "private_path_detected" in codes


# ── Fixture validation ────────────────────────────────────────────

def test_accepted_fixtures_pass():
    for name in ACCEPTED:
        report = _run(str(FIXTURE_DIR / name))
        assert report["status"] == "passed", f"{name} should pass: {report['results'][0]['errors']}"


def test_rejected_fixtures_fail():
    for name in REJECTED:
        report = _run(str(FIXTURE_DIR / name))
        assert report["status"] == "failed", f"{name} should fail"


# ── Byte-stability ────────────────────────────────────────────────

def test_accepted_read_tool_deterministic():
    r1 = _run(str(FIXTURE_DIR / "accepted_read_tool.json"))
    r2 = _run(str(FIXTURE_DIR / "accepted_read_tool.json"))
    assert r1["report_fingerprint"] == r2["report_fingerprint"]


def test_rejected_autonomous_write_deterministic():
    r1 = _run(str(FIXTURE_DIR / "rejected_autonomous_write.json"))
    r2 = _run(str(FIXTURE_DIR / "rejected_autonomous_write.json"))
    assert r1["report_fingerprint"] == r2["report_fingerprint"]


# ── Full directory scan ───────────────────────────────────────────

def test_directory_validation():
    report = _run(str(FIXTURE_DIR))
    assert report["total_artifacts"] == len(ACCEPTED) + len(REJECTED)
    assert report["passed_count"] == len(ACCEPTED)
    assert report["failed_count"] == len(REJECTED)


# ── Valid proposal construction ───────────────────────────────────

def test_valid_proposal_no_errors():
    data = {
        "schema_version": "core.tool_invocation_proposal.v1",
        "type": "tool_invocation_proposal",
        "proposal_id": "tool_invocation_proposal:valid.test.v1",
        "session_ref": "agent_session:valid.v1",
        "plan_step_ref": "agent_plan_step:valid.step0.v1",
        "tool": {"logical_name": "reader", "version": "1.0.0", "category": "read_only"},
        "arguments": {"key": "value"},
        "risk": {"risk_tier": "none", "side_effects": "none", "reversibility": "reversible"},
        "approval": {"requires_human_approval": True, "approval_reason": "Session policy."},
        "expected_evidence": {"evidence_type": "output_summary", "description": "Data output."},
        "safety": {"forbids_autonomous_execution": True, "timeout_seconds": 10, "max_retries": 0},
    }
    errors = _validate(data)
    assert errors == [], f"Unexpected errors: {errors}"


def test_risk_tier_none_with_read_only_side_effects():
    """read_only side_effects with risk_tier=none should NOT require approval for side_effects."""
    data = {
        "schema_version": "core.tool_invocation_proposal.v1",
        "type": "tool_invocation_proposal",
        "proposal_id": "tool_invocation_proposal:readonly.test.v1",
        "session_ref": "s",
        "plan_step_ref": "p",
        "tool": {"logical_name": "reader", "version": "1.0.0", "category": "read_only"},
        "arguments": {"k": "v"},
        "risk": {"risk_tier": "none", "side_effects": "read_only", "reversibility": "reversible"},
        "approval": {"requires_human_approval": True, "approval_reason": "ok"},
        "expected_evidence": {"evidence_type": "output_summary", "description": "x"},
        "safety": {"forbids_autonomous_execution": True, "timeout_seconds": 10, "max_retries": 0},
    }
    errors = _validate(data)
    codes = [e["code"] for e in errors]
    assert "approval_not_required_for_side_effects" not in codes
