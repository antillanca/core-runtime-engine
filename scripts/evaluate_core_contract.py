#!/usr/bin/env python3
"""Evaluate one public CORE contract with executable semantics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core_runtime.core.contract_evaluator import evaluate_contract_file  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate structure, semantic invariants, evidence binding, and authority limits."
    )
    parser.add_argument("path", type=Path, help="JSON contract artifact to evaluate.")
    parser.add_argument(
        "--compat-shape",
        action="store_true",
        help="Allow legacy schema extension fields. Semantic checks still run.",
    )
    args = parser.parse_args()

    result = evaluate_contract_file(args.path, strict=not args.compat_shape)
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
