from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core_runtime.core.sensor_evidence import (
    SensorSource,
    derive_threshold_observation_event,
    load_sensor_trace_csv,
)

ROOT = PROJECT_ROOT / "examples" / "adapters" / "minimal_sensor_adapter"
FIXTURE_DIR = ROOT / "fixtures" / "minimal_temperature_v1"
FIXTURE_DIR_REL = FIXTURE_DIR.relative_to(PROJECT_ROOT)
SAMPLES_CSV = FIXTURE_DIR / "samples.csv"
MANIFEST_JSON = FIXTURE_DIR / "manifest.json"


def _write_samples() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    with SAMPLES_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["index", "logical_time", "temperature"],
        )
        writer.writeheader()

        for index in range(100):
            if 30 <= index <= 45:
                temperature = 31.5
            else:
                temperature = 24.0 + ((index % 5) * 0.1)

            writer.writerow(
                {
                    "index": index,
                    "logical_time": f"t{index:03d}",
                    "temperature": f"{temperature:.2f}",
                }
            )


def _build_manifest() -> dict[str, object]:
    source = SensorSource(
        sensor_id="sensor:minimal:temperature:v1",
        sensor_type="minimal_temperature",
        capture_mode="offline_fixture",
        calibration_id="calibration:minimal:temperature:v1",
        environment_id="environment:example",
    )

    trace = load_sensor_trace_csv(
        FIXTURE_DIR_REL / "samples.csv",
        trace_id="trace:minimal:temperature:v1",
        source=source,
    )

    event = derive_threshold_observation_event(
        trace,
        event_id="event:minimal:temperature:threshold:v1",
        event_type="sensor.minimal.temperature.threshold_crossing",
        value_key="temperature",
        threshold=30.0,
    )

    return {
        "fixture_id": "minimal_temperature_v1",
        "schema_version": "core.sensor_evidence.v1",
        "trace_id": "trace:minimal:temperature:v1",
        "sensor_id": "sensor:minimal:temperature:v1",
        "expected_trace_id": "trace:minimal:temperature:v1",
        "expected_sensor_id": "sensor:minimal:temperature:v1",
        "sensor_type": "minimal_temperature",
        "capture_mode": "offline_fixture",
        "calibration_id": "calibration:minimal:temperature:v1",
        "environment_id": "environment:example",
        "sample_count": 100,
        "value_keys": ["temperature"],
        "value_key": "temperature",
        "threshold": 30.0,
        "expected_event_type": "sensor.minimal.temperature.threshold_crossing",
        "observation_event_id": "event:minimal:temperature:threshold:v1",
        "trace_fingerprint": trace.fingerprint(),
        "observation_event_fingerprints": {
            event.event_id: event.fingerprint(),
        },
        "notes": [
            "Minimal adapter example.",
            "Offline-only.",
            "No hardware dependency.",
            "No runtime authority is granted to adapter data.",
        ],
    }


def main() -> int:
    _write_samples()
    manifest = _build_manifest()

    MANIFEST_JSON.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print("Wrote fixture: examples/adapters/minimal_sensor_adapter/fixtures/minimal_temperature_v1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
