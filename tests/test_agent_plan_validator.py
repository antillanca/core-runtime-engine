#!/usr/bin/env python3
"""Tests for validate_agent_plan.py — CORE v8.1 Agent Plan Contract."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path("scripts/validate_agent_plan.py")
FIXTURES = Path("examples/agent_plans")


# --- Helpers ------------------------------------------------------------

def _run_validator(target: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), target],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parent.parent,
    )
    return json.loads(result.stdout)


def _validate_artifact(artifact: dict) -> list[dict]:
    """Import and run the validator directly."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import validate_agent_plan as vap

    vap_module = vap
    return vap_module.validate_single(artifact)


# --- Agent Plan tests ---------------------------------------------------

class TestAgentPlanStructural:
    def test_missing_schema_version(self):
        errors = _validate_artifact({"type": "agent_plan"})
        codes = {e["code"] for e in errors}
        assert "missing_schema_version" in codes

    def test_unknown_schema_version(self):
        errors = _validate_artifact({"schema_version": "core.agent_plan.v99"})
        codes = {e["code"] for e in errors}
        assert "unknown_schema_version" in codes

    def test_invalid_type(self):
        errors = _validate_artifact({"schema_version": "core.agent_plan.v1", "type": "wrong"})
        codes = {e["code"] for e in errors}
        assert "invalid_type" in codes

    def test_missing_plan_id(self):
        errors = _validate_artifact({"schema_version": "core.agent_plan.v1", "type": "agent_plan"})
        codes = {e["code"] for e in errors}
        assert "missing_plan_id" in codes

    def test_invalid_plan_id_format(self):
        errors = _validate_artifact({
            "schema_version": "core.agent_plan.v1",
            "type": "agent_plan",
            "plan_id": "bad_format",
        })
        codes = {e["code"] for e in errors}
        assert "invalid_plan_id_format" in codes

    def test_missing_session_ref(self):
        errors = _validate_artifact({
            "schema_version": "core.agent_plan.v1",
            "type": "agent_plan",
            "plan_id": "agent_plan:valid.name.v1",
        })
        codes = {e["code"] for e in errors}
        assert "missing_session_ref" in codes


class TestAgentPlanSteps:
    def _base_plan(self) -> dict:
        return {
            "schema_version": "core.agent_plan.v1",
            "type": "agent_plan",
            "plan_id": "agent_plan:test.base.v1",
            "session_ref": "agent_session:test.v1",
            "steps": [
                {
                    "step_index": 0,
                    "intent": "Read data",
                    "tool_proposal_ref": None,
                    "depends_on": [],
                    "safety": {
                        "requires_human_approval": True,
                        "risk_tier": "none",
                        "forbids_autonomous_execution": True,
                    },
                    "expected_result": {
                        "result_type": "read_result",
                        "description": "Data read",
                    },
                    "status": "planned",
                }
            ],
            "safety": {
                "requires_step_approval": True,
                "forbids_parallel_execution": True,
                "max_steps": 8,
            },
        }

    def test_valid_linear_plan(self):
        errors = _validate_artifact(self._base_plan())
        assert errors == []

    def test_empty_steps(self):
        plan = self._base_plan()
        plan["steps"] = []
        errors = _validate_artifact(plan)
        codes = {e["code"] for e in errors}
        assert "empty_steps" in codes

    def test_max_steps_exceeded(self):
        plan = self._base_plan()
        plan["safety"]["max_steps"] = 1
        plan["steps"].append({
            "step_index": 1,
            "intent": "Second step",
            "depends_on": [0],
            "safety": {
                "requires_human_approval": True,
                "risk_tier": "none",
                "forbids_autonomous_execution": True,
            },
            "expected_result": {"result_type": "read_result", "description": "Read 2"},
            "status": "planned",
        })
        errors = _validate_artifact(plan)
        codes = {e["code"] for e in errors}
        assert "max_steps_exceeded" in codes

    def test_step_approval_not_required(self):
        plan = self._base_plan()
        plan["steps"][0]["tool_proposal_ref"] = "tool_invocation_proposal:test.v1"
        plan["steps"][0]["safety"]["requires_human_approval"] = False
        errors = _validate_artifact(plan)
        codes = {e["code"] for e in errors}
        assert "step_approval_not_required" in codes

    def test_step_autonomous_allowed(self):
        plan = self._base_plan()
        plan["steps"][0]["safety"]["forbids_autonomous_execution"] = False
        errors = _validate_artifact(plan)
        codes = {e["code"] for e in errors}
        assert "step_autonomous_execution_allowed" in codes

    def test_invalid_risk_tier(self):
        plan = self._base_plan()
        plan["steps"][0]["safety"]["risk_tier"] = "extreme"
        errors = _validate_artifact(plan)
        codes = {e["code"] for e in errors}
        assert "invalid_risk_tier" in codes

    def test_missing_expected_result(self):
        plan = self._base_plan()
        del plan["steps"][0]["expected_result"]
        errors = _validate_artifact(plan)
        codes = {e["code"] for e in errors}
        assert "missing_expected_result" in codes

    def test_invalid_result_type(self):
        plan = self._base_plan()
        plan["steps"][0]["expected_result"]["result_type"] = "execute_directly"
        errors = _validate_artifact(plan)
        codes = {e["code"] for e in errors}
        assert "invalid_expected_result_type" in codes

    def test_missing_step_intent(self):
        plan = self._base_plan()
        plan["steps"][0]["intent"] = ""
        errors = _validate_artifact(plan)
        codes = {e["code"] for e in errors}
        assert "missing_step_intent" in codes

    def test_duplicate_step_index(self):
        plan = self._base_plan()
        plan["steps"].append(dict(plan["steps"][0]))
        errors = _validate_artifact(plan)
        codes = {e["code"] for e in errors}
        assert "duplicate_step_index" in codes

    def test_step_index_out_of_range(self):
        plan = self._base_plan()
        plan["steps"][0]["step_index"] = 99
        errors = _validate_artifact(plan)
        codes = {e["code"] for e in errors}
        assert "step_index_out_of_range" in codes

    def test_invalid_depends_on(self):
        plan = self._base_plan()
        plan["steps"][0]["depends_on"] = [5]
        errors = _validate_artifact(plan)
        codes = {e["code"] for e in errors}
        assert "invalid_depends_on" in codes


