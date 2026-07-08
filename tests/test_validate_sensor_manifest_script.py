from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


FIXTURE_DIR = Path("tests/fixtures/sensor_evidence/simulated_scalar_v1")
SCRIPT = Path("scripts/validate_sensor_manifest.py")


def _run_validator(fixture_dir: Path = FIXTURE_DIR) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(fixture_dir)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_validate_sensor_manifest_script_passes() -> None:
    result = _run_validator()

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)

    assert payload["status"] == "passed"
    assert payload["errors"] == []
    assert payload["deterministic"] is True
    assert len(payload["trace_fingerprint"]) == 64
    assert len(payload["observation_event_fingerprint"]) == 64


def test_validate_sensor_manifest_script_is_deterministic() -> None:
    first = _run_validator()
    second = _run_validator()

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert json.loads(first.stdout) == json.loads(second.stdout)


def test_validate_sensor_manifest_script_fails_for_missing_fixture(tmp_path: Path) -> None:
    result = _run_validator(tmp_path / "missing_fixture")

    assert result.returncode == 1
    payload = json.loads(result.stdout)

    assert payload["status"] == "failed"
    assert payload["errors"]
