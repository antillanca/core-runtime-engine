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

ROOT = PROJECT_ROOT / "examples" / "adapters" / "multi_channel_environment"
FIXTURE_DIR = ROOT / "fixtures" / "multi_channel_environment_v1"
FIXTURE_DIR_REL = FIXTURE_DIR.relative_to(PROJECT_ROOT)
SAMPLES_CSV = FIXTURE_DIR / "samples.csv"
MANIFEST_JSON = FIXTURE_DIR / "manifest.json"

ADAPTER_NAME = "multi_channel_environment"
FIXTURE_ID = "multi_channel_environment_v1"
VALUE_KEYS = ["temperature", "humidity", "pressure"]
VALUE_KEY = "temperature"
THRESHOLD = 30.0
SENSOR_ID = "sensor:multi_channel_environment:v1"
TRACE_ID = "trace:multi_channel_environment:v1"
EVENT_ID = "event:multi_channel_environment:temperature_threshold:v1"
EVENT_TYPE = "sensor.multi_channel_environment.temperature_threshold_crossing"


def _write_samples() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    with SAMPLES_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["index", "logical_time", *VALUE_KEYS],
        )
        writer.writeheader()

        for index in range(100):
            if 35 <= index <= 50:
                temperature = 32.0
            else:
                temperature = 24.0 + ((index % 7) * 0.2)

            humidity = 45.0 + ((index % 10) * 0.5)
            pressure = 1000.0 + ((index % 6) * 0.3)

            writer.writerow(
                {
                    "index": index,
                    "logical_time": f"t{index:03d}",
                    "temperature": f"{temperature:.2f}",
                    "humidity": f"{humidity:.2f}",
                    "pressure": f"{pressure:.2f}",
                }
            )


def _build_manifest() -> dict[str, object]:
    source = SensorSource(
        sensor_id=SENSOR_ID,
        sensor_type=ADAPTER_NAME,
        capture_mode="offline_fixture",
        calibration_id="calibration:multi_channel_environment:v1",
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
        "calibration_id": "calibration:multi_channel_environment:v1",
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
            "Multi-channel environment example.",
            "Only temperature is used to derive the ObservationEvent.",
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

    print("Wrote fixture: examples/adapters/multi_channel_environment/fixtures/multi_channel_environment_v1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