class TestAgentPlanSafety:
    def _base_plan(self) -> dict:
        return {
            "schema_version": "core.agent_plan.v1",
            "type": "agent_plan",
            "plan_id": "agent_plan:safety.test.v1",
            "session_ref": "agent_session:test.v1",
            "steps": [
                {
                    "step_index": 0,
                    "intent": "Read data",
                    "tool_proposal_ref": None,
                    "depends_on": [],
                    "safety": {
                        "requires_human_approval": True,
                        "risk_tier": "none",
                        "forbids_autonomous_execution": True,
                    },
                    "expected_result": {
                        "result_type": "read_result",
                        "description": "Data read",
                    },
                    "status": "planned",
                }
            ],
            "safety": {
                "requires_step_approval": True,
                "forbids_parallel_execution": True,
                "max_steps": 8,
            },
        }

    def test_plan_approval_not_required(self):
        plan = self._base_plan()
        plan["safety"]["requires_step_approval"] = False
        errors = _validate_artifact(plan)
        codes = {e["code"] for e in errors}
        assert "plan_approval_not_required" in codes

    def test_parallel_execution_with_side_effects(self):
        plan = self._base_plan()
        plan["steps"][0]["tool_proposal_ref"] = "tool_invocation_proposal:test.v1"
        plan["steps"][0]["safety"]["risk_tier"] = "high"
        plan["safety"]["forbids_parallel_execution"] = False
        errors = _validate_artifact(plan)
        codes = {e["code"] for e in errors}
        assert "plan_parallel_execution_with_side_effects" in codes

    def test_circular_dependency(self):
        plan = self._base_plan()
        plan["steps"].append({
            "step_index": 1,
            "intent": "Step 1",
            "depends_on": [0],
            "safety": {
                "requires_human_approval": True,
                "risk_tier": "none",
                "forbids_autonomous_execution": True,
            },
            "expected_result": {"result_type": "read_result", "description": "Read 1"},
            "status": "planned",
        })
        plan["steps"][0]["depends_on"] = [1]
        errors = _validate_artifact(plan)
        codes = {e["code"] for e in errors}
        assert "circular_dependency" in codes

    def test_private_path_detected(self):
        plan = self._base_plan()
        plan["steps"][0]["intent"] = "Read /home/real-user/.env"
        errors = _validate_artifact(plan)
        codes = {e["code"] for e in errors}
        assert "private_path_detected" in codes


