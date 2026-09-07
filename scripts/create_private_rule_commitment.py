#!/usr/bin/env python3
"""Create a blinded personal-rule commitment without exposing its opening.

The private content and random nonce stay off-chain.  The nonce is written to
an explicit, new file with mode 0600 and is never printed to stdout.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT_PATH = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_PATH))

from core_runtime.core.rule_anchor import (  # noqa: E402
    artifact_fingerprint,
    private_content_fingerprint,
    private_rule_commitment,
    validate_frozen_rule_set_payload,
)


def _write_new_json(path: Path, payload: Any, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, mode)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _inside_public_repository(path: Path) -> bool:
    try:
        path.resolve().relative_to(PROJECT_ROOT_PATH.resolve())
    except ValueError:
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a private-rule commitment and a secret local opening."
    )
    parser.add_argument("--private-rules", required=True, type=Path)
    parser.add_argument("--public-template", required=True, type=Path)
    parser.add_argument("--public-output", required=True, type=Path)
    parser.add_argument("--opening-output", required=True, type=Path)
    args = parser.parse_args()

    if _inside_public_repository(args.opening_output):
        parser.error("--opening-output must be outside the public CORE repository")

    private_payload = json.loads(args.private_rules.read_text(encoding="utf-8"))
    public_envelope = json.loads(args.public_template.read_text(encoding="utf-8"))
    if not isinstance(public_envelope, dict):
        parser.error("public template must contain a JSON object")

    nonce = os.urandom(32)
    commitment = private_rule_commitment(private_payload, nonce)
    content = public_envelope.get("content")
    if not isinstance(content, dict) or content.get("mode") != "private_commitment":
        parser.error("public template content.mode must be private_commitment")
    content["commitment"] = commitment
    public_envelope["fingerprint"] = artifact_fingerprint(public_envelope)

    validation_errors = validate_frozen_rule_set_payload(public_envelope)
    if validation_errors:
        parser.error(f"generated public envelope is invalid: {validation_errors[0]['code']}")

    opening = {
        "schema_version": "core.private_rule_opening.v1",
        "type": "private_rule_opening",
        "sensitive": True,
        "commitment": commitment,
        "private_content_fingerprint": private_content_fingerprint(private_payload),
        "blinding_nonce_hex": nonce.hex(),
    }

    _write_new_json(args.opening_output, opening, mode=0o600)
    try:
        _write_new_json(args.public_output, public_envelope)
    except Exception:
        args.opening_output.unlink(missing_ok=True)
        raise

    print(
        json.dumps(
            {
                "schema": "core.private_rule_commitment_creation.v1",
                "status": "passed",
                "errors": [],
                "public_fingerprint": public_envelope["fingerprint"],
                "opening_permissions": "0600",
                "opening_published": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
