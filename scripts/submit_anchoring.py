#!/usr/bin/env python3
"""Prepare a legacy CoreAnchor request without custody, signing, or broadcast.

This compatibility command intentionally does not accept wallet secrets.  New
frozen-rule work should use ``build_rule_anchor_batch.py`` followed by
``prepare_rule_anchor_transaction.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core_runtime.core.rule_anchor import artifact_fingerprint  # noqa: E402
from scripts.validate_anchoring_submission import validate_anchoring_submission  # noqa: E402


NOTARIZE_HASH_SELECTOR = "1535884e"


def encode_notarize_hash(anchor_hash: str) -> str:
    """ABI-encode ``notarizeHash(bytes32)`` for the legacy contract."""

    if len(anchor_hash) != 66 or not anchor_hash.startswith("0x"):
        raise ValueError("anchor_hash must be a 0x-prefixed bytes32")
    try:
        bytes.fromhex(anchor_hash[2:])
    except ValueError as exc:
        raise ValueError("anchor_hash must contain hexadecimal bytes") from exc
    return "0x" + NOTARIZE_HASH_SELECTOR + anchor_hash[2:].lower()


def build_unsigned_legacy_request(submission: dict[str, Any]) -> dict[str, Any]:
    """Build a reviewable request for an external wallet."""

    request: dict[str, Any] = {
        "schema_version": "core.unsigned_legacy_anchor_transaction.v1",
        "type": "unsigned_legacy_anchor_transaction",
        "deprecated": True,
        "signing_mode": "external_wallet_only",
        "broadcast": False,
        "submission_id": submission["submission_id"],
        "artifact_fingerprint": submission["artifact_fingerprint"],
        "transaction": {
            "from": submission["submitter"],
            "to": submission["contract_address"],
            "chain_id": submission["chain_id"],
            "value_wei": 0,
            "data": encode_notarize_hash(submission["anchor_hash"]),
        },
        "warnings": [
            "Legacy CoreAnchor stores one hash per transaction and is superseded by CoreRuleAnchor batching.",
            "Review and sign only in an external wallet; this command never signs or broadcasts.",
        ],
    }
    request["fingerprint"] = artifact_fingerprint(request)
    return request


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare a deprecated legacy anchor for external-wallet review."
    )
    parser.add_argument("--submission", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    validation = validate_anchoring_submission(args.submission)
    if validation["status"] != "passed":
        print(json.dumps(validation, indent=2, ensure_ascii=False, sort_keys=True))
        return 1

    submission = json.loads(args.submission.read_text(encoding="utf-8"))
    request = build_unsigned_legacy_request(submission)
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
                "schema": "core.legacy_anchor_preparation.v1",
                "status": "passed",
                "errors": [],
                "deprecated": True,
                "signing_mode": "external_wallet_only",
                "broadcast": False,
                "request_fingerprint": request["fingerprint"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
