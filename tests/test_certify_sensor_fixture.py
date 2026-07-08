from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


VALID_FIXTURE = Path("tests/fixtures/sensor_evidence/simulated_scalar_v1")
SCRIPT = Path("scripts/certify_sensor_fixture.py")


def _run_certifier(fixture_dir: Path = VALID_FIXTURE) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(fixture_dir)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_certify_sensor_fixture_passes() -> None:
    result = _run_certifier()

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)

    assert payload["certification_schema"] == "core.sensor_fixture_certification.v1"
    assert payload["fixture_id"] == "simulated_scalar_v1"
    assert payload["status"] == "certified"
    assert payload["valid"] is True
    assert payload["certified"] is True
    assert payload["fixture_dir"] == "tests/fixtures/sensor_evidence/simulated_scalar_v1"

    assert payload["checks"]["manifest_valid"]["status"] == "passed"
    assert payload["checks"]["csv_consistency"]["status"] == "passed"
    assert payload["checks"]["trace_fingerprint_match"]["status"] == "passed"
    assert payload["checks"]["observation_event_deterministic"]["status"] == "passed"
    assert payload["checks"]["observation_event_fingerprint_match"]["status"] == "passed"
    assert payload["checks"]["explainability_bridge"]["status"] == "passed"

    assert len(payload["trace"]["fingerprint"]) == 64

    event_id = "event:sensor:simulated:threshold:v1"
    assert event_id in payload["observation_events"]
    assert len(payload["observation_events"][event_id]["fingerprint"]) == 64


def test_certify_sensor_fixture_output_is_byte_stable() -> None:
    first = _run_certifier()
    second = _run_certifier()

    assert first.returncode == 0
    assert second.returncode == 0
    assert first.stdout == second.stdout


def test_certify_sensor_fixture_output_json_is_deterministic() -> None:
    first = _run_certifier()
    second = _run_certifier()

    assert json.loads(first.stdout) == json.loads(second.stdout)


def test_certify_sensor_fixture_has_regeneration_command() -> None:
    result = _run_certifier()
    payload = json.loads(result.stdout)

    assert payload["regeneration_command"] == (
        "python scripts/certify_sensor_fixture.py "
        "tests/fixtures/sensor_evidence/simulated_scalar_v1"
    )


def test_certify_sensor_fixture_has_tool_versions() -> None:
    result = _run_certifier()
    payload = json.loads(result.stdout)

    tooling = payload["tooling"]

    assert tooling["validator_script"] == "scripts/validate_sensor_manifest.py"
    assert len(tooling["validator_version"]) == 64
    assert tooling["certifier_script"] == "scripts/certify_sensor_fixture.py"
    assert len(tooling["certifier_version"]) == 64


def test_certify_sensor_fixture_fails_invalid_fixture(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture"
    shutil.copytree(VALID_FIXTURE, fixture)

    manifest_path = fixture / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["trace_fingerprint"] = "0" * 64
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = _run_certifier(fixture)
    payload = json.loads(result.stdout)

    assert result.returncode == 1
    assert payload["status"] == "failed"
    assert payload["valid"] is False
    assert payload["certified"] is False
    assert payload["checks"]["manifest_valid"]["status"] == "failed"


def test_certify_sensor_fixture_output_file_matches_stdout(tmp_path: Path) -> None:
    output = tmp_path / "certification_report.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(VALID_FIXTURE),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert output.read_text(encoding="utf-8") == result.stdout
