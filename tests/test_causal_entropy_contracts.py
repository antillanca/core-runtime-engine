from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from core_runtime.core import available_contracts, contract_schema_path, load_contract_schema


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas" / "core"


def _schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def test_causal_entropy_contracts_are_registered():
    contracts = available_contracts()
    assert "state_transition.v1" in contracts
    assert "entropy_signal.v1" in contracts
    assert "causal_trace.v1" in contracts
    assert "reversibility_policy.v1" in contracts


def test_contract_loader_paths_resolve_to_public_schema_tree():
    assert contract_schema_path("state_transition.v1") == SCHEMA_DIR / "state_transition.v1.json"
    assert contract_schema_path("entropy_signal.v1") == SCHEMA_DIR / "entropy_signal.v1.json"
    assert contract_schema_path("causal_trace.v1") == SCHEMA_DIR / "causal_trace.v1.json"
    assert contract_schema_path("reversibility_policy.v1") == SCHEMA_DIR / "reversibility_policy.v1.json"


def test_contract_loader_reads_new_schema_objects():
    schema = load_contract_schema("state_transition.v1")
    assert schema["title"] == "StateTransition.v1"
    assert schema["properties"]["reversibility_class"]["enum"] == [
        "reversible",
        "compensable",
        "irreversible",
        "unknown",
    ]


def test_state_transition_schema_contract():
    schema = _schema("state_transition.v1.json")
    assert schema["title"] == "StateTransition.v1"
    assert schema["properties"]["schema_version"]["const"] == "core.state_transition.v1"
    assert schema["properties"]["type"]["const"] == "state_transition"
    assert schema["properties"]["before_ref"]["pattern"] == "^(?!/).+"
    assert schema["properties"]["cause_refs"]["items"]["pattern"] == "^(?!/).+"
    assert schema["properties"]["evidence_refs"]["items"]["pattern"] == "^(?!/).+"


def test_entropy_signal_schema_contract():
    schema = _schema("entropy_signal.v1.json")
    assert schema["title"] == "EntropySignal.v1"
    assert schema["properties"]["schema_version"]["const"] == "core.entropy_signal.v1"
    assert schema["properties"]["type"]["const"] == "entropy_signal"
    assert schema["properties"]["signal_type"]["enum"] == [
        "repetition",
        "context_bloat",
        "state_drift",
        "invariant_violation",
        "cost_growth",
        "ambiguous_intent",
        "missing_evidence",
        "stale_memory",
        "manual_review_required",
    ]


def test_causal_trace_schema_contract():
    schema = _schema("causal_trace.v1.json")
    assert schema["title"] == "CausalTrace.v1"
    assert schema["properties"]["schema_version"]["const"] == "core.causal_trace.v1"
    assert schema["properties"]["type"]["const"] == "causal_trace"
    assert schema["properties"]["root_ref"]["pattern"] == "^(?!/).+"
    assert schema["properties"]["nodes"]["items"]["properties"]["ref"]["pattern"] == "^(?!/).+"
    assert schema["properties"]["edges"]["items"]["properties"]["from_ref"]["pattern"] == "^(?!/).+"


def test_reversibility_policy_schema_contract():
    schema = _schema("reversibility_policy.v1.json")
    assert schema["title"] == "ReversibilityPolicy.v1"
    assert schema["properties"]["schema_version"]["const"] == "core.reversibility_policy.v1"
    assert schema["properties"]["type"]["const"] == "reversibility_policy"
    assert schema["properties"]["reversibility_class"]["enum"] == [
        "reversible",
        "compensable",
        "irreversible",
        "unknown",
    ]


