#!/usr/bin/env python3
"""Validate and evaluate one public DSK v3 declaration."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core_runtime.core.dsk_v3 import evaluate_dsk_v3  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: validate_dsk_v3.py <declaration.json>", file=sys.stderr)
        return 2
    payload = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    result = evaluate_dsk_v3(payload)
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
