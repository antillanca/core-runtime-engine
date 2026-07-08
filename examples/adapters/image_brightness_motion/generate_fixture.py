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

ROOT = PROJECT_ROOT / "examples" / "adapters" / "image_brightness_motion"
FIXTURE_DIR = ROOT / "fixtures" / "image_brightness_motion_v1"
FIXTURE_DIR_REL = FIXTURE_DIR.relative_to(PROJECT_ROOT)
FRAMES_DIR = FIXTURE_DIR / "frames"
SAMPLES_CSV = FIXTURE_DIR / "samples.csv"
SAMPLES_CSV_REL = SAMPLES_CSV.relative_to(PROJECT_ROOT)
MANIFEST_JSON = FIXTURE_DIR / "manifest.json"

ADAPTER_NAME = "image_brightness_motion"
FIXTURE_ID = "image_brightness_motion_v1"
VALUE_KEY = "frame_delta"
VALUE_KEYS = ["frame_delta", "mean_brightness"]
THRESHOLD = 0.25
SENSOR_ID = "sensor:image_brightness_motion:v1"
TRACE_ID = "trace:image_brightness_motion:v1"
EVENT_ID = "event:image_brightness_motion:motion_spike:v1"
EVENT_TYPE = "sensor.image_brightness_motion.motion_spike"
WIDTH = 32
HEIGHT = 32
FRAME_COUNT = 10
MAX_PIXEL = 255


def _pixel_value(frame_index: int, x: int, y: int) -> int:
    base = 42

    if 4 <= frame_index <= 6:
        if 4 <= x < 28 and 4 <= y < 28:
            return 220
        return 64 + ((x + y + frame_index) % 5)

    if frame_index >= 7:
        return base + ((x * 2 + y + frame_index) % 7)

    return base + ((x + y + frame_index) % 7)


def _generate_frame(frame_index: int) -> bytes:
    pixels = bytearray()

    for y in range(HEIGHT):
        for x in range(WIDTH):
            pixels.append(_pixel_value(frame_index, x, y))

    return bytes(pixels)


def _write_pgm(path: Path, pixels: bytes) -> None:
    header = f"P5\n{WIDTH} {HEIGHT}\n{MAX_PIXEL}\n".encode("ascii")
    path.write_bytes(header + pixels)


def _mean_brightness(pixels: bytes) -> float:
    return sum(pixels) / (len(pixels) * MAX_PIXEL)


def _frame_delta(previous: bytes | None, current: bytes) -> float:
    if previous is None:
        return 0.0

    total = sum(abs(a - b) for a, b in zip(previous, current, strict=True))
    return total / (len(current) * MAX_PIXEL)


def _write_frames_and_samples() -> None:
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)

    previous: bytes | None = None

    with SAMPLES_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["index", "logical_time", "mean_brightness", VALUE_KEY],
        )
        writer.writeheader()

        for frame_index in range(FRAME_COUNT):
            pixels = _generate_frame(frame_index)
            _write_pgm(FRAMES_DIR / f"frame_{frame_index:03d}.pgm", pixels)

            mean = _mean_brightness(pixels)
            delta = _frame_delta(previous, pixels)

            writer.writerow(
                {
                    "index": frame_index,
                    "logical_time": f"f{frame_index:03d}",
                    "mean_brightness": f"{mean:.6f}",
                    VALUE_KEY: f"{delta:.6f}",
                }
            )

            previous = pixels


def _build_manifest() -> dict[str, object]:
    source = SensorSource(
        sensor_id=SENSOR_ID,
        sensor_type=ADAPTER_NAME,
        capture_mode="offline_fixture",
        calibration_id="calibration:image_brightness_motion:v1",
        environment_id="environment:synthetic_image_example",
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
        "calibration_id": "calibration:image_brightness_motion:v1",
        "environment_id": "environment:synthetic_image_example",
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
        "media": {
            "type": "pgm_sequence",
            "format": "P5",
            "frame_count": FRAME_COUNT,
            "width": WIDTH,
            "height": HEIGHT,
            "pixel_max": MAX_PIXEL,
            "frames_dir": "frames",
        },
        "notes": [
            "Synthetic image brightness/motion example.",
            "PGM frames are generated deterministically with Python stdlib.",
            "frame_delta is computed as mean absolute pixel difference.",
            "Offline-only.",
            "No camera.",
            "No external image dataset.",
            "No runtime authority is granted to adapter data.",
        ],
    }


def main() -> int:
    _write_frames_and_samples()

    manifest = _build_manifest()
    MANIFEST_JSON.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote fixture: {FIXTURE_DIR_REL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
