"""Tests for CORE human-approved execution gate validation contract.

Covers all 7 artifact types (accepted) and 4 rejection scenarios,
plus schema dispatch, structural validation, and byte-stability.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "examples" / "human_approved_execution_gate"
VALIDATOR = REPO_ROOT / "scripts" / "validate_human_approved_execution_gate.py"

ZERO_FP = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
REVIEW_FP = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
REVIEW_FP_B = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
REVIEW_FP_C = "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"


# --- Helpers -----------------------------------------------------------

def _run_validator(path: str | Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(path)],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    return json.loads(result.stdout)


def _validate_one(artifact: dict) -> dict:
    from scripts.validate_human_approved_execution_gate import _validate_one
    return _validate_one(artifact, "<test>")


# --- Accepted fixtures -------------------------------------------------

class TestAcceptedExecutionProposal:
    def test_accepted_fixture_passes(self):
        r = _run_validator(FIXTURES_DIR / "accepted_execution_proposal.json")
        assert r["status"] == "passed"
        assert r["passed_count"] == 1

    def test_valid_proposal_structure(self):
        proposal = {
            "schema_version": "core.execution_proposal.v1",
            "type": "execution_proposal",
            "proposal_id": "test.proposal.v1",
            "producer": {"id": "test.assistant", "kind": "private_assistant"},
            "requested_action": {
                "action_type": "run_script",
                "command_ref": "scripts/test.py",
                "sandbox_required": True,
            },
            "risk_tier": "low",
            "declared_scope": ["docs/"],
            "expected_outputs": ["report"],
            "requires_human_approval": True,
        }
        r = _validate_one(proposal)
        assert r["status"] == "passed"


class TestAcceptedAdvisoryReview:
    def test_accepted_fixture_passes(self):
        r = _run_validator(FIXTURES_DIR / "accepted_advisory_review.json")
        assert r["status"] == "passed"

    def test_authority_must_be_advisory_only(self):
        review = {
            "schema_version": "core.advisory_review.v1",
            "type": "advisory_review",
            "proposal_id": "test.v1",
            "expert_id": "expert_a",
            "verdict": "approve",
            "authority": "advisory_only",
        }
        r = _validate_one(review)
        assert r["status"] == "passed"


class TestAcceptedMultiExpertReviewBundle:
    def test_accepted_fixture_passes(self):
        r = _run_validator(FIXTURES_DIR / "accepted_multi_expert_review_bundle.json")
        assert r["status"] == "passed"

    def test_unanimous_approval_still_requires_human(self):
        bundle = {
            "schema_version": "core.multi_expert_review_bundle.v1",
            "type": "multi_expert_review_bundle",
            "proposal_id": "test.v1",
            "reviews": [REVIEW_FP],
            "agreement": "unanimous_approval",
            "requires_human_review": True,
        }
        r = _validate_one(bundle)
        assert r["status"] == "passed"


class TestAcceptedHumanApprovalRecord:
    def test_accepted_fixture_passes(self):
        r = _run_validator(FIXTURES_DIR / "accepted_human_approval_record.json")
        assert r["status"] == "passed"


class TestAcceptedSandboxExecutionRecord:
    def test_accepted_fixture_passes(self):
        r = _run_validator(FIXTURES_DIR / "accepted_sandbox_execution_record.json")
        assert r["status"] == "passed"


class TestAcceptedSkillPromotionCandidate:
    def test_accepted_fixture_passes(self):
        r = _run_validator(FIXTURES_DIR / "accepted_skill_promotion_candidate.json")
        assert r["status"] == "passed"


class TestAcceptedAmbiguityResolutionRecord:
    def test_accepted_fixture_passes(self):
        r = _run_validator(FIXTURES_DIR / "accepted_ambiguity_resolution_record.json")
        assert r["status"] == "passed"


# --- Rejected fixtures -------------------------------------------------

class TestRejectedLlmAuthority:
    def test_rejected_fixture_fails(self):
        r = _run_validator(FIXTURES_DIR / "rejected_llm_authority.json")
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["results"][0]["errors"]]
        assert "llm_authority_rejected" in codes

    def test_authority_binding_rejected(self):
        review = {
            "schema_version": "core.advisory_review.v1",
            "type": "advisory_review",
            "proposal_id": "test.v1",
            "expert_id": "expert_a",
            "verdict": "approve",
            "authority": "binding",
        }
        r = _validate_one(review)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "llm_authority_rejected" in codes


class TestRejectedMissingHumanApproval:
    def test_rejected_fixture_fails(self):
        r = _run_validator(FIXTURES_DIR / "rejected_missing_human_approval.json")
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["results"][0]["errors"]]
        assert "missing_human_approval" in codes

    def test_false_human_approval_rejected(self):
        proposal = {
            "schema_version": "core.execution_proposal.v1",
            "type": "execution_proposal",
            "proposal_id": "test.v1",
            "producer": {"id": "test.assistant", "kind": "private_assistant"},
            "requested_action": {
                "action_type": "run_script",
                "command_ref": "scripts/test.py",
                "sandbox_required": True,
            },
            "risk_tier": "low",
            "declared_scope": ["docs/"],
            "expected_outputs": ["report"],
            "requires_human_approval": False,
        }
        r = _validate_one(proposal)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "missing_human_approval" in codes


class TestRejectedScopeExpansion:
    def test_rejected_fixture_fails(self):
        r = _run_validator(FIXTURES_DIR / "rejected_scope_expansion.json")
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["results"][0]["errors"]]
        assert "scope_expansion_detected" in codes

    def test_absolute_path_in_scope(self):
        proposal = {
            "schema_version": "core.execution_proposal.v1",
            "type": "execution_proposal",
            "proposal_id": "test.v1",
            "producer": {"id": "test.assistant", "kind": "private_assistant"},
            "requested_action": {
                "action_type": "run_script",
                "command_ref": "scripts/test.py",
                "sandbox_required": True,
            },
            "risk_tier": "medium",
            "declared_scope": ["/etc/passwd"],
            "expected_outputs": ["data"],
            "requires_human_approval": True,
        }
        r = _validate_one(proposal)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "scope_expansion_detected" in codes


class TestRejectedSkillAutoActivation:
    def test_rejected_fixture_fails(self):
        r = _run_validator(FIXTURES_DIR / "rejected_skill_auto_activation.json")
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["results"][0]["errors"]]
        assert "skill_auto_activation_rejected" in codes

    def test_enabled_activation_rejected(self):
        candidate = {
            "schema_version": "core.skill_promotion_candidate.v1",
            "type": "skill_promotion_candidate",
            "source_execution_id": "exec_001",
            "skill_id": "test_skill.v1",
            "promotion_reason": "test",
            "requires_human_approval": True,
            "activation_default": "enabled",
        }
        r = _validate_one(candidate)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "skill_auto_activation_rejected" in codes


# --- Additional edge cases ---------------------------------------------

class TestSchemaDispatch:
    def test_missing_schema_version_infers_from_type(self):
        review = {
            "type": "advisory_review",
            "proposal_id": "test.v1",
            "expert_id": "expert_a",
            "verdict": "approve",
            "authority": "advisory_only",
        }
        r = _validate_one(review)
        assert r["status"] == "passed"

    def test_unknown_schema_version(self):
        artifact = {
            "schema_version": "core.unknown.v1",
            "type": "something",
        }
        r = _validate_one(artifact)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "unknown_schema_version" in codes

    def test_unknown_type_without_schema_version(self):
        artifact = {"type": "completely_unknown"}
        r = _validate_one(artifact)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "missing_schema_version" in codes


class TestDivergenceValidation:
    def test_partial_without_divergence_summary_fails(self):
        bundle = {
            "schema_version": "core.multi_expert_review_bundle.v1",
            "type": "multi_expert_review_bundle",
            "proposal_id": "test.v1",
            "reviews": [REVIEW_FP, REVIEW_FP_B],
            "agreement": "partial",
            "requires_human_review": True,
        }
        r = _validate_one(bundle)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "missing_divergence_summary" in codes


class TestMissingSandboxProfile:
    def test_empty_sandbox_profile_fails(self):
        record = {
            "schema_version": "core.sandbox_execution_record.v1",
            "type": "sandbox_execution_record",
            "proposal_id": "test.v1",
            "execution_id": "exec_001",
            "sandbox_profile": "",
            "started": True,
            "completed": True,
            "exit_code": 0,
            "mutations_detected": False,
        }
        r = _validate_one(record)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "missing_sandbox_profile" in codes


class TestAmbiguityUnresolved:
    def test_ambiguity_without_resolution_fails(self):
        record = {
            "schema_version": "core.ambiguity_resolution_record.v1",
            "type": "ambiguity_resolution_record",
            "proposal_id": "test.v1",
            "ambiguity_type": "scope_interpretation",
            "interpretations": ["option_a", "option_b"],
            "resolved_by": "human.operator.local",
        }
        r = _validate_one(record)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "ambiguity_requires_resolution" in codes

    def test_ambiguity_with_single_interpretation_fails(self):
        record = {
            "schema_version": "core.ambiguity_resolution_record.v1",
            "type": "ambiguity_resolution_record",
            "proposal_id": "test.v1",
            "ambiguity_type": "scope_interpretation",
            "interpretations": ["only_option"],
            "resolution": "only_option",
            "resolved_by": "human.operator.local",
        }
        r = _validate_one(record)
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"]]
        assert "ambiguity_requires_resolution" in codes


class TestByteStability:
    def test_validator_output_is_deterministic(self):
        import subprocess
        r1 = subprocess.run(
            [sys.executable, str(VALIDATOR), str(FIXTURES_DIR)],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        r2 = subprocess.run(
            [sys.executable, str(VALIDATOR), str(FIXTURES_DIR)],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        assert r1.stdout == r2.stdout


class TestFullDirectoryValidation:
    def test_directory_fixture_counts(self):
        r = _run_validator(FIXTURES_DIR)
        assert r["total_artifacts"] == 11
        assert r["passed_count"] == 7
        assert r["failed_count"] == 4
