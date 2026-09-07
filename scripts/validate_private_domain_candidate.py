#!/usr/bin/env python3
"""Validate a private-domain integration command candidate.

This script is deterministic and offline. It never mutates runtime state.

It performs three layers of validation:
  1. Structural: the candidate must conform to core.command_candidate.v1.
  2. Private-data rejection: candidates must not embed real business data
     (costs, margins, customer records, etc.).
  3. Command-known check: the command must exist in a known vocabulary
     (public bundle or external vocabulary with the `external:` prefix).

Usage:
    python scripts/validate_private_domain_candidate.py <candidate.json> [--vocab-dir <dir>]

Exit codes:
    0  all checks passed
    1  validation failed (errors printed to stderr)
    2  usage error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "core.command_candidate.v1"
VALIDATION_SCHEMA = "core.private_domain_candidate_validation.v1"
EXTERNAL_VOCAB_PREFIX = "external:"

# Fields that indicate private business data embedding
PRIVATE_DATA_INDICATOR_FIELDS = frozenset({
    "margin_data",
    "cost",
    "margin_percent",
    "customer_data",
    "customer_id",
    "employee_salary",
    "salary",
    "bank_account",
    "credit_card",
    "ssn",
    "tax_id",
    "phone_number",
    "email_address",
})

# Effects that are never allowed in a read_only vocabulary
FORBIDDEN_EFFECTS = frozenset({
    "write",
    "delete",
    "drop",
    "truncate",
    "alter",
    "create_table",
    "insert",
    "update",
    "exec",
    "execute",
    "system",
    "shell",
    "network",
})


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _error(code: str, message: str, **metadata: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    for key, value in sorted(metadata.items()):
        if value is not None:
            payload[key] = value
    return payload


def _check_structure(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """Layer 1: structural validation of the command candidate envelope."""
    errors: list[dict[str, Any]] = []

    if candidate.get("schema") != SCHEMA:
        errors.append(_error(
            "invalid_schema",
            f"Expected schema '{SCHEMA}', got '{candidate.get('schema')}'",
            field="schema",
        ))

    for required in ("vocabulary_id", "domain_id", "command", "output_kind", "label"):
        if required not in candidate or not candidate.get(required):
            errors.append(_error(
                "missing_required_field",
                f"Missing or empty required field: {required}",
                field=required,
            ))

    if candidate.get("output_kind") not in ("command_candidate", "command_not_found", "clarification_required"):
        errors.append(_error(
            "invalid_output_kind",
            f"Invalid output_kind: '{candidate.get('output_kind')}'",
            field="output_kind",
        ))

    if candidate.get("label") not in ("accepted_candidate", "rejected_candidate", "clarification_required"):
        errors.append(_error(
            "invalid_label",
            f"Invalid label: '{candidate.get('label')}'",
            field="label",
        ))

    return errors


def _check_private_data(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """Layer 2: reject candidates that embed private business data."""
    errors: list[dict[str, Any]] = []

    def _scan_for_private_fields(obj: Any, path: str = "") -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                current_path = f"{path}.{key}" if path else key
                if key in PRIVATE_DATA_INDICATOR_FIELDS:
                    errors.append(_error(
                        "private_business_data_embedded",
                        f"Private data field '{current_path}' found in candidate. "
                        f"CORE candidates must not embed real business data.",
                        field=current_path,
                    ))
                _scan_for_private_fields(value, current_path)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _scan_for_private_fields(item, f"{path}[{i}]")

    _scan_for_private_fields(candidate.get("arguments", {}))
    return errors


def _check_effects(candidate: dict[str, Any], vocab: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Layer 3: reject candidates with forbidden effects."""
    errors: list[dict[str, Any]] = []

    candidate_effects = set(candidate.get("effects", []))
    forbidden = candidate_effects & FORBIDDEN_EFFECTS

    if forbidden:
        errors.append(_error(
            "forbidden_effects",
            f"Candidate declares forbidden effects: {sorted(forbidden)}. "
            f"Read-only vocabularies must not allow write/delete effects.",
            effects=sorted(forbidden),
        ))

    # If we have a vocabulary, cross-check command exists
    if vocab is not None:
        commands = vocab.get("commands", [])
        command_names = {c["name"] for c in commands if "name" in c}
        candidate_command = candidate.get("command", "")

        if candidate_command not in command_names:
            errors.append(_error(
                "unknown_command",
                f"Command '{candidate_command}' not found in vocabulary "
                f"'{candidate.get('vocabulary_id', '')}'. "
                f"Known commands: {sorted(command_names)}",
                command=candidate_command,
                known_commands=sorted(command_names),
            ))

    return errors


