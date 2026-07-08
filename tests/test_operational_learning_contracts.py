from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas" / "core"


def _schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def test_pattern_candidate_schema_contract():
    schema = _schema("pattern_candidate.v1.json")
    assert schema["title"] == "PatternCandidate.v1"
    assert schema["properties"]["schema_version"]["const"] == "core.pattern_candidate.v1"
    assert schema["properties"]["type"]["const"] == "pattern_candidate"
    assert "candidate_for_template" in schema["properties"]["classification"]["enum"]


def test_template_promotion_candidate_schema_contract():
    schema = _schema("template_promotion_candidate.v1.json")
    assert schema["title"] == "TemplatePromotionCandidate.v1"
    assert schema["properties"]["schema_version"]["const"] == "core.template_promotion_candidate.v1"
    assert schema["properties"]["human_approval_required"]["type"] == "boolean"


def test_operational_learning_event_schema_contract():
    schema = _schema("operational_learning_event.v1.json")
    assert schema["title"] == "OperationalLearningEvent.v1"
    assert schema["properties"]["schema_version"]["const"] == "core.operational_learning_event.v1"
    assert schema["required"] == [
        "schema_version",
        "event_type",
        "source_type",
        "source_id",
        "status",
        "timestamp",
        "payload",
    ]


def test_pattern_candidate_valid_fixture_rejects_private_path_leak():
    schema = _schema("pattern_candidate.v1.json")
    valid = {
        "schema_version": "core.pattern_candidate.v1",
        "type": "pattern_candidate",
        "pattern_id": "closeout_abcdef123456",
        "source_type": "run",
        "source_id": "run-001",
        "classification": "candidate_for_closeout_builder",
        "confidence": 0.9,
        "occurrences": 3,
        "normalized_signature": {"family": "run", "status": "passed"},
        "source_refs": ["run:run-001/state.json"],
        "suggested_action": "Keep as structured closeout assembly.",
    }
    jsonschema.validate(instance=valid, schema=schema)

    invalid = dict(valid)
    invalid["source_refs"] = ["/home/real-user/private/run-001/state.json"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=invalid, schema=schema)


def test_template_promotion_candidate_valid_fixture():
    schema = _schema("template_promotion_candidate.v1.json")
    valid = {
        "schema_version": "core.template_promotion_candidate.v1",
        "type": "template_promotion_candidate",
        "template_candidate_id": "tpl_001",
        "source_pattern_id": "closeout_abcdef123456",
        "required_inputs": ["run_state", "chain_state"],
        "output_contract": "downstream.structured_closeout_summary.v1",
        "expected_evidence": ["json_schema_validation", "unit_tests"],
        "risk_tier": "low",
        "stop_conditions": ["missing_state", "ambiguous_inputs"],
        "human_approval_required": False,
    }
    jsonschema.validate(instance=valid, schema=schema)


def test_operational_learning_event_valid_fixture():
    schema = _schema("operational_learning_event.v1.json")
    valid = {
        "schema_version": "core.operational_learning_event.v1",
        "event_type": "pattern_detected",
        "source_type": "run",
        "source_id": "run-001",
        "status": "passed",
        "timestamp": "2026-06-01T00:00:00Z",
        "payload": {"pattern_id": "closeout_abcdef123456"},
    }
    jsonschema.validate(instance=valid, schema=schema)
