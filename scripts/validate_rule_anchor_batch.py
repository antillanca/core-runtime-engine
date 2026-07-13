#!/usr/bin/env python3
"""Validate every leaf and proof in a CORE rule-anchor batch."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core_runtime.core.rule_anchor import (  # noqa: E402
    ANCHOR_BATCH_SCHEMA,
    error,
    validate_rule_anchor_batch_payload,
)


def validate_rule_anchor_batch(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors = [error("file_not_found", "Rule-anchor batch file does not exist.", "path")]
        payload = {}
    except json.JSONDecodeError:
        errors = [error("invalid_json", "Rule-anchor batch file is not valid JSON.", "path")]
        payload = {}
    except OSError as exc:
        errors = [error("file_read_error", exc.__class__.__name__, "path")]
        payload = {}
    else:
        errors = validate_rule_anchor_batch_payload(payload)

    return {
        "schema": ANCHOR_BATCH_SCHEMA,
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "batch_id": payload.get("batch_id") if isinstance(payload, dict) else None,
        "merkle_root": payload.get("merkle_root") if isinstance(payload, dict) else None,
        "batch_valid": not errors,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: validate_rule_anchor_batch.py <path>", file=sys.stderr)
        return 2
    result = validate_rule_anchor_batch(Path(sys.argv[1]))
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
