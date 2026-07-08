from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core_runtime.core.sensor_evidence import (  # noqa: E402
    SensorSource,
    derive_threshold_observation_event,
    load_sensor_trace_csv,
)

ROOT = PROJECT_ROOT / "examples" / "adapters" / "privacy_safe_customer_flow"
FIXTURE_DIR = ROOT / "fixtures" / "privacy_safe_customer_flow_v1"
SAMPLES_CSV = FIXTURE_DIR / "samples.csv"
MANIFEST_JSON = FIXTURE_DIR / "manifest.json"

ADAPTER_NAME = "privacy_safe_customer_flow"
FIXTURE_ID = "privacy_safe_customer_flow_v1"
VALUE_KEYS = ["anonymous_customer_hash", "flow_count", "visits_in_window"]
VALUE_KEY = "flow_count"
THRESHOLD = 30.0
SENSOR_ID = "sensor:privacy_safe_customer_flow:v1"
TRACE_ID = "trace:privacy_safe_customer_flow:v1"
EVENT_ID = "event:privacy_safe_customer_flow:flow_spike:v1"
EVENT_TYPE = "sensor.privacy_safe_customer_flow.flow_spike"


def _stable_customer_hash(index: int) -> str:
    synthetic_id = f"synthetic_customer_{index % 17:03d}"
    digest = hashlib.sha256(synthetic_id.encode("utf-8")).hexdigest()
    return f"{int(digest[:16], 16) % 10**16:016d}"


def _canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _write_samples() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    with SAMPLES_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "index",
                "logical_time",
                "anonymous_customer_hash",
                "visits_in_window",
                "flow_count",
            ],
        )
        writer.writeheader()

        for index in range(100):
            if 50 <= index <= 65:
                flow_count = 36.0 + ((index % 3) * 1.0)
            else:
                flow_count = 18.0 + ((index % 5) * 1.0)

            visits_in_window = flow_count + (index % 4)

            writer.writerow(
                {
                    "index": index,
                    "logical_time": f"t{index:03d}",
                    "anonymous_customer_hash": _stable_customer_hash(index),
                    "visits_in_window": f"{visits_in_window:.2f}",
                    "flow_count": f"{flow_count:.2f}",
                }
            )


def _build_manifest() -> dict[str, object]:
    samples_csv_rel = SAMPLES_CSV.relative_to(PROJECT_ROOT)

    source = SensorSource(
        sensor_id=SENSOR_ID,
        sensor_type=ADAPTER_NAME,
        capture_mode="offline_fixture",
        calibration_id="calibration:privacy_safe_customer_flow:v1",
        environment_id="environment:privacy_example",
    )

    trace = load_sensor_trace_csv(
        samples_csv_rel,
        trace_id=TRACE_ID,
        source=source,
    )

    event = derive_threshold_observation_event(
        trace,
        event_id=EVENT_ID,
        event_type=EVENT_TYPE,
        value_key=VALUE_KEY,
        threshold=THRESHOLD,
    )

    return {
        "fixture_id": FIXTURE_ID,
        "schema_version": "core.sensor_evidence.v1",
        "trace_id": TRACE_ID,
        "sensor_id": SENSOR_ID,
        "expected_trace_id": TRACE_ID,
        "expected_sensor_id": SENSOR_ID,
        "sensor_type": ADAPTER_NAME,
        "capture_mode": "offline_fixture",
        "calibration_id": "calibration:privacy_safe_customer_flow:v1",
        "environment_id": "environment:privacy_example",
        "sample_count": 100,
        "value_keys": VALUE_KEYS,
        "value_key": VALUE_KEY,
        "threshold": THRESHOLD,
        "expected_event_type": EVENT_TYPE,
        "observation_event_id": EVENT_ID,
        "trace_fingerprint": trace.fingerprint(),
        "observation_event_fingerprints": {
            event.event_id: event.fingerprint(),
        },
        "notes": [
            "Privacy-safe customer flow example.",
            "Uses synthetic hashed customer identifiers.",
            "No raw PII is included.",
            "Offline-only.",
            "No runtime authority is granted to adapter data.",
        ],
    }


def main() -> int:
    _write_samples()
    manifest = _build_manifest()

    MANIFEST_JSON.write_text(_canonical_json(manifest), encoding="utf-8")

    rel = FIXTURE_DIR.relative_to(PROJECT_ROOT)
    print(f"Wrote fixture: {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
