from __future__ import annotations

import json
from pathlib import Path

from core_runtime.core.contract_evaluator import (
    bind_artifact_fingerprint,
    evaluate_contract_payload,
    validate_contract_structure,
)
from core_runtime.core.contract_loader import load_contract_schema
from core_runtime.core.contract_probes import build_physical_safety_case


def _codes(report: dict) -> set[str]:
    return {item["code"] for item in report["errors"]}


def _rebind(payload: dict) -> dict:
    return bind_artifact_fingerprint(payload)


def _open_objects(schema: object) -> list[dict]:
    found: list[dict] = []
    if isinstance(schema, dict):
        if schema.get("type") == "object" and isinstance(schema.get("properties"), dict):
            if schema.get("additionalProperties") is not False:
                found.append(schema)
        for value in schema.values():
            found.extend(_open_objects(value))
    elif isinstance(schema, list):
        for value in schema:
            found.extend(_open_objects(value))
    return found


def test_safety_schema_is_closed_at_every_declared_object_boundary() -> None:
    schema = load_contract_schema("physical_safety_assurance_case.v1")
    assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert _open_objects(schema) == []


def test_simulation_is_valid_but_never_deployment_authority() -> None:
    report = evaluate_contract_payload(build_physical_safety_case())
    assert report["status"] == "passed"
    assert report["details"]["achieved_assurance_level"] == "simulation_only"
    assert report["details"]["deployment_authorized"] is False
    assert report["deployment_authorized"] is False
    assert {warning["code"] for warning in report["warnings"]} == {
        "simulation_is_not_deployment_evidence"
    }


def test_hardware_in_loop_evidence_reaches_evidence_ready_only() -> None:
    report = evaluate_contract_payload(
        build_physical_safety_case(method="hardware_in_loop")
    )
    assert report["status"] == "passed"
    assert report["details"]["achieved_assurance_level"] == "evidence_ready"
    assert report["deployment_authorized"] is False


def test_independent_evidence_requires_independent_assessor_provenance() -> None:
    payload = build_physical_safety_case(method="independent_assessment")
    report = evaluate_contract_payload(payload)
    assert report["status"] == "passed"
    assert report["details"]["achieved_assurance_level"] == "independent_evidence_ready"

    for item in payload["evidence"]:
        if item["evidence_id"] == "evidence:test-suite":
            item["source_kind"] = "software"
    payload = _rebind(payload)
    report = evaluate_contract_payload(payload)
    assert "requested_assurance_level_not_met" in _codes(report)
    assert report["details"]["achieved_assurance_level"] == "rejected"


def test_requesting_more_assurance_than_evidence_provides_fails_closed() -> None:
    payload = build_physical_safety_case(
        method="simulation",
        requested_level="evidence_ready",
    )
    report = evaluate_contract_payload(payload)
    assert "requested_assurance_level_not_met" in _codes(report)


def test_absolute_truth_or_zero_risk_language_is_semantically_rejected() -> None:
    payload = build_physical_safety_case()
    payload["claim"]["scope"] = "Guaranteed safe in all circumstances."
    payload = _rebind(payload)
    assert validate_contract_structure(payload) == []
    report = evaluate_contract_payload(payload)
    assert "absolute_safety_claim_forbidden" in _codes(report)


def test_formal_demonstration_is_bounded_to_declared_model_and_proof() -> None:
    payload = build_physical_safety_case()
    payload["claim"]["claim_status"] = "demonstrated_within_model"
    payload = _rebind(payload)
    report = evaluate_contract_payload(payload)
    assert "formal_demonstration_evidence_required" in _codes(report)

    payload["claim"]["reference_classes"].append("formal_model")
    payload["claim"]["proof_refs"] = ["evidence:test-suite"]
    payload = _rebind(payload)
    report = evaluate_contract_payload(payload)
    assert report["status"] == "passed"
    assert report["knowledge_status"] == "demonstrated_within_model"
    assert report["truth_claimed"] is False


def test_average_only_evidence_is_rejected_at_the_schema_boundary() -> None:
    payload = build_physical_safety_case()
    payload["observed_envelope"]["average_only"] = True
    payload = _rebind(payload)
    errors = validate_contract_structure(payload)
    assert any(item["code"] == "schema_validation_error" for item in errors)


def test_missing_extreme_diversity_is_rejected_even_with_valid_shape() -> None:
    payload = build_physical_safety_case()
    payload["observed_envelope"]["known_extremes"][1]["direction"] = "lower"
    payload = _rebind(payload)
    assert validate_contract_structure(payload) == []
    assert "extreme_diversity_required" in _codes(evaluate_contract_payload(payload))


def test_catastrophic_hazard_requires_independent_hardware_barriers() -> None:
    payload = build_physical_safety_case()
    payload["barriers"][1]["enforcement_domain"] = "isolated_controller"
    payload["barriers"][1]["kind"] = "isolated_safety_controller"
    payload = _rebind(payload)
    report = evaluate_contract_payload(payload)
    assert "catastrophic_hazard_needs_independent_barriers" in _codes(report)
    assert "physical_isolation_required" in _codes(report)


def test_failed_or_hazardous_test_rejects_the_whole_case() -> None:
    payload = build_physical_safety_case()
    payload["verification_tests"][0]["result"] = "failed"
    payload["verification_tests"][0]["hazardous_actuation_observed"] = True
    payload = _rebind(payload)
    codes = _codes(evaluate_contract_payload(payload))
    assert "safety_test_not_passed" in codes
    assert "hazardous_actuation_observed" in codes


def test_out_of_distribution_scenario_is_mandatory() -> None:
    payload = build_physical_safety_case()
    tests = payload["verification_tests"]
    removed = next(item for item in tests if item["scenario"] == "out_of_distribution_input")
    tests.remove(removed)
    payload["hazards"][0]["test_refs"].remove(removed["test_id"])
    payload = _rebind(payload)
    report = evaluate_contract_payload(payload)
    assert "required_scenario_missing" in _codes(report)
    missing = next(item["missing"] for item in report["errors"] if item["code"] == "required_scenario_missing")
    assert missing == ["out_of_distribution_input"]


def test_evidence_cannot_come_from_the_future() -> None:
    payload = build_physical_safety_case()
    payload["evidence"][0]["captured_at"] = "2026-07-14T00:00:00+00:00"
    payload = _rebind(payload)
    assert "future_evidence_forbidden" in _codes(evaluate_contract_payload(payload))


def test_critical_ledger_events_are_required_but_ordinary_telemetry_is_not() -> None:
    payload = build_physical_safety_case()
    payload["traceability"]["recorded_event_types"].remove("unexpected_physical_outcome")
    payload = _rebind(payload)
    assert "critical_ledger_event_missing" in _codes(evaluate_contract_payload(payload))


def test_direct_llm_actuation_cannot_be_expressed_as_a_valid_case() -> None:
    payload = build_physical_safety_case()
    payload["authority_boundary"]["direct_llm_actuation"] = True
    payload = _rebind(payload)
    assert validate_contract_structure(payload)
    report = evaluate_contract_payload(payload)
    assert report["status"] == "failed"


def test_case_fingerprint_binds_every_safety_claim() -> None:
    payload = build_physical_safety_case()
    payload["hazards"][0]["safe_state"] = "Tampered state"
    report = evaluate_contract_payload(payload)
    assert "fingerprint_mismatch" in _codes(report)


def test_safety_case_is_json_serializable_without_runtime_state(tmp_path: Path) -> None:
    path = tmp_path / "case.json"
    payload = build_physical_safety_case()
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8")) == payload
