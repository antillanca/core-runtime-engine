from __future__ import annotations

import argparse
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

ROOT = PROJECT_ROOT / "examples" / "adapters" / "threshold_scalar_basic"
FIXTURE_DIR = ROOT / "fixtures" / "threshold_scalar_basic_v1"
FIXTURE_DIR_REL = FIXTURE_DIR.relative_to(PROJECT_ROOT)
SAMPLES_CSV = FIXTURE_DIR / "samples.csv"
MANIFEST_JSON = FIXTURE_DIR / "manifest.json"

HYSTERESIS_FIXTURE_DIR = ROOT / "fixtures" / "hysteresis_v1"
HYSTERESIS_FIXTURE_DIR_REL = HYSTERESIS_FIXTURE_DIR.relative_to(PROJECT_ROOT)
HYSTERESIS_SAMPLES_CSV = HYSTERESIS_FIXTURE_DIR / "samples.csv"
HYSTERESIS_MANIFEST_JSON = HYSTERESIS_FIXTURE_DIR / "manifest.json"

ADAPTER_NAME = "threshold_scalar_basic"
FIXTURE_ID = "threshold_scalar_basic_v1"
VALUE_KEY = "signal"
THRESHOLD = 10.0
SENSOR_ID = "sensor:threshold_scalar_basic:v1"
TRACE_ID = "trace:threshold_scalar_basic:v1"
EVENT_ID = "event:threshold_scalar_basic:threshold:v1"
EVENT_TYPE = "sensor.threshold_scalar_basic.threshold_crossing"

HYSTERESIS_FIXTURE_ID = "hysteresis_v1"
HYSTERESIS_SENSOR_ID = "sensor:threshold_scalar_basic:hysteresis:v1"
HYSTERESIS_TRACE_ID = "trace:threshold_scalar_basic:hysteresis:v1"
HYSTERESIS_EVENT_ID = "event:threshold_scalar_basic:hysteresis_active:v1"
HYSTERESIS_EVENT_TYPE = "sensor.threshold_scalar_basic.hysteresis_active"
HYSTERESIS_UPPER_THRESHOLD = 11.0
HYSTERESIS_LOWER_THRESHOLD = 9.0
HYSTERESIS_VALUE_KEYS = ["signal", "hysteresis_state"]
HYSTERESIS_VALUE_KEY = "hysteresis_state"
HYSTERESIS_THRESHOLD = 0.5


def _canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _write_samples() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    with SAMPLES_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["index", "logical_time", VALUE_KEY],
        )
        writer.writeheader()

        for index in range(100):
            if 40 <= index <= 55:
                value = 12.5
            else:
                value = 7.0 + ((index % 5) * 0.1)

            writer.writerow(
                {
                    "index": index,
                    "logical_time": f"t{index:03d}",
                    VALUE_KEY: f"{value:.2f}",
                }
            )


def _write_hysteresis_samples() -> None:
    HYSTERESIS_FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    with HYSTERESIS_SAMPLES_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["index", "logical_time", "signal", "hysteresis_state"],
        )
        writer.writeheader()

        hysteresis_state = 0
        for index in range(100):
            if index < 12:
                signal = 8.6 + ((index % 3) * 0.1)
            elif index < 24:
                signal = 9.4 + ((index % 4) * 0.2)
            elif index < 36:
                signal = 10.6 + ((index % 3) * 0.2)
            elif index < 48:
                signal = 11.2 + ((index % 2) * 0.1)
            elif index < 60:
                signal = 8.7 + ((index % 3) * 0.1)
            elif index < 72:
                signal = 10.0 + ((index % 4) * 0.15)
            elif index < 84:
                signal = 11.3 + ((index % 2) * 0.1)
            else:
                signal = 8.5 + ((index % 4) * 0.1)

            if signal >= HYSTERESIS_UPPER_THRESHOLD:
                hysteresis_state = 1
            elif signal <= HYSTERESIS_LOWER_THRESHOLD:
                hysteresis_state = 0

            writer.writerow(
                {
                    "index": index,
                    "logical_time": f"h{index:03d}",
                    "signal": f"{signal:.2f}",
                    "hysteresis_state": str(hysteresis_state),
                }
            )


