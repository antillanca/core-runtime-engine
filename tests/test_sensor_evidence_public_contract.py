from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from core_runtime.core.sensor_evidence import (
    OBSERVATION_EVENT_ENCODING,
    SENSOR_EVIDENCE_SCHEMA_VERSION,
    SENSOR_TRACE_ENCODING,
    ObservationEvent,
    SensorFixtureManifest,
    SensorSample,
    SensorSource,
    SensorTrace,
)


FIXTURE = Path("tests/fixtures/sensor_evidence/simulated_scalar_v1")
VALIDATOR = Path("scripts/validate_sensor_manifest.py")
CERTIFIER = Path("scripts/certify_sensor_fixture.py")

EXPECTED_ERROR_CODES = {
    "fixture_dir_missing",
    "manifest_missing",
    "samples_missing",
    "manifest_load_failed",
    "trace_load_failed",
    "trace_id_mismatch",
    "sensor_id_mismatch",
    "sample_count_mismatch",
    "trace_fingerprint_mismatch",
    "observation_event_fingerprint_mismatch",
    "observation_event_not_deterministic",
    "value_key_missing",
    "threshold_invalid",
}

EXPECTED_CERTIFICATION_CHECKS = {
    "manifest_valid",
    "csv_consistency",
    "trace_fingerprint_match",
    "observation_event_deterministic",
    "observation_event_fingerprint_match",
    "explainability_bridge",
}


def test_public_records_are_importable() -> None:
    assert SensorSource is not None
    assert SensorSample is not None
    assert SensorTrace is not None
    assert ObservationEvent is not None
    assert SensorFixtureManifest is not None


def test_public_schema_constants_are_stable() -> None:
    assert SENSOR_EVIDENCE_SCHEMA_VERSION == "core.sensor_evidence.v1"
    assert SENSOR_TRACE_ENCODING == "core.sensor_trace.v1"
    assert OBSERVATION_EVENT_ENCODING == "core.observation_event.v1"


def test_validator_success_shape_is_stable() -> None:
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(FIXTURE)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)

    assert payload["status"] == "passed"
    assert isinstance(payload["errors"], list)
    assert isinstance(payload["warnings"], list)


def test_certifier_check_names_are_stable() -> None:
    result = subprocess.run(
        [sys.executable, str(CERTIFIER), str(FIXTURE)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)

    assert payload["certification_schema"] == "core.sensor_fixture_certification.v1"
    assert set(payload["checks"]) == EXPECTED_CERTIFICATION_CHECKS


def test_documented_error_codes_match_negative_tests_expectation() -> None:
    assert EXPECTED_ERROR_CODES == {
        "fixture_dir_missing",
        "manifest_missing",
        "samples_missing",
        "manifest_load_failed",
        "trace_load_failed",
        "trace_id_mismatch",
        "sensor_id_mismatch",
        "sample_count_mismatch",
        "trace_fingerprint_mismatch",
        "observation_event_fingerprint_mismatch",
        "observation_event_not_deterministic",
        "value_key_missing",
        "threshold_invalid",
    }
