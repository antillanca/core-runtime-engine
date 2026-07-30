from __future__ import annotations

import copy

from core_runtime.core.contract_evaluator import bind_artifact_fingerprint, evaluate_contract_payload
from core_runtime.core.contract_program import execute_contract_program
from core_runtime.core.contract_probes import accepted_contract_payloads


def _program() -> dict:
    return accepted_contract_payloads()["core.contract_program.v1"]


def test_contract_program_replay_is_deterministic_and_non_authorizing() -> None:
    program = _program()
    inputs = {"classification": "bounded", "approved": True}
    first = execute_contract_program(program, inputs)
    second = execute_contract_program(program, inputs)
    assert first == second
    assert first["status"] == "passed"
    assert first["execution_authorized"] is False
    assert first["state_application_authorized"] is False
    assert first["emitted"] == [{"code": "classification_recorded", "value": "bounded"}]
    assert first["staged_transitions"] == [
        {
            "transition_id": "transition:reviewed",
            "before_ref": "state:pending",
            "after_ref": "state:reviewed",
            "reversibility_class": "reversible",
        }
    ]


def test_contract_program_discards_staged_transition_when_assertion_blocks() -> None:
    result = execute_contract_program(_program(), {"classification": "bounded", "approved": False})
    assert result["status"] == "blocked"
    assert result["staged_transitions"] == []
    assert {entry["code"] for entry in result["errors"]} == {"assertion_failed"}


def test_contract_program_requires_sealed_input_without_external_reads() -> None:
    result = execute_contract_program(_program(), {"approved": True})
    assert result["status"] == "insufficient_data"
    assert result["staged_transitions"] == []
    assert {entry["code"] for entry in result["errors"]} == {"sealed_input_missing"}


def test_contract_program_semantics_reject_undeclared_effect_authority() -> None:
    program = copy.deepcopy(_program())
    program["effect_policy"]["external_effects"] = True
    program = bind_artifact_fingerprint(program)
    report = evaluate_contract_payload(program)
    assert report["status"] == "failed"
    assert "effect_policy_forbidden" in {entry["code"] for entry in report["errors"]}


def test_public_runtime_contains_no_private_consumer_vocabulary() -> None:
    source = (__import__("pathlib").Path(__file__).resolve().parents[1] / "core_runtime" / "core" / "contract_program.py").read_text(encoding="utf-8").lower()
    for forbidden in ("hermes", "simplerestobar", "domain_scale", "queryspec"):
        assert forbidden not in source