class TestAgentPlanStep:
    def test_valid_step(self):
        artifact = {
            "schema_version": "core.agent_plan_step.v1",
            "type": "agent_plan_step",
            "step_id": "agent_plan_step:valid.step.v1",
            "plan_ref": "agent_plan:test.v1",
            "step_index": 0,
            "intent": "Read data",
            "depends_on": [],
            "safety": {
                "requires_human_approval": True,
                "risk_tier": "none",
                "forbids_autonomous_execution": True,
            },
            "expected_result": {"result_type": "read_result", "description": "Read"},
            "status": "planned",
        }
        errors = _validate_artifact(artifact)
        assert errors == []

    def test_missing_step_id(self):
        errors = _validate_artifact({
            "schema_version": "core.agent_plan_step.v1",
            "type": "agent_plan_step",
        })
        codes = {e["code"] for e in errors}
        assert "missing_step_id" in codes

    def test_invalid_step_type(self):
        errors = _validate_artifact({
            "schema_version": "core.agent_plan_step.v1",
            "type": "wrong",
        })
        codes = {e["code"] for e in errors}
        assert "invalid_step_type" in codes


class TestAgentPlanDependency:
    def test_valid_dependency(self):
        artifact = {
            "schema_version": "core.agent_plan_dependency.v1",
            "type": "agent_plan_dependency",
            "dependency_id": "agent_plan_dependency:test.s0.s1.v1",
            "plan_ref": "agent_plan:test.v1",
            "from_step": 0,
            "to_step": 1,
            "dependency_type": "sequential",
            "description": "Step 1 needs step 0",
        }
        errors = _validate_artifact(artifact)
        assert errors == []

    def test_self_dependency(self):
        artifact = {
            "schema_version": "core.agent_plan_dependency.v1",
            "type": "agent_plan_dependency",
            "dependency_id": "agent_plan_dependency:bad.s0.s0.v1",
            "plan_ref": "agent_plan:test.v1",
            "from_step": 0,
            "to_step": 0,
            "dependency_type": "sequential",
            "description": "Self dep",
        }
        errors = _validate_artifact(artifact)
        codes = {e["code"] for e in errors}
        assert "self_dependency" in codes

    def test_invalid_dependency_type(self):
        artifact = {
            "schema_version": "core.agent_plan_dependency.v1",
            "type": "agent_plan_dependency",
            "dependency_id": "agent_plan_dependency:bad.s0.s1.v1",
            "plan_ref": "agent_plan:test.v1",
            "from_step": 0,
            "to_step": 1,
            "dependency_type": "invalid",
            "description": "Bad type",
        }
        errors = _validate_artifact(artifact)
        codes = {e["code"] for e in errors}
        assert "invalid_dependency_type" in codes

    def test_missing_dependency_id(self):
        errors = _validate_artifact({
            "schema_version": "core.agent_plan_dependency.v1",
            "type": "agent_plan_dependency",
        })
        codes = {e["code"] for e in errors}
        assert "missing_dependency_id" in codes


