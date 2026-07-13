#!/usr/bin/env python3
"""Materialize the exact FrozenReleaseManifest for CORE v11.1.0."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_frozen_release_manifest import (  # noqa: E402
    RELEASE_VERSION,
    build_v11_1_manifest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the exact, repository-bound CORE v11.1.0 release manifest."
    )
    parser.add_argument(
        "--frozen-at",
        required=True,
        help="Release freeze timestamp with an explicit timezone.",
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = build_v11_1_manifest(args.frozen_at)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "schema": "core.frozen_release_manifest_build.v1",
                    "status": "failed",
                    "release_version": RELEASE_VERSION,
                    "errors": [
                        {
                            "code": "manifest_build_failed",
                            "message": str(exc),
                        }
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "schema": "core.frozen_release_manifest_build.v1",
                "status": "passed",
                "release_version": payload["release_version"],
                "artifact_count": payload["artifact_count"],
                "fingerprint": payload["fingerprint"],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
