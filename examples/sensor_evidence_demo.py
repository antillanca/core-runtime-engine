from __future__ import annotations

import json
import sys
from pathlib import Path

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
    validate_sensor_trace_against_manifest,
)


FIXTURE_DIR = Path("tests/fixtures/sensor_evidence/simulated_scalar_v1")


def build_report() -> dict[str, object]:
    manifest = load_sensor_fixture_manifest(FIXTURE_DIR / "manifest.json")
    source = SensorSource(
        sensor_id=manifest.sensor_id,
        sensor_type="simulated_scalar",
        capture_mode="offline_fixture",
        calibration_id="calibration:simulated:scalar:v1",
        environment_id="environment:test",
    )
    trace = load_sensor_trace_csv(
        FIXTURE_DIR / "samples.csv",
        trace_id=manifest.trace_id,
        source=source,
    )
    warnings = validate_sensor_trace_against_manifest(trace, manifest)
    event = derive_threshold_observation_event(
        trace,
        event_id="event:sensor:simulated:threshold:v1",
        event_type="sensor.simulated.threshold_crossing",
        value_key="signal",
        threshold=0.75,
    )
    artifacts = observation_event_to_explainability_artifacts(event)
    explainer = StaticExplainer(
        execution_graph=artifacts["execution_graph"],
        event_log=artifacts["event_log"],
        knowledge_base=artifacts["knowledge_base"],
    )

    explanation = explainer.trace_of_event(event.event_id)
    return {
        "manifest": manifest.to_dict(),
        "manifest_warnings": warnings,
        "trace": trace.to_dict(),
        "trace_fingerprint": trace.fingerprint(),
        "observation_event": event.to_dict(),
        "observation_event_fingerprint": event.fingerprint(),
        "explanation": explanation.to_dict(),
    }


def main() -> int:
    print(json.dumps(build_report(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
