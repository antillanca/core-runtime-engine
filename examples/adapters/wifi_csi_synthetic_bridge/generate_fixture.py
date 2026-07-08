from __future__ import annotations

import csv
import json
import math
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

ROOT = PROJECT_ROOT / "examples" / "adapters" / "wifi_csi_synthetic_bridge"
FIXTURE_DIR = ROOT / "fixtures" / "wifi_csi_synthetic_v1"
FIXTURE_DIR_REL = FIXTURE_DIR.relative_to(PROJECT_ROOT)
SAMPLES_CSV = FIXTURE_DIR / "samples.csv"
SAMPLES_CSV_REL = SAMPLES_CSV.relative_to(PROJECT_ROOT)
MANIFEST_JSON = FIXTURE_DIR / "manifest.json"

ADAPTER_NAME = "wifi_csi_synthetic_bridge"
FIXTURE_ID = "wifi_csi_synthetic_v1"
VALUE_KEY = "motion_score"
VALUE_KEYS = [
    "motion_score",
    "phase_delta",
    "subcarrier_amplitude_variance",
    "subcarrier_mean_amplitude",
]
THRESHOLD = 0.65

SENSOR_ID = "sensor:wifi_csi_synthetic_bridge:v1"
TRACE_ID = "trace:wifi_csi_synthetic_bridge:v1"
EVENT_ID = "event:wifi_csi_synthetic_bridge:motion_spike:v1"
EVENT_TYPE = "sensor.wifi_csi_synthetic_bridge.motion_spike"

FRAME_COUNT = 100
SUBCARRIER_COUNT = 30


def _perturbation(frame_index: int) -> float:
    if 40 <= frame_index <= 65:
        center = 52.5
        distance = abs(frame_index - center) / 12.5
        return max(0.0, 1.0 - distance) * 0.7
    return 0.0


def _synthetic_amplitude(frame_index: int, subcarrier_index: int) -> float:
    base = 1.0
    slow_wave = 0.04 * math.sin((frame_index + subcarrier_index) * 0.17)
    texture = 0.02 * math.cos(subcarrier_index * 0.31)
    disturbance = _perturbation(frame_index) * (
        1.0 + 0.15 * math.sin(subcarrier_index * 0.5)
    )
    return base + slow_wave + texture + disturbance


def _synthetic_phase(frame_index: int, subcarrier_index: int) -> float:
    base_phase = 0.03 * frame_index + 0.11 * subcarrier_index
    disturbance = _perturbation(frame_index) * 0.85
    return base_phase + disturbance * math.sin(subcarrier_index * 0.23)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _variance(values: list[float], mean: float) -> float:
    return sum((value - mean) ** 2 for value in values) / len(values)


def _frame_features(
    frame_index: int,
    previous_mean_phase: float | None,
) -> tuple[float, float, float, float, float]:
    amplitudes = [
        _synthetic_amplitude(frame_index, subcarrier_index)
        for subcarrier_index in range(SUBCARRIER_COUNT)
    ]
    phases = [
        _synthetic_phase(frame_index, subcarrier_index)
        for subcarrier_index in range(SUBCARRIER_COUNT)
    ]

    mean_amplitude = _mean(amplitudes)
    amplitude_variance = _variance(amplitudes, mean_amplitude)
    mean_phase = _mean(phases)

    if previous_mean_phase is None:
        phase_delta = 0.0
    else:
        phase_delta = abs(mean_phase - previous_mean_phase)

    motion_score = min(
        1.0,
        0.12
        + _perturbation(frame_index) * 0.78
        + min(0.18, amplitude_variance * 8.0)
        + min(0.16, phase_delta * 0.6),
    )

    return mean_amplitude, amplitude_variance, phase_delta, motion_score, mean_phase


def _write_samples() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    previous_mean_phase: float | None = None

    with SAMPLES_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "index",
                "logical_time",
                "subcarrier_mean_amplitude",
                "subcarrier_amplitude_variance",
                "phase_delta",
                VALUE_KEY,
            ],
            lineterminator="\n",
        )
        writer.writeheader()

        for frame_index in range(FRAME_COUNT):
            (
                mean_amplitude,
                amplitude_variance,
                phase_delta,
                motion_score,
                previous_mean_phase,
            ) = _frame_features(frame_index, previous_mean_phase)

            writer.writerow(
                {
                    "index": frame_index,
                    "logical_time": f"csi{frame_index:03d}",
                    "subcarrier_mean_amplitude": f"{mean_amplitude:.6f}",
                    "subcarrier_amplitude_variance": f"{amplitude_variance:.6f}",
                    "phase_delta": f"{phase_delta:.6f}",
                    VALUE_KEY: f"{motion_score:.6f}",
                }
            )


def _build_manifest() -> dict[str, object]:
    source = SensorSource(
        sensor_id=SENSOR_ID,
        sensor_type=ADAPTER_NAME,
        capture_mode="offline_fixture",
        calibration_id="calibration:wifi_csi_synthetic_bridge:v1",
        environment_id="environment:synthetic_wifi_csi_example",
    )

    trace = load_sensor_trace_csv(
        SAMPLES_CSV_REL,
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
        "calibration_id": "calibration:wifi_csi_synthetic_bridge:v1",
        "environment_id": "environment:synthetic_wifi_csi_example",
        "sample_count": FRAME_COUNT,
        "value_keys": VALUE_KEYS,
        "value_key": VALUE_KEY,
        "threshold": THRESHOLD,
        "expected_event_type": EVENT_TYPE,
        "observation_event_id": EVENT_ID,
        "trace_fingerprint": trace.fingerprint(),
        "observation_event_fingerprints": {
            event.event_id: event.fingerprint(),
        },
        "synthetic_csi": {
            "frame_count": FRAME_COUNT,
            "subcarrier_count": SUBCARRIER_COUNT,
            "features": VALUE_KEYS,
            "disturbance_window": {
                "start_frame": 40,
                "end_frame": 65,
            },
        },
        "notes": [
            "Synthetic CSI-like bridge example.",
            "This is not RuView integration.",
            "This is not real WiFi sensing.",
            "No WiFi hardware is used.",
            "No packets are captured.",
            "No external CSI dataset is used.",
            "No human detection is performed.",
            "No localization is performed.",
            "No presence inference is performed.",
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

    print(f"Wrote fixture: {FIXTURE_DIR_REL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
