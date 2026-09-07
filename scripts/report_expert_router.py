#!/usr/bin/env python3
"""Produce a deterministic batch report for Expert Router fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core_runtime.core.audit_event import compute_operational_fingerprint
from scripts.expert_router_common import evaluate_fixture, fixture_paths


DEFAULT_ROOT = Path("examples/expert_router/routing_fixtures")


def build_report(root: Path = DEFAULT_ROOT) -> dict[str, Any]:
    fixtures = []
    for path in fixture_paths(root):
        evaluation = evaluate_fixture(path)
        fixtures.append(
            {
                "file": path.as_posix(),
                "routing_id": evaluation.get("routing_id", ""),
                "status": evaluation["status"],
                "evaluation_fingerprint": evaluation.get("evaluation_fingerprint"),
            }
        )
    summary = {
        "fixture_count": len(fixtures),
        "passed_count": sum(item["status"] == "passed" for item in fixtures),
        "failed_count": sum(item["status"] != "passed" for item in fixtures),
    }
    result: dict[str, Any] = {
        "schema": "core.expert_router_batch_report.v1",
        "status": "passed" if fixtures and summary["failed_count"] == 0 else "failed",
        "execution_authorized": False,
        "fixtures": fixtures,
        "summary": summary,
    }
    result["report_fingerprint"] = "sha256:" + compute_operational_fingerprint(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Report deterministic Expert Router fixture results.")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_report(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
