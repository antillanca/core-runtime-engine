"""Finite registry-only operations for the isolated ContractProgram fork.

This module deliberately exposes a small, versioned operation surface.  It is
not a dynamic evaluator and it never loads executable configuration from a
declaration.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

REGISTRY_VERSION = "core.contract_program.registry.v1"
REGISTRY_KEYS = frozenset(
    {
        "rank.quantity.v1",
        "member.scale_adapter.v1",
        "regex.grammar_context.v1",
    }
)
OPERATION_ALLOWLIST = frozenset(
    {
        "equals",
        "distinct_count",
        "is_nonempty_string",
        "rank_of",
        "min_of",
        "compare",
        "logical_and",
        "logical_or",
        "logical_not",
        "member_of",
        "regex_match",
    }
)
FORBIDDEN_CONSTRUCTS = frozenset(
    {"loop", "branch", "jump", "dynamic_import", "eval", "callback", "inline_policy"}
)

_GRAMMARS = {
    "qualified_ref": re.compile(r"^[a-z][a-z0-9_.-]{2,}:[^\s]{3,}$", re.IGNORECASE),
    "identifier": re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$"),
}


class RegistryOperationError(ValueError):
    """Raised when a candidate requests an operation outside the registry."""


def _require_arity(inputs: Sequence[Any], expected: int) -> None:
    if len(inputs) != expected:
        raise RegistryOperationError(f"registry operation requires {expected} inputs")


def execute_registry_operation(registry_key: str, inputs: Sequence[Any]) -> Any:
    """Execute one deterministic, allowlisted registry operation."""

    if registry_key not in REGISTRY_KEYS:
        raise RegistryOperationError(f"unknown registry key: {registry_key!r}")
    if not isinstance(inputs, Sequence) or isinstance(inputs, (str, bytes)):
        raise RegistryOperationError("registry inputs must be a finite sequence")

    if registry_key == "rank.quantity.v1":
        _require_arity(inputs, 1)
        value = inputs[0]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RegistryOperationError("quantity rank must be a non-negative integer")
        return value

    if registry_key == "member.scale_adapter.v1":
        _require_arity(inputs, 4)
        adapter_from, adapter_to, requested_from, requested_to = inputs
        return adapter_from == requested_from and adapter_to == requested_to

    _require_arity(inputs, 2)
    value, grammar_name = inputs
    if not isinstance(value, str) or not isinstance(grammar_name, str):
        return False
    grammar = _GRAMMARS.get(grammar_name)
    if grammar is None:
        raise RegistryOperationError(f"unknown grammar context: {grammar_name!r}")
    return bool(grammar.fullmatch(value))


def validate_registry_program(program: Mapping[str, Any]) -> list[str]:
    """Return deterministic profile errors for a candidate program."""

    errors: list[str] = []
    instructions = program.get("instructions", [])
    if not isinstance(instructions, list):
        return ["instructions must be a list"]
    for index, instruction in enumerate(instructions):
        if not isinstance(instruction, Mapping):
            errors.append(f"instructions[{index}] is not an object")
            continue
        for key in FORBIDDEN_CONSTRUCTS:
            if key in instruction:
                errors.append(f"forbidden construct {key!r} at instructions[{index}]")
        if instruction.get("opcode") == "derive" and instruction.get("operation") == "registry":
            registry_key = instruction.get("registry_key")
            if registry_key not in REGISTRY_KEYS:
                errors.append(f"unknown registry key at instructions[{index}]")
    return errors
