from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import wave
from pathlib import Path

ADAPTER = Path("examples/adapters/audio_envelope_wav")
FIXTURE = ADAPTER / "fixtures" / "audio_envelope_wav_v1"
WAV_PATH = FIXTURE / "synthetic.wav"
SAMPLES_CSV = FIXTURE / "samples.csv"
MANIFEST_JSON = FIXTURE / "manifest.json"

VALIDATOR = Path("scripts/validate_sensor_manifest.py")
CERTIFIER = Path("scripts/certify_sensor_fixture.py")
COMPLIANCE = Path("scripts/check_adapter_compliance.py")


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def _payload(result: subprocess.CompletedProcess[str]) -> dict:
    assert result.stdout.strip(), result.stderr
    return json.loads(result.stdout)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_audio_envelope_wav_generates_expected_files() -> None:
    result = _run([sys.executable, str(ADAPTER / "generate_fixture.py")])
    assert result.returncode == 0, result.stderr

    assert WAV_PATH.exists()
    assert SAMPLES_CSV.exists()
    assert MANIFEST_JSON.exists()

    with wave.open(str(WAV_PATH), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        assert handle.getframerate() == 8000
        assert handle.getnframes() == 8000

    manifest = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))

    assert manifest["fixture_id"] == "audio_envelope_wav_v1"
    assert manifest["value_key"] == "rms_amplitude"
    assert manifest["value_keys"] == [
        "rms_amplitude",
        "window_end",
        "window_start",
    ]
    assert manifest["threshold"] == 0.5
    assert manifest["observation_event_id"] == "event:audio_envelope_wav:rms_spike:v1"
    assert manifest["expected_event_type"] == "sensor.audio_envelope_wav.rms_spike"
    assert manifest["sample_count"] == 10

    with SAMPLES_CSV.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 10
    assert rows[0]["window_start"] == "0.00"
    assert rows[-1]["window_end"] == "1.00"


def test_audio_envelope_wav_validate_certify_compliance() -> None:
    generated = _run([sys.executable, str(ADAPTER / "generate_fixture.py")])
    assert generated.returncode == 0, generated.stderr

    validation = _run([sys.executable, str(VALIDATOR), str(FIXTURE)])
    validation_payload = _payload(validation)
    assert validation.returncode == 0, validation.stderr
    assert validation_payload["status"] == "passed"

    certification = _run([sys.executable, str(CERTIFIER), str(FIXTURE)])
    certification_payload = _payload(certification)
    assert certification.returncode == 0, certification.stderr
    assert certification_payload["status"] == "certified"
    assert certification_payload["valid"] is True
    assert certification_payload["certified"] is True

    compliance = _run([sys.executable, str(COMPLIANCE), str(ADAPTER)])
    compliance_payload = _payload(compliance)
    assert compliance.returncode == 0, compliance.stderr
    assert compliance_payload["status"] == "compliant"
    assert compliance_payload["compliant"] is True


def test_audio_envelope_wav_generation_is_byte_stable() -> None:
    first = _run([sys.executable, str(ADAPTER / "generate_fixture.py")])
    assert first.returncode == 0, first.stderr

    first_hashes = {
        "wav": _sha256(WAV_PATH),
        "samples": _sha256(SAMPLES_CSV),
        "manifest": _sha256(MANIFEST_JSON),
    }

    second = _run([sys.executable, str(ADAPTER / "generate_fixture.py")])
    assert second.returncode == 0, second.stderr

    second_hashes = {
        "wav": _sha256(WAV_PATH),
        "samples": _sha256(SAMPLES_CSV),
        "manifest": _sha256(MANIFEST_JSON),
    }

    assert first_hashes == second_hashes


def test_audio_envelope_wav_compliance_is_deterministic() -> None:
    generated = _run([sys.executable, str(ADAPTER / "generate_fixture.py")])
    assert generated.returncode == 0, generated.stderr

    first = _run([sys.executable, str(COMPLIANCE), str(ADAPTER)])
    second = _run([sys.executable, str(COMPLIANCE), str(ADAPTER)])

    assert first.returncode == 0
    assert second.returncode == 0
    assert first.stdout == second.stdout
