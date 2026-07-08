#!/usr/bin/env python3
"""Validate an offline CORE Sensor Evidence fixture manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core_runtime.core.sensor_evidence import (  # noqa: E402
    OBSERVATION_EVENT_ENCODING,
    SENSOR_EVIDENCE_SCHEMA_VERSION,
    SensorSource,
    derive_threshold_observation_event,
    load_sensor_fixture_manifest,
    load_sensor_trace_csv,
    validate_sensor_trace_against_manifest,
)

DEFAULT_EVENT_ID = "event:sensor:simulated:threshold:v1"
DEFAULT_EVENT_TYPE = "sensor.simulated.threshold_crossing"
DEFAULT_THRESHOLD = 0.75
BLOCKING_WARNING_CODES = {
    "trace_id_mismatch",
    "sensor_id_mismatch",
    "sample_count_mismatch",
    "trace_fingerprint_mismatch",
}


def _canonical_dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _error(code: str, message: str, **metadata: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    for key, value in sorted(metadata.items()):
        if value is not None:
            payload[key] = value
    return payload


def _warning(code: str, message: str, **metadata: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    for key, value in sorted(metadata.items()):
        if value is not None:
            payload[key] = value
    return payload


def _result_payload(
    *,
    fixture_dir: Path,
    status: str,
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    **metadata: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "fixture_dir": str(fixture_dir),
        "status": status,
        "errors": errors,
        "warnings": warnings,
    }
    for key, value in sorted(metadata.items()):
        payload[key] = value
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate an offline CORE Sensor Evidence fixture manifest.",
    )
    parser.add_argument(
        "fixture_dir",
        help="Path to a sensor evidence fixture directory containing manifest.json and samples.csv.",
    )
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _resolve_sensor_source(manifest_payload: dict[str, Any], manifest: Any) -> SensorSource:
    metadata = manifest_payload.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    return SensorSource(
        sensor_id=manifest.sensor_id,
        sensor_type=str(manifest_payload.get("sensor_type", "simulated_scalar")),
        capture_mode=str(manifest_payload.get("capture_mode", "offline_fixture")),
        hardware_version=manifest_payload.get("hardware_version"),
        firmware_version=manifest_payload.get("firmware_version"),
        model_version=manifest_payload.get("model_version"),
        calibration_id=manifest_payload.get("calibration_id", "calibration:simulated:scalar:v1"),
        environment_id=manifest_payload.get("environment_id", "environment:test"),
        metadata=metadata,
    )


def _resolve_threshold_config(
    manifest_payload: dict[str, Any],
) -> tuple[str, float | None, str, str, list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []

    value_key = manifest_payload.get("value_key")
    if value_key is None:
        value_keys = manifest_payload.get("value_keys", [])
        if isinstance(value_keys, list) and value_keys:
            value_key = value_keys[0]

    if value_key is None:
        value_key = "signal"

    raw_threshold = manifest_payload.get("threshold", DEFAULT_THRESHOLD)
    threshold: float | None
    try:
        threshold = float(raw_threshold)
    except (TypeError, ValueError):
        threshold = None
        errors.append(
            _error(
                "threshold_invalid",
                "Threshold must be numeric.",
                actual=raw_threshold,
            )
        )

    event_type = str(manifest_payload.get("expected_event_type", DEFAULT_EVENT_TYPE))
    event_id = str(manifest_payload.get("observation_event_id", DEFAULT_EVENT_ID))
    return str(value_key), threshold, event_type, event_id, errors


def _trace_has_value_key(trace: Any, value_key: str) -> bool:
    for sample in getattr(trace, "samples", ()):
        values = getattr(sample, "values", {})
        if isinstance(values, dict) and value_key in values:
            return True
    return False


def validate_fixture(fixture_dir: Path) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    manifest_path = fixture_dir / "manifest.json"
    samples_path = fixture_dir / "samples.csv"

    if not fixture_dir.exists():
        return _result_payload(
            fixture_dir=fixture_dir,
            status="failed",
            errors=[_error("fixture_dir_missing", "Fixture directory does not exist.")],
            warnings=[],
            deterministic=False,
        )

    if not manifest_path.exists():
        errors.append(_error("manifest_missing", "Missing manifest.json."))

    if not samples_path.exists():
        errors.append(_error("samples_missing", "Missing samples.csv."))

    if errors:
        return _result_payload(
            fixture_dir=fixture_dir,
            status="failed",
            errors=errors,
            warnings=warnings,
            deterministic=False,
        )

    try:
        manifest_payload = _load_json(manifest_path)
        manifest = load_sensor_fixture_manifest(manifest_path)
    except Exception as exc:  # expected failure path for invalid manifests
        return _result_payload(
            fixture_dir=fixture_dir,
            status="failed",
            errors=[_error("manifest_load_failed", "Failed to load manifest.json.", actual=str(exc))],
            warnings=warnings,
            deterministic=False,
        )

    expected_trace_id = str(manifest_payload.get("expected_trace_id", manifest.trace_id))
    if manifest.trace_id != expected_trace_id:
        errors.append(
            _error(
                "trace_id_mismatch",
                "SensorTrace trace_id does not match the expected manifest contract.",
                expected=expected_trace_id,
                actual=manifest.trace_id,
            )
        )

    expected_sensor_id = str(manifest_payload.get("expected_sensor_id", manifest.sensor_id))
    if manifest.sensor_id != expected_sensor_id:
        errors.append(
            _error(
                "sensor_id_mismatch",
                "SensorTrace sensor_id does not match the expected manifest contract.",
                expected=expected_sensor_id,
                actual=manifest.sensor_id,
            )
        )

    source = _resolve_sensor_source(manifest_payload, manifest)
    try:
        trace = load_sensor_trace_csv(samples_path, trace_id=manifest.trace_id, source=source)
    except Exception as exc:  # expected failure path for invalid CSV fixtures
        return _result_payload(
            fixture_dir=fixture_dir,
            status="failed",
            errors=[_error("trace_load_failed", "Failed to load samples.csv.", actual=str(exc))],
            warnings=warnings,
            trace_id=manifest.trace_id,
            sensor_id=manifest.sensor_id,
            deterministic=False,
        )

    manifest_warnings = validate_sensor_trace_against_manifest(trace, manifest)
    warnings.extend(manifest_warnings)
    for warning in manifest_warnings:
        if warning.get("code") in BLOCKING_WARNING_CODES:
            errors.append(
                _error(
                    str(warning.get("code")),
                    str(warning.get("message", "Blocking sensor manifest validation warning.")),
                    expected=warning.get("expected"),
                    actual=warning.get("actual"),
                )
            )

    value_key, threshold, event_type, event_id, config_errors = _resolve_threshold_config(manifest_payload)
    errors.extend(config_errors)

    if manifest.value_keys and "value_key" not in manifest_payload:
        warnings.append(
            _warning(
                "value_key_defaulted",
                "Using the first declared value key because value_key was omitted from the manifest.",
                value_key=value_key,
            )
        )

    if not _trace_has_value_key(trace, value_key):
        errors.append(
            _error(
                "value_key_missing",
                "Configured value_key is not present in the sensor samples.",
                value_key=value_key,
            )
        )

    trace_fingerprint = trace.fingerprint()
    deterministic = False
    observation_event_fingerprint: str | None = None

    if threshold is not None and not any(error["code"] in {"threshold_invalid", "value_key_missing"} for error in errors):
        first_event = derive_threshold_observation_event(
            trace,
            event_id=event_id,
            event_type=event_type,
            value_key=value_key,
            threshold=threshold,
        )
        second_event = derive_threshold_observation_event(
            trace,
            event_id=event_id,
            event_type=event_type,
            value_key=value_key,
            threshold=threshold,
        )

        deterministic = first_event.to_dict() == second_event.to_dict()
        observation_event_fingerprint = first_event.fingerprint()

        if not deterministic:
            errors.append(
                _error(
                    "observation_event_not_deterministic",
                    "ObservationEvent derivation produced different results across runs.",
                )
            )

        expected_event_fingerprint = manifest.observation_event_fingerprints.get(event_id)
        if expected_event_fingerprint is None:
            warnings.append(
                _warning(
                    "observation_event_fingerprint_missing",
                    "ObservationEvent fingerprint is not declared in the manifest.",
                    event_id=event_id,
                )
            )
        elif expected_event_fingerprint != observation_event_fingerprint:
            errors.append(
                _error(
                    "observation_event_fingerprint_mismatch",
                    "ObservationEvent fingerprint does not match manifest.",
                    event_id=event_id,
                    expected=expected_event_fingerprint,
                    actual=observation_event_fingerprint,
                )
            )

    payload = _result_payload(
        fixture_dir=fixture_dir,
        status="failed" if errors else "passed",
        errors=errors,
        warnings=warnings,
        fixture_id=manifest.fixture_id,
        trace_id=manifest.trace_id,
        sensor_id=manifest.sensor_id,
        sample_count=len(trace.samples),
        value_keys=list(manifest.value_keys),
        value_key=value_key,
        threshold=threshold,
        event_id=event_id,
        event_type=event_type,
        trace_fingerprint=trace_fingerprint,
        observation_event_fingerprint=observation_event_fingerprint,
        deterministic=deterministic,
        encoding=OBSERVATION_EVENT_ENCODING,
        schema_version=SENSOR_EVIDENCE_SCHEMA_VERSION,
    )
    return payload


def main() -> int:
    args = parse_args()
    payload = validate_fixture(Path(args.fixture_dir))
    print(_canonical_dump(payload))
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
