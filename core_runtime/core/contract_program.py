"""Closed deterministic replay for the public validation-only contract language."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any, TypedDict

from core_runtime.core.canonicalization import canonical_json_hash
from core_runtime.core.contract_evaluator import evaluate_contract_payload, input_fingerprint
from core_runtime.core.contract_program_registry import execute_registry_operation


class ContractProgramExecution(TypedDict):
    schema: str
    status: str
    authority: str
    execution_authorized: bool
    state_application_authorized: bool
    program_fingerprint: str
    input_fingerprint: str
    emitted: list[dict[str, Any]]
    staged_transitions: list[dict[str, str]]
    errors: list[dict[str, str]]
    execution_fingerprint: str


def _error(code: str, message: str, field: str) -> dict[str, str]:
    return {"code": code, "message": message, "field": field}


def execute_contract_program(program: Mapping[str, Any], sealed_inputs: Mapping[str, Any]) -> ContractProgramExecution:
    """Replay one closed program against caller-supplied sealed inputs.

    This function neither reads external state nor applies transitions. A transition
    instruction only records a candidate transition in the result for a separate,
    explicitly authorized system to evaluate.
    """

    program_payload = copy.deepcopy(dict(program))
    evaluation = evaluate_contract_payload(program_payload)
    execution: dict[str, Any] = {
        "schema": "core.contract_program_execution.v1",
        "status": "rejected" if evaluation["status"] != "passed" else "passed",
        "authority": "validation_only",
        "execution_authorized": False,
        "state_application_authorized": False,
        "program_fingerprint": str(program_payload.get("fingerprint", "")),
        "input_fingerprint": input_fingerprint(dict(sealed_inputs)),
        "emitted": [],
        "staged_transitions": [],
        "errors": [],
    }
    if evaluation["status"] != "passed":
        execution["errors"] = [
            {"code": str(item["code"]), "message": str(item["message"]), "field": str(item["field"])}
            for item in evaluation["errors"]
        ]
    else:
        values: dict[str, Any] = {}
        max_items = int(program_payload["limits"]["max_items"])
        for index, instruction in enumerate(program_payload["instructions"]):
            opcode = instruction["opcode"]
            field = f"instructions[{index}]"
            if opcode == "load":
                key = instruction["key"]
                if key not in sealed_inputs:
                    execution["status"] = "insufficient_data"
                    execution["errors"].append(_error("sealed_input_missing", "Required sealed input is absent.", f"{field}.key"))
                    break
                values[instruction["output"]] = copy.deepcopy(sealed_inputs[key])
            elif opcode == "assert":
                key = instruction["key"]
                if key not in sealed_inputs:
                    execution["status"] = "insufficient_data"
                    execution["errors"].append(_error("sealed_input_missing", "Required sealed input is absent.", f"{field}.key"))
                    break
                if sealed_inputs[key] != instruction["equals"]:
                    execution["status"] = "blocked"
                    execution["errors"].append(_error("assertion_failed", "Sealed input does not match the declared assertion.", f"{field}.equals"))
                    break
            elif opcode == "derive":
                keys = instruction["input_keys"]
                if any(key not in values for key in keys):
                    execution["status"] = "blocked"
                    execution["errors"].append(_error("derived_input_missing", "Derivation requires a prior output key.", f"{field}.input_keys"))
                    break
                if instruction["operation"] == "copy":
                    values[instruction["output"]] = copy.deepcopy(values[keys[0]])
                elif instruction["operation"] == "registry":
                    try:
                        values[instruction["output"]] = execute_registry_operation(
                            instruction["registry_key"],
                            [values[key] for key in keys],
                        )
                    except ValueError as exc:
                        execution["status"] = "blocked"
                        execution["errors"].append(_error("registry_operation_failed", str(exc), f"{field}.registry_key"))
                        break
                else:
                    values[instruction["output"]] = len(keys)
            elif opcode == "transition":
                execution["staged_transitions"].append(
                    {
                        "transition_id": instruction["transition_id"],
                        "before_ref": instruction["before_ref"],
                        "after_ref": instruction["after_ref"],
                        "reversibility_class": instruction["reversibility_class"],
                    }
                )
            elif opcode == "emit":
                key = instruction["value_key"]
                if key not in values:
                    execution["status"] = "blocked"
                    execution["errors"].append(_error("emitted_value_missing", "Emit requires a prior output key.", f"{field}.value_key"))
                    break
                execution["emitted"].append({"code": instruction["code"], "value": copy.deepcopy(values[key])})
            elif opcode == "halt":
                execution["status"] = instruction["status"]

            if len(values) > max_items:
                execution["status"] = "blocked"
                execution["errors"].append(_error("runtime_item_limit_exceeded", "Runtime output count exceeds max_items.", "limits.max_items"))
                break

    if execution["status"] != "passed":
        execution["staged_transitions"] = []
    execution["execution_fingerprint"] = f"sha256:{canonical_json_hash(execution)}"
    return execution  # type: ignore[return-value]
