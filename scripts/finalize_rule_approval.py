#!/usr/bin/env python3
"""Attach and verify a signature produced by an external wallet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core_runtime.core.rule_anchor import finalize_approval_request  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify and record an external rule signature.")
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument(
        "--signature-file",
        required=True,
        type=Path,
        help="File containing only the public 0x signature; never a wallet secret",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    request = json.loads(args.request.read_text(encoding="utf-8"))
    signature = args.signature_file.read_text(encoding="utf-8").strip()
    try:
        approval = finalize_approval_request(request, signature)
    except ValueError as exc:
        parser.error(str(exc))

    if args.output.exists():
        parser.error("output already exists; refusing to overwrite")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(approval, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "schema": "core.rule_approval_finalization.v1",
                "status": "passed",
                "errors": [],
                "approval_fingerprint": approval["fingerprint"],
                "signer": approval["signer"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
