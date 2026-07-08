from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


VALID_FIXTURE = Path("tests/fixtures/sensor_evidence/simulated_scalar_v1")
SCRIPT = Path("scripts/validate_sensor_manifest.py")


def _copy_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "fixture"
    shutil.copytree(VALID_FIXTURE, target)
    return target


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _run_validator(fixture_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(fixture_dir)],
        check=False,
        capture_output=True,
        text=True,
    )


def _payload(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    assert result.stdout.strip(), result.stderr
    return json.loads(result.stdout)


def _error_codes(payload: dict[str, Any]) -> set[str]:
    return {error["code"] for error in payload.get("errors", [])}


def _assert_failed(result: subprocess.CompletedProcess[str], expected_code: str) -> dict[str, Any]:
    payload = _payload(result)

    assert result.returncode == 1
    assert payload["status"] == "failed"
    assert expected_code in _error_codes(payload)
    assert not result.stderr.strip()
    return payload


def test_missing_manifest_fails(tmp_path: Path) -> None:
    fixture = _copy_fixture(tmp_path)
    (fixture / "manifest.json").unlink()

    _assert_failed(_run_validator(fixture), "manifest_missing")


def test_missing_samples_fails(tmp_path: Path) -> None:
    fixture = _copy_fixture(tmp_path)
    (fixture / "samples.csv").unlink()

    _assert_failed(_run_validator(fixture), "samples_missing")


def test_wrong_sample_count_fails(tmp_path: Path) -> None:
    fixture = _copy_fixture(tmp_path)
    manifest_path = fixture / "manifest.json"
    manifest = _load_json(manifest_path)
    manifest["sample_count"] = 999
    _write_json(manifest_path, manifest)

    _assert_failed(_run_validator(fixture), "sample_count_mismatch")


def test_wrong_trace_fingerprint_fails(tmp_path: Path) -> None:
    fixture = _copy_fixture(tmp_path)
    manifest_path = fixture / "manifest.json"
    manifest = _load_json(manifest_path)
    manifest["trace_fingerprint"] = "0" * 64
    _write_json(manifest_path, manifest)

    _assert_failed(_run_validator(fixture), "trace_fingerprint_mismatch")


def test_wrong_observation_event_fingerprint_fails(tmp_path: Path) -> None:
    fixture = _copy_fixture(tmp_path)
    manifest_path = fixture / "manifest.json"
    manifest = _load_json(manifest_path)
    event_id = manifest.get("observation_event_id", "event:sensor:simulated:threshold:v1")
    manifest["observation_event_fingerprints"] = {event_id: "1" * 64}
    _write_json(manifest_path, manifest)

    _assert_failed(_run_validator(fixture), "observation_event_fingerprint_mismatch")


def test_wrong_sensor_id_fails(tmp_path: Path) -> None:
    fixture = _copy_fixture(tmp_path)
    manifest_path = fixture / "manifest.json"
    manifest = _load_json(manifest_path)
    manifest["sensor_id"] = "sensor:wrong"
    _write_json(manifest_path, manifest)

    _assert_failed(_run_validator(fixture), "sensor_id_mismatch")


def test_wrong_trace_id_fails(tmp_path: Path) -> None:
    fixture = _copy_fixture(tmp_path)
    manifest_path = fixture / "manifest.json"
    manifest = _load_json(manifest_path)
    manifest["trace_id"] = "trace:wrong"
    _write_json(manifest_path, manifest)

    _assert_failed(_run_validator(fixture), "trace_id_mismatch")


def test_missing_value_key_fails(tmp_path: Path) -> None:
    fixture = _copy_fixture(tmp_path)
    manifest_path = fixture / "manifest.json"
    manifest = _load_json(manifest_path)
    manifest["value_key"] = "missing_signal"
    manifest["value_keys"] = ["missing_signal"]
    _write_json(manifest_path, manifest)

    _assert_failed(_run_validator(fixture), "value_key_missing")


def test_invalid_threshold_fails(tmp_path: Path) -> None:
    fixture = _copy_fixture(tmp_path)
    manifest_path = fixture / "manifest.json"
    manifest = _load_json(manifest_path)
    manifest["threshold"] = "not-a-number"
    _write_json(manifest_path, manifest)

    _assert_failed(_run_validator(fixture), "threshold_invalid")


def test_negative_case_output_is_deterministic(tmp_path: Path) -> None:
    fixture = _copy_fixture(tmp_path)
    manifest_path = fixture / "manifest.json"
    manifest = _load_json(manifest_path)
    manifest["sample_count"] = 999
    _write_json(manifest_path, manifest)

    first = _run_validator(fixture)
    second = _run_validator(fixture)

    assert first.returncode == 1
    assert second.returncode == 1
    assert json.loads(first.stdout) == json.loads(second.stdout)
