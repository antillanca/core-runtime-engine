#!/usr/bin/env python3
"""Validate CORE parametric template, variable binding, and cache entry artifacts.

Accepts a single JSON file or a directory of JSON files.
Validates all three artifact types based on their schema_version:
  - core.parametric_template.v1
  - core.variable_binding.v1
  - core.parametric_cache_entry.v1

Outputs a deterministic validation report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORT_SCHEMA = "core.parametric_template_validation.v1"

FINGERPRINT_RE = r"^sha256:[a-f0-9]{64}$"
VALID_SLOT_TYPES = {"string", "integer", "float", "boolean", "enum"}
VALID_METHODS = {"read", "write", "delete"}
VALID_BINDING_SOURCES = {"explicit", "inferred", "default"}
VALID_EVICTION_POLICIES = {"lru", "fifo", "ttl_only"}
FORBIDDEN_CATEGORIES = {"live_results", "state_events", "permissions", "financial_state", "stock_state"}

# --- Rejection codes ---

# Template codes
MISSING_SCHEMA_VERSION = "missing_schema_version"
INVALID_TYPE = "invalid_type"
INVALID_TEMPLATE_FINGERPRINT = "invalid_template_fingerprint"
MISSING_TEMPLATE_ID = "missing_template_id"
MISSING_DOMAIN = "missing_domain"
MISSING_INTENT = "missing_intent"
SLOTS_NOT_ARRAY = "slots_not_array"
SLOTS_EMPTY = "slots_empty"
SLOT_MISSING_NAME = "slot_missing_name"
SLOT_INVALID_TYPE = "slot_invalid_type"
SLOT_MISSING_REQUIRED_FLAG = "slot_missing_required_flag"
ENUM_SLOT_EMPTY_VALUES = "enum_slot_empty_values"
NON_ENUM_SLOT_HAS_ENUM_VALUES = "non_enum_slot_has_enum_values"
MISSING_ROUTE = "missing_route"
ROUTE_MISSING_ACTION = "route_missing_action"
ROUTE_INVALID_METHOD = "route_invalid_method"
COMMAND_VALIDATION_NOT_REQUIRED = "command_validation_not_required"
FORBIDDEN_CATEGORIES_MISSING_LIVE_RESULTS = "forbidden_categories_missing_live_results"
FORBIDDEN_CATEGORIES_EMPTY = "forbidden_categories_empty"
FORBIDDEN_CATEGORIES_INVALID = "forbidden_categories_invalid"

# Binding codes
BINDING_FINGERPRINT_MISMATCH = "binding_fingerprint_mismatch"
BINDINGS_NOT_OBJECT = "bindings_not_object"
BINDING_MISSING_VALUE = "binding_missing_value"
BINDING_INVALID_SOURCE = "binding_invalid_source"

# Cache entry codes
MISSING_BINDING_FINGERPRINT = "missing_binding_fingerprint"
COMPILED_SHAPE_MISSING_ACTION = "compiled_shape_missing_action"
COMPILED_SHAPE_INVALID_METHOD = "compiled_shape_invalid_method"
COMPILED_SHAPE_MISSING_RESOLVED_SLOTS = "compiled_shape_missing_resolved_slots"
CACHE_POLICY_INVALID_TTL = "cache_policy_invalid_ttl"
CACHE_POLICY_INVALID_MAX_ENTRIES = "cache_policy_invalid_max_entries"
CACHE_POLICY_INVALID_EVICTION = "cache_policy_invalid_eviction"
LIVE_DATA_NOT_EXCLUDED = "live_data_not_excluded"
FORBIDDEN_CATEGORIES_CACHED_MISMATCH = "forbidden_categories_cached_mismatch"

UNKNOWN_SCHEMA_VERSION = "unknown_schema_version"


def _canonical_dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)


def _report_fingerprint(report: dict[str, Any]) -> str:
    payload = {k: v for k, v in report.items() if k != "report_fingerprint"}
    return f"sha256:{hashlib.sha256(_canonical_dump(payload).encode('utf-8')).hexdigest()}"


def _error(code: str, message: str, field: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    if field is not None:
        payload["field"] = field
    return payload


def _validate_fingerprint(value: Any, field_name: str) -> str | None:
    """Return error code if fingerprint is invalid, None if valid."""
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        return INVALID_TEMPLATE_FINGERPRINT
    return None


# ============================================================================
# Parametric Template Validation
# ============================================================================


def _validate_template(artifact: dict[str, Any], source: str) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []

    # 1. schema_version
    sv = artifact.get("schema_version")
    if not sv or not isinstance(sv, str):
        errors.append(_error(MISSING_SCHEMA_VERSION, "Missing or invalid schema_version.", "schema_version"))

    # 2. type
    t = artifact.get("type")
    if t != "parametric_template":
        errors.append(_error(INVALID_TYPE, f"Expected type 'parametric_template', got {t!r}.", "type"))

    # 3. template_fingerprint
    fp = artifact.get("template_fingerprint", "")
    fp_err = _validate_fingerprint(fp, "template_fingerprint")
    if fp_err:
        errors.append(_error(fp_err, "template_fingerprint must match sha256:<64 hex chars>.", "template_fingerprint"))

    # 4. template_id
    tid = artifact.get("template_id")
    if not tid or not isinstance(tid, str) or not tid.strip():
        errors.append(_error(MISSING_TEMPLATE_ID, "template_id must be a non-empty string.", "template_id"))

    # 5. domain
    domain = artifact.get("domain")
    if not domain or not isinstance(domain, str) or not domain.strip():
        errors.append(_error(MISSING_DOMAIN, "domain must be a non-empty string.", "domain"))

    # 6. intent
    intent = artifact.get("intent")
    if not intent or not isinstance(intent, str) or not intent.strip():
        errors.append(_error(MISSING_INTENT, "intent must be a non-empty string.", "intent"))

    # 7. slots
    slots = artifact.get("slots")
    if not isinstance(slots, list):
        errors.append(_error(SLOTS_NOT_ARRAY, "slots must be an array.", "slots"))
    else:
        if len(slots) == 0:
            errors.append(_error(SLOTS_EMPTY, "slots must have at least one entry.", "slots"))
        for i, slot in enumerate(slots):
            if not isinstance(slot, dict):
                errors.append(_error(SLOT_MISSING_NAME, f"Slot at index {i} is not an object.", f"slots[{i}]"))
                continue
            name = slot.get("name")
            if not name or not isinstance(name, str) or not name.strip():
                errors.append(_error(SLOT_MISSING_NAME, f"Slot at index {i} missing 'name'.", f"slots[{i}].name"))
            slot_type = slot.get("type")
            if slot_type not in VALID_SLOT_TYPES:
                errors.append(_error(SLOT_INVALID_TYPE, f"Slot '{name}' has invalid type {slot_type!r}.", f"slots[{i}].type"))
            if "required" not in slot:
                errors.append(_error(SLOT_MISSING_REQUIRED_FLAG, f"Slot '{name}' missing 'required' flag.", f"slots[{i}].required"))
            # enum slot must have non-empty enum_values
            if slot_type == "enum":
                ev = slot.get("enum_values")
                if not isinstance(ev, list) or len(ev) == 0:
                    errors.append(_error(ENUM_SLOT_EMPTY_VALUES, f"Enum slot '{name}' must have non-empty enum_values.", f"slots[{i}].enum_values"))
            # non-enum slot should NOT have enum_values
            if slot_type and slot_type != "enum" and "enum_values" in slot:
                errors.append(_error(NON_ENUM_SLOT_HAS_ENUM_VALUES, f"Non-enum slot '{name}' has enum_values.", f"slots[{i}].enum_values"))

    # 8. route
    route = artifact.get("route")
    if not isinstance(route, dict):
        errors.append(_error(MISSING_ROUTE, "route must be an object.", "route"))
    else:
        action = route.get("action")
        if not action or not isinstance(action, str) or not action.strip():
            errors.append(_error(ROUTE_MISSING_ACTION, "route.action must be a non-empty string.", "route.action"))
        method = route.get("method")
        if method not in VALID_METHODS:
            errors.append(_error(ROUTE_INVALID_METHOD, f"route.method must be one of {sorted(VALID_METHODS)}, got {method!r}.", "route.method"))

    # 9. safety.requires_command_validation
    safety = artifact.get("safety", {})
    if safety.get("requires_command_validation") is not True:
        errors.append(_error(COMMAND_VALIDATION_NOT_REQUIRED, "requires_command_validation must be true.", "safety.requires_command_validation"))

    # 10. safety.forbidden_categories
    fc = safety.get("forbidden_categories")
    if not isinstance(fc, list):
        errors.append(_error(FORBIDDEN_CATEGORIES_INVALID, "forbidden_categories must be an array.", "safety.forbidden_categories"))
    else:
        if len(fc) == 0:
            errors.append(_error(FORBIDDEN_CATEGORIES_EMPTY, "forbidden_categories must not be empty. At minimum 'live_results' is required.", "safety.forbidden_categories"))
        else:
            # Check all entries are valid
            invalid_cats = [c for c in fc if c not in FORBIDDEN_CATEGORIES]
            if invalid_cats:
                errors.append(_error(FORBIDDEN_CATEGORIES_INVALID, f"Invalid forbidden categories: {invalid_cats}.", "safety.forbidden_categories"))
            # Must include live_results
            if "live_results" not in fc:
                errors.append(_error(FORBIDDEN_CATEGORIES_MISSING_LIVE_RESULTS, "forbidden_categories must include 'live_results'.", "safety.forbidden_categories"))

    passed = len(errors) == 0
    result: dict[str, Any] = {
        "source": source,
        "artifact_type": "parametric_template",
        "status": "passed" if passed else "failed",
        "errors": errors,
    }
    if passed:
        result["template_id"] = tid
        result["domain"] = domain
        result["intent"] = intent
        result["method"] = route.get("method") if isinstance(route, dict) else None
    return result


# ============================================================================
# Variable Binding Validation
# ============================================================================


def _validate_binding(artifact: dict[str, Any], source: str) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []

    # 1. schema_version
    sv = artifact.get("schema_version")
    if not sv or not isinstance(sv, str):
        errors.append(_error(MISSING_SCHEMA_VERSION, "Missing or invalid schema_version.", "schema_version"))

    # 2. type
    t = artifact.get("type")
    if t != "variable_binding":
        errors.append(_error(INVALID_TYPE, f"Expected type 'variable_binding', got {t!r}.", "type"))

    # 3. template_fingerprint
    fp = artifact.get("template_fingerprint", "")
    fp_err = _validate_fingerprint(fp, "template_fingerprint")
    if fp_err:
        errors.append(_error(fp_err, "template_fingerprint must match sha256:<64 hex chars>.", "template_fingerprint"))

    # 4. template_id
    tid = artifact.get("template_id")
    if not tid or not isinstance(tid, str) or not tid.strip():
        errors.append(_error(MISSING_TEMPLATE_ID, "template_id must be a non-empty string.", "template_id"))

    # 5. bindings
    bindings = artifact.get("bindings")
    if not isinstance(bindings, dict):
        errors.append(_error(BINDINGS_NOT_OBJECT, "bindings must be a JSON object.", "bindings"))
    else:
        for slot_name, binding in bindings.items():
            if not isinstance(binding, dict):
                errors.append(_error(BINDING_MISSING_VALUE, f"Binding for slot '{slot_name}' is not an object.", f"bindings.{slot_name}"))
                continue
            if "value" not in binding:
                errors.append(_error(BINDING_MISSING_VALUE, f"Binding for slot '{slot_name}' missing 'value'.", f"bindings.{slot_name}.value"))
            source_val = binding.get("source")
            if source_val is not None and source_val not in VALID_BINDING_SOURCES:
                errors.append(_error(BINDING_INVALID_SOURCE, f"Binding for slot '{slot_name}' has invalid source {source_val!r}.", f"bindings.{slot_name}.source"))

    passed = len(errors) == 0
    result: dict[str, Any] = {
        "source": source,
        "artifact_type": "variable_binding",
        "status": "passed" if passed else "failed",
        "errors": errors,
    }
    if passed:
        result["template_id"] = tid
        result["slot_count"] = len(bindings) if isinstance(bindings, dict) else 0
    return result


# ============================================================================
# Parametric Cache Entry Validation
# ============================================================================


def _validate_cache_entry(artifact: dict[str, Any], source: str) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []

    # 1. schema_version
    sv = artifact.get("schema_version")
    if not sv or not isinstance(sv, str):
        errors.append(_error(MISSING_SCHEMA_VERSION, "Missing or invalid schema_version.", "schema_version"))

    # 2. type
    t = artifact.get("type")
    if t != "parametric_cache_entry":
        errors.append(_error(INVALID_TYPE, f"Expected type 'parametric_cache_entry', got {t!r}.", "type"))

    # 3. template_fingerprint
    fp = artifact.get("template_fingerprint", "")
    fp_err = _validate_fingerprint(fp, "template_fingerprint")
    if fp_err:
        errors.append(_error(fp_err, "template_fingerprint must match sha256:<64 hex chars>.", "template_fingerprint"))

    # 4. binding_fingerprint
    bfp = artifact.get("binding_fingerprint", "")
    bfp_err = _validate_fingerprint(bfp, "binding_fingerprint")
    if bfp_err:
        errors.append(_error(MISSING_BINDING_FINGERPRINT, "binding_fingerprint must match sha256:<64 hex chars>.", "binding_fingerprint"))

    # 5. template_id
    tid = artifact.get("template_id")
    if not tid or not isinstance(tid, str) or not tid.strip():
        errors.append(_error(MISSING_TEMPLATE_ID, "template_id must be a non-empty string.", "template_id"))

    # 6. compiled_shape
    shape = artifact.get("compiled_shape")
    if not isinstance(shape, dict):
        errors.append(_error(COMPILED_SHAPE_MISSING_ACTION, "compiled_shape must be an object.", "compiled_shape"))
    else:
        action = shape.get("action")
        if not action or not isinstance(action, str) or not action.strip():
            errors.append(_error(COMPILED_SHAPE_MISSING_ACTION, "compiled_shape.action must be a non-empty string.", "compiled_shape.action"))
        method = shape.get("method")
        if method not in VALID_METHODS:
            errors.append(_error(COMPILED_SHAPE_INVALID_METHOD, f"compiled_shape.method must be one of {sorted(VALID_METHODS)}, got {method!r}.", "compiled_shape.method"))
        resolved_slots = shape.get("resolved_slots")
        if not isinstance(resolved_slots, dict):
            errors.append(_error(COMPILED_SHAPE_MISSING_RESOLVED_SLOTS, "compiled_shape.resolved_slots must be a JSON object.", "compiled_shape.resolved_slots"))

    # 7. cache_policy
    policy = artifact.get("cache_policy")
    if isinstance(policy, dict):
        ttl = policy.get("ttl_seconds")
        if not isinstance(ttl, int) or ttl < 0:
            errors.append(_error(CACHE_POLICY_INVALID_TTL, "cache_policy.ttl_seconds must be a non-negative integer.", "cache_policy.ttl_seconds"))
        max_entries = policy.get("max_entries_per_template")
        if not isinstance(max_entries, int) or max_entries < 1:
            errors.append(_error(CACHE_POLICY_INVALID_MAX_ENTRIES, "cache_policy.max_entries_per_template must be a positive integer.", "cache_policy.max_entries_per_template"))
        eviction = policy.get("eviction_policy")
        if eviction not in VALID_EVICTION_POLICIES:
            errors.append(_error(CACHE_POLICY_INVALID_EVICTION, f"cache_policy.eviction_policy must be one of {sorted(VALID_EVICTION_POLICIES)}, got {eviction!r}.", "cache_policy.eviction_policy"))

    # 8. safety.live_data_excluded
    safety = artifact.get("safety", {})
    if safety.get("live_data_excluded") is not True:
        errors.append(_error(LIVE_DATA_NOT_EXCLUDED, "safety.live_data_excluded must be true.", "safety.live_data_excluded"))

    # 9. safety.forbidden_categories_cached
    fcc = safety.get("forbidden_categories_cached")
    if isinstance(fcc, list):
        invalid_cats = [c for c in fcc if c not in FORBIDDEN_CATEGORIES]
        if invalid_cats:
            errors.append(_error(FORBIDDEN_CATEGORIES_CACHED_MISMATCH, f"Invalid categories in forbidden_categories_cached: {invalid_cats}.", "safety.forbidden_categories_cached"))

    passed = len(errors) == 0
    result: dict[str, Any] = {
        "source": source,
        "artifact_type": "parametric_cache_entry",
        "status": "passed" if passed else "failed",
        "errors": errors,
    }
    if passed:
        result["template_id"] = tid
        result["method"] = shape.get("method") if isinstance(shape, dict) else None
    return result


# ============================================================================
# Dispatch
# ============================================================================


def _validate_one(artifact: dict[str, Any], source: str) -> dict[str, Any]:
    sv = artifact.get("schema_version", "")
    # Infer artifact type from the 'type' field when schema_version is missing/empty
    if not sv or not isinstance(sv, str):
        inferred_type = artifact.get("type", "")
        if inferred_type == "parametric_template":
            return _validate_template(artifact, source)
        elif inferred_type == "variable_binding":
            return _validate_binding(artifact, source)
        elif inferred_type == "parametric_cache_entry":
            return _validate_cache_entry(artifact, source)
        else:
            return {
                "source": source,
                "artifact_type": "unknown",
                "status": "failed",
                "errors": [_error(MISSING_SCHEMA_VERSION, "Missing or invalid schema_version.", "schema_version")],
            }
    if sv == "core.parametric_template.v1":
        return _validate_template(artifact, source)
    elif sv == "core.variable_binding.v1":
        return _validate_binding(artifact, source)
    elif sv == "core.parametric_cache_entry.v1":
        return _validate_cache_entry(artifact, source)
    else:
        return {
            "source": source,
            "artifact_type": "unknown",
            "status": "failed",
            "errors": [_error(UNKNOWN_SCHEMA_VERSION, f"Unknown schema_version: {sv!r}.", "schema_version")],
        }


def validate_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"source": str(path), "artifact_type": "unknown", "status": "failed", "errors": [_error("invalid_json", str(exc))]}
    if not isinstance(payload, dict):
        return {"source": str(path), "artifact_type": "unknown", "status": "failed", "errors": [_error("invalid_json", "Expected a JSON object.")]}
    return _validate_one(payload, str(path))


def validate_directory(dir_path: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for json_file in sorted(dir_path.glob("*.json")):
        results.append(validate_file(json_file))
    return results


def build_report(results: list[dict[str, Any]]) -> dict[str, Any]:
    passed_count = sum(1 for r in results if r["status"] == "passed")
    failed_count = sum(1 for r in results if r["status"] == "failed")
    total = len(results)

    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "status": "passed" if failed_count == 0 else "failed",
        "total_artifacts": total,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "results": results,
    }
    report["report_fingerprint"] = _report_fingerprint(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate CORE parametric template artifacts.")
    parser.add_argument("path", type=Path, help="JSON file or directory of JSON files to validate.")
    args = parser.parse_args()

    target = args.path.resolve()
    if not target.exists():
        print(f"Error: {target} does not exist.", file=sys.stderr)
        sys.exit(1)

    if target.is_dir():
        results = validate_directory(target)
    else:
        results = [validate_file(target)]

    report = build_report(results)
    print(_canonical_dump(report))

    if report["status"] == "failed":
        sys.exit(1)


if __name__ == "__main__":
    main()
