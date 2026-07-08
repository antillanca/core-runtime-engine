from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


VALIDATION_SCHEMA = "core.execution_profile_validation.v1"
PROFILE_SCHEMA = "core.execution_profile.v1"

ALLOWED_ROOT_FIELDS = {
    "profile_schema",
    "profile_id",
    "profile_name",
    "description",
    "requirements",
    "safety",
    "expected_use",
    "notes",
}

REQUIRED_ROOT_FIELDS = ALLOWED_ROOT_FIELDS

FIELD_TYPES = {
    "profile_schema": str,
    "profile_id": str,
    "profile_name": str,
    "description": str,
    "requirements": dict,
    "safety": dict,
    "expected_use": str,
    "notes": list,
}

REQUIRED_REQUIREMENTS = {
    "audit_level",
    "requires_batch_report",
    "requires_certified_evidence",
    "requires_deterministic_evaluation",
    "requires_explainability",
    "requires_replay_certification",
    "requires_structural_validation",
}

REQUIRED_SAFETY = {
    "allows_runtime_mutation",
    "allows_tool_execution",
}

BOOLEAN_REQUIREMENTS = {
    "requires_batch_report",
    "requires_certified_evidence",
    "requires_deterministic_evaluation",
    "requires_explainability",
    "requires_replay_certification",
    "requires_structural_validation",
}

PROFILE_ID_PATTERN = re.compile(r"^execution_profile:[a-z][a-z0-9_]*:v1$")

ABSOLUTE_PATH_PATTERNS = [
    re.compile(r"/home/"),
    re.compile(r"/Users/"),
    re.compile(r"^[A-Za-z]:\\\\"),
    re.compile(r"\n[A-Za-z]:\\\\"),
]

SECRET_LIKE_PATTERNS = [
    re.compile(r"password\s*[:=]", re.IGNORECASE),
    re.compile(r"api[_-]?key\s*[:=]", re.IGNORECASE),
    re.compile(r"secret\s*[:=]", re.IGNORECASE),
    re.compile(r"token\s*[:=]", re.IGNORECASE),
    re.compile(r"connection_string\s*[:=]", re.IGNORECASE),
]

UNVERIFIED_CLAIM_PATTERNS = [
    re.compile(r"[0-9]+%"),
    re.compile(r"\$[0-9]"),
    re.compile(r"\bROI\b", re.IGNORECASE),
    re.compile(r"\baccuracy\b", re.IGNORECASE),
    re.compile(r"compliance guaranteed", re.IGNORECASE),
    re.compile(r"\bfalsos positivos\b", re.IGNORECASE),
    re.compile(r"\bprecisión\b", re.IGNORECASE),
    re.compile(r"\bahorro\b", re.IGNORECASE),
]


def _error(code: str, message: str, field: str | None = None) -> dict[str, str]:
    payload = {
        "code": code,
        "message": message,
    }
    if field is not None:
        payload["field"] = field
    return payload


def _flatten(value: Any) -> str:
    if isinstance(value, dict):
        return "\n".join(
            f"{key}: {_flatten(inner)}"
            for key, inner in sorted(value.items())
        )
    if isinstance(value, list):
        return "\n".join(_flatten(item) for item in value)
    return str(value)


def _load_json(path: Path) -> tuple[dict[str, Any] | None, list[dict[str, str]], int]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, [
            _error(
                "file_not_found",
                "Execution profile file does not exist.",
                "path",
            ),
        ], 2
    except OSError as exc:
        return None, [
            _error(
                "file_read_error",
                f"Could not read execution profile file: {exc.__class__.__name__}.",
                "path",
            ),
        ], 2

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None, [
            _error(
                "invalid_json",
                "Execution profile file is not valid JSON.",
            ),
        ], 1

    if not isinstance(parsed, dict):
        return None, [
            _error(
                "invalid_root_type",
                "Execution profile JSON root must be an object.",
            ),
        ], 1

    return parsed, [], 0