@pytest.mark.parametrize(
    "schema_name,valid,invalid",
    [
        (
            "state_transition.v1.json",
            {
                "schema_version": "core.state_transition.v1",
                "type": "state_transition",
                "transition_id": "transition_001",
                "source_type": "run",
                "source_id": "run-001",
                "before_ref": "run:run-001:before",
                "after_ref": "run:run-001:after",
                "cause_refs": ["run:run-001:state"],
                "effect_refs": ["memory:memory-001"],
                "actor_kind": "system",
                "timestamp": "2026-06-01T00:00:00Z",
                "reversibility_class": "compensable",
                "source_refs": ["run:run-001"],
                "evidence_refs": ["report:reports/run-001.md"],
                "fingerprint": "abc123",
            },
            {
                "schema_version": "core.state_transition.v1",
                "type": "state_transition",
                "transition_id": "transition_001",
                "source_type": "run",
                "source_id": "run-001",
                "before_ref": "/home/real-user/private/before.json",
                "after_ref": "run:run-001:after",
                "cause_refs": ["run:run-001:state"],
                "effect_refs": ["memory:memory-001"],
                "actor_kind": "system",
                "timestamp": "2026-06-01T00:00:00Z",
                "reversibility_class": "compensable",
                "source_refs": ["run:run-001"],
                "evidence_refs": ["report:reports/run-001.md"],
                "fingerprint": "abc123",
            },
        ),
        (
            "entropy_signal.v1.json",
            {
                "schema_version": "core.entropy_signal.v1",
                "type": "entropy_signal",
                "signal_id": "signal_001",
                "source_type": "run",
                "source_id": "run-001",
                "signal_type": "repetition",
                "severity": "high",
                "confidence": 0.9,
                "measurement": {"count": 4, "window": "1h"},
                "suggested_response": "compress",
                "source_refs": ["run:run-001"],
                "evidence_refs": ["report:reports/run-001.md"],
                "timestamp": "2026-06-01T00:00:00Z",
                "fingerprint": "abc123",
            },
            {
                "schema_version": "core.entropy_signal.v1",
                "type": "entropy_signal",
                "signal_id": "signal_001",
                "source_type": "run",
                "source_id": "run-001",
                "signal_type": "repetition",
                "severity": "high",
                "confidence": 0.9,
                "measurement": {"count": 4, "window": "1h"},
                "suggested_response": "compress",
                "source_refs": ["run:run-001"],
                "evidence_refs": ["/home/real-user/private/report.md"],
                "timestamp": "2026-06-01T00:00:00Z",
                "fingerprint": "abc123",
            },
        ),
        (
            "causal_trace.v1.json",
            {
                "schema_version": "core.causal_trace.v1",
                "type": "causal_trace",
                "trace_id": "trace_001",
                "root_ref": "run:run-001",
                "nodes": [
                    {"node_id": "node_1", "kind": "run", "ref": "run:run-001"},
                    {"node_id": "node_2", "kind": "memory", "ref": "memory:memory-001"},
                ],
                "edges": [
                    {"from_ref": "run:run-001", "to_ref": "memory:memory-001", "relation": "produces"}
                ],
                "source_refs": ["run:run-001"],
                "evidence_refs": ["report:reports/run-001.md"],
                "created_at": "2026-06-01T00:00:00Z",
                "fingerprint": "abc123",
            },
            {
                "schema_version": "core.causal_trace.v1",
                "type": "causal_trace",
                "trace_id": "trace_001",
                "root_ref": "run:run-001",
                "nodes": [
                    {"node_id": "node_1", "kind": "run", "ref": "/home/real-user/private/run.json"},
                    {"node_id": "node_2", "kind": "memory", "ref": "memory:memory-001"},
                ],
                "edges": [
                    {"from_ref": "run:run-001", "to_ref": "memory:memory-001", "relation": "produces"}
                ],
                "source_refs": ["run:run-001"],
                "evidence_refs": ["report:reports/run-001.md"],
                "created_at": "2026-06-01T00:00:00Z",
                "fingerprint": "abc123",
            },
        ),
        (
            "reversibility_policy.v1.json",
            {
                "schema_version": "core.reversibility_policy.v1",
                "type": "reversibility_policy",
                "policy_id": "policy_001",
                "action_family": "archive",
                "reversibility_class": "compensable",
                "compensation_required": True,
                "human_approval_required": False,
                "stop_conditions": ["missing_restore_ref"],
                "evidence_required": ["restore_ref", "audit_log"],
                "notes": ["requires restore evidence"],
                "source_refs": ["policy:archive"],
                "evidence_refs": ["report:reports/policy_001.md"],
                "created_at": "2026-06-01T00:00:00Z",
                "fingerprint": "abc123",
            },
            {
                "schema_version": "core.reversibility_policy.v1",
                "type": "reversibility_policy",
                "policy_id": "policy_001",
                "action_family": "archive",
                "reversibility_class": "compensable",
                "compensation_required": True,
                "human_approval_required": False,
                "stop_conditions": ["missing_restore_ref"],
                "evidence_required": ["restore_ref", "audit_log"],
                "notes": ["requires restore evidence"],
                "source_refs": ["/home/real-user/private/policy.json"],
                "evidence_refs": ["report:reports/policy_001.md"],
                "created_at": "2026-06-01T00:00:00Z",
                "fingerprint": "abc123",
            },
        ),
    ],
)
def test_causal_entropy_contracts_validate_and_reject_absolute_paths(schema_name, valid, invalid):
    schema = _schema(schema_name)
    jsonschema.validate(instance=valid, schema=schema)

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=invalid, schema=schema)
