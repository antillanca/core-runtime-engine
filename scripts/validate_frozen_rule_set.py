#!/usr/bin/env python3
"""Validate a CORE FrozenRuleSet.v1 artifact."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core_runtime.core.rule_anchor import (  # noqa: E402
    FROZEN_RULE_SET_SCHEMA,
    error,
    validate_frozen_rule_set_payload,
)


def validate_frozen_rule_set(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors = [error("file_not_found", "Frozen rule-set file does not exist.", "path")]
        payload = {}
    except json.JSONDecodeError:
        errors = [error("invalid_json", "Frozen rule-set file is not valid JSON.", "path")]
        payload = {}
    except OSError as exc:
        errors = [error("file_read_error", exc.__class__.__name__, "path")]
        payload = {}
    else:
        errors = validate_frozen_rule_set_payload(payload)

    return {
        "schema": FROZEN_RULE_SET_SCHEMA,
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "rule_set_id": payload.get("rule_set_id") if isinstance(payload, dict) else None,
        "fingerprint": payload.get("fingerprint") if isinstance(payload, dict) else None,
        "rule_set_valid": not errors,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: validate_frozen_rule_set.py <path>", file=sys.stderr)
        return 2
    result = validate_frozen_rule_set(Path(sys.argv[1]))
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
