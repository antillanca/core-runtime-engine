#!/usr/bin/env python3
"""Certify deterministic replay for one or all offline router fixtures."""

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
from scripts.expert_router_common import evaluate_fixture, fixture_label, fixture_paths


DEFAULT_ROOT = Path("examples/expert_router/routing_fixtures")


def certify_fixture(path: Path) -> dict[str, Any]:
    first = evaluate_fixture(path)
    second = evaluate_fixture(path)
    first_hash = "sha256:" + compute_operational_fingerprint(first)
    second_hash = "sha256:" + compute_operational_fingerprint(second)
    status = "certified" if first == second and first["status"] == "passed" else "diverged"
    result: dict[str, Any] = {
        "replay_schema": "core.expert_router_replay.v1",
        "status": status,
        "execution_authorized": False,
        "fixture": fixture_label(path),
        "routing_id": first.get("routing_id", ""),
        "run_1": {"output_hash": first_hash},
        "run_2": {"output_hash": second_hash},
        "diff": None if first == second else "deterministic outputs differ",
    }
    result["fingerprint"] = "sha256:" + compute_operational_fingerprint(result)
    return result


def certify_all(root: Path) -> dict[str, Any]:
    fixtures = [certify_fixture(path) for path in fixture_paths(root)]
    result: dict[str, Any] = {
        "replay_schema": "core.expert_router_replay_certification_batch.v1",
        "status": "certified" if fixtures and all(item["status"] == "certified" for item in fixtures) else "diverged",
        "execution_authorized": False,
        "fixtures": fixtures,
        "summary": {
            "fixture_count": len(fixtures),
            "certified_count": sum(item["status"] == "certified" for item in fixtures),
            "diverged_count": sum(item["status"] != "certified" for item in fixtures),
        },
    }
    result["fingerprint"] = "sha256:" + compute_operational_fingerprint(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Certify deterministic Expert Router replay.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fixture", type=Path)
    group.add_argument("--all", action="store_true")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = certify_all(args.root) if args.all else certify_fixture(args.fixture)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] == "certified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