def _load_vocabulary(vocab_id: str, vocab_dirs: list[Path]) -> dict[str, Any] | None:
    """Try to load a vocabulary file from the given directories."""
    if vocab_id.startswith(EXTERNAL_VOCAB_PREFIX):
        # External vocabularies: strip prefix, derive filename from domain segment.
        # e.g. "external:synthetic_sales.commands.v1" -> "synthetic_sales_v1.json"
        segments = vocab_id.replace(EXTERNAL_VOCAB_PREFIX, "").split(".")
        # First segment is the domain_id, last segment is the version tag
        domain_part = segments[0] if segments else "unknown"
        version_part = segments[-1] if len(segments) > 1 else "v1"
        filename = f"{domain_part}_{version_part}.json"
    else:
        filename = vocab_id.replace(".", "_") + ".json"

    for vocab_dir in vocab_dirs:
        root = vocab_dir.resolve()
        candidate_path = (root / filename).resolve()
        try:
            candidate_path.relative_to(root)
        except ValueError:
            # A vocabulary id is data, not a path expression.  Refuse both
            # traversal and symlink escapes before opening a file.
            continue
        if candidate_path.is_file():
            return _load_json(candidate_path)

    return None


def validate_candidate(
    candidate_path: Path,
    vocab_dirs: list[Path] | None = None,
) -> dict[str, Any]:
    """Validate a private-domain integration command candidate."""
    if vocab_dirs is None:
        vocab_dirs = []

    candidate = _load_json(candidate_path)

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    # Layer 1: structure
    errors.extend(_check_structure(candidate))

    # Layer 2: private data
    errors.extend(_check_private_data(candidate))

    # Layer 3: effects + command-known
    vocab_id = candidate.get("vocabulary_id", "")
    vocab = _load_vocabulary(vocab_id, vocab_dirs) if vocab_dirs else None
    errors.extend(_check_effects(candidate, vocab))

    # Warn if external vocabulary referenced but not resolved
    if vocab_id.startswith(EXTERNAL_VOCAB_PREFIX) and vocab is None and vocab_dirs:
        warnings.append({
            "code": "external_vocabulary_unresolved",
            "message": (
                f"External vocabulary '{vocab_id}' was not found in the provided "
                f"vocabulary directories. CORE validates structure only; the "
                f"downstream fork validates semantics."
            ),
            "vocabulary_id": vocab_id,
        })

    verdict = "accepted" if not errors else "rejected"

    return {
        "schema": VALIDATION_SCHEMA,
        "candidate_path": str(candidate_path),
        "verdict": verdict,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a private-domain integration command candidate."
    )
    parser.add_argument("candidate", type=Path, help="Path to the candidate JSON file.")
    parser.add_argument(
        "--vocab-dir",
        action="append",
        type=Path,
        default=[],
        help="Directory containing vocabulary JSON files (can be repeated).",
    )
    args = parser.parse_args()

    if not args.candidate.exists():
        print(f"Error: candidate file not found: {args.candidate}", file=sys.stderr)
        return 2

    result = validate_candidate(args.candidate, args.vocab_dir)
    print(json.dumps(result, indent=2, sort_keys=True))

    return 0 if result["verdict"] == "accepted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
