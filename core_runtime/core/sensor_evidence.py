"""Sensor evidence primitives for CORE v4.4 bootstrap.

This module defines deterministic, serializable records for future sensor
evidence integration. It does not implement live sensors and does not mutate
runtime state.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


SENSOR_EVIDENCE_SCHEMA_VERSION = "core.sensor_evidence.v1"
SENSOR_TRACE_ENCODING = "core.sensor_trace.v1"
OBSERVATION_EVENT_ENCODING = "core.observation_event.v1"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _require_finite_float(value: Any, field_name: str) -> float:
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{field_name} must be finite")
    return number


def _sorted_strings(values: Mapping[str, Any] | list[Any] | tuple[Any, ...]) -> tuple[str, ...]:
    collected: list[str] = []
    if isinstance(values, Mapping):
        iterable: list[Any] = list(values.values())
    else:
        iterable = list(values)
    for item in iterable:
        if isinstance(item, str) and item.strip():
            collected.append(item.strip())
    return tuple(sorted(dict.fromkeys(collected)))


@dataclass(frozen=True)
class SensorSource:
    sensor_id: str
    sensor_type: str
    capture_mode: str
    hardware_version: str | None = None
    firmware_version: str | None = None
    model_version: str | None = None
    calibration_id: str | None = None
    environment_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "sensor_id", _require_non_empty_string(self.sensor_id, "sensor_id"))
        object.__setattr__(self, "sensor_type", _require_non_empty_string(self.sensor_type, "sensor_type"))
        object.__setattr__(self, "capture_mode", _require_non_empty_string(self.capture_mode, "capture_mode"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SENSOR_EVIDENCE_SCHEMA_VERSION,
            "sensor_id": self.sensor_id,
            "sensor_type": self.sensor_type,
            "capture_mode": self.capture_mode,
            "hardware_version": self.hardware_version,
            "firmware_version": self.firmware_version,
            "model_version": self.model_version,
            "calibration_id": self.calibration_id,
            "environment_id": self.environment_id,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class SensorSample:
    index: int
    logical_time: str
    values: Mapping[str, float]

    def __post_init__(self) -> None:
        if int(self.index) < 0:
            raise ValueError("index must be non-negative")
        object.__setattr__(self, "logical_time", _require_non_empty_string(self.logical_time, "logical_time"))
        for key, value in self.values.items():
            _require_non_empty_string(str(key), "value key")
            _require_finite_float(value, f"values[{key}]")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SENSOR_EVIDENCE_SCHEMA_VERSION,
            "index": int(self.index),
            "logical_time": self.logical_time,
            "values": {key: float(self.values[key]) for key in sorted(self.values)},
        }


@dataclass(frozen=True)
class SensorTrace:
    trace_id: str
    source: SensorSource
    samples: tuple[SensorSample, ...]
    encoding: str = SENSOR_TRACE_ENCODING
    normalization_version: str = "sensor-evidence-bootstrap-v1"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "trace_id", _require_non_empty_string(self.trace_id, "trace_id"))
        object.__setattr__(self, "encoding", _require_non_empty_string(self.encoding, "encoding"))
        object.__setattr__(
            self,
            "normalization_version",
            _require_non_empty_string(self.normalization_version, "normalization_version"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SENSOR_EVIDENCE_SCHEMA_VERSION,
            "trace_id": self.trace_id,
            "source": self.source.to_dict(),
            "samples": [sample.to_dict() for sample in self.samples],
            "sample_count": len(self.samples),
            "encoding": self.encoding,
            "normalization_version": self.normalization_version,
            "metadata": dict(self.metadata),
        }

    def fingerprint(self) -> str:
        return _sha256_text(_canonical_json(self.to_dict()))


@dataclass(frozen=True)
class ObservationEvent:
    event_id: str
    trace_id: str
    sensor_id: str
    event_type: str
    logical_time: str
    evidence_window: tuple[int, int]
    input_fingerprint: str
    output_fingerprint: str
    confidence: float | None = None
    uncertainty: float | None = None
    processor_version: str = "sensor-evidence-bootstrap-v1"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _require_non_empty_string(self.event_id, "event_id"))
        object.__setattr__(self, "trace_id", _require_non_empty_string(self.trace_id, "trace_id"))
        object.__setattr__(self, "sensor_id", _require_non_empty_string(self.sensor_id, "sensor_id"))
        object.__setattr__(self, "event_type", _require_non_empty_string(self.event_type, "event_type"))
        object.__setattr__(self, "logical_time", _require_non_empty_string(self.logical_time, "logical_time"))
        object.__setattr__(
            self,
            "processor_version",
            _require_non_empty_string(self.processor_version, "processor_version"),
        )
        object.__setattr__(self, "input_fingerprint", _require_non_empty_string(self.input_fingerprint, "input_fingerprint"))
        object.__setattr__(self, "output_fingerprint", _require_non_empty_string(self.output_fingerprint, "output_fingerprint"))
        if len(self.evidence_window) != 2:
            raise ValueError("evidence_window must contain exactly two integers")
        start, end = self.evidence_window
        if int(start) < 0 or int(end) < 0:
            raise ValueError("evidence_window values must be non-negative")
        if int(start) > int(end):
            raise ValueError("evidence_window start must be <= end")
        if self.confidence is not None:
            object.__setattr__(self, "confidence", _require_finite_float(self.confidence, "confidence"))
        if self.uncertainty is not None:
            object.__setattr__(self, "uncertainty", _require_finite_float(self.uncertainty, "uncertainty"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SENSOR_EVIDENCE_SCHEMA_VERSION,
            "encoding": OBSERVATION_EVENT_ENCODING,
            "event_id": self.event_id,
            "trace_id": self.trace_id,
            "sensor_id": self.sensor_id,
            "event_type": self.event_type,
            "logical_time": self.logical_time,
            "evidence_window": [int(self.evidence_window[0]), int(self.evidence_window[1])],
            "input_fingerprint": self.input_fingerprint,
            "output_fingerprint": self.output_fingerprint,
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "processor_version": self.processor_version,
            "metadata": dict(self.metadata),
        }

    def fingerprint(self) -> str:
        return _sha256_text(_canonical_json(self.to_dict()))


@dataclass(frozen=True)
class SensorFixtureManifest:
    fixture_id: str
    schema_version: str
    trace_id: str
    sensor_id: str
    sample_count: int
    value_keys: tuple[str, ...]
    trace_fingerprint: str | None = None
    observation_event_fingerprints: Mapping[str, str] = field(default_factory=dict)
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "fixture_id", _require_non_empty_string(self.fixture_id, "fixture_id"))
        object.__setattr__(self, "schema_version", _require_non_empty_string(self.schema_version, "schema_version"))
        object.__setattr__(self, "trace_id", _require_non_empty_string(self.trace_id, "trace_id"))
        object.__setattr__(self, "sensor_id", _require_non_empty_string(self.sensor_id, "sensor_id"))
        if int(self.sample_count) < 0:
            raise ValueError("sample_count must be non-negative")
        object.__setattr__(self, "value_keys", tuple(_require_non_empty_string(key, "value_key") for key in self.value_keys))
        if self.trace_fingerprint is not None:
            object.__setattr__(self, "trace_fingerprint", _require_non_empty_string(self.trace_fingerprint, "trace_fingerprint"))
        normalized_events = {
            _require_non_empty_string(key, "observation_event_fingerprint key"): _require_non_empty_string(
                value,
                "observation_event_fingerprint value",
            )
            for key, value in dict(self.observation_event_fingerprints).items()
        }
        object.__setattr__(self, "observation_event_fingerprints", normalized_events)
        object.__setattr__(self, "notes", tuple(_require_non_empty_string(note, "note") for note in self.notes))

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "schema_version": self.schema_version,
            "trace_id": self.trace_id,
            "sensor_id": self.sensor_id,
            "sample_count": int(self.sample_count),
            "value_keys": list(self.value_keys),
            "trace_fingerprint": self.trace_fingerprint,
            "observation_event_fingerprints": dict(self.observation_event_fingerprints),
            "notes": list(self.notes),
        }


def load_sensor_fixture_manifest(path: str | Path) -> SensorFixtureManifest:
    manifest_path = Path(path)
    with manifest_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return SensorFixtureManifest(
        fixture_id=data["fixture_id"],
        schema_version=data.get("schema_version", SENSOR_EVIDENCE_SCHEMA_VERSION),
        trace_id=data["trace_id"],
        sensor_id=data["sensor_id"],
        sample_count=int(data["sample_count"]),
        value_keys=tuple(data.get("value_keys", ())),
        trace_fingerprint=data.get("trace_fingerprint"),
        observation_event_fingerprints=dict(data.get("observation_event_fingerprints", {})),
        notes=tuple(data.get("notes", ())),
    )


def validate_sensor_trace_against_manifest(
    trace: SensorTrace,
    manifest: SensorFixtureManifest,
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []

    if trace.trace_id != manifest.trace_id:
        warnings.append(
            {
                "code": "trace_id_mismatch",
                "message": "SensorTrace trace_id does not match manifest.",
                "expected": manifest.trace_id,
                "actual": trace.trace_id,
            }
        )

    if trace.source.sensor_id != manifest.sensor_id:
        warnings.append(
            {
                "code": "sensor_id_mismatch",
                "message": "SensorTrace sensor_id does not match manifest.",
                "expected": manifest.sensor_id,
                "actual": trace.source.sensor_id,
            }
        )

    if len(trace.samples) != manifest.sample_count:
        warnings.append(
            {
                "code": "sample_count_mismatch",
                "message": "SensorTrace sample count does not match manifest.",
                "expected": manifest.sample_count,
                "actual": len(trace.samples),
            }
        )

    actual_value_keys = tuple(
        sorted(
            {
                key
                for sample in trace.samples
                for key in sample.values
                if isinstance(key, str) and key.strip()
            }
        )
    )
    if tuple(manifest.value_keys) != actual_value_keys:
        warnings.append(
            {
                "code": "value_key_mismatch",
                "message": "SensorTrace value keys do not match manifest.",
                "expected": list(manifest.value_keys),
                "actual": list(actual_value_keys),
            }
        )

    if manifest.trace_fingerprint is not None:
        actual_trace_fingerprint = trace.fingerprint()
        if actual_trace_fingerprint != manifest.trace_fingerprint:
            warnings.append(
                {
                    "code": "trace_fingerprint_mismatch",
                    "message": "SensorTrace fingerprint does not match manifest.",
                    "expected": manifest.trace_fingerprint,
                    "actual": actual_trace_fingerprint,
                }
            )

    return warnings


def observation_event_to_explainability_artifacts(
    event: ObservationEvent,
    *,
    fact_id: str | None = None,
    node_id: str | None = None,
) -> dict[str, dict[str, Any]]:
    resolved_fact_id = fact_id or f"fact:{event.event_id}"
    resolved_node_id = node_id or f"node:{event.event_id}"

    event_log = {
        "events": {
            event.event_id: {
                "schema_version": SENSOR_EVIDENCE_SCHEMA_VERSION,
                "encoding": OBSERVATION_EVENT_ENCODING,
                "event_id": event.event_id,
                "event_type": event.event_type,
                "trace_id": event.trace_id,
                "sensor_id": event.sensor_id,
                "input_fingerprint": event.input_fingerprint,
                "output_fingerprint": event.output_fingerprint,
            }
        }
    }

    knowledge_base = {
        "facts": {
            resolved_fact_id: {
                "schema_version": SENSOR_EVIDENCE_SCHEMA_VERSION,
                "fact_id": resolved_fact_id,
                "metadata": {
                    "source_event_ids": [event.event_id],
                    "trace_id": event.trace_id,
                    "sensor_id": event.sensor_id,
                    "event_type": event.event_type,
                },
            }
        }
    }

    execution_graph = {
        "nodes": {
            resolved_node_id: {
                "schema_version": SENSOR_EVIDENCE_SCHEMA_VERSION,
                "node_id": resolved_node_id,
                "node_type": "ObservationEmitted",
                "event_ids": [event.event_id],
                "fact_ids": [resolved_fact_id],
                "trace_id": event.trace_id,
                "sensor_id": event.sensor_id,
            }
        },
        "edges": [],
        "metadata": {
            "sensor_event_id": event.event_id,
            "sensor_trace_id": event.trace_id,
            "sensor_id": event.sensor_id,
        },
    }

    return {
        "event_log": event_log,
        "knowledge_base": knowledge_base,
        "execution_graph": execution_graph,
    }


def load_sensor_trace_csv(
    path: str | Path,
    *,
    trace_id: str,
    source: SensorSource,
) -> SensorTrace:
    """Load a deterministic SensorTrace from CSV.

    Expected CSV columns:
    - index
    - logical_time
    - one or more numeric value columns

    This loader is for offline fixtures only.
    """

    csv_path = Path(path)
    samples: list[SensorSample] = []

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV fixture must include a header")

        required = {"index", "logical_time"}
        missing = required.difference(reader.fieldnames)
        if missing:
            raise ValueError(f"CSV fixture missing required columns: {sorted(missing)}")

        value_columns = [name for name in reader.fieldnames if name not in required]
        if not value_columns:
            raise ValueError("CSV fixture must include at least one value column")

        for row in reader:
            values = {column: _require_finite_float(row[column], f"values[{column}]") for column in value_columns}
            samples.append(
                SensorSample(
                    index=int(row["index"]),
                    logical_time=row["logical_time"],
                    values=values,
                )
            )

    samples = sorted(samples, key=lambda sample: sample.index)

    return SensorTrace(
        trace_id=trace_id,
        source=source,
        samples=tuple(samples),
        metadata={
            "source_path": str(csv_path),
            "sample_count": len(samples),
            "value_keys": list(sorted(samples[0].values)) if samples else [],
        },
    )


def derive_threshold_observation_event(
    trace: SensorTrace,
    *,
    event_id: str,
    event_type: str,
    value_key: str,
    threshold: float,
    processor_version: str = "sensor-evidence-bootstrap-v1",
) -> ObservationEvent:
    """Derive a deterministic ObservationEvent from a simple threshold rule.

    This is intentionally simple and fixture-oriented. It is not a general
    inference engine and does not imply causal reasoning.
    """

    normalized_value_key = _require_non_empty_string(value_key, "value_key")
    threshold_value = _require_finite_float(threshold, "threshold")

    matching = [
        sample
        for sample in trace.samples
        if normalized_value_key in sample.values and sample.values[normalized_value_key] >= threshold_value
    ]

    if not matching:
        evidence_window = (0, 0)
        logical_time = trace.samples[0].logical_time if trace.samples else "t0"
        confidence = 0.0
    else:
        evidence_window = (matching[0].index, matching[-1].index)
        logical_time = matching[0].logical_time
        confidence = min(1.0, len(matching) / max(1, len(trace.samples)))

    input_fingerprint = trace.fingerprint()
    event_payload = {
        "event_id": event_id,
        "trace_id": trace.trace_id,
        "sensor_id": trace.source.sensor_id,
        "event_type": event_type,
        "logical_time": logical_time,
        "evidence_window": list(evidence_window),
        "value_key": normalized_value_key,
        "threshold": threshold_value,
        "processor_version": processor_version,
    }
    output_fingerprint = _sha256_text(_canonical_json(event_payload))

    return ObservationEvent(
        event_id=event_id,
        trace_id=trace.trace_id,
        sensor_id=trace.source.sensor_id,
        event_type=event_type,
        logical_time=logical_time,
        evidence_window=evidence_window,
        input_fingerprint=input_fingerprint,
        output_fingerprint=output_fingerprint,
        confidence=confidence,
        uncertainty=None if confidence == 1.0 else 1.0 - confidence,
        processor_version=processor_version,
        metadata={
            "value_key": normalized_value_key,
            "threshold": threshold_value,
            "matching_sample_count": len(matching),
        },
    )


__all__ = [
    "SENSOR_EVIDENCE_SCHEMA_VERSION",
    "SENSOR_TRACE_ENCODING",
    "OBSERVATION_EVENT_ENCODING",
    "SensorSource",
    "SensorSample",
    "SensorTrace",
    "SensorFixtureManifest",
    "ObservationEvent",
    "load_sensor_fixture_manifest",
    "validate_sensor_trace_against_manifest",
    "observation_event_to_explainability_artifacts",
    "load_sensor_trace_csv",
    "derive_threshold_observation_event",
]
