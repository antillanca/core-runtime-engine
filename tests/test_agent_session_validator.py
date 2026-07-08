"""Tests for agent session validator.

Covers all four artifact types, rejection scenarios, byte-stability,
directory validation, leak check, and v7 contract integration.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

VALIDATOR = Path(__file__).resolve().parent.parent / "scripts" / "validate_agent_session.py"
EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "agent_sessions"

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


# --- Agent Session: Accepted Fixtures ----------------------------------

class TestAgentSessionAccepted:
    def test_valid_read_and_propose(self):
        r = _run_validator(EXAMPLES / "accepted_read_and_propose.json")
        item = r["results"][0]
        assert item["status"] == "passed"
        assert item["artifact_type"] == "agent_session"

    def test_valid_escalation_to_human(self):
        r = _run_validator(EXAMPLES / "accepted_escalation_to_human.json")
        item = r["results"][0]
        assert item["status"] == "passed"
        assert item["artifact_type"] == "agent_session"


# --- Agent Session: Rejected Fixtures ----------------------------------

class TestAgentSessionRejected:
    def test_unbounded_context(self):
        r = _run_validator(EXAMPLES / "rejected_unbounded_context.json")
        item = r["results"][0]
        assert item["status"] == "failed"
        codes = [e["code"] for e in item["errors"]]
        assert "unbounded_context" in codes

    def test_tool_execution_without_approval(self):
        r = _run_validator(EXAMPLES / "rejected_tool_execution.json")
        item = r["results"][0]
        assert item["status"] == "failed"
        codes = [e["code"] for e in item["errors"]]
        assert "human_approval_not_required" in codes
        assert "autonomous_execution_allowed" in codes

    def test_autonomous_execution_allowed(self):
        r = _run_validator(EXAMPLES / "rejected_autonomous_execution.json")
        item = r["results"][0]
        assert item["status"] == "failed"
        codes = [e["code"] for e in item["errors"]]
        assert "autonomous_execution_allowed" in codes

    def test_private_path_detected(self):
        r = _run_validator(EXAMPLES / "rejected_private_path.json")
        item = r["results"][0]
        assert item["status"] == "failed"
        codes = [e["code"] for e in item["errors"]]
        assert "private_path_detected" in codes


# --- Rejection Codes: Structural ---------------------------------------

class TestStructuralRejections:
    def test_missing_schema_version(self):
        artifact = {"type": "agent_session"}
        r = _validate_artifact(artifact)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "missing_schema_version" in codes

    def test_unknown_schema_version(self):
        artifact = {"schema_version": "core.unknown.v99"}
        r = _validate_artifact(artifact)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "unknown_schema_version" in codes

    def test_invalid_type(self):
        artifact = {
            "schema_version": "core.agent_session.v1",
            "type": "wrong_type",
        }
        r = _validate_artifact(artifact)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "invalid_type" in codes

    def test_missing_session_id(self):
        artifact = {
            "schema_version": "core.agent_session.v1",
            "type": "agent_session",
            "session_id": "",
            "agent": {"agent_id": "a", "agent_kind": "synthetic_assistant"},
            "task": {"task_ref": "t"},
            "context_budget": {"budget_ref": "b", "read_policy": "no_access"},
            "safety": {"requires_human_approval": True, "forbids_autonomous_execution": True},
            "trace": {"decision_trace_ref": "d"},
        }
        r = _validate_artifact(artifact)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "missing_session_id" in codes

    def test_invalid_session_id_format(self):
        artifact = {
            "schema_version": "core.agent_session.v1",
            "type": "agent_session",
            "session_id": "BAD_FORMAT",
            "agent": {"agent_id": "a", "agent_kind": "synthetic_assistant"},
            "task": {"task_ref": "t"},
            "context_budget": {"budget_ref": "b", "read_policy": "no_access"},
            "safety": {"requires_human_approval": True, "forbids_autonomous_execution": True},
            "trace": {"decision_trace_ref": "d"},
        }
        r = _validate_artifact(artifact)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "invalid_session_id_format" in codes


# --- Rejection Codes: Safety -------------------------------------------

class TestSafetyRejections:
    def test_human_approval_not_required(self):
        artifact = {
            "schema_version": "core.agent_session.v1",
            "type": "agent_session",
            "session_id": "agent_session:test.v1",
            "agent": {"agent_id": "a", "agent_kind": "synthetic_assistant"},
            "task": {"task_ref": "t"},
            "context_budget": {"budget_ref": "b", "read_policy": "no_access"},
            "safety": {"requires_human_approval": False, "forbids_autonomous_execution": True},
            "trace": {"decision_trace_ref": "d"},
        }
        r = _validate_artifact(artifact)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "human_approval_not_required" in codes

    def test_autonomous_execution_allowed(self):
        artifact = {
            "schema_version": "core.agent_session.v1",
            "type": "agent_session",
            "session_id": "agent_session:test.v1",
            "agent": {"agent_id": "a", "agent_kind": "synthetic_assistant"},
            "task": {"task_ref": "t"},
            "context_budget": {"budget_ref": "b", "read_policy": "no_access"},
            "safety": {"requires_human_approval": True, "forbids_autonomous_execution": False},
            "trace": {"decision_trace_ref": "d"},
        }
        r = _validate_artifact(artifact)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "autonomous_execution_allowed" in codes


# --- Rejection Codes: Context Boundary ---------------------------------

class TestContextBoundaryRejections:
    def test_unbounded_context_bounded_read_no_index(self):
        artifact = {
            "schema_version": "core.agent_session.v1",
            "type": "agent_session",
            "session_id": "agent_session:test.v1",
            "agent": {"agent_id": "a", "agent_kind": "synthetic_assistant"},
            "task": {"task_ref": "t"},
            "context_budget": {"budget_ref": "b", "read_policy": "bounded_read_only"},
            "safety": {"requires_human_approval": True, "forbids_autonomous_execution": True},
            "trace": {"decision_trace_ref": "d"},
        }
        r = _validate_artifact(artifact)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "unbounded_context" in codes

    def test_unbounded_context_proposal_no_index(self):
        artifact = {
            "schema_version": "core.agent_session.v1",
            "type": "agent_session",
            "session_id": "agent_session:test.v1",
            "agent": {"agent_id": "a", "agent_kind": "synthetic_assistant"},
            "task": {"task_ref": "t"},
            "context_budget": {"budget_ref": "b", "read_policy": "read_write_proposal_only"},
            "safety": {"requires_human_approval": True, "forbids_autonomous_execution": True},
            "trace": {"decision_trace_ref": "d"},
        }
        r = _validate_artifact(artifact)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "unbounded_context" in codes


# --- Rejection Codes: Private Path --------------------------------------

class TestPrivatePathRejections:
    def test_private_path_unix(self):
        artifact = {
            "schema_version": "core.agent_session.v1",
            "type": "agent_session",
            "session_id": "agent_session:test.v1",
            "agent": {"agent_id": "a", "agent_kind": "synthetic_assistant"},
            "task": {"task_ref": "t"},
            "context_budget": {"budget_ref": "b", "read_policy": "no_access"},
            "safety": {"requires_human_approval": True, "forbids_autonomous_execution": True},
            "trace": {"decision_trace_ref": "d"},
            "metadata": {"db_path": "/home/user/private/db.sqlite"},
        }
        r = _validate_artifact(artifact)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "private_path_detected" in codes

    def test_private_path_windows(self):
        artifact = {
            "schema_version": "core.agent_session.v1",
            "type": "agent_session",
            "session_id": "agent_session:test.v1",
            "agent": {"agent_id": "a", "agent_kind": "synthetic_assistant"},
            "task": {"task_ref": "t"},
            "context_budget": {"budget_ref": "b", "read_policy": "no_access"},
            "safety": {"requires_human_approval": True, "forbids_autonomous_execution": True},
            "trace": {"decision_trace_ref": "d"},
            "metadata": {"config": "C:\\Users\\admin\\secrets.env"},
        }
        r = _validate_artifact(artifact)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "private_path_detected" in codes


# --- Agent Task Tests ---------------------------------------------------

class TestAgentTask:
    def test_valid_task(self):
        r = _run_validator(EXAMPLES / "accepted_agent_task.json")
        item = r["results"][0]
        assert item["status"] == "passed"
        assert item["artifact_type"] == "agent_task"

    def test_command_validation_not_required(self):
        artifact = {
            "schema_version": "core.agent_task.v1",
            "type": "agent_task",
            "task_id": "agent_task:test.v1",
            "intent": "test intent",
            "slots": {},
            "safety": {"requires_command_validation": False},
        }
        r = _validate_artifact(artifact)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "command_validation_not_required" in codes

    def test_missing_intent(self):
        artifact = {
            "schema_version": "core.agent_task.v1",
            "type": "agent_task",
            "task_id": "agent_task:test.v1",
            "intent": "",
            "slots": {},
            "safety": {"requires_command_validation": True},
        }
        r = _validate_artifact(artifact)
        assert r["status"] == "failed"


# --- Agent Context Budget Tests -----------------------------------------

class TestAgentContextBudget:
    def test_valid_budget(self):
        r = _run_validator(EXAMPLES / "accepted_agent_context_budget.json")
        item = r["results"][0]
        assert item["status"] == "passed"
        assert item["artifact_type"] == "agent_context_budget"

    def test_proposal_only_violated(self):
        artifact = {
            "schema_version": "core.agent_context_budget.v1",
            "type": "agent_context_budget",
            "budget_id": "context_budget:test.v1",
            "read_limit": {"max_references": 5, "max_depth": 2},
            "write_limit": {"allows_proposal_only": False},
            "tools": {"allowed_tools": []},
        }
        r = _validate_artifact(artifact)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "proposal_only_violated" in codes


# --- Agent Decision Trace Tests -----------------------------------------

class TestAgentDecisionTrace:
    def test_valid_trace(self):
        r = _run_validator(EXAMPLES / "accepted_agent_decision_trace.json")
        item = r["results"][0]
        assert item["status"] == "passed"
        assert item["artifact_type"] == "agent_decision_trace"

    def test_empty_decisions(self):
        artifact = {
            "schema_version": "core.agent_decision_trace.v1",
            "type": "agent_decision_trace",
            "trace_id": "decision_trace:test.v1",
            "session_ref": "agent_session:test.v1",
            "decisions": [],
        }
        r = _validate_artifact(artifact)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "empty_decisions" in codes

    def test_invalid_action(self):
        artifact = {
            "schema_version": "core.agent_decision_trace.v1",
            "type": "agent_decision_trace",
            "trace_id": "decision_trace:test.v1",
            "session_ref": "agent_session:test.v1",
            "decisions": [
                {"step": 0, "action": "execute_sql", "outcome": "success", "timestamp": "2025-01-01T00:00:00Z"}
            ],
        }
        r = _validate_artifact(artifact)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "invalid_trace_type" in codes


# --- Byte Stability -----------------------------------------------------

class TestByteStability:
    def test_accepted_session_byte_stable(self):
        r1 = _run_validator(EXAMPLES / "accepted_read_and_propose.json")
        r2 = _run_validator(EXAMPLES / "accepted_read_and_propose.json")
        assert r1["report_fingerprint"] == r2["report_fingerprint"]

    def test_accepted_task_byte_stable(self):
        r1 = _run_validator(EXAMPLES / "accepted_agent_task.json")
        r2 = _run_validator(EXAMPLES / "accepted_agent_task.json")
        assert r1["report_fingerprint"] == r2["report_fingerprint"]

    def test_accepted_budget_byte_stable(self):
        r1 = _run_validator(EXAMPLES / "accepted_agent_context_budget.json")
        r2 = _run_validator(EXAMPLES / "accepted_agent_context_budget.json")
        assert r1["report_fingerprint"] == r2["report_fingerprint"]

    def test_accepted_trace_byte_stable(self):
        r1 = _run_validator(EXAMPLES / "accepted_agent_decision_trace.json")
        r2 = _run_validator(EXAMPLES / "accepted_agent_decision_trace.json")
        assert r1["report_fingerprint"] == r2["report_fingerprint"]


# --- Directory Validation -----------------------------------------------

class TestDirectoryValidation:
    def test_directory_scan(self):
        r = _run_validator(EXAMPLES)
        assert r["total_artifacts"] == 9  # 5 accepted + 4 rejected
        assert r["passed_count"] == 5
        assert r["failed_count"] == 4

    def test_directory_report_has_fingerprint(self):
        r = _run_validator(EXAMPLES)
        assert r["report_fingerprint"].startswith("sha256:")
        assert len(r["report_fingerprint"]) == 71  # sha256: + 64 hex chars


# --- Leak Check ---------------------------------------------------------

class TestLeakCheck:
    def test_no_private_references_in_examples(self):
        """Verify no example files contain private downstream references."""
        for f in EXAMPLES.glob("*.json"):
            content = f.read_text()
            # Must not reference private projects or real operator paths.
            assert "private_product_name" not in content.lower()
            assert "private_customer_name" not in content.lower()
            assert "/home/real-user" not in content
            # rejected_private_path intentionally has /home/user (generic).


# --- V7 Contract Integration --------------------------------------------

class TestV7ContractIntegration:
    def test_session_references_bounded_index(self):
        """Valid session with bounded_read_only must reference bounded_reference_index."""
        r = _run_validator(EXAMPLES / "accepted_read_and_propose.json")
        item = r["results"][0]
        assert item["status"] == "passed"
        # The fixture itself has allowed_reference_index set

    def test_session_with_no_access_no_index_needed(self):
        """Session with no_access read policy doesn't need bounded_reference_index."""
        artifact = {
            "schema_version": "core.agent_session.v1",
            "type": "agent_session",
            "session_id": "agent_session:no_access_test.v1",
            "agent": {"agent_id": "a", "agent_kind": "synthetic_assistant"},
            "task": {"task_ref": "t"},
            "context_budget": {"budget_ref": "b", "read_policy": "no_access"},
            "safety": {"requires_human_approval": True, "forbids_autonomous_execution": True},
            "trace": {"decision_trace_ref": "d"},
        }
        r = _validate_artifact(artifact)
        assert r["status"] == "passed"

    def test_agent_kind_invalid(self):
        artifact = {
            "schema_version": "core.agent_session.v1",
            "type": "agent_session",
            "session_id": "agent_session:bad_kind.v1",
            "agent": {"agent_id": "a", "agent_kind": "autonomous_agent"},
            "task": {"task_ref": "t"},
            "context_budget": {"budget_ref": "b", "read_policy": "no_access"},
            "safety": {"requires_human_approval": True, "forbids_autonomous_execution": True},
            "trace": {"decision_trace_ref": "d"},
        }
        r = _validate_artifact(artifact)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "invalid_agent_kind" in codes