def _build_manifest() -> dict[str, object]:
    source = SensorSource(
        sensor_id=SENSOR_ID,
        sensor_type=ADAPTER_NAME,
        capture_mode="offline_fixture",
        calibration_id="calibration:threshold_scalar_basic:v1",
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
        "sensor_type": "threshold_scalar_basic",
        "capture_mode": "offline_fixture",
        "calibration_id": "calibration:threshold_scalar_basic:v1",
        "environment_id": "environment:example",
        "sample_count": 100,
        "value_keys": [VALUE_KEY],
        "value_key": VALUE_KEY,
        "threshold": THRESHOLD,
        "expected_event_type": EVENT_TYPE,
        "observation_event_id": EVENT_ID,
        "trace_fingerprint": trace.fingerprint(),
        "observation_event_fingerprints": {
            event.event_id: event.fingerprint(),
        },
        "notes": [
            "Basic scalar threshold example.",
            "Offline-only.",
            "No hardware dependency.",
            "No runtime authority is granted to adapter data.",
        ],
    }


def _build_hysteresis_manifest() -> dict[str, object]:
    source = SensorSource(
        sensor_id=HYSTERESIS_SENSOR_ID,
        sensor_type=ADAPTER_NAME,
        capture_mode="offline_fixture",
        calibration_id="calibration:threshold_scalar_basic:hysteresis:v1",
        environment_id="environment:example",
    )

    trace = load_sensor_trace_csv(
        HYSTERESIS_FIXTURE_DIR_REL / "samples.csv",
        trace_id=HYSTERESIS_TRACE_ID,
        source=source,
    )

    event = derive_threshold_observation_event(
        trace,
        event_id=HYSTERESIS_EVENT_ID,
        event_type=HYSTERESIS_EVENT_TYPE,
        value_key=HYSTERESIS_VALUE_KEY,
        threshold=HYSTERESIS_THRESHOLD,
    )

    return {
        "fixture_id": HYSTERESIS_FIXTURE_ID,
        "schema_version": "core.sensor_evidence.v1",
        "trace_id": HYSTERESIS_TRACE_ID,
        "sensor_id": HYSTERESIS_SENSOR_ID,
        "expected_trace_id": HYSTERESIS_TRACE_ID,
        "expected_sensor_id": HYSTERESIS_SENSOR_ID,
        "sensor_type": ADAPTER_NAME,
        "capture_mode": "offline_fixture",
        "calibration_id": "calibration:threshold_scalar_basic:hysteresis:v1",
        "environment_id": "environment:example",
        "sample_count": 100,
        "value_keys": HYSTERESIS_VALUE_KEYS,
        "value_key": HYSTERESIS_VALUE_KEY,
        "threshold": HYSTERESIS_THRESHOLD,
        "expected_event_type": HYSTERESIS_EVENT_TYPE,
        "observation_event_id": HYSTERESIS_EVENT_ID,
        "trace_fingerprint": trace.fingerprint(),
        "observation_event_fingerprints": {
            event.event_id: event.fingerprint(),
        },
        "notes": [
            "Hysteresis threshold example.",
            "Offline-only.",
            "No hardware dependency.",
            "No runtime authority is granted to adapter data.",
        ],
    }


def generate_threshold_fixture() -> Path:
    _write_samples()
    manifest = _build_manifest()

    MANIFEST_JSON.write_text(_canonical_json(manifest), encoding="utf-8")
    return FIXTURE_DIR


def generate_hysteresis_fixture() -> Path:
    _write_hysteresis_samples()
    manifest = _build_hysteresis_manifest()

    HYSTERESIS_MANIFEST_JSON.write_text(_canonical_json(manifest), encoding="utf-8")
    return HYSTERESIS_FIXTURE_DIR


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate deterministic threshold scalar fixtures."
    )
    parser.add_argument(
        "--scenario",
        choices=["threshold", "hysteresis", "all"],
        default="all",
        help="Fixture scenario to generate.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    generated: list[Path] = []
    if args.scenario in {"threshold", "all"}:
        generated.append(generate_threshold_fixture())
    if args.scenario in {"hysteresis", "all"}:
        generated.append(generate_hysteresis_fixture())

    for fixture_dir in generated:
        print(f"Wrote fixture: {fixture_dir.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
