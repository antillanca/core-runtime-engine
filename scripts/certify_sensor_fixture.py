#!/usr/bin/env python3
"""Certify an offline CORE Sensor Evidence fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core_runtime.core.explainability import StaticExplainer  # noqa: E402
from core_runtime.core.sensor_evidence import (  # noqa: E402
    SensorSource,
    derive_threshold_observation_event,
    load_sensor_fixture_manifest,
    load_sensor_trace_csv,
    observation_event_to_explainability_artifacts,
)
from scripts.validate_sensor_manifest import validate_fixture  # noqa: E402


CERTIFICATION_SCHEMA = "core.sensor_fixture_certification.v1"
DEFAULT_FIXTURE = "tests/fixtures/sensor_evidence/simulated_scalar_v1"
DEFAULT_EVENT_ID = "event:sensor:simulated:threshold:v1"
DEFAULT_EVENT_TYPE = "sensor.simulated.threshold_crossing"
DEFAULT_THRESHOLD = 0.75


def _canonical_dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return path.as_posix().lstrip("/")


def _check(status: str, **metadata: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": status}
    for key, value in sorted(metadata.items()):
        if value is not None:
            payload[key] = value
    return payload


def _manifest_value(manifest: Any, name: str, default: Any = None) -> Any:
    if isinstance(manifest, dict):
        return manifest.get(name, default)
    return getattr(manifest, name, default)


def _load_threshold_config(manifest_payload: dict[str, Any]) -> tuple[str, float, str, str]:
    value_key = _manifest_value(manifest_payload, "value_key", None)
    if value_key is None:
        value_keys = _manifest_value(manifest_payload, "value_keys", ())
        if value_keys:
            value_key = value_keys[0]
    if value_key is None:
        value_key = "signal"

    threshold = float(_manifest_value(manifest_payload, "threshold", DEFAULT_THRESHOLD))
    event_type = str(
        _manifest_value(
            manifest_payload,
            "expected_event_type",
            DEFAULT_EVENT_TYPE,
        )
    )
    event_id = str(_manifest_value(manifest_payload, "observation_event_id", DEFAULT_EVENT_ID))
    return str(value_key), threshold, event_type, event_id


def _non_goals() -> list[str]:
    return [
        "no_live_sensors",
        "no_ruview_integration",
        "no_gpu_dependency",
        "no_runtime_mutation",
    ]


def _build_validation_failure_report(
    *,
    fixture_dir: Path,
    validation_payload: dict[str, Any],
    certifier_script: Path,
    validator_script: Path,
) -> dict[str, Any]:
    fixture_dir_rel = _relative_path(fixture_dir)
    return {
        "certification_schema": CERTIFICATION_SCHEMA,
        "fixture_id": validation_payload.get("fixture_id"),
        "fixture_dir": fixture_dir_rel,
        "status": "failed",
        "valid": False,
        "certified": False,
        "checks": {
            "manifest_valid": _check(
                "failed",
                errors=validation_payload.get("errors", []),
                warnings=validation_payload.get("warnings", []),
            ),
            "csv_consistency": _check("skipped", reason="validation_failed"),
            "trace_fingerprint_match": _check("skipped", reason="validation_failed"),
            "observation_event_deterministic": _check("skipped", reason="validation_failed"),
            "observation_event_fingerprint_match": _check("skipped", reason="validation_failed"),
            "explainability_bridge": _check("skipped", reason="validation_failed"),
        },
        "trace": None,
        "observation_events": {},
        "tooling": {
            "validator_script": _relative_path(validator_script),
            "validator_version": _sha256_file(validator_script),
            "certifier_script": _relative_path(certifier_script),
            "certifier_version": _sha256_file(certifier_script),
        },
        "regeneration_command": (
            f"python scripts/certify_sensor_fixture.py {fixture_dir_rel}"
        ),
        "non_goals": _non_goals(),
    }


def certify_fixture(fixture_dir: Path) -> tuple[int, dict[str, Any]]:
    fixture_dir = Path(fixture_dir)
    certifier_script = Path(__file__).resolve()
    validator_script = PROJECT_ROOT / "scripts" / "validate_sensor_manifest.py"
    fixture_dir_rel = _relative_path(fixture_dir)

    validation_payload = validate_fixture(fixture_dir)
    if validation_payload.get("status") != "passed":
        return 1, _build_validation_failure_report(
            fixture_dir=fixture_dir,
            validation_payload=validation_payload,
            certifier_script=certifier_script,
            validator_script=validator_script,
        )

    manifest_path = fixture_dir / "manifest.json"
    samples_path = fixture_dir / "samples.csv"
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = load_sensor_fixture_manifest(manifest_path)

    source = SensorSource(
        sensor_id=manifest.sensor_id,
        sensor_type=str(manifest_payload.get("sensor_type", "simulated_scalar")),
        capture_mode=str(manifest_payload.get("capture_mode", "offline_fixture")),
        hardware_version=manifest_payload.get("hardware_version"),
        firmware_version=manifest_payload.get("firmware_version"),
        model_version=manifest_payload.get("model_version"),
        calibration_id=manifest_payload.get("calibration_id", "calibration:simulated:scalar:v1"),
        environment_id=manifest_payload.get("environment_id", "environment:test"),
        metadata=manifest_payload.get("metadata", {})
        if isinstance(manifest_payload.get("metadata", {}), dict)
        else {},
    )

    trace = load_sensor_trace_csv(
        samples_path,
        trace_id=manifest.trace_id,
        source=source,
    )

    value_key, threshold, event_type, event_id = _load_threshold_config(manifest_payload)
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

    deterministic_event = first_event.to_dict() == second_event.to_dict()
    trace_fingerprint = trace.fingerprint()
    event_fingerprint = first_event.fingerprint()
    expected_trace_fingerprint = manifest.trace_fingerprint
    expected_event_fingerprint = manifest.observation_event_fingerprints.get(event_id)

    artifacts = observation_event_to_explainability_artifacts(first_event)
    explainer = StaticExplainer(
        execution_graph=artifacts["execution_graph"],
        event_log=artifacts["event_log"],
        knowledge_base=artifacts["knowledge_base"],
    )
    explanation = explainer.trace_of_event(event_id)
    explanation_payload = explanation.to_dict()
    explanation_status = explanation_payload.get("status")

    checks = {
        "manifest_valid": _check("passed"),
        "csv_consistency": _check(
            "passed",
            sample_count=len(trace.samples),
            value_key=value_key,
        ),
        "trace_fingerprint_match": _check(
            "passed" if expected_trace_fingerprint == trace_fingerprint else "failed",
            expected=expected_trace_fingerprint,
            actual=trace_fingerprint,
        ),
        "observation_event_deterministic": _check(
            "passed" if deterministic_event else "failed",
        ),
        "observation_event_fingerprint_match": _check(
            "passed" if expected_event_fingerprint == event_fingerprint else "failed",
            event_id=event_id,
            expected=expected_event_fingerprint,
            actual=event_fingerprint,
        ),
        "explainability_bridge": _check(
            "passed" if explanation_status in {"complete", "partial"} else "failed",
            event_id=event_id,
            explanation_status=explanation_status,
            query="trace_of_event",
        ),
    }

    certified = all(check["status"] == "passed" for check in checks.values())

    payload = {
        "certification_schema": CERTIFICATION_SCHEMA,
        "fixture_id": manifest.fixture_id,
        "fixture_dir": fixture_dir_rel,
        "status": "certified" if certified else "failed",
        "valid": True,
        "certified": certified,
        "checks": checks,
        "trace": {
            "trace_id": trace.trace_id,
            "sensor_id": trace.source.sensor_id,
            "sample_count": len(trace.samples),
            "fingerprint": trace_fingerprint,
        },
        "observation_events": {
            event_id: {
                "event_type": first_event.event_type,
                "fingerprint": event_fingerprint,
            }
        },
        "tooling": {
            "validator_script": _relative_path(validator_script),
            "validator_version": _sha256_file(validator_script),
            "certifier_script": _relative_path(certifier_script),
            "certifier_version": _sha256_file(certifier_script),
        },
        "regeneration_command": (
            f"python scripts/certify_sensor_fixture.py {fixture_dir_rel}"
        ),
        "non_goals": _non_goals(),
    }

    return (0 if certified else 1), payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Certify an offline CORE Sensor Evidence fixture.",
    )
    parser.add_argument(
        "fixture_dir",
        nargs="?",
        default=DEFAULT_FIXTURE,
        help="Path to a sensor evidence fixture directory.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output path for the deterministic certification report.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    exit_code, payload = certify_fixture(Path(args.fixture_dir))
    rendered = _canonical_dump(payload)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(rendered + "\n", encoding="utf-8")

    print(rendered)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
