from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

from core_runtime.core.contract_program_v2 import (
    ESLABONES,
    SCHEMA_VERSION,
    VERDICTS,
    evaluate_contract_v2,
)

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples" / "contract_program_v2"
SCHEMA = json.loads((ROOT / "schemas" / "core" / "contract_program.v2.json").read_text())
VALIDATOR = Draft7Validator(SCHEMA)


def _load(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text())


def test_constants_are_stable() -> None:
    assert len(ESLABONES) == 6
    assert ESLABONES == ["PERFIL", "VOCABULARIO", "QUERYSPEC", "RESULTADO", "VISTA", "EVIDENCIA"]
    assert len(VERDICTS) == 9
    assert "aborted" in VERDICTS
    assert "pass" in VERDICTS
    assert SCHEMA_VERSION == "core.contract_program.v2"


def test_accepted_contract_passes_schema_and_runtime() -> None:
    contract = _load("accepted_v1.json")
    assert not list(VALIDATOR.iter_errors(contract)), "accepted fixture should be schema-valid"
    result = evaluate_contract_v2(contract)
    assert result["verdict"] == "pass"
    assert result["findings"] == []
    assert result["deterministic"] is True
    assert result["llm_used"] is False
    assert result["schema_version"] == SCHEMA_VERSION


def test_evaluation_is_deterministic() -> None:
    contract = _load("accepted_v1.json")
    first = evaluate_contract_v2(contract)
    second = evaluate_contract_v2(contract)
    assert first == second
    assert first["fingerprint"] == second["fingerprint"]


def test_fingerprint_is_stable_and_content_addressed() -> None:
    contract = _load("accepted_v1.json")
    result = evaluate_contract_v2(contract)
    expected = "sha256:" + __import__("hashlib").sha256(
        json.dumps(contract, sort_keys=True).encode()
    ).hexdigest()
    assert result["fingerprint"] == expected


def test_missing_eslabones_returns_incomplete() -> None:
    contract = {"schema_version": SCHEMA_VERSION, "contract_id": "x", "eslabones": []}
    result = evaluate_contract_v2(contract)
    assert result["verdict"] == "incomplete"
    assert result["findings"][0]["code"] == "incomplete"


def test_wrong_order_returns_incomplete() -> None:
    contract = _load("rejected_incomplete_wrong_order.json")
    assert not list(VALIDATOR.iter_errors(contract)), "should pass schema"
    result = evaluate_contract_v2(contract)
    assert result["verdict"] == "incomplete"
    assert any(f["code"] == "incomplete" for f in result["findings"])


def test_missing_composition_rule_returns_scale_violation() -> None:
    contract = _load("rejected_scale_violation.json")
    result = evaluate_contract_v2(contract)
    assert result["verdict"] == "scale_violation"
    assert any(f["code"] == "scale_violation" for f in result["findings"])


def test_invalid_authority_ceiling_returns_authority_violation() -> None:
    contract = _load("rejected_authority_violation.json")
    result = evaluate_contract_v2(contract)
    assert result["verdict"] == "authority_violation"
    assert any(f["code"] == "authority_violation" for f in result["findings"])


def test_empty_declared_loss_returns_loss_undeclared() -> None:
    contract = _load("rejected_loss_undeclared.json")
    result = evaluate_contract_v2(contract)
    assert result["verdict"] == "loss_undeclared"
    assert any(f["code"] == "loss_undeclared" for f in result["findings"])


def test_empty_temporal_invariant_returns_temporal_violation() -> None:
    contract = _load("rejected_temporal_violation.json")
    result = evaluate_contract_v2(contract)
    assert result["verdict"] == "temporal_violation"
    assert any(f["code"] == "temporal_violation" for f in result["findings"])


def test_empty_translation_map_returns_translation_missing() -> None:
    contract = _load("rejected_translation_missing.json")
    result = evaluate_contract_v2(contract)
    assert result["verdict"] == "translation_missing"
    assert any(f["code"] == "translation_missing" for f in result["findings"])


def test_agent_confirmed_intent_returns_intent_unconfirmed() -> None:
    contract = _load("rejected_intent_unconfirmed.json")
    assert not list(VALIDATOR.iter_errors(contract)), "should pass schema (agent is valid enum)"
    result = evaluate_contract_v2(contract)
    assert result["verdict"] == "intent_unconfirmed"
    assert any(f["code"] == "intent_unconfirmed" for f in result["findings"])


def test_operator_confirmed_intent_passes() -> None:
    contract = _load("accepted_v1.json")
    result = evaluate_contract_v2(contract)
    # accepted fixture has paraphrase_intent.confirmed_by="operator" in PERFIL
    assert result["verdict"] == "pass"


def test_first_finding_determines_verdict() -> None:
    """When multiple findings exist, the first one's code is the verdict."""
    contract = _load("rejected_incomplete_wrong_order.json")
    result = evaluate_contract_v2(contract)
    assert result["verdict"] == result["findings"][0]["code"]


def test_contract_id_is_preserved_in_result() -> None:
    contract = _load("accepted_v1.json")
    result = evaluate_contract_v2(contract)
    assert result["contract_id"] == contract["contract_id"]


def test_public_runtime_contains_no_private_vocabulary() -> None:
    source = (ROOT / "core_runtime" / "core" / "contract_program_v2.py").read_text(encoding="utf-8").lower()
    # privacy-guard:allow -- asserts these are absent, does not leak them
    for forbidden in ("hermes", "simplerestobar", "srb", "private"):  # privacy-guard:allow -- asserts absence, does not leak
        assert forbidden not in source
