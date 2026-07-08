#!/usr/bin/env python3
"""Derive business events from observations using a state watcher registration.

This script is deterministic and offline. It never mutates runtime state.
It reads a watcher registration and a directory of observations, then derives
business events for observations that satisfy the watch condition.

Usage:
    python scripts/derive_business_event.py <watcher.json> <observations_dir>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUSINESS_EVENT_SCHEMA_PATH = PROJECT_ROOT / "schemas" / "business_event.schema.json"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _canonical_dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _compute_fingerprint(event: dict[str, Any]) -> str:
    """Compute SHA-256 fingerprint of the event envelope (excluding the fingerprint field)."""
    envelope = {k: v for k, v in sorted(event.items()) if k != "fingerprint"}
    canonical = json.dumps(envelope, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _evaluate_condition(
    operator: str,
    value: float,
    threshold: float,
    threshold_value_override: float | None = None,
) -> bool:
    """Evaluate a scalar watch condition against a single observation."""
    ref = threshold_value_override if threshold_value_override is not None else threshold

    if operator == "gt":
        return value > ref
    elif operator == "gte":
        return value >= ref
    elif operator == "lt":
        return value < ref
    elif operator == "lte":
        return value <= ref
    elif operator == "eq":
        return value == ref
    elif operator == "neq":
        return value != ref
    else:
        # within_range and outside_range require range semantics not applicable to scalar
        return False


def derive_events(
    watcher_data: dict[str, Any],
    observations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Derive business events from observations based on the watcher registration."""
    if not watcher_data.get("enabled", True):
        return []

    condition = watcher_data.get("watch_condition", {})
    operator = condition.get("operator", "")
    watcher_id = watcher_data.get("watcher_id", "unknown")
    event_type = watcher_data.get("event_type", "unknown")
    threshold_value = watcher_data.get("threshold_value")

    if operator in ("within_range", "outside_range"):
        # Range operators require range definitions not in the scalar fixture
        return []

    events: list[dict[str, Any]] = []

    for obs in observations:
        value = obs.get("value")
        reference = obs.get("reference")

        if value is None or reference is None:
            continue

        triggered = _evaluate_condition(operator, float(value), float(reference), threshold_value)

        if triggered:
            event: dict[str, Any] = {
                "event_id": f"evt_{watcher_id}_{obs.get('observation_id', 'unknown')}",
                "event_type": event_type,
                "source_watcher_id": watcher_id,
                "timestamp": obs.get("timestamp", ""),
                "fingerprint": "PLACEHOLDER",
                "payload": {
                    "operand_value": float(value),
                    "threshold_value": float(threshold_value if threshold_value is not None else reference),
                    "observation_id": obs.get("observation_id", ""),
                },
            }
            event["fingerprint"] = _compute_fingerprint(event)
            events.append(event)

    return events


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Derive business events from observations using a state watcher registration.",
    )
    parser.add_argument(
        "watcher_path",
        help="Path to a watcher registration .json file.",
    )
    parser.add_argument(
        "observations_dir",
        help="Path to a directory containing observations.jsonl.",
    )
    args = parser.parse_args()

    watcher_path = Path(args.watcher_path)
    observations_dir = Path(args.observations_dir)

    if not watcher_path.exists():
        print(_canonical_dump({"status": "failed", "errors": [{"code": "watcher_missing", "message": "Watcher file not found."}]}))
        return 1

    if not observations_dir.exists():
        print(_canonical_dump({"status": "failed", "errors": [{"code": "observations_dir_missing", "message": "Observations directory not found."}]}))
        return 1

    try:
        watcher_data = _load_json(watcher_path)
    except (json.JSONDecodeError, OSError) as exc:
        print(_canonical_dump({"status": "failed", "errors": [{"code": "watcher_load_failed", "message": str(exc)}]}))
        return 1

    observations_file = observations_dir / "observations.jsonl"
    if not observations_file.exists():
        print(_canonical_dump({"status": "failed", "errors": [{"code": "observations_file_missing", "message": "observations.jsonl not found."}]}))
        return 1

    observations: list[dict[str, Any]] = []
    with observations_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                observations.append(json.loads(line))

    events = derive_events(watcher_data, observations)

    result = {
        "schema": "core.business_event_derivation.v1",
        "status": "derived",
        "watcher_id": watcher_data.get("watcher_id"),
        "event_type": watcher_data.get("event_type"),
        "observation_count": len(observations),
        "derived_event_count": len(events),
        "events": events,
    }

    print(_canonical_dump(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
