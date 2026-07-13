#!/usr/bin/env python3
"""Create a public message for an external wallet to sign."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core_runtime.core.rule_anchor import (  # noqa: E402
    build_approval_request,
    validate_approval_request_payload,
    validate_frozen_rule_set_payload,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an external-wallet rule approval request.")
    parser.add_argument("--rule-set", required=True, type=Path)
    parser.add_argument("--chain-id", required=True, type=int)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--signer", required=True, help="Expected public EVM address")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    rule_set = json.loads(args.rule_set.read_text(encoding="utf-8"))
    rule_errors = validate_frozen_rule_set_payload(rule_set)
    if rule_errors:
        parser.error(f"invalid frozen rule set: {rule_errors[0]['code']}")

    authorized = {
        address.lower() for address in rule_set["governance"]["authorized_signers"]
    }
    if args.signer.lower() not in authorized:
        parser.error("signer is not authorized by the frozen rule set")

    request = build_approval_request(
        rule_set["fingerprint"], args.chain_id, args.contract, args.signer
    )
    request_errors = validate_approval_request_payload(request)
    if request_errors:
        parser.error(f"approval request is invalid: {request_errors[0]['code']}")
    if args.output.exists():
        parser.error("output already exists; refusing to overwrite")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(request, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "schema": "core.rule_approval_request_creation.v1",
                "status": "passed",
                "errors": [],
                "request_fingerprint": request["fingerprint"],
                "signing_mode": "external_wallet_only",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
