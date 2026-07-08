from __future__ import annotations

import csv
import json
import math
import struct
import sys
import wave
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core_runtime.core.sensor_evidence import (  # noqa: E402
    SensorSource,
    derive_threshold_observation_event,
    load_sensor_trace_csv,
)

ROOT = PROJECT_ROOT / "examples" / "adapters" / "audio_envelope_wav"
FIXTURE_DIR = ROOT / "fixtures" / "audio_envelope_wav_v1"
FIXTURE_DIR_REL = FIXTURE_DIR.relative_to(PROJECT_ROOT)
WAV_PATH = FIXTURE_DIR / "synthetic.wav"
SAMPLES_CSV = FIXTURE_DIR / "samples.csv"
MANIFEST_JSON = FIXTURE_DIR / "manifest.json"

ADAPTER_NAME = "audio_envelope_wav"
FIXTURE_ID = "audio_envelope_wav_v1"
VALUE_KEY = "rms_amplitude"
VALUE_KEYS = ["rms_amplitude", "window_end", "window_start"]
THRESHOLD = 0.50
SENSOR_ID = "sensor:audio_envelope_wav:v1"
TRACE_ID = "trace:audio_envelope_wav:v1"
EVENT_ID = "event:audio_envelope_wav:rms_spike:v1"
EVENT_TYPE = "sensor.audio_envelope_wav.rms_spike"
SAMPLE_RATE = 8000
DURATION_SECONDS = 1.0
FREQUENCY_HZ = 440.0
WINDOW_SECONDS = 0.1
MAX_INT16 = 32767


def _amplitude_for_time(seconds: float) -> float:
    if 0.40 <= seconds < 0.65:
        return 0.85
    return 0.20


def _generate_pcm_samples() -> list[int]:
    sample_count = int(SAMPLE_RATE * DURATION_SECONDS)
    samples: list[int] = []

    for index in range(sample_count):
        seconds = index / SAMPLE_RATE
        amplitude = _amplitude_for_time(seconds)
        value = amplitude * math.sin(2.0 * math.pi * FREQUENCY_HZ * seconds)
        samples.append(int(round(value * MAX_INT16)))

    return samples


def _write_wav(samples: list[int]) -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    with wave.open(str(WAV_PATH), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))


def _window_rms(samples: list[int], start: int, stop: int) -> float:
    window = samples[start:stop]
    if not window:
        return 0.0

    mean_square = sum((sample / MAX_INT16) ** 2 for sample in window) / len(window)
    return math.sqrt(mean_square)


def _write_samples_csv(samples: list[int]) -> None:
    window_size = int(SAMPLE_RATE * WINDOW_SECONDS)
    window_count = int(len(samples) / window_size)

    with SAMPLES_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "index",
                "logical_time",
                "window_start",
                "window_end",
                VALUE_KEY,
            ],
        )
        writer.writeheader()

        for window_index in range(window_count):
            start = window_index * window_size
            stop = start + window_size
            window_start = window_index * WINDOW_SECONDS
            window_end = window_start + WINDOW_SECONDS
            rms = _window_rms(samples, start, stop)

            writer.writerow(
                {
                    "index": window_index,
                    "logical_time": f"w{window_index:03d}",
                    "window_start": f"{window_start:.2f}",
                    "window_end": f"{window_end:.2f}",
                    VALUE_KEY: f"{rms:.6f}",
                }
            )


def _build_manifest() -> dict[str, object]:
    source = SensorSource(
        sensor_id=SENSOR_ID,
        sensor_type=ADAPTER_NAME,
        capture_mode="offline_fixture",
        calibration_id="calibration:audio_envelope_wav:v1",
        environment_id="environment:synthetic_audio_example",
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
        "calibration_id": "calibration:audio_envelope_wav:v1",
        "environment_id": "environment:synthetic_audio_example",
        "sample_count": 10,
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
            "type": "wav",
            "path": "synthetic.wav",
            "sample_rate": SAMPLE_RATE,
            "duration_seconds": DURATION_SECONDS,
            "channels": 1,
            "sample_width_bytes": 2,
            "window_seconds": WINDOW_SECONDS,
        },
        "notes": [
            "Synthetic audio envelope example.",
            "WAV file is generated deterministically with Python stdlib.",
            "RMS envelope is computed over fixed rectangular windows.",
            "Offline-only.",
            "No microphone.",
            "No external audio dataset.",
            "No runtime authority is granted to adapter data.",
        ],
    }


def main() -> int:
    samples = _generate_pcm_samples()
    _write_wav(samples)
    _write_samples_csv(samples)

    manifest = _build_manifest()
    MANIFEST_JSON.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote fixture: {FIXTURE_DIR_REL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
