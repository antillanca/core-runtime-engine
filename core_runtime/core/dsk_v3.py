"""Domain Scale Kernel v3 evaluator.

The kernel validates one typed scale crossing. It never calls a provider,
consults a domain or increases the authority declared by the input.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from importlib.resources import files
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator

from core_runtime.core.rule_anchor import canonical_fingerprint

SCHEMA_VERSION = "core.dsk.v3"
SCHEMA_PATH = files("core_runtime").joinpath("data", "schemas", "core", "dsk.v3.json")
STATUSES = ("pass", "invalid", "insufficient_data", "blocked")


def _error(code: str, message: str, field: str | None = None) -> dict[str, str]:
    result = {"code": code, "message": message}
    if field is not None:
        result["field"] = field
    return result


def _decimal(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise InvalidOperation
    decimal = Decimal(str(value))
    if not decimal.is_finite():
        raise InvalidOperation
    return decimal


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _decimal_places(value: Decimal) -> int:
    text = _decimal_text(value)
    return len(text.partition(".")[2])


def _envelope(payload: dict[str, Any], status: str, errors: list[dict[str, str]], **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "status": status,
        "errors": errors,
        "fingerprint": canonical_fingerprint(payload),
        "deterministic": True,
        "llm_used": False,
    }
    result.update(extra)
    return result


def _schema_errors(payload: Any) -> list[dict[str, str]]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return [
        _error("schema_validation_error", item.message, ".".join(map(str, item.absolute_path)) or "$")
        for item in sorted(Draft7Validator(schema).iter_errors(payload), key=lambda item: list(item.absolute_path))
    ]


def evaluate_dsk_v3(payload: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a DSK v3 declaration and return the standard CORE envelope."""

    if not isinstance(payload, dict):
        return _envelope({}, "invalid", [_error("payload_type_invalid", "DSK input must be an object.")])
    schema_errors = _schema_errors(payload)
    if schema_errors:
        return _envelope(payload, "invalid", schema_errors)

    crossing = payload["crossing"]
    source = crossing["source"]
    target = crossing["target"]
    conversion = crossing["conversion"]
    authority = payload["authority"]
    if "value" not in source:
        return _envelope(payload, "insufficient_data", [_error("source_value_missing", "source.value is required to evaluate the crossing.", "crossing.source.value")])

    errors: list[dict[str, str]] = []
    if source["unit"] != conversion["source_unit"] or target["unit"] != conversion["target_unit"]:
        errors.append(_error("scale_violation", "Declared conversion units do not match the crossing endpoints.", "crossing.conversion"))

    ceiling = authority["ceiling"]
    if ceiling in {"domain_authoritative", "externally_validated"} and authority["source"] != "external_validator":
        errors.append(_error("authority_non_amplification", "A scale crossing cannot create authority without an external validator.", "authority"))

    try:
        value = _decimal(source["value"])
        numerator = _decimal(conversion["numerator"])
        denominator = _decimal(conversion["denominator"])
        converted = value * numerator / denominator
    except (InvalidOperation, ZeroDivisionError):
        return _envelope(payload, "invalid", [_error("numeric_value_invalid", "Numeric values must be finite and deterministic.", "crossing.source.value")])

    policies = payload.get("policies", {})
    discrete = policies.get("discrete_multiple")
    if discrete is not None:
        try:
            multiple = _decimal(discrete["multiple"])
            discrete_violation = converted % multiple != 0
        except (InvalidOperation, ZeroDivisionError):
            return _envelope(payload, "invalid", [_error("numeric_value_invalid", "Numeric values must be finite and deterministic.", "policies.discrete_multiple.multiple")])
        if discrete_violation:
            errors.append(_error("discrete_multiple_violation", "Converted value is not an allowed discrete multiple.", "policies.discrete_multiple"))

    resolution = policies.get("resolution")
    if resolution is not None and _decimal_places(converted) > resolution["max_decimal_places"]:
        errors.append(_error("resolution_violation", "Converted value exceeds the declared resolution.", "policies.resolution"))

    threshold = policies.get("threshold")
    if threshold is not None:
        try:
            minimum_value = _decimal(threshold["minimum_value"])
        except InvalidOperation:
            return _envelope(payload, "invalid", [_error("numeric_value_invalid", "Numeric values must be finite and deterministic.", "policies.threshold.minimum_value")])
        if converted < minimum_value:
            errors.append(_error("threshold_ineligible", "Threshold eligibility was not met; no authority is created.", "policies.threshold"))

    if errors:
        return _envelope(payload, "blocked", errors, authority_ceiling=ceiling)

    return _envelope(
        payload,
        "pass",
        [],
        result={
            "resource": target["resource"],
            "unit": target["unit"],
            "value": _decimal_text(converted),
            "authority_ceiling": ceiling,
            "composition_rule": crossing["composition_rule"],
            "declared_loss": crossing["declared_loss"],
        },
    )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: dsk_v3.py <declaration.json>", file=__import__("sys").stderr)
        return 2
    payload = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    result = evaluate_dsk_v3(payload)
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv))
