#!/usr/bin/env python3
"""core-anchor — CLI for CORE v9.1 blockchain anchoring operations.

Subcommands:
    submit   — Validate and prepare an anchoring submission (dry-run by default).
    verify   — Validate an anchoring event against the schema.

Usage:
    core-anchor submit --artifact <path> [--chain-id N] [--contract 0x...] [--submitter 0x...] [--dry-run] [--broadcast]
    core-anchor verify <event_path>

Both commands are deterministic and fail-closed.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_module(name: str, path: Path):
    """Dynamically load a Python module by path."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def cmd_submit(args: argparse.Namespace) -> int:
    """Handle 'submit' subcommand."""
    submit_mod = _load_module("submit_anchoring", PROJECT_ROOT / "scripts" / "submit_anchoring.py")

    artifact_path = Path(args.artifact)
    chain_id = args.chain_id or 11155111
    contract = args.contract or "0x0000000000000000000000000000000000000001"
    submitter = args.submitter or "0x0000000000000000000000000000000000000002"
    dry_run = not args.broadcast

    result = submit_mod.build_submission(
        artifact_path=artifact_path,
        artifact_type="freeze_artifact",
        chain_id=chain_id,
        contract_address=contract,
        submitter=submitter,
    )

    if result.get("status") == "failed":
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1

    if dry_run:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print("\n[dry-run] Use --broadcast to submit on-chain.", file=sys.stderr)
        return 0
    else:
        # In real implementation, this would call web3.py
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print("\n[broadcast] On-chain submission not yet implemented.", file=sys.stderr)
        return 1


def cmd_verify(args: argparse.Namespace) -> int:
    """Handle 'verify' subcommand."""
    verify_mod = _load_module("validate_anchoring_event", PROJECT_ROOT / "scripts" / "validate_anchoring_event.py")

    target = Path(args.event_path)
    result = verify_mod.validate_anchoring_event(target)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "passed" else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="core-anchor",
        description="CORE v9.1 blockchain anchoring CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── submit ──
    submit_p = subparsers.add_parser("submit", help="Validate and prepare an anchoring submission")
    submit_p.add_argument("--artifact", required=True, help="Path to artifact JSON to anchor")
    submit_p.add_argument("--chain-id", type=int, default=None, help="Chain ID (default: 11155111 = Sepolia)")
    submit_p.add_argument("--contract", default=None, help="Contract address (0x...)")
    submit_p.add_argument("--submitter", default=None, help="Submitter address (0x...)")
    submit_p.add_argument("--broadcast", action="store_true", help="Actually broadcast (default: dry-run)")
    submit_p.set_defaults(func=cmd_submit)

    # ── verify ──
    verify_p = subparsers.add_parser("verify", help="Validate an anchoring event against schema")
    verify_p.add_argument("event_path", help="Path to anchoring event JSON (or directory)")
    verify_p.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    exit_code = args.func(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
