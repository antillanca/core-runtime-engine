from __future__ import annotations

import copy
import json
from pathlib import Path

from jsonschema import Draft7Validator

from core_runtime.core.dsk_v3 import SCHEMA_VERSION, evaluate_dsk_v3

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples" / "dsk_v3"
SCHEMA = json.loads((ROOT / "schemas" / "core" / "dsk.v3.json").read_text(encoding="utf-8"))
VALIDATOR = Draft7Validator(SCHEMA)


def load(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def test_accepted_crossing_has_closed_schema_and_passes() -> None:
    payload = load("accepted_basic.json")
    assert not list(VALIDATOR.iter_errors(payload))
    result = evaluate_dsk_v3(payload)
    assert result["schema"] == SCHEMA_VERSION
    assert result["status"] == "pass"
    assert result["errors"] == []
    assert result["result"]["value"] == "0.25"
    assert result["deterministic"] is True


def test_replay_is_byte_stable() -> None:
    payload = load("accepted_basic.json")
    assert evaluate_dsk_v3(payload) == evaluate_dsk_v3(copy.deepcopy(payload))


def test_schema_rejects_unknown_fields() -> None:
    payload = load("rejected_schema_unknown_field.json")
    assert list(VALIDATOR.iter_errors(payload))
    result = evaluate_dsk_v3(payload)
    assert result["status"] == "invalid"
    assert result["errors"][0]["code"] == "schema_validation_error"


def test_missing_value_is_insufficient_data() -> None:
    result = evaluate_dsk_v3(load("rejected_insufficient_data.json"))
    assert result["status"] == "insufficient_data"
    assert result["errors"][0]["code"] == "source_value_missing"


def test_threshold_is_blocked_without_authority_creation() -> None:
    result = evaluate_dsk_v3(load("rejected_blocked_threshold.json"))
    assert result["status"] == "blocked"
    assert result["errors"][0]["code"] == "threshold_ineligible"
    assert "result" not in result


def test_authority_cannot_be_amplified_by_declaration() -> None:
    result = evaluate_dsk_v3(load("rejected_authority_amplification.json"))
    assert result["status"] == "blocked"
    assert result["errors"][0]["code"] == "authority_non_amplification"


def test_unit_mismatch_is_blocked() -> None:
    result = evaluate_dsk_v3(load("rejected_scale_violation.json"))
    assert result["status"] == "blocked"
    assert result["errors"][0]["code"] == "scale_violation"


def test_nonfinite_numeric_values_fail_closed() -> None:
    payload = load("accepted_basic.json")
    payload["crossing"]["source"]["value"] = float("nan")
    result = evaluate_dsk_v3(payload)
    assert result["status"] == "invalid"
    assert result["errors"][0]["code"] == "numeric_value_invalid"

    payload = load("accepted_basic.json")
    payload["crossing"]["conversion"]["numerator"] = float("inf")
    result = evaluate_dsk_v3(payload)
    assert result["status"] == "invalid"
    assert result["errors"][0]["code"] in {"numeric_value_invalid", "schema_validation_error"}


def test_public_runtime_contains_no_private_vocabulary() -> None:
    source = (ROOT / "core_runtime" / "core" / "dsk_v3.py").read_text(encoding="utf-8").lower()
    # privacy-guard:allow -- asserts these are absent, does not leak them
    for forbidden in ("hermes", "simplerestobar", "srb", "private"):  # privacy-guard:allow -- asserts absence
        assert forbidden not in source
