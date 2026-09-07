#!/usr/bin/env python3
"""Evaluate Expert Router eligibility without invoking any provider."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.expert_router_common import evaluate_fixture


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a deterministic Expert Router fixture.")
    parser.add_argument("fixture", type=Path)
    args = parser.parse_args()
    result = evaluate_fixture(args.fixture)
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
