#!/usr/bin/env python3
"""Read-only/non-custodial CLI for legacy CORE anchor artifacts.

New frozen-rule workflows use the dedicated rule scripts documented in
``docs/FROZEN_RULE_ANCHORING.md``. This compatibility CLI never signs or
transmits a transaction.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load validator module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cmd_prepare_legacy(args: argparse.Namespace) -> int:
    submit_module = _load_module(
        "submit_anchoring", PROJECT_ROOT / "scripts" / "submit_anchoring.py"
    )
    validator_module = _load_module(
        "validate_anchoring_submission",
        PROJECT_ROOT / "scripts" / "validate_anchoring_submission.py",
    )
    validation = validator_module.validate_anchoring_submission(args.submission)
    if validation["status"] != "passed":
        print(json.dumps(validation, indent=2, ensure_ascii=False, sort_keys=True))
        return 1

    submission = json.loads(args.submission.read_text(encoding="utf-8"))
    request = submit_module.build_unsigned_legacy_request(submission)
    if args.output.exists():
        raise ValueError("output already exists; refusing to overwrite")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(request, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "schema": "core.legacy_anchor_preparation.v1",
                "status": "passed",
                "errors": [],
                "signing_mode": "external_wallet_only",
                "transmission": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def cmd_verify_event(args: argparse.Namespace) -> int:
    verify_module = _load_module(
        "validate_anchoring_event",
        PROJECT_ROOT / "scripts" / "validate_anchoring_event.py",
    )
    result = verify_module.validate_anchoring_event(args.event_path)
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="core-anchor",
        description="Prepare unsigned legacy anchors or validate recorded events.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser(
        "prepare-legacy",
        help="Prepare a validated legacy request for review in an external wallet",
    )
    prepare_parser.add_argument("--submission", required=True, type=Path)
    prepare_parser.add_argument("--output", required=True, type=Path)
    prepare_parser.set_defaults(func=cmd_prepare_legacy)

    verify_parser = subparsers.add_parser(
        "verify-event", help="Validate a recorded legacy anchoring event"
    )
    verify_parser.add_argument("event_path", type=Path)
    verify_parser.set_defaults(func=cmd_verify_event)

    args = parser.parse_args()
    try:
        return int(args.func(args))
    except (OSError, ValueError, RuntimeError) as exc:
        print(
            json.dumps(
                {
                    "schema": "core.anchor_cli.v1",
                    "status": "failed",
                    "errors": [{"code": "anchor_cli_failed", "message": str(exc)}],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
