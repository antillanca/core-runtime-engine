from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ADAPTER_SCRIPT = Path("examples/adapters/minimal_sensor_adapter/generate_fixture.py")
FIXTURE_DIR = Path("examples/adapters/minimal_sensor_adapter/fixtures/minimal_temperature_v1")
VALIDATOR = Path("scripts/validate_sensor_manifest.py")
CERTIFIER = Path("scripts/certify_sensor_fixture.py")


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
    )


def test_minimal_sensor_adapter_generates_fixture() -> None:
    result = _run([sys.executable, str(ADAPTER_SCRIPT)])

    assert result.returncode == 0, result.stderr
    assert (FIXTURE_DIR / "samples.csv").exists()
    assert (FIXTURE_DIR / "manifest.json").exists()


def test_minimal_sensor_adapter_validator_passes() -> None:
    _run([sys.executable, str(ADAPTER_SCRIPT)])

    result = _run([sys.executable, str(VALIDATOR), str(FIXTURE_DIR)])

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    assert payload["errors"] == []


def test_minimal_sensor_adapter_certifier_passes() -> None:
    _run([sys.executable, str(ADAPTER_SCRIPT)])

    result = _run([sys.executable, str(CERTIFIER), str(FIXTURE_DIR)])

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "certified"
    assert payload["valid"] is True
    assert payload["certified"] is True


def test_minimal_sensor_adapter_outputs_are_deterministic() -> None:
    _run([sys.executable, str(ADAPTER_SCRIPT)])
    first_validation = _run([sys.executable, str(VALIDATOR), str(FIXTURE_DIR)])
    first_certification = _run([sys.executable, str(CERTIFIER), str(FIXTURE_DIR)])

    _run([sys.executable, str(ADAPTER_SCRIPT)])
    second_validation = _run([sys.executable, str(VALIDATOR), str(FIXTURE_DIR)])
    second_certification = _run([sys.executable, str(CERTIFIER), str(FIXTURE_DIR)])

    assert first_validation.stdout == second_validation.stdout
    assert first_certification.stdout == second_certification.stdout
