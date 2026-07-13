"""Tests for validate_downstream_bridge_adapter.py.

Covers all 20 rejection codes across 6 layers.
Fixtures are loaded from examples/bridge_adapters/.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


VALIDATOR = Path("scripts/validate_downstream_bridge_adapter.py")
FIXTURES = Path("examples/bridge_adapters")


def _validate(filename: str) -> dict:
    path = FIXTURES / filename
    r = subprocess.run(
        [sys.executable, str(VALIDATOR), str(path)],
        capture_output=True, text=True,
    )
    return json.loads(r.stdout)


def _validate_data(data: dict) -> dict:
    # Use the validator's internal function directly
    sys.path.insert(0, str(Path("scripts").resolve()))
    from validate_downstream_bridge_adapter import validate_adapter
    return validate_adapter(data)


# ── Structural ──────────────────────────────────────────────────────

class TestStructural:
    def test_missing_schema_version(self):
        d = _validate_data({"type": "downstream_bridge_adapter"})
        codes = [e["code"] for e in d["errors"]]
        assert "missing_schema_version" in codes
        assert d["status"] == "failed"

    def test_unknown_schema_version(self):
        d = _validate_data({
            "schema_version": "v99",
            "type": "downstream_bridge_adapter",
            "adapter_id": "bridge_test_v1",
            "core_schemas_consumed": ["agent_session"],
            "translation_invariants": [{
                "invariant_id": "inv_test",
                "core_artifact_ref": "agent_session.forbids_autonomous_execution",
                "downstream_enforcement": "test",
                "verification_method": "test",
            }],
            "forbids_autonomous_execution": True,
            "forbids_private_namespace_leak": True,
            "runtime_enforcement_policy": {
                "enforcement_level": "strict",
                "fail_closed": True,
                "human_override_allowed": False,
            },
            "audit": {
                "adapter_fingerprint": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
                "created_at": "2025-01-01T00:00:00Z",
                "core_release_ref": "v8.3.0",
            },
        })
        codes = [e["code"] for e in d["errors"]]
        assert "unknown_schema_version" in codes

    def test_invalid_type(self):
        d = _validate_data({"schema_version": "v1", "type": "wrong_type"})
        codes = [e["code"] for e in d["errors"]]
        assert "invalid_type" in codes


# ── Identity ────────────────────────────────────────────────────────

class TestIdentity:
    def test_missing_adapter_id(self):
        d = _validate_data({"schema_version": "v1", "type": "downstream_bridge_adapter", "adapter_id": ""})
        codes = [e["code"] for e in d["errors"]]
        assert "missing_adapter_id" in codes

    def test_invalid_adapter_id_format(self):
        d = _validate_data({
            "schema_version": "v1",
            "type": "downstream_bridge_adapter",
            "adapter_id": "bad-format",
        })
        codes = [e["code"] for e in d["errors"]]
        assert "invalid_adapter_id_format" in codes

    def test_duplicate_core_schema_consumed(self):
        data = {
            "schema_version": "v1",
            "type": "downstream_bridge_adapter",
            "adapter_id": "bridge_test_v1",
            "core_schemas_consumed": ["agent_session", "agent_session"],
            "translation_invariants": [{
                "invariant_id": "inv_test",
                "core_artifact_ref": "agent_session.forbids_autonomous_execution",
                "downstream_enforcement": "test",
                "verification_method": "test",
            }],
            "forbids_autonomous_execution": True,
            "forbids_private_namespace_leak": True,
            "runtime_enforcement_policy": {
                "enforcement_level": "strict",
                "fail_closed": True,
                "human_override_allowed": False,
            },
            "audit": {
                "adapter_fingerprint": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
                "created_at": "2025-01-01T00:00:00Z",
                "core_release_ref": "v8.3.0",
            },
        }
        d = _validate_data(data)
        codes = [e["code"] for e in d["errors"]]
        assert "duplicate_core_schema_consumed" in codes


# ── Content ─────────────────────────────────────────────────────────

class TestContent:
    def test_empty_core_schemas_consumed(self):
        d = _validate_data({
            "schema_version": "v1",
            "type": "downstream_bridge_adapter",
            "adapter_id": "bridge_test_v1",
            "core_schemas_consumed": [],
        })
        codes = [e["code"] for e in d["errors"]]
        assert "empty_core_schemas_consumed" in codes

    def test_unknown_core_schema_referenced(self):
        r = _validate("rejected_unknown_schema_ref.json")
        codes = [e["code"] for e in r["errors"] if e["code"] != "adapter_fingerprint_mismatch"]
        assert "unknown_core_schema_referenced" in codes

    def test_empty_translation_invariants(self):
        d = _validate_data({
            "schema_version": "v1",
            "type": "downstream_bridge_adapter",
            "adapter_id": "bridge_test_v1",
            "core_schemas_consumed": ["agent_session"],
            "translation_invariants": [],
        })
        codes = [e["code"] for e in d["errors"]]
        assert "empty_translation_invariants" in codes

    def test_duplicate_invariant_id(self):
        data = {
            "schema_version": "v1",
            "type": "downstream_bridge_adapter",
            "adapter_id": "bridge_test_v1",
            "core_schemas_consumed": ["agent_session"],
            "translation_invariants": [
                {
                    "invariant_id": "inv_dup",
                    "core_artifact_ref": "agent_session.forbids_autonomous_execution",
                    "downstream_enforcement": "test",
                    "verification_method": "test",
                },
                {
                    "invariant_id": "inv_dup",
                    "core_artifact_ref": "agent_session.forbids_autonomous_execution",
                    "downstream_enforcement": "test2",
                    "verification_method": "test2",
                },
            ],
            "forbids_autonomous_execution": True,
            "forbids_private_namespace_leak": True,
            "runtime_enforcement_policy": {
                "enforcement_level": "strict",
                "fail_closed": True,
                "human_override_allowed": False,
            },
            "audit": {
                "adapter_fingerprint": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
                "created_at": "2025-01-01T00:00:00Z",
                "core_release_ref": "v8.3.0",
            },
        }
        d = _validate_data(data)
        codes = [e["code"] for e in d["errors"]]
        assert "duplicate_invariant_id" in codes

    def test_invariant_missing_core_ref(self):
        d = _validate_data({
            "schema_version": "v1",
            "type": "downstream_bridge_adapter",
            "adapter_id": "bridge_test_v1",
            "core_schemas_consumed": ["agent_session"],
            "translation_invariants": [{
                "invariant_id": "inv_test",
                "core_artifact_ref": "",
                "downstream_enforcement": "test",
                "verification_method": "test",
            }],
            "forbids_autonomous_execution": True,
            "forbids_private_namespace_leak": True,
            "runtime_enforcement_policy": {
                "enforcement_level": "strict",
                "fail_closed": True,
                "human_override_allowed": False,
            },
            "audit": {
                "adapter_fingerprint": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
                "created_at": "2025-01-01T00:00:00Z",
                "core_release_ref": "v8.3.0",
            },
        })
        codes = [e["code"] for e in d["errors"]]
        assert "invariant_missing_core_ref" in codes


# ── Governance ──────────────────────────────────────────────────────

class TestGovernance:
    def test_autonomous_execution_allowed(self):
        r = _validate("rejected_autonomous_execution.json")
        codes = [e["code"] for e in r["errors"] if e["code"] != "adapter_fingerprint_mismatch"]
        assert "autonomous_execution_allowed" in codes

    def test_private_namespace_leak_not_forbidden(self):
        r = _validate("rejected_private_namespace_leak.json")
        codes = [e["code"] for e in r["errors"] if e["code"] != "adapter_fingerprint_mismatch"]
        assert "private_namespace_leak_not_forbidden" in codes

    def test_fail_closed_not_set(self):
        r = _validate("rejected_fail_closed_false.json")
        codes = [e["code"] for e in r["errors"] if e["code"] != "adapter_fingerprint_mismatch"]
        assert "fail_closed_not_set" in codes

    def test_human_override_without_emergency(self):
        d = _validate_data({
            "schema_version": "v1",
            "type": "downstream_bridge_adapter",
            "adapter_id": "bridge_test_v1",
            "core_schemas_consumed": ["agent_session"],
            "translation_invariants": [{
                "invariant_id": "inv_test",
                "core_artifact_ref": "agent_session.forbids_autonomous_execution",
                "downstream_enforcement": "test",
                "verification_method": "test",
            }],
            "forbids_autonomous_execution": True,
            "forbids_private_namespace_leak": True,
            "runtime_enforcement_policy": {
                "enforcement_level": "strict",
                "fail_closed": True,
                "human_override_allowed": True,
            },
            "audit": {
                "adapter_fingerprint": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
                "created_at": "2025-01-01T00:00:00Z",
                "core_release_ref": "v8.3.0",
            },
        })
        codes = [e["code"] for e in d["errors"]]
        assert "human_override_without_emergency" in codes

    def test_enforcement_level_invalid(self):
        d = _validate_data({
            "schema_version": "v1",
            "type": "downstream_bridge_adapter",
            "adapter_id": "bridge_test_v1",
            "core_schemas_consumed": ["agent_session"],
            "translation_invariants": [{
                "invariant_id": "inv_test",
                "core_artifact_ref": "agent_session.forbids_autonomous_execution",
                "downstream_enforcement": "test",
                "verification_method": "test",
            }],
            "forbids_autonomous_execution": True,
            "forbids_private_namespace_leak": True,
            "runtime_enforcement_policy": {
                "enforcement_level": "invalid_level",
                "fail_closed": True,
                "human_override_allowed": False,
            },
            "audit": {
                "adapter_fingerprint": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
                "created_at": "2025-01-01T00:00:00Z",
                "core_release_ref": "v8.3.0",
            },
        })
        codes = [e["code"] for e in d["errors"]]
        assert "enforcement_level_invalid" in codes


# ── Integrity ───────────────────────────────────────────────────────

class TestIntegrity:
    def test_adapter_fingerprint_mismatch(self):
        r = _validate("rejected_autonomous_execution.json")
        codes = [e["code"] for e in r["errors"]]
        assert "adapter_fingerprint_mismatch" in codes

    def test_consumed_schema_not_in_core_registry(self):
        r = _validate("rejected_unknown_schema_ref.json")
        codes = [e["code"] for e in r["errors"] if e["code"] != "adapter_fingerprint_mismatch"]
        assert "unknown_core_schema_referenced" in codes

    def test_verification_method_not_declared(self):
        r = _validate("rejected_missing_verification_method.json")
        codes = [e["code"] for e in r["errors"] if e["code"] != "adapter_fingerprint_mismatch"]
        assert "verification_method_not_declared" in codes


# ── Fixture acceptance ─────────────────────────────────────────────

class TestFixtureAcceptance:
    def test_accepted_strict_bridge(self):
        r = _validate("accepted_strict_bridge.json")
        assert r["status"] == "passed"

    def test_accepted_emergency_bridge(self):
        r = _validate("accepted_emergency_bridge.json")
        assert r["status"] == "passed"


# ── Fixture rejection ──────────────────────────────────────────────

class TestFixtureRejection:
    def test_rejected_autonomous_execution(self):
        r = _validate("rejected_autonomous_execution.json")
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"] if e["code"] != "adapter_fingerprint_mismatch"]
        assert "autonomous_execution_allowed" in codes

    def test_rejected_private_namespace_leak(self):
        r = _validate("rejected_private_namespace_leak.json")
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"] if e["code"] != "adapter_fingerprint_mismatch"]
        assert "private_namespace_leak_not_forbidden" in codes

    def test_rejected_unknown_schema_ref(self):
        r = _validate("rejected_unknown_schema_ref.json")
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"] if e["code"] != "adapter_fingerprint_mismatch"]
        assert "unknown_core_schema_referenced" in codes

    def test_rejected_fail_closed_false(self):
        r = _validate("rejected_fail_closed_false.json")
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"] if e["code"] != "adapter_fingerprint_mismatch"]
        assert "fail_closed_not_set" in codes

    def test_rejected_missing_verification(self):
        r = _validate("rejected_missing_verification_method.json")
        assert r["status"] == "failed"
        codes = [e["code"] for e in r["errors"] if e["code"] != "adapter_fingerprint_mismatch"]
        assert "verification_method_not_declared" in codes
