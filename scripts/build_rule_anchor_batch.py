#!/usr/bin/env python3
"""Build a deterministic Merkle batch from frozen rules and approvals."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT_PATH = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_PATH))

from core_runtime.core.rule_anchor import PROJECT_ROOT, build_rule_anchor_batch  # noqa: E402


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_repository_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("build-request paths must be repository-relative and cannot contain '..'")
    resolved = (PROJECT_ROOT / candidate).resolve()
    try:
        resolved.relative_to(PROJECT_ROOT.resolve())
    except ValueError as exc:
        raise ValueError("build-request path escapes the repository") from exc
    return resolved


def _paths_from_request(path: Path) -> tuple[list[Path], list[Path]]:
    request = _read_json(path)
    if not isinstance(request, dict):
        raise ValueError("batch build request must be a JSON object")
    allowed = {"schema_version", "type", "rule_set_paths", "approval_paths"}
    if set(request) != allowed:
        raise ValueError("batch build request has missing or additional fields")
    if request.get("schema_version") != "core.rule_anchor_batch_build_request.v1":
        raise ValueError("unsupported batch build request schema_version")
    if request.get("type") != "rule_anchor_batch_build_request":
        raise ValueError("invalid batch build request type")
    rule_paths = request.get("rule_set_paths")
    approval_paths = request.get("approval_paths")
    if not isinstance(rule_paths, list) or not rule_paths:
        raise ValueError("rule_set_paths must be a non-empty list")
    if not isinstance(approval_paths, list) or not approval_paths:
        raise ValueError("approval_paths must be a non-empty list")
    if not all(isinstance(item, str) and item for item in rule_paths + approval_paths):
        raise ValueError("all build-request paths must be non-empty strings")
    return (
        [_safe_repository_path(item) for item in rule_paths],
        [_safe_repository_path(item) for item in approval_paths],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a CORE frozen-rule Merkle batch.")
    parser.add_argument(
        "request",
        nargs="?",
        type=Path,
        help="Optional repository-local batch build request JSON",
    )
    parser.add_argument("--rule-set", action="append", default=[], type=Path)
    parser.add_argument("--approval", action="append", default=[], type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        if args.request is not None:
            if args.rule_set or args.approval:
                parser.error("request cannot be combined with --rule-set or --approval")
            rule_paths, approval_paths = _paths_from_request(args.request)
        else:
            rule_paths, approval_paths = args.rule_set, args.approval
            if not rule_paths or not approval_paths:
                parser.error("provide a request or at least one --rule-set and --approval")

        rule_sets = [_read_json(path) for path in rule_paths]
        approvals = [_read_json(path) for path in approval_paths]
        batch = build_rule_anchor_batch(rule_sets, approvals)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "schema": "core.rule_anchor_batch_build.v1",
                    "status": "failed",
                    "errors": [
                        {
                            "code": "batch_build_failed",
                            "message": str(exc),
                        }
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    if args.output is not None:
        if args.output.exists():
            parser.error("output already exists; refusing to overwrite")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(batch, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    result: dict[str, Any] = {
        "schema": "core.rule_anchor_batch_build.v1",
        "status": "passed",
        "errors": [],
        "batch_id": batch["batch_id"],
        "merkle_root": batch["merkle_root"],
        "manifest_fingerprint": batch["manifest_fingerprint"],
        "rule_set_count": batch["rule_set_count"],
    }
    if args.output is None:
        result["artifact"] = batch
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
