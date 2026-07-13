from __future__ import annotations

import csv
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

ROOT = PROJECT_ROOT / "examples" / "adapters" / "logic_debounce"
FIXTURE_DIR = ROOT / "fixtures" / "logic_debounce_v1"
FIXTURE_DIR_REL = FIXTURE_DIR.relative_to(PROJECT_ROOT)
SAMPLES_CSV = FIXTURE_DIR / "samples.csv"
MANIFEST_JSON = FIXTURE_DIR / "manifest.json"

ADAPTER_NAME = "logic_debounce"
FIXTURE_ID = "logic_debounce_v1"
VALUE_KEYS = ["raw_signal", "debounced_signal"]
VALUE_KEY = "debounced_signal"
THRESHOLD = 0.5
SENSOR_ID = "sensor:logic_debounce:v1"
TRACE_ID = "trace:logic_debounce:v1"
EVENT_ID = "event:logic_debounce:stable_high:v1"
EVENT_TYPE = "sensor.logic_debounce.stable_high"


def _raw_signal(index: int) -> int:
    if index < 30:
        return 0

    if 30 <= index <= 37:
        return [1, 0, 1, 1, 0, 1, 0, 1][index - 30]

    return 1


def _debounced_signal(index: int) -> int:
    return 1 if index >= 38 else 0


def _write_samples() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    with SAMPLES_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["index", "logical_time", *VALUE_KEYS],
        )
        writer.writeheader()

        for index in range(100):
            writer.writerow(
                {
                    "index": index,
                    "logical_time": f"t{index:03d}",
                    "raw_signal": _raw_signal(index),
                    "debounced_signal": _debounced_signal(index),
                }
            )


def _build_manifest() -> dict[str, object]:
    source = SensorSource(
        sensor_id=SENSOR_ID,
        sensor_type=ADAPTER_NAME,
        capture_mode="offline_fixture",
        calibration_id="calibration:logic_debounce:v1",
        environment_id="environment:example",
    )

    trace = load_sensor_trace_csv(
        FIXTURE_DIR_REL / "samples.csv",
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
        "calibration_id": "calibration:logic_debounce:v1",
        "environment_id": "environment:example",
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
            "Digital debounce example.",
            "raw_signal contains deterministic bounce.",
            "debounced_signal is used to derive the ObservationEvent.",
            "Offline-only.",
            "No hardware dependency.",
        ],
    }


def main() -> int:
    _write_samples()
    manifest = _build_manifest()

    MANIFEST_JSON.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print("Wrote fixture: examples/adapters/logic_debounce/fixtures/logic_debounce_v1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
