#!/usr/bin/env python3
"""Validate a CORE State Watcher registration against the public schema.

This script is deterministic and offline. It never mutates runtime state.

Usage:
    python scripts/validate_state_watcher.py <watcher.json>
    python scripts/validate_state_watcher.py <directory_of_watchers>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "state_watcher.schema.json"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _canonical_dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _error(code: str, message: str, **metadata: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    for key, value in sorted(metadata.items()):
        if value is not None:
            payload[key] = value
    return payload


def validate_watcher(watcher_path: Path) -> dict[str, Any]:
    """Validate a single watcher registration file against the schema."""
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if not watcher_path.exists():
        return {
            "file": str(watcher_path),
            "status": "failed",
            "errors": [_error("file_missing", "Watcher registration file does not exist.")],
            "warnings": [],
        }

    try:
        watcher_data = _load_json(watcher_path)
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "file": str(watcher_path),
            "status": "failed",
            "errors": [_error("json_load_failed", "Failed to parse JSON.", actual=str(exc))],
            "warnings": [],
        }

    try:
        import jsonschema  # type: ignore[import-untyped]
    except ImportError:
        warnings.append(
            _error(
                "schema_validation_skipped",
                "jsonschema is not installed; only semantic checks were applied.",
            )
        )
    else:
        try:
            schema = _load_json(SCHEMA_PATH)
            jsonschema.validate(instance=watcher_data, schema=schema)
        except jsonschema.ValidationError as exc:
            errors.append(
                _error(
                    "schema_validation_failed",
                    str(exc.message),
                    path=".".join(str(p) for p in exc.absolute_path) if exc.absolute_path else "",
                )
            )

    # Extra semantic checks beyond JSON Schema
    if not errors:
        condition = watcher_data.get("watch_condition", {})
        operator = condition.get("operator", "")

        threshold_value = watcher_data.get("threshold_value")
        if operator in ("gt", "gte", "lt", "lte") and threshold_value is None:
            errors.append(
                _error(
                    "threshold_value_missing",
                    f"Operator '{operator}' requires a threshold_value.",
                )
            )

        if operator in ("within_range", "outside_range") and threshold_value is not None:
            errors.append(
                _error(
                    "threshold_value_unexpected",
                    f"Operator '{operator}' does not use scalar threshold_value.",
                )
            )

    return {
        "file": str(watcher_path),
        "status": "failed" if errors else "passed",
        "errors": errors,
        "warnings": warnings,
        "watcher_id": watcher_data.get("watcher_id"),
        "event_type": watcher_data.get("event_type"),
    }


def validate_directory(directory: Path) -> dict[str, Any]:
    """Validate all .json files in a directory of watcher registrations."""
    results: list[dict[str, Any]] = []
    watcher_files = sorted(directory.glob("*.json"))

    if not watcher_files:
        return {
            "directory": str(directory),
            "status": "failed",
            "errors": [_error("no_watcher_files", "No .json files found in directory.")],
            "warnings": [],
            "results": [],
        }

    for watcher_path in watcher_files:
        result = validate_watcher(watcher_path)
        results.append(result)

    passed = sum(1 for r in results if r["status"] == "passed")
    failed = sum(1 for r in results if r["status"] == "failed")

    return {
        "schema": "core.state_watcher_validation.v1",
        "directory": str(directory),
        "status": "passed" if failed == 0 else "failed",
        "total_count": len(results),
        "passed_count": passed,
        "failed_count": failed,
        "errors": [],
        "warnings": [],
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a CORE State Watcher registration against the public schema.",
    )
    parser.add_argument(
        "path",
        help="Path to a watcher .json file or a directory of watcher registrations.",
    )
    args = parser.parse_args()

    target = Path(args.path)

    if target.is_dir():
        payload = validate_directory(target)
    else:
        payload = validate_watcher(target)

    print(_canonical_dump(payload))
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
