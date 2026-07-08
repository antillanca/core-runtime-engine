from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ADAPTER = Path("examples/adapters/image_brightness_motion")
FIXTURE = ADAPTER / "fixtures" / "image_brightness_motion_v1"
FRAMES_DIR = FIXTURE / "frames"
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


def _fixture_hashes() -> dict[str, str]:
    return {
        str(path.relative_to(FIXTURE)): _sha256(path)
        for path in sorted(FIXTURE.rglob("*"))
        if path.is_file()
    }


def test_image_brightness_motion_generates_expected_files() -> None:
    result = _run([sys.executable, str(ADAPTER / "generate_fixture.py")])
    assert result.returncode == 0, result.stderr

    assert FRAMES_DIR.exists()
    assert SAMPLES_CSV.exists()
    assert MANIFEST_JSON.exists()

    frames = sorted(FRAMES_DIR.glob("frame_*.pgm"))
    assert len(frames) == 10

    for frame in frames:
        data = frame.read_bytes()
        assert data.startswith(b"P5\n32 32\n255\n")
        assert len(data) == len(b"P5\n32 32\n255\n") + 1024

    manifest = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))

    assert manifest["fixture_id"] == "image_brightness_motion_v1"
    assert manifest["value_key"] == "frame_delta"
    assert manifest["value_keys"] == ["frame_delta", "mean_brightness"]
    assert manifest["threshold"] == 0.25
    assert manifest["observation_event_id"] == "event:image_brightness_motion:motion_spike:v1"
    assert manifest["expected_event_type"] == "sensor.image_brightness_motion.motion_spike"
    assert manifest["sample_count"] == 10


def test_image_brightness_motion_validate_certify_compliance() -> None:
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


def test_image_brightness_motion_generation_is_byte_stable() -> None:
    first = _run([sys.executable, str(ADAPTER / "generate_fixture.py")])
    assert first.returncode == 0, first.stderr
    first_hashes = _fixture_hashes()

    second = _run([sys.executable, str(ADAPTER / "generate_fixture.py")])
    assert second.returncode == 0, second.stderr
    second_hashes = _fixture_hashes()

    assert first_hashes == second_hashes


def test_image_brightness_motion_compliance_is_deterministic() -> None:
    generated = _run([sys.executable, str(ADAPTER / "generate_fixture.py")])
    assert generated.returncode == 0, generated.stderr

    first = _run([sys.executable, str(COMPLIANCE), str(ADAPTER)])
    second = _run([sys.executable, str(COMPLIANCE), str(ADAPTER)])

    assert first.returncode == 0
    assert second.returncode == 0
    assert first.stdout == second.stdout
