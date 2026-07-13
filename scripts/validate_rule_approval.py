#!/usr/bin/env python3
"""Validate and cryptographically recover a CORE rule approval."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core_runtime.core.rule_anchor import (  # noqa: E402
    APPROVAL_SCHEMA,
    error,
    validate_rule_approval_payload,
)


def validate_rule_approval(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors = [error("file_not_found", "Rule-approval file does not exist.", "path")]
        payload = {}
    except json.JSONDecodeError:
        errors = [error("invalid_json", "Rule-approval file is not valid JSON.", "path")]
        payload = {}
    except OSError as exc:
        errors = [error("file_read_error", exc.__class__.__name__, "path")]
        payload = {}
    else:
        errors = validate_rule_approval_payload(payload)

    return {
        "schema": APPROVAL_SCHEMA,
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "rule_set_fingerprint": (
            payload.get("rule_set_fingerprint") if isinstance(payload, dict) else None
        ),
        "signer": payload.get("signer") if isinstance(payload, dict) else None,
        "approval_valid": not errors,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: validate_rule_approval.py <path>", file=sys.stderr)
        return 2
    result = validate_rule_approval(Path(sys.argv[1]))
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