class TestAgentPlanResult:
    def test_valid_result(self):
        artifact = {
            "schema_version": "core.agent_plan_result.v1",
            "type": "agent_plan_result",
            "result_id": "agent_plan_result:test.done.v1",
            "plan_ref": "agent_plan:test.v1",
            "session_ref": "agent_session:test.v1",
            "overall_status": "completed",
            "step_results": [
                {
                    "step_index": 0,
                    "status": "completed",
                    "outcome_fingerprint": "sha256:" + "a" * 64,
                }
            ],
            "plan_fingerprint": "sha256:" + "b" * 64,
            "validation_fingerprint": "sha256:" + "c" * 64,
        }
        errors = _validate_artifact(artifact)
        assert errors == []

    def test_missing_result_id(self):
        errors = _validate_artifact({
            "schema_version": "core.agent_plan_result.v1",
            "type": "agent_plan_result",
        })
        codes = {e["code"] for e in errors}
        assert "missing_result_id" in codes

    def test_invalid_result_type(self):
        errors = _validate_artifact({
            "schema_version": "core.agent_plan_result.v1",
            "type": "wrong",
        })
        codes = {e["code"] for e in errors}
        assert "invalid_result_type" in codes

    def test_empty_step_results(self):
        errors = _validate_artifact({
            "schema_version": "core.agent_plan_result.v1",
            "type": "agent_plan_result",
            "result_id": "agent_plan_result:test.empty.v1",
            "plan_ref": "agent_plan:test.v1",
            "session_ref": "agent_session:test.v1",
            "overall_status": "completed",
            "step_results": [],
            "plan_fingerprint": "sha256:" + "a" * 64,
            "validation_fingerprint": "sha256:" + "b" * 64,
        })
        codes = {e["code"] for e in errors}
        assert "empty_step_results" in codes

    def test_invalid_overall_status(self):
        artifact = {
            "schema_version": "core.agent_plan_result.v1",
            "type": "agent_plan_result",
            "result_id": "agent_plan_result:test.bad.v1",
            "plan_ref": "agent_plan:test.v1",
            "session_ref": "agent_session:test.v1",
            "overall_status": "exploded",
            "step_results": [
                {
                    "step_index": 0,
                    "status": "completed",
                    "outcome_fingerprint": "sha256:" + "a" * 64,
                }
            ],
            "plan_fingerprint": "sha256:" + "b" * 64,
            "validation_fingerprint": "sha256:" + "c" * 64,
        }
        errors = _validate_artifact(artifact)
        codes = {e["code"] for e in errors}
        assert "invalid_overall_status" in codes


class TestByteStability:
    def test_validator_deterministic_output(self):
        artifact = {
            "schema_version": "core.agent_plan.v1",
            "type": "agent_plan",
            "plan_id": "agent_plan:stable.test.v1",
            "session_ref": "agent_session:stable.v1",
            "steps": [
                {
                    "step_index": 0,
                    "intent": "Read",
                    "depends_on": [],
                    "safety": {
                        "requires_human_approval": True,
                        "risk_tier": "none",
                        "forbids_autonomous_execution": True,
                    },
                    "expected_result": {"result_type": "read_result", "description": "Data"},
                    "status": "planned",
                }
            ],
            "safety": {
                "requires_step_approval": True,
                "forbids_parallel_execution": True,
                "max_steps": 4,
            },
        }
        r1 = _validate_artifact(artifact)
        r2 = _validate_artifact(artifact)
        assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)


class TestFixtureFiles:
    def test_accepted_linear_plan(self):
        report = _run_validator(str(FIXTURES / "accepted_linear_plan.json"))
        assert report["status"] == "passed"

    def test_accepted_dag_plan(self):
        report = _run_validator(str(FIXTURES / "accepted_dag_plan.json"))
        assert report["status"] == "passed"

    def test_accepted_step_proposal(self):
        report = _run_validator(str(FIXTURES / "accepted_step_proposal.json"))
        assert report["status"] == "passed"

    def test_accepted_dependency(self):
        report = _run_validator(str(FIXTURES / "accepted_dependency_sequential.json"))
        assert report["status"] == "passed"

    def test_accepted_result(self):
        report = _run_validator(str(FIXTURES / "accepted_result_completed.json"))
        assert report["status"] == "passed"

    def test_rejected_autonomous(self):
        report = _run_validator(str(FIXTURES / "rejected_autonomous_plan.json"))
        assert report["status"] == "failed"

    def test_rejected_circular(self):
        report = _run_validator(str(FIXTURES / "rejected_circular_plan.json"))
        assert report["status"] == "failed"

    def test_rejected_parallel_side_effects(self):
        report = _run_validator(str(FIXTURES / "rejected_parallel_side_effects.json"))
        assert report["status"] == "failed"

    def test_rejected_private_path(self):
        report = _run_validator(str(FIXTURES / "rejected_private_path_plan.json"))
        assert report["status"] == "failed"

    def test_rejected_invalid_depends_on(self):
        report = _run_validator(str(FIXTURES / "rejected_invalid_depends_on.json"))
        assert report["status"] == "failed"

    def test_rejected_self_dependency(self):
        report = _run_validator(str(FIXTURES / "rejected_self_dependency.json"))
        assert report["status"] == "failed"
