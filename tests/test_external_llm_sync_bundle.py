#!/usr/bin/env python3
"""Tests for the external LLM sync bundle validator."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add scripts/ to path for import
SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import validate_external_llm_sync_bundle as validator

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples" / "external_llm_sync"
SCHEMA_VERSION = "core.external_llm_sync_bundle.v1"
PLACEHOLDER_FP = "sha256:" + "a" * 64


def _make_bundle(**overrides) -> dict:
    """Build a valid bundle with optional overrides."""
    bundle = {
        "schema_version": SCHEMA_VERSION,
        "type": "external_llm_sync_bundle",
        "bundle_id": "test:bundle:v1",
        "producer": {"id": "external_llm:test:v1", "kind": "llm_classification"},
        "context": {
            "context_budget_ref": "context_budget:test:v1",
            "read_refs": ["llm_context"],
            "query_fingerprint": PLACEHOLDER_FP,
        },
        "retrieval": {
            "retrieval_profile": "controlled_retrieval:test_v1",
            "context_bundle_fingerprint": PLACEHOLDER_FP,
            "freshness": "fresh",
        },
        "candidate": {
            "candidate_type": "classification_candidate",
            "candidate_ref": "test/cixture.json",
            "candidate_fingerprint": PLACEHOLDER_FP,
        },
        "evidence": {
            "evidence_bundle_fingerprint": PLACEHOLDER_FP,
            "missing_facts": [],
        },
        "safety": {
            "authority": "advisory_only",
            "private_data_included": False,
            "unbounded_context_used": False,
            "tool_execution_requested": False,
        },
        "status": "accepted",
    }
    bundle.update(overrides)
    return bundle


def test_accepted_bundle_passes() -> None:
    result = validator._validate_one(_make_bundle(), "test:accepted")
    assert result["status"] == "passed", f"Expected passed, got {result}"
    assert result["errors"] == []


def test_private_data_rejected() -> None:
    bundle = _make_bundle(safety={
        "authority": "advisory_only",
        "private_data_included": True,
        "unbounded_context_used": False,
        "tool_execution_requested": False,
    })
    result = validator._validate_one(bundle, "test:private_data")
    assert result["status"] == "failed"
    codes = [e["code"] for e in result["errors"]]
    assert "private_data_included" in codes


def test_unbounded_context_rejected() -> None:
    bundle = _make_bundle(safety={
        "authority": "advisory_only",
        "private_data_included": False,
        "unbounded_context_used": True,
        "tool_execution_requested": False,
    })
    result = validator._validate_one(bundle, "test:unbounded")
    assert result["status"] == "failed"
    codes = [e["code"] for e in result["errors"]]
    assert "unbounded_context_used" in codes


def test_tool_execution_requested_rejected() -> None:
    bundle = _make_bundle(safety={
        "authority": "advisory_only",
        "private_data_included": False,
        "unbounded_context_used": False,
        "tool_execution_requested": True,
    })
    result = validator._validate_one(bundle, "test:tool_exec")
    assert result["status"] == "failed"
    codes = [e["code"] for e in result["errors"]]
    assert "tool_execution_requested" in codes


def test_non_advisory_authority_rejected() -> None:
    bundle = _make_bundle(safety={
        "authority": "executive",
        "private_data_included": False,
        "unbounded_context_used": False,
        "tool_execution_requested": False,
    })
    result = validator._validate_one(bundle, "test:authority")
    assert result["status"] == "failed"
    codes = [e["code"] for e in result["errors"]]
    assert "non_advisory_authority" in codes


def test_accepted_with_missing_facts_rejected() -> None:
    bundle = _make_bundle(
        status="accepted",
        evidence={
            "evidence_bundle_fingerprint": PLACEHOLDER_FP,
            "missing_facts": ["domain_boundary_unknown"],
        },
    )
    result = validator._validate_one(bundle, "test:missing_facts_accepted")
    assert result["status"] == "failed"
    codes = [e["code"] for e in result["errors"]]
    assert "accepted_with_missing_facts" in codes


def test_clarification_with_missing_facts_passes() -> None:
    bundle = _make_bundle(
        status="clarification_needed",
        evidence={
            "evidence_bundle_fingerprint": PLACEHOLDER_FP,
            "missing_facts": ["domain_boundary_unknown"],
        },
    )
    result = validator._validate_one(bundle, "test:clarification")
    assert result["status"] == "passed", f"Expected passed, got {result}"


def test_invalid_fingerprint_rejected() -> None:
    bundle = _make_bundle(
        context={
            "context_budget_ref": "context_budget:test:v1",
            "read_refs": ["llm_context"],
            "query_fingerprint": "not-a-sha256",
        },
    )
    result = validator._validate_one(bundle, "test:bad_fp")
    assert result["status"] == "failed"
    codes = [e["code"] for e in result["errors"]]
    assert any("invalid_" in c and "fingerprint" in c for c in codes)


def test_examples_accepted_sync_bundle_passes() -> None:
    path = EXAMPLES_DIR / "accepted_sync_bundle.json"
    if not path.exists():
        return  # skip if not present
    result = validator.validate_file(path)
    assert result["status"] == "passed", f"accepted_sync_bundle.json: {result}"


def test_examples_clarification_passes() -> None:
    path = EXAMPLES_DIR / "clarification_missing_fact.json"
    if not path.exists():
        return
    result = validator.validate_file(path)
    assert result["status"] == "passed", f"clarification_missing_fact.json: {result}"


def test_examples_rejected_private_data_fails() -> None:
    path = EXAMPLES_DIR / "rejected_private_data.json"
    if not path.exists():
        return
    result = validator.validate_file(path)
    assert result["status"] == "failed"
    codes = [e["code"] for e in result["errors"]]
    assert "private_data_included" in codes


def test_examples_rejected_unbounded_context_fails() -> None:
    path = EXAMPLES_DIR / "rejected_unbounded_context.json"
    if not path.exists():
        return
    result = validator.validate_file(path)
    assert result["status"] == "failed"
    codes = [e["code"] for e in result["errors"]]
    assert "unbounded_context_used" in codes


def test_directory_validation() -> None:
    if not EXAMPLES_DIR.exists():
        return
    results = validator.validate_directory(EXAMPLES_DIR)
    assert len(results) == 4
    passed = [r for r in results if r["status"] == "passed"]
    failed = [r for r in results if r["status"] == "failed"]
    assert len(passed) == 2
    assert len(failed) == 2


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
