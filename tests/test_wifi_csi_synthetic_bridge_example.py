from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ADAPTER = Path("examples/adapters/wifi_csi_synthetic_bridge")
FIXTURE = ADAPTER / "fixtures" / "wifi_csi_synthetic_v1"
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


def test_wifi_csi_synthetic_bridge_generates_expected_files() -> None:
    result = _run([sys.executable, str(ADAPTER / "generate_fixture.py")])
    assert result.returncode == 0, result.stderr

    assert SAMPLES_CSV.exists()
    assert MANIFEST_JSON.exists()

    rows = list(csv.DictReader(SAMPLES_CSV.open(encoding="utf-8", newline="")))
    assert len(rows) == 100

    expected_fields = {
        "index",
        "logical_time",
        "subcarrier_mean_amplitude",
        "subcarrier_amplitude_variance",
        "phase_delta",
        "motion_score",
    }
    assert expected_fields.issubset(rows[0])

    manifest = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))

    assert manifest["fixture_id"] == "wifi_csi_synthetic_v1"
    assert manifest["value_key"] == "motion_score"
    assert manifest["value_keys"] == [
        "motion_score",
        "phase_delta",
        "subcarrier_amplitude_variance",
        "subcarrier_mean_amplitude",
    ]
    assert manifest["threshold"] == 0.65
    assert (
        manifest["observation_event_id"]
        == "event:wifi_csi_synthetic_bridge:motion_spike:v1"
    )
    assert (
        manifest["expected_event_type"]
        == "sensor.wifi_csi_synthetic_bridge.motion_spike"
    )
    assert manifest["sample_count"] == 100

    notes = "\n".join(manifest["notes"])
    assert "not RuView integration" in notes
    assert "not real WiFi sensing" in notes
    assert "No human detection" in notes
    assert "No localization" in notes


def test_wifi_csi_synthetic_bridge_motion_score_crosses_threshold_in_window() -> None:
    result = _run([sys.executable, str(ADAPTER / "generate_fixture.py")])
    assert result.returncode == 0, result.stderr

    rows = list(csv.DictReader(SAMPLES_CSV.open(encoding="utf-8", newline="")))
    scores = [float(row["motion_score"]) for row in rows]

    assert max(scores) > 0.65
    assert any(
        40 <= int(row["index"]) <= 65 and float(row["motion_score"]) > 0.65
        for row in rows
    )


def test_wifi_csi_synthetic_bridge_validate_certify_compliance() -> None:
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


def test_wifi_csi_synthetic_bridge_generation_is_byte_stable() -> None:
    first = _run([sys.executable, str(ADAPTER / "generate_fixture.py")])
    assert first.returncode == 0, first.stderr

    first_hashes = {
        "samples": _sha256(SAMPLES_CSV),
        "manifest": _sha256(MANIFEST_JSON),
    }

    second = _run([sys.executable, str(ADAPTER / "generate_fixture.py")])
    assert second.returncode == 0, second.stderr

    second_hashes = {
        "samples": _sha256(SAMPLES_CSV),
        "manifest": _sha256(MANIFEST_JSON),
    }

    assert first_hashes == second_hashes


def test_wifi_csi_synthetic_bridge_compliance_is_deterministic() -> None:
    generated = _run([sys.executable, str(ADAPTER / "generate_fixture.py")])
    assert generated.returncode == 0, generated.stderr

    first = _run([sys.executable, str(COMPLIANCE), str(ADAPTER)])
    second = _run([sys.executable, str(COMPLIANCE), str(ADAPTER)])

    assert first.returncode == 0
    assert second.returncode == 0
    assert first.stdout == second.stdout