def _validate_root(payload: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []

    for field in sorted(REQUIRED_ROOT_FIELDS):
        if field not in payload:
            errors.append(
                _error(
                    "missing_required_field",
                    f"Missing required field: {field}.",
                    field,
                )
            )

    for field in sorted(set(payload) - ALLOWED_ROOT_FIELDS):
        errors.append(
            _error(
                "unknown_field",
                f"Unknown field is not part of the execution profile contract: {field}.",
                field,
            )
        )

    for field, expected_type in sorted(FIELD_TYPES.items()):
        if field in payload and not isinstance(payload[field], expected_type):
            errors.append(
                _error(
                    "invalid_field_type",
                    f"Field {field} must be {expected_type.__name__}.",
                    field,
                )
            )

    if payload.get("profile_schema") != PROFILE_SCHEMA:
        errors.append(
            _error(
                "invalid_profile_schema",
                f"profile_schema must be {PROFILE_SCHEMA}.",
                "profile_schema",
            )
        )

    profile_id = payload.get("profile_id")
    profile_name = payload.get("profile_name")

    if isinstance(profile_id, str):
        if not PROFILE_ID_PATTERN.match(profile_id):
            errors.append(
                _error(
                    "invalid_profile_id_format",
                    "profile_id must match execution_profile:<profile_name>:v1.",
                    "profile_id",
                )
            )
        elif isinstance(profile_name, str):
            expected_profile_id = f"execution_profile:{profile_name}:v1"
            if profile_id != expected_profile_id:
                errors.append(
                    _error(
                        "profile_id_name_mismatch",
                        "profile_id must match profile_name.",
                        "profile_id",
                    )
                )

    return errors


def _validate_requirements(payload: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    requirements = payload.get("requirements")

    if not isinstance(requirements, dict):
        return errors

    for field in sorted(REQUIRED_REQUIREMENTS):
        if field not in requirements:
            errors.append(
                _error(
                    "missing_requirement_field",
                    f"Missing requirement field: {field}.",
                    f"requirements.{field}",
                )
            )

    for field in sorted(set(requirements) - REQUIRED_REQUIREMENTS):
        errors.append(
            _error(
                "unknown_requirement_field",
                f"Unknown requirement field: {field}.",
                f"requirements.{field}",
            )
        )

    if "audit_level" in requirements and not isinstance(requirements["audit_level"], str):
        errors.append(
            _error(
                "invalid_requirement_type",
                "requirements.audit_level must be str.",
                "requirements.audit_level",
            )
        )

    for field in sorted(BOOLEAN_REQUIREMENTS):
        if field in requirements and not isinstance(requirements[field], bool):
            errors.append(
                _error(
                    "invalid_requirement_type",
                    f"requirements.{field} must be bool.",
                    f"requirements.{field}",
                )
            )

    return errors


def _validate_safety(payload: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    safety = payload.get("safety")

    if not isinstance(safety, dict):
        return errors

    for field in sorted(REQUIRED_SAFETY):
        if field not in safety:
            errors.append(
                _error(
                    "missing_safety_field",
                    f"Missing safety field: {field}.",
                    f"safety.{field}",
                )
            )

    for field in sorted(set(safety) - REQUIRED_SAFETY):
        errors.append(
            _error(
                "unknown_safety_field",
                f"Unknown safety field: {field}.",
                f"safety.{field}",
            )
        )

    for field in sorted(REQUIRED_SAFETY):
        if field in safety and not isinstance(safety[field], bool):
            errors.append(
                _error(
                    "invalid_safety_type",
                    f"safety.{field} must be bool.",
                    f"safety.{field}",
                )
            )

    if safety.get("allows_tool_execution") is True:
        errors.append(
            _error(
                "unsafe_tool_execution_allowed",
                "Execution profiles must not allow tool execution.",
                "safety.allows_tool_execution",
            )
        )

    if safety.get("allows_runtime_mutation") is True:
        errors.append(
            _error(
                "unsafe_runtime_mutation_allowed",
                "Execution profiles must not allow runtime mutation.",
                "safety.allows_runtime_mutation",
            )
        )

    return errors


def _validate_content(payload: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    flattened = _flatten(payload)

    for pattern in ABSOLUTE_PATH_PATTERNS:
        if pattern.search(flattened):
            errors.append(
                _error(
                    "absolute_path_detected",
                    "Execution profile contains a local absolute path.",
                )
            )
            break

    for pattern in SECRET_LIKE_PATTERNS:
        if pattern.search(flattened):
            errors.append(
                _error(
                    "secret_like_content_detected",
                    "Execution profile contains secret-like assignment content.",
                )
            )
            break

    for pattern in UNVERIFIED_CLAIM_PATTERNS:
        if pattern.search(flattened):
            errors.append(
                _error(
                    "unverified_claim_detected",
                    "Execution profile contains an unverified quantitative or compliance claim.",
                )
            )
            break

    return errors


def validate_payload(payload: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    errors.extend(_validate_root(payload))
    errors.extend(_validate_requirements(payload))
    errors.extend(_validate_safety(payload))
    errors.extend(_validate_content(payload))
    return errors


def validate_file(path: Path) -> tuple[int, dict[str, Any]]:
    payload, load_errors, load_exit_code = _load_json(path)

    if payload is None:
        output = {
            "errors": load_errors,
            "profile_id": None,
            "schema": VALIDATION_SCHEMA,
            "status": "failed",
            "warnings": [],
        }
        return load_exit_code, output

    errors = validate_payload(payload)

    profile_id = payload.get("profile_id")
    if not isinstance(profile_id, str):
        profile_id = None

    output = {
        "errors": errors,
        "profile_id": profile_id,
        "schema": VALIDATION_SCHEMA,
        "status": "passed" if not errors else "failed",
        "warnings": [],
    }

    return (0 if not errors else 1), output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a CORE Execution Profile JSON fixture structurally.",
    )
    parser.add_argument("profile_path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    exit_code, payload = validate_file(Path(args.profile_path))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
