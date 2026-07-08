"""Tests for expert conflict pre-resolution validator.

Covers all five artifact types and all rejection scenarios.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

VALIDATOR = Path(__file__).resolve().parent.parent / "scripts" / "validate_expert_conflict_pre_resolution.py"
EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "expert_conflict_pre_resolution"


# --- Helpers -----------------------------------------------------------

def _run_validator(path: str | Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(path)],
        capture_output=True, text=True, timeout=30,
    )
    return json.loads(result.stdout)


def _validate_artifact(artifact: dict) -> dict:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(artifact, f)
        f.flush()
        tmppath = f.name
    try:
        result = subprocess.run(
            [sys.executable, str(VALIDATOR), tmppath],
            capture_output=True, text=True, timeout=30,
        )
        report = json.loads(result.stdout)
        if report.get("results"):
            return report["results"][0]
        return {"status": "failed", "errors": [{"code": "no_results", "message": "empty", "field": ""}]}
    finally:
        Path(tmppath).unlink(missing_ok=True)


# --- Conflict Bundle Tests ---------------------------------------------

class TestConflictBundle:
    def test_valid_bundle(self):
        r = _run_validator(EXAMPLES / "accepted_conflict_bundle.json")
        item = r["results"][0]
        assert item["status"] == "passed"
        assert item["artifact_type"] == "expert_conflict_bundle"

    def test_missing_conflict_id(self):
        artifact = {
            "schema_version": "core.expert_conflict_bundle.v1",
            "type": "expert_conflict_bundle",
            "conflict_id": "",
            "input_fingerprint": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
            "expert_outputs": [
                {"expert_id": "a", "output_ref": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                 "claim_type": "command_candidate", "decision": "accepted"},
                {"expert_id": "b", "output_ref": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                 "claim_type": "command_candidate", "decision": "accepted"}
            ],
            "risk_tier": "low",
            "human_required_by_profile": False
        }
        r = _validate_artifact(artifact)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "invalid_conflict_bundle" in codes

    def test_single_expert_rejected(self):
        artifact = {
            "schema_version": "core.expert_conflict_bundle.v1",
            "type": "expert_conflict_bundle",
            "conflict_id": "c1",
            "input_fingerprint": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
            "expert_outputs": [
                {"expert_id": "a", "output_ref": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                 "claim_type": "command_candidate", "decision": "accepted"}
            ],
            "risk_tier": "low",
            "human_required_by_profile": False
        }
        r = _validate_artifact(artifact)
        assert r["status"] == "failed"

    def test_invalid_risk_tier(self):
        artifact = {
            "schema_version": "core.expert_conflict_bundle.v1",
            "type": "expert_conflict_bundle",
            "conflict_id": "c1",
            "input_fingerprint": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
            "expert_outputs": [
                {"expert_id": "a", "output_ref": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                 "claim_type": "command_candidate", "decision": "accepted"},
                {"expert_id": "b", "output_ref": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                 "claim_type": "command_candidate", "decision": "accepted"}
            ],
            "risk_tier": "extreme",
            "human_required_by_profile": False
        }
        r = _validate_artifact(artifact)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "invalid_conflict_bundle" in codes


# --- Protocol Tests ----------------------------------------------------

class TestPreResolutionProtocol:
    def test_valid_protocol(self):
        r = _run_validator(EXAMPLES / "accepted_pre_resolution_protocol.json")
        item = r["results"][0]
        assert item["status"] == "passed"
        assert item["artifact_type"] == "pre_resolution_protocol"

    def test_non_deterministic_rejected(self):
        artifact = {
            "schema_version": "core.pre_resolution_protocol.v1",
            "protocol_id": "p1",
            "input_conflict_id": "c1",
            "protocol_type": "canonicalization_check",
            "deterministic": False,
            "requires_human_approval": False
        }
        r = _validate_artifact(artifact)
        codes = [e["code"] for e in r["errors"]]
        assert "non_deterministic_protocol" in codes

    def test_unknown_protocol_type(self):
        artifact = {
            "schema_version": "core.pre_resolution_protocol.v1",
            "protocol_id": "p1",
            "input_conflict_id": "c1",
            "protocol_type": "llm_arbitration",
            "deterministic": True,
            "requires_human_approval": False
        }
        r = _validate_artifact(artifact)
        codes = [e["code"] for e in r["errors"]]
        assert "unknown_protocol_type" in codes


# --- Step Tests --------------------------------------------------------

class TestPreResolutionStep:
    def test_valid_step(self):
        r = _run_validator(EXAMPLES / "accepted_pre_resolution_step.json")
        item = r["results"][0]
        assert item["status"] == "passed"
        assert item["artifact_type"] == "pre_resolution_step"

    def test_invalid_step_status(self):
        artifact = {
            "schema_version": "core.pre_resolution_step.v1",
            "conflict_id": "c1",
            "protocol_id": "p1",
            "status": "executed_action"
        }
        r = _validate_artifact(artifact)
        codes = [e["code"] for e in r["errors"]]
        assert "invalid_pre_resolution_outcome" in codes


# --- Report Tests ------------------------------------------------------

class TestPreResolutionReport:
    def test_valid_report(self):
        r = _run_validator(EXAMPLES / "accepted_pre_resolution_report.json")
        item = r["results"][0]
        assert item["status"] == "passed"
        assert item["artifact_type"] == "pre_resolution_report"

    def test_llm_authority_rejected(self):
        r = _run_validator(EXAMPLES / "rejected_llm_authority_resolution.json")
        item = r["results"][0]
        assert item["status"] == "failed"
        codes = [e["code"] for e in item["errors"]]
        assert "llm_authority_resolution_rejected" in codes

    def test_missing_preserved_claims(self):
        r = _run_validator(EXAMPLES / "rejected_missing_preserved_claims.json")
        item = r["results"][0]
        assert item["status"] == "failed"
        codes = [e["code"] for e in item["errors"]]
        assert "missing_preserved_claims" in codes

    def test_human_required_bypassed(self):
        r = _run_validator(EXAMPLES / "rejected_human_required_bypassed.json")
        item = r["results"][0]
        assert item["status"] == "failed"
        codes = [e["code"] for e in item["errors"]]
        assert "human_required_bypassed" in codes

    def test_unbounded_context_rejected(self):
        r = _run_validator(EXAMPLES / "rejected_unbounded_context_resolution.json")
        item = r["results"][0]
        assert item["status"] == "failed"
        codes = [e["code"] for e in item["errors"]]
        assert "unbounded_context_resolution_rejected" in codes

    def test_executes_action_rejected(self):
        artifact = {
            "schema_version": "core.pre_resolution_report.v1",
            "conflict_id": "c1",
            "steps": ["sha256:0000000000000000000000000000000000000000000000000000000000000001"],
            "outcome": "resolved_by_protocol",
            "human_required": False,
            "resolution_summary": "test",
            "preserved_claims": ["sha256:0000000000000000000000000000000000000000000000000000000000000002"],
            "executes_action": True
        }
        r = _validate_artifact(artifact)
        codes = [e["code"] for e in r["errors"]]
        assert "pre_resolution_executes_action" in codes

    def test_core_rejection_overridden(self):
        artifact = {
            "schema_version": "core.pre_resolution_report.v1",
            "conflict_id": "c1",
            "steps": [],
            "outcome": "resolved_by_protocol",
            "human_required": False,
            "resolution_summary": "test",
            "preserved_claims": ["sha256:0000000000000000000000000000000000000000000000000000000000000002"],
            "core_rejection_overridden": True
        }
        r = _validate_artifact(artifact)
        codes = [e["code"] for e in r["errors"]]
        assert "core_rejection_overridden" in codes


# --- Human Escalation Decision Tests -----------------------------------

class TestHumanEscalationDecision:
    def test_valid_escalation(self):
        r = _run_validator(EXAMPLES / "accepted_human_escalation_decision.json")
        item = r["results"][0]
        assert item["status"] == "passed"
        assert item["artifact_type"] == "human_escalation_decision"

    def test_outcome_unresolved_but_human_not_required(self):
        artifact = {
            "schema_version": "core.human_escalation_decision.v1",
            "conflict_id": "c1",
            "human_required": False,
            "reason": "no_human_override_needed",
            "pre_resolution_outcome": "unresolved"
        }
        r = _validate_artifact(artifact)
        codes = [e["code"] for e in r["errors"]]
        assert "human_required_bypassed" in codes

    def test_human_reason_but_flag_false(self):
        artifact = {
            "schema_version": "core.human_escalation_decision.v1",
            "conflict_id": "c1",
            "human_required": False,
            "reason": "risk_tier_requires_human_approval",
            "pre_resolution_outcome": "human_required"
        }
        r = _validate_artifact(artifact)
        codes = [e["code"] for e in r["errors"]]
        assert "human_required_bypassed" in codes

    def test_invalid_reason(self):
        artifact = {
            "schema_version": "core.human_escalation_decision.v1",
            "conflict_id": "c1",
            "human_required": True,
            "reason": "llm_decided_not_needed",
            "pre_resolution_outcome": "resolved_by_protocol"
        }
        r = _validate_artifact(artifact)
        codes = [e["code"] for e in r["errors"]]
        assert "missing_human_escalation_decision" in codes


# --- Structural Tests --------------------------------------------------

class TestStructural:
    def test_missing_schema_version(self):
        artifact = {"type": "expert_conflict_bundle"}
        r = _validate_artifact(artifact)
        codes = [e["code"] for e in r["errors"]]
        assert "missing_schema_version" in codes

    def test_unknown_schema_version(self):
        artifact = {"schema_version": "core.unknown.v1"}
        r = _validate_artifact(artifact)
        codes = [e["code"] for e in r["errors"]]
        assert "unknown_schema_version" in codes

    def test_byte_stability(self):
        """Two runs on the same input produce identical fingerprints."""
        r1 = _run_validator(EXAMPLES)
        r2 = _run_validator(EXAMPLES)
        assert r1["report_fingerprint"] == r2["report_fingerprint"]
