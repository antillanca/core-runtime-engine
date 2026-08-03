from __future__ import annotations

import copy

from core_runtime.core.contract_evaluator import bind_artifact_fingerprint, evaluate_contract_payload
from core_runtime.core.contract_program import execute_contract_program
from core_runtime.core.contract_probes import accepted_contract_payloads


def _registry_program() -> dict:
    program = copy.deepcopy(accepted_contract_payloads()["core.contract_program.v1"])
    program["capabilities"] = ["read_input", "derive", "emit_result"]
    program["limits"] = {"max_steps": 4, "max_items": 4, "max_emits": 1}
    program["instructions"] = [
        {"opcode": "load", "key": "quantity", "output": "quantity_value"},
        {
            "opcode": "derive",
            "operation": "registry",
            "registry_key": "rank.quantity.v1",
            "input_keys": ["quantity_value"],
            "output": "ranked_quantity",
        },
        {"opcode": "emit", "code": "quantity_ranked", "value_key": "ranked_quantity"},
        {"opcode": "halt", "status": "passed"},
    ]
    return bind_artifact_fingerprint(program)


def test_registry_operation_has_evaluator_runtime_parity() -> None:
    program = _registry_program()
    evaluation = evaluate_contract_payload(program)
    assert evaluation["status"] == "passed"

    execution = execute_contract_program(program, {"quantity": 3})
    assert execution["status"] == "passed"
    assert execution["execution_authorized"] is False
    assert execution["emitted"] == [{"code": "quantity_ranked", "value": 3}]


def test_registry_operation_fails_closed_on_invalid_arity() -> None:
    program = _registry_program()
    program["instructions"][1]["input_keys"] = ["quantity_value", "quantity_value"]
    program = bind_artifact_fingerprint(program)
    evaluation = evaluate_contract_payload(program)
    assert evaluation["status"] == "failed"
    assert evaluation["errors"]
