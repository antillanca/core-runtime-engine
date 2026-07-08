from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas" / "core"


def _schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def _validate(schema_name: str, payload: dict) -> None:
    jsonschema.validate(instance=payload, schema=_schema(schema_name))


def test_control_decision_schema_contract():
    schema = _schema("control_decision.v1.json")
    assert schema["title"] == "ControlDecision.v1"
    assert schema["properties"]["schema_version"]["const"] == "core.control_decision.v1"
    assert schema["properties"]["decision"]["enum"] == [
        "allow",
        "simulate_only",
        "require_confirmation",
        "block",
    ]
    assert schema["properties"]["intent_ref"]["pattern"] == "^(?!/).+"


def test_policy_lifecycle_schema_contract():
    schema = _schema("policy_lifecycle.v1.json")
    assert schema["title"] == "PolicyLifecycle.v1"
    assert schema["properties"]["schema_version"]["const"] == "core.policy_lifecycle.v1"
    assert schema["properties"]["status"]["enum"] == ["draft", "active", "superseded", "retired"]
    assert schema["properties"]["approval_refs"]["minItems"] == 1


def test_execution_receipt_schema_contract():
    schema = _schema("execution_receipt.v1.json")
    assert schema["title"] == "ExecutionReceipt.v1"
    assert schema["properties"]["schema_version"]["const"] == "core.execution_receipt.v1"
    assert schema["properties"]["status"]["enum"] == ["succeeded", "failed", "skipped", "simulated"]
    assert schema["properties"]["executor_ref"]["pattern"] == "^(?!/).+"


def test_control_decision_valid_fixture_rejects_absolute_path_refs():
    valid = {
        "schema_version": "core.control_decision.v1",
        "type": "control_decision",
        "decision_id": "decision_001",
        "intent_ref": "intent:creator-001",
        "target_ref": "tenant_a:order_cancel:order-123",
        "decision": "require_confirmation",
        "reason": "policy_requires_human_confirmation",
        "policy_refs": ["policy:order_cancel:v3"],
        "entropy_signal_refs": ["signal:missing_evidence:001"],
        "reversibility_class": "compensable",
        "evidence_required": ["receipt", "audit_log"],
        "source_refs": ["intent:creator-001"],
        "evidence_refs": ["artifact:private/evidence/decision_001.json"],
        "created_at": "2026-06-01T00:00:00Z",
        "fingerprint": "abc123",
    }
    _validate("control_decision.v1.json", valid)

    invalid = dict(valid)
    invalid["policy_refs"] = ["/home/real-user/private/policy.json"]
    with pytest.raises(jsonschema.ValidationError):
        _validate("control_decision.v1.json", invalid)


def test_policy_lifecycle_valid_fixture_rejects_absolute_path_refs():
    valid = {
        "schema_version": "core.policy_lifecycle.v1",
        "type": "policy_lifecycle",
        "policy_id": "policy_order_cancel",
        "policy_version": "v3",
        "status": "active",
        "effective_from": "2026-06-01T00:00:00Z",
        "effective_to": None,
        "supersedes": "policy_order_cancel:v2",
        "scope": {
            "domain": "tenant_a",
            "action_family": "order_cancel",
        },
        "change_reason": "refund_now_requires_fee",
        "approval_refs": ["approval:bp-001"],
        "source_refs": ["policy:order_cancel:v3"],
        "evidence_refs": ["artifact:private/reports/policy-v3.md"],
        "fingerprint": "def456",
    }
    _validate("policy_lifecycle.v1.json", valid)

    invalid = dict(valid)
    invalid["approval_refs"] = ["/tmp/approval.json"]
    with pytest.raises(jsonschema.ValidationError):
        _validate("policy_lifecycle.v1.json", invalid)


def test_execution_receipt_valid_fixture_rejects_absolute_path_refs():
    valid = {
        "schema_version": "core.execution_receipt.v1",
        "type": "execution_receipt",
        "receipt_id": "receipt_001",
        "executor_ref": "executor:tenant_a",
        "decision_ref": "decision:decision_001",
        "command_ref": "command:order_cancel:123",
        "status": "succeeded",
        "state_transition_refs": ["transition:order_cancel:123"],
        "evidence_refs": ["artifact:private/reports/receipt_001.json"],
        "source_refs": ["command:order_cancel:123"],
        "created_at": "2026-06-01T00:00:00Z",
        "fingerprint": "ghi789",
    }
    _validate("execution_receipt.v1.json", valid)

    invalid = dict(valid)
    invalid["decision_ref"] = "/home/real-user/private/decision.json"
    with pytest.raises(jsonschema.ValidationError):
        _validate("execution_receipt.v1.json", invalid)
