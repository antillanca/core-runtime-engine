#!/usr/bin/env python3
"""Tests for validate_agent_decision_trace.py — CORE v8.3 Agent Decision Trace."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT / "scripts" / "validate_agent_decision_trace.py"
FIXTURES = PROJECT / "examples" / "agent_traces"


def _run(target: str) -> dict:
    cmd = [sys.executable, str(SCRIPT), str(FIXTURES / target)]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT))
    return json.loads(r.stdout)


def _errors(result: dict) -> list[str]:
    codes = []
    for artifact in result.get("results", []):
        for err in artifact.get("errors", []):
            codes.append(err["code"])
    return codes


# ── Accepted fixtures ──────────────────────────────────────────────

class TestAcceptedLinearTrace:
    def test_passes(self):
        r = _run("accepted_linear_trace.json")
        assert r["status"] == "passed"

    def test_single_artifact(self):
        r = _run("accepted_linear_trace.json")
        assert r["total_artifacts"] == 1

    def test_no_errors(self):
        r = _run("accepted_linear_trace.json")
        assert r["failed_count"] == 0


class TestAcceptedGovernanceRejectionTrace:
    def test_passes(self):
        r = _run("accepted_governance_rejection_trace.json")
        assert r["status"] == "passed"

    def test_governance_violation_counted(self):
        data = json.loads((FIXTURES / "accepted_governance_rejection_trace.json").read_text())
        assert data["trace_summary"]["governance_violations"] == 1
        assert data["trace_summary"]["requires_review"] is True


# ── Rejected fixtures: specific error codes ────────────────────────

class TestRejectedNonContiguousIds:
    def test_fails(self):
        r = _run("rejected_non_contiguous_ids.json")
        assert r["status"] == "failed"

    def test_correct_code(self):
        r = _run("rejected_non_contiguous_ids.json")
        assert "non_contiguous_entry_ids" in _errors(r)


class TestRejectedReviewNotSet:
    def test_fails(self):
        r = _run("rejected_review_not_set.json")
        assert r["status"] == "failed"

    def test_correct_code(self):
        r = _run("rejected_review_not_set.json")
        assert "requires_review_not_set" in _errors(r)


class TestRejectedImmutabilityFalse:
    def test_fails(self):
        r = _run("rejected_immutability_false.json")
        assert r["status"] == "failed"

    def test_correct_code(self):
        r = _run("rejected_immutability_false.json")
        assert "immutability_guarantee_not_true" in _errors(r)


class TestRejectedNonMonotonicTimestamps:
    def test_fails(self):
        r = _run("rejected_non_monotonic_timestamps.json")
        assert r["status"] == "failed"

    def test_correct_code(self):
        r = _run("rejected_non_monotonic_timestamps.json")
        assert "non_monotonic_timestamps" in _errors(r)


class TestRejectedSummaryCountMismatch:
    def test_fails(self):
        r = _run("rejected_summary_count_mismatch.json")
        assert r["status"] == "failed"

    def test_correct_code(self):
        r = _run("rejected_summary_count_mismatch.json")
        assert "trace_summary_entry_count_mismatch" in _errors(r)


# ── Structural validation ──────────────────────────────────────────

class TestStructuralMissingSchemaVersion:
    def test_fails(self):
        data = json.loads((FIXTURES / "accepted_linear_trace.json").read_text())
        del data["schema_version"]
        p = PROJECT / "tmp_test_structural.json"
        p.write_text(json.dumps(data))
        try:
            cmd = [sys.executable, str(SCRIPT), str(p)]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT))
            result = json.loads(r.stdout)
            assert result["status"] == "failed"
            assert "missing_schema_version" in _errors(result)
        finally:
            p.unlink()


class TestStructuralWrongSchemaVersion:
    def test_fails(self):
        data = json.loads((FIXTURES / "accepted_linear_trace.json").read_text())
        data["schema_version"] = "core.agent_decision_trace.v99"
        p = PROJECT / "tmp_test_schema_v.json"
        p.write_text(json.dumps(data))
        try:
            cmd = [sys.executable, str(SCRIPT), str(p)]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT))
            result = json.loads(r.stdout)
            assert result["status"] == "failed"
            assert "unknown_schema_version" in _errors(result)
        finally:
            p.unlink()


class TestStructuralInvalidType:
    def test_fails(self):
        data = json.loads((FIXTURES / "accepted_linear_trace.json").read_text())
        data["type"] = "wrong_type"
        p = PROJECT / "tmp_test_type.json"
        p.write_text(json.dumps(data))
        try:
            cmd = [sys.executable, str(SCRIPT), str(p)]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT))
            result = json.loads(r.stdout)
            assert result["status"] == "failed"
            assert "invalid_type" in _errors(result)
        finally:
            p.unlink()


# ── Identity validation ────────────────────────────────────────────

class TestIdentityMissingTraceId:
    def test_fails(self):
        data = json.loads((FIXTURES / "accepted_linear_trace.json").read_text())
        del data["trace_id"]
        p = PROJECT / "tmp_test_tid.json"
        p.write_text(json.dumps(data))
        try:
            cmd = [sys.executable, str(SCRIPT), str(p)]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT))
            result = json.loads(r.stdout)
            assert result["status"] == "failed"
            assert "missing_trace_id" in _errors(result)
        finally:
            p.unlink()


class TestIdentityInvalidTraceIdFormat:
    def test_fails(self):
        data = json.loads((FIXTURES / "accepted_linear_trace.json").read_text())
        data["trace_id"] = "bad-format-no-dots"
        p = PROJECT / "tmp_test_tid_fmt.json"
        p.write_text(json.dumps(data))
        try:
            cmd = [sys.executable, str(SCRIPT), str(p)]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT))
            result = json.loads(r.stdout)
            assert result["status"] == "failed"
            assert "invalid_trace_id_format" in _errors(result)
        finally:
            p.unlink()


# ── Reference validation ───────────────────────────────────────────

class TestReferenceMissingSessionRef:
    def test_fails(self):
        data = json.loads((FIXTURES / "accepted_linear_trace.json").read_text())
        del data["session_ref"]
        p = PROJECT / "tmp_test_sref.json"
        p.write_text(json.dumps(data))
        try:
            cmd = [sys.executable, str(SCRIPT), str(p)]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT))
            result = json.loads(r.stdout)
            assert result["status"] == "failed"
            assert "missing_session_ref" in _errors(result)
        finally:
            p.unlink()


class TestReferenceInvalidPlanRefFormat:
    def test_fails(self):
        data = json.loads((FIXTURES / "accepted_linear_trace.json").read_text())
        data["plan_ref"] = "INVALID FORMAT"
        p = PROJECT / "tmp_test_pref.json"
        p.write_text(json.dumps(data))
        try:
            cmd = [sys.executable, str(SCRIPT), str(p)]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT))
            result = json.loads(r.stdout)
            assert result["status"] == "failed"
            assert "invalid_plan_ref_format" in _errors(result)
        finally:
            p.unlink()


# ── Content validation ─────────────────────────────────────────────

class TestContentEmptyEntries:
    def test_fails(self):
        data = json.loads((FIXTURES / "accepted_linear_trace.json").read_text())
        data["trace_entries"] = []
        p = PROJECT / "tmp_test_empty.json"
        p.write_text(json.dumps(data))
        try:
            cmd = [sys.executable, str(SCRIPT), str(p)]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT))
            result = json.loads(r.stdout)
            assert result["status"] == "failed"
            assert "empty_trace_entries" in _errors(result)
        finally:
            p.unlink()


class TestContentInvalidEntryType:
    def test_fails(self):
        data = json.loads((FIXTURES / "accepted_linear_trace.json").read_text())
        data["trace_entries"][0]["entry_type"] = "teleportation"
        p = PROJECT / "tmp_test_etype.json"
        p.write_text(json.dumps(data))
        try:
            cmd = [sys.executable, str(SCRIPT), str(p)]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT))
            result = json.loads(r.stdout)
            assert result["status"] == "failed"
            assert "invalid_entry_type" in _errors(result)
        finally:
            p.unlink()


class TestContentMissingSummary:
    def test_fails(self):
        data = json.loads((FIXTURES / "accepted_linear_trace.json").read_text())
        del data["trace_entries"][0]["summary"]
        p = PROJECT / "tmp_test_msum.json"
        p.write_text(json.dumps(data))
        try:
            cmd = [sys.executable, str(SCRIPT), str(p)]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT))
            result = json.loads(r.stdout)
            assert result["status"] == "failed"
            assert "missing_entry_summary" in _errors(result)
        finally:
            p.unlink()


class TestContentEmptySummary:
    def test_fails(self):
        data = json.loads((FIXTURES / "accepted_linear_trace.json").read_text())
        data["trace_entries"][0]["summary"] = "   "
        p = PROJECT / "tmp_test_esum.json"
        p.write_text(json.dumps(data))
        try:
            cmd = [sys.executable, str(SCRIPT), str(p)]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT))
            result = json.loads(r.stdout)
            assert result["status"] == "failed"
            assert "empty_entry_summary" in _errors(result)
        finally:
            p.unlink()


# ── Evidence validation ────────────────────────────────────────────

class TestEvidenceMissingHashForRef:
    def test_fails(self):
        data = json.loads((FIXTURES / "accepted_linear_trace.json").read_text())
        data["trace_entries"][0]["source_ref"] = "some_ref"
        del data["trace_entries"][0]["evidence_hash"]
        p = PROJECT / "tmp_test_ehash.json"
        p.write_text(json.dumps(data))
        try:
            cmd = [sys.executable, str(SCRIPT), str(p)]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT))
            result = json.loads(r.stdout)
            assert result["status"] == "failed"
            assert "missing_evidence_hash_for_ref" in _errors(result)
        finally:
            p.unlink()


class TestEvidenceInvalidHashFormat:
    def test_fails(self):
        data = json.loads((FIXTURES / "accepted_linear_trace.json").read_text())
        data["trace_entries"][0]["evidence_hash"] = "not-a-valid-hash"
        p = PROJECT / "tmp_test_ehf.json"
        p.write_text(json.dumps(data))
        try:
            cmd = [sys.executable, str(SCRIPT), str(p)]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT))
            result = json.loads(r.stdout)
            assert result["status"] == "failed"
            assert "invalid_evidence_hash_format" in _errors(result)
        finally:
            p.unlink()


# ── Integrity validation ───────────────────────────────────────────

class TestIntegrityChainRootHashMismatch:
    def test_fails(self):
        data = json.loads((FIXTURES / "accepted_linear_trace.json").read_text())
        data["integrity"]["chain_root_hash"] = "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
        p = PROJECT / "tmp_test_crh.json"
        p.write_text(json.dumps(data))
        try:
            cmd = [sys.executable, str(SCRIPT), str(p)]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT))
            result = json.loads(r.stdout)
            assert result["status"] == "failed"
            assert "chain_root_hash_mismatch" in _errors(result)
        finally:
            p.unlink()


class TestIntegrityEntryCountMismatch:
    def test_fails(self):
        data = json.loads((FIXTURES / "accepted_linear_trace.json").read_text())
        data["integrity"]["entry_count"] = 99
        p = PROJECT / "tmp_test_ec.json"
        p.write_text(json.dumps(data))
        try:
            cmd = [sys.executable, str(SCRIPT), str(p)]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT))
            result = json.loads(r.stdout)
            assert result["status"] == "failed"
            assert "entry_count_mismatch" in _errors(result)
        finally:
            p.unlink()


# ── Governance validation ──────────────────────────────────────────

class TestGovernanceViolationCountMismatch:
    def test_fails(self):
        data = json.loads((FIXTURES / "accepted_governance_rejection_trace.json").read_text())
        data["trace_summary"]["governance_violations"] = 0
        p = PROJECT / "tmp_test_gv.json"
        p.write_text(json.dumps(data))
        try:
            cmd = [sys.executable, str(SCRIPT), str(p)]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT))
            result = json.loads(r.stdout)
            assert result["status"] == "failed"
            assert "governance_violation_count_mismatch" in _errors(result)
        finally:
            p.unlink()


class TestGovernanceEntryTypeCountsMismatch:
    def test_fails(self):
        data = json.loads((FIXTURES / "accepted_linear_trace.json").read_text())
        data["trace_summary"]["entry_type_counts"] = {"observation": 99}
        p = PROJECT / "tmp_test_etc.json"
        p.write_text(json.dumps(data))
        try:
            cmd = [sys.executable, str(SCRIPT), str(p)]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT))
            result = json.loads(r.stdout)
            assert result["status"] == "failed"
            assert "entry_type_counts_mismatch" in _errors(result)
        finally:
            p.unlink()


# ── Directory scan ─────────────────────────────────────────────────

class TestDirectoryScan:
    def test_all_fixtures(self):
        cmd = [sys.executable, str(SCRIPT), str(FIXTURES)]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT))
        result = json.loads(r.stdout)
        assert result["total_artifacts"] == 7
        assert result["passed_count"] == 2
        assert result["failed_count"] == 5
