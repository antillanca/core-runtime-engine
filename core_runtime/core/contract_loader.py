"""Load public CORE v10 contract schemas from the repository tree."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_ROOT = PROJECT_ROOT / "schemas" / "core"
CONTRACT_SCHEMAS = {
    "causal_trace.v1": "causal_trace.v1.json",
    "entropy_signal.v1": "entropy_signal.v1.json",
    "control_decision.v1": "control_decision.v1.json",
    "execution_receipt.v1": "execution_receipt.v1.json",
    "pattern_candidate.v1": "pattern_candidate.v1.json",
    "memory_artifact.v1": "memory_artifact.v1.json",
    "task_closeout.v1": "task_closeout.v1.json",
    "effect_result.v1": "effect_result.v1.json",
    "memory_generation_result.v1": "memory_generation_result.v1.json",
    "operational_learning_event.v1": "operational_learning_event.v1.json",
    "policy_lifecycle.v1": "policy_lifecycle.v1.json",
    "context_threshold.v1": "context_threshold.v1.json",
    "context_gate.v1": "context_gate.v1.json",
    "retention_manifest.v1": "retention_manifest.v1.json",
    "reversibility_policy.v1": "reversibility_policy.v1.json",
    "state_transition.v1": "state_transition.v1.json",
    "template_promotion_candidate.v1": "template_promotion_candidate.v1.json",
    "physical_safety_assurance_case.v1": "physical_safety_assurance_case.v1.json",
}


def available_contracts() -> tuple[str, ...]:
    """Return the known public contract names in stable order."""

    return tuple(sorted(CONTRACT_SCHEMAS))


def contract_schema_path(contract_name: str) -> Path:
    """Resolve the schema file for a known contract name."""

    filename = CONTRACT_SCHEMAS.get(contract_name)
    if filename is None:
        raise KeyError(f"unknown contract schema: {contract_name}")
    return SCHEMA_ROOT / filename


def load_contract_schema(contract_name: str) -> dict[str, Any]:
    """Load and parse a public contract schema from `schemas/core/`."""

    path = contract_schema_path(contract_name)
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"contract schema must be a JSON object: {path}")
    return payload
