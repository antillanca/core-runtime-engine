"""CORE v4.3 - Static Explainability Layer.

Read-only explanations over completed CORE executions.

This module never:
- schedules execution
- mutates runtime state
- mutates KnowledgeBase
- changes replay semantics
- changes fingerprints
- recomputes domain answers
- introduces probabilistic behavior

The explainer consumes existing artifacts only:
- ExecutionGraph
- EventLog
- KnowledgeBase
- ReplayMetadata when available

Missing evidence is treated as a normal outcome. Only invalid query input
or clearly corrupt inputs should raise exceptions.
"""

from __future__ import annotations

from collections.abc import Mapping as AbcMapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Mapping, Protocol, Sequence

from core_runtime.core.canonicalization import canonical_graph_nodes
from core_runtime.core.audit_event import report_correlation_id, router_correlation_id
from core_runtime.core.audit_trail_index import AuditTrailIndex


ExplanationStatus = Literal["complete", "partial", "missing", "unsupported"]


class AuditExplainabilityAPI(Protocol):
    def cause_of_event(self, event_id: str) -> list[str]: ...

    def lineage_of_fact(self, fact_id: str) -> list[str]: ...

    def trace_of_report(self, report_id: str) -> list[str]: ...


def _freeze_value(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze_value(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_value(v) for v in value)
    if isinstance(value, tuple):
        return tuple(_freeze_value(v) for v in value)
    if isinstance(value, set):
        return frozenset(_freeze_value(v) for v in value)
    return value


def _unfreeze_value(value: Any) -> Any:
    if isinstance(value, MappingProxyType):
        return {k: _unfreeze_value(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_unfreeze_value(v) for v in value]
    if isinstance(value, frozenset):
        return [_unfreeze_value(v) for v in value]
    return value


def _normalize_id(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"Expected string identifier, got {type(value).__name__}")
    normalized = value.strip()
    if not normalized:
        raise ValueError("Identifier must not be empty")
    return normalized


def _sorted_unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if isinstance(value, str) and value.strip()}))


def _dedupe_sorted_stable(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if isinstance(value, str) and value.strip()}))


def _has_any_artifact(*artifacts: Any | None) -> bool:
    return any(artifact is not None for artifact in artifacts)


def _call_optional_method(artifact: Any, method_names: Sequence[str], *args: Any) -> Any | None:
    for method_name in method_names:
        method = getattr(artifact, method_name, None)
        if not callable(method):
            continue
        try:
            return method(*args)
        except TypeError:
            continue
        except Exception:
            continue
    return None


def _artifact_field(artifact: Any, field_name: str, default: Any = "") -> Any:
    if isinstance(artifact, Mapping):
        return artifact.get(field_name, default)
    return getattr(artifact, field_name, default)


def _extract_explainability_payload(value: Any, target_id: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {
        "graph_node_ids": [],
        "event_ids": [],
        "fact_ids": [],
        "projection_ids": [],
        "constraint_ids": [],
    }

    if value is None:
        return result

    if isinstance(value, list) or isinstance(value, tuple) or isinstance(value, frozenset):
        for item in value:
            extracted = _extract_explainability_payload(item, target_id)
            for key, values in extracted.items():
                result[key].extend(values)
        return {key: list(_dedupe_sorted_stable(values)) for key, values in result.items()}

    data = _to_mapping(value)
    if not data and isinstance(value, str):
        data = {"id": value}

    def add(key: str, candidate: Any) -> None:
        if candidate is None:
            return
        if isinstance(candidate, str):
            result[key].append(candidate)
        elif isinstance(candidate, list) or isinstance(candidate, tuple):
            for item in candidate:
                if isinstance(item, str):
                    result[key].append(item)

    aliases = {
        "graph_node_ids": ("graph_node_ids", "node_ids", "nodes", "node_id", "id"),
        "event_ids": ("event_ids", "events", "event_id"),
        "fact_ids": ("fact_ids", "facts", "fact_id"),
        "projection_ids": ("projection_ids", "projections", "projection_id"),
        "constraint_ids": ("constraint_ids", "constraints", "constraint_id"),
    }

    for output_key, input_keys in aliases.items():
        for input_key in input_keys:
            if input_key in data:
                add(output_key, data[input_key])

    if target_id:
        lowered = target_id.lower()
        if "event" in lowered:
            result["event_ids"].append(target_id)
        elif "fact" in lowered:
            result["fact_ids"].append(target_id)
        elif "projection" in lowered:
            result["projection_ids"].append(target_id)
        elif "constraint" in lowered:
            result["constraint_ids"].append(target_id)
        else:
            result["graph_node_ids"].append(target_id)

    return {key: list(_dedupe_sorted_stable(values)) for key, values in result.items()}


def _native_graph_lookup(execution_graph: Any, target_id: str) -> dict[str, list[str]]:
    """
    Best-effort read-only lookup using native ExecutionGraph APIs if available.

    Returns keys:
    - graph_node_ids
    - event_ids
    - fact_ids
    - projection_ids
    - constraint_ids

    Never mutates the graph. Never raises for missing native APIs.
    """
    result: dict[str, list[str]] = {
        "graph_node_ids": [],
        "event_ids": [],
        "fact_ids": [],
        "projection_ids": [],
        "constraint_ids": [],
    }

    if execution_graph is None:
        return result

    native_payload = _call_optional_method(
        execution_graph,
        (
            "explain",
            "lookup",
            "lookup_node",
            "find_node",
            "find_related",
            "find_related_ids",
            "get_related_ids",
        ),
        target_id,
    )

    if native_payload is not None:
        extracted = _extract_explainability_payload(native_payload, target_id)
        for key, values in extracted.items():
            if key in result:
                result[key].extend(values)

    return {key: list(_dedupe_sorted_stable(values)) for key, values in result.items()}


def _native_event_lookup(event_log: Any, target_id: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {
        "graph_node_ids": [],
        "event_ids": [],
        "fact_ids": [],
        "projection_ids": [],
        "constraint_ids": [],
    }

    if event_log is None:
        return result

    native_payload = _call_optional_method(
        event_log,
        (
            "lookup_event",
            "find_event",
            "lookup",
            "find_related",
            "find_related_ids",
            "get_related_ids",
            "by_task",
            "by_type",
        ),
        target_id,
    )
    if native_payload is None:
        native_payload = _call_optional_method(event_log, ("all",))

    if native_payload is not None:
        extracted = _extract_explainability_payload(native_payload, target_id)
        for key, values in extracted.items():
            if key in result:
                result[key].extend(values)

    return {key: list(_dedupe_sorted_stable(values)) for key, values in result.items()}


def _native_knowledge_base_lookup(knowledge_base: Any, target_id: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {
        "graph_node_ids": [],
        "event_ids": [],
        "fact_ids": [],
        "projection_ids": [],
        "constraint_ids": [],
    }

    if knowledge_base is None:
        return result

    native_payload = _call_optional_method(
        knowledge_base,
        (
            "query_fact",
            "query_by_hash",
            "lookup_ids",
            "lookup_fact",
            "find_fact",
            "lookup",
        ),
        target_id,
    )
    if native_payload is None:
        native_payload = _call_optional_method(knowledge_base, ("all_facts",))

    if native_payload is not None:
        extracted = _extract_explainability_payload(native_payload, target_id)
        for key, values in extracted.items():
            if key in result:
                result[key].extend(values)

    return {key: list(_dedupe_sorted_stable(values)) for key, values in result.items()}


def _native_audit_lookup(audit_trail: Any, target_id: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {
        "graph_node_ids": [],
        "event_ids": [],
        "fact_ids": [],
        "projection_ids": [],
        "constraint_ids": [],
    }

    if audit_trail is None:
        return result

    if isinstance(audit_trail, AuditTrailIndex):
        entries = list(audit_trail.events)
    else:
        entries = []
        if hasattr(audit_trail, "events"):
            try:
                entries = list(getattr(audit_trail, "events"))
            except Exception:
                entries = []
        elif hasattr(audit_trail, "all") and callable(getattr(audit_trail, "all")):
            try:
                entries = list(audit_trail.all())
            except Exception:
                entries = []
        elif isinstance(audit_trail, Mapping):
            raw_events = audit_trail.get("events", [])
            try:
                entries = list(raw_events)
            except Exception:
                entries = []

    if not entries:
        return result

    correlation_match = target_id.startswith("report::")
    correlation_target = target_id if correlation_match else ""

    for entry in entries:
        entry_id = _artifact_field(entry, "event_id", "")
        entry_type = _artifact_field(entry, "event_type", "")
        entry_correlation = _artifact_field(entry, "correlation_id", "")
        entry_payload = _artifact_field(entry, "payload", {})
        if target_id in {entry_id, entry_type, entry_correlation} or _contains_target(entry_payload, target_id):
            if entry_id:
                result["event_ids"].append(str(entry_id))
            if entry_correlation:
                result["projection_ids"].append(str(entry_correlation))
        if correlation_match and entry_correlation == correlation_target:
            if entry_id:
                result["event_ids"].append(str(entry_id))
            if entry_correlation:
                result["projection_ids"].append(str(entry_correlation))
        for key_name in ("fact_id", "projection_id", "constraint_id"):
            value = _artifact_field(entry_payload, key_name, "")
            if isinstance(value, str) and value == target_id:
                if key_name == "fact_id":
                    result["fact_ids"].append(value)
                elif key_name == "projection_id":
                    result["projection_ids"].append(value)
                elif key_name == "constraint_id":
                    result["constraint_ids"].append(value)

    return {key: list(_dedupe_sorted_stable(values)) for key, values in result.items()}


def _string_values(value: Any) -> list[str]:
    """Extract string leaves from shallow/semi-structured values."""
    strings: list[str] = []

    if value is None:
        return strings

    if isinstance(value, str):
        if value.strip():
            strings.append(value)
        return strings

    if isinstance(value, Mapping):
        for key, item in value.items():
            strings.extend(_string_values(key))
            strings.extend(_string_values(item))
        return strings

    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        for item in value:
            strings.extend(_string_values(item))
        return strings

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            strings.extend(_string_values(to_dict()))
        except Exception:
            pass
        return strings

    if hasattr(value, "__dict__"):
        try:
            strings.extend(_string_values(vars(value)))
        except Exception:
            pass
        return strings

    for attr in ("id", "event_id", "fact_id", "projection_id", "node_id", "constraint_id"):
        if hasattr(value, attr):
            try:
                attr_value = getattr(value, attr)
            except Exception:
                continue
            strings.extend(_string_values(attr_value))

    return strings


def _contains_target(value: Any, target_id: str) -> bool:
    return target_id in _string_values(value)


def _contains_any_target(value: Any, target_ids: Sequence[str]) -> bool:
    target_set = {target_id for target_id in target_ids if isinstance(target_id, str) and target_id.strip()}
    if not target_set:
        return False
    values = set(_string_values(value))
    return bool(values.intersection(target_set))


def _summary(
    entity: str,
    target_id: str,
    status: ExplanationStatus,
    *,
    graph_node_ids: Sequence[str] = (),
    event_ids: Sequence[str] = (),
    fact_ids: Sequence[str] = (),
    projection_ids: Sequence[str] = (),
    constraint_ids: Sequence[str] = (),
) -> str:
    if status == "missing":
        return f"No static explainability evidence found for {entity} '{target_id}'."
    if status == "unsupported":
        return f"Static explainability is unsupported for {entity} '{target_id}' with the provided artifacts."

    parts = [f"Static explanation for {entity} '{target_id}' is {status}."]
    if graph_node_ids:
        parts.append(f"graph_nodes={len(graph_node_ids)}")
    if event_ids:
        parts.append(f"events={len(event_ids)}")
    if fact_ids:
        parts.append(f"facts={len(fact_ids)}")
    if projection_ids:
        parts.append(f"projections={len(projection_ids)}")
    if constraint_ids:
        parts.append(f"constraints={len(constraint_ids)}")
    return " ".join(parts)


def _router_summary(
    entity: str,
    target_id: str,
    status: ExplanationStatus,
    *,
    profile_id: str | None = None,
    expert_id: str | None = None,
    reason: str | None = None,
    selected_count: int | None = None,
    rejected_count: int | None = None,
    total_proposals: int | None = None,
    validation_found: bool = False,
    report_found: bool = False,
    replay_status: str | None = None,
) -> str:
    if status == "missing":
        return f"No static router explainability evidence found for {entity} '{target_id}'."
    if status == "unsupported":
        return f"Static router explainability is unsupported for {entity} '{target_id}' with the provided artifacts."

    parts = [f"Static router explanation for {entity} '{target_id}' is {status}."]
    if profile_id:
        parts.append(f"profile={profile_id}")
    if expert_id:
        parts.append(f"expert={expert_id}")
    if reason:
        parts.append(f"reason={reason}")
    if selected_count is not None:
        parts.append(f"selected={selected_count}")
    if rejected_count is not None:
        parts.append(f"rejected={rejected_count}")
    if total_proposals is not None:
        parts.append(f"proposals={total_proposals}")
    if validation_found:
        parts.append("validation=present")
    if report_found:
        parts.append("report=present")
    if replay_status:
        parts.append(f"replay={replay_status}")
    return " ".join(parts)


def _int_payload_field(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    if isinstance(value, float):
        return int(value)
    return None


def _audit_event_sort_key(event: Any) -> tuple[int, str, str, str]:
    logical_tick = _artifact_field(event, "logical_tick", 0)
    try:
        tick = int(logical_tick)
    except (TypeError, ValueError):
        tick = 0
    return (
        tick,
        str(_artifact_field(event, "correlation_id", "")),
        str(_artifact_field(event, "event_type", "")),
        str(_artifact_field(event, "event_id", "")),
    )


def _router_payload_records(payload: Any, key: str) -> list[dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return []
    records = payload.get(key, [])
    if not isinstance(records, Sequence) or isinstance(records, (bytes, bytearray, str)):
        return []
    results: list[dict[str, Any]] = []
    for record in records:
        if isinstance(record, Mapping):
            results.append(dict(record))
    return results


def _is_supported_artifact(artifact: Any) -> bool:
    if artifact is None:
        return False
    if isinstance(artifact, Mapping):
        return True
    if isinstance(artifact, Sequence) and not isinstance(artifact, (bytes, bytearray, str)):
        return True

    supported_attrs = (
        "to_dict",
        "node_by_id",
        "topological_order",
        "edges_to",
        "edges_from",
        "all",
        "by_type",
        "query_fact",
        "query_by_hash",
        "all_facts",
        "fingerprint",
        "__dict__",
    )
    return any(hasattr(artifact, attr) for attr in supported_attrs)


def _artifact_documents(artifact: Any) -> list[Any]:
    docs: list[Any] = []
    if artifact is None:
        return docs

    if isinstance(artifact, Mapping):
        docs.append(artifact)

    if hasattr(artifact, "__dict__"):
        try:
            docs.append(dict(vars(artifact)))
        except Exception:
            pass

    if hasattr(artifact, "nodes"):
        try:
            docs.append({"nodes": getattr(artifact, "nodes")})
        except Exception:
            pass
    if hasattr(artifact, "edges"):
        try:
            docs.append({"edges": getattr(artifact, "edges")})
        except Exception:
            pass
    if hasattr(artifact, "events"):
        try:
            docs.append({"events": getattr(artifact, "events")})
        except Exception:
            pass
    if hasattr(artifact, "facts"):
        try:
            docs.append({"facts": getattr(artifact, "facts")})
        except Exception:
            pass

    to_dict = getattr(artifact, "to_dict", None)
    if callable(to_dict):
        try:
            docs.append(to_dict())
        except Exception:
            pass

    return docs


@dataclass(frozen=True)
class ExplainabilityWarning:
    """Serializable warning emitted by static explainability."""

    code: str
    message: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "metadata": dict(self.metadata),
        }


def _to_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, AbcMapping):
        return dict(value)
    if hasattr(value, "to_dict") and callable(getattr(value, "to_dict")):
        try:
            data = value.to_dict()
        except Exception:
            return {}
        if isinstance(data, dict):
            return data
    if hasattr(value, "__dict__"):
        try:
            return dict(vars(value))
        except Exception:
            return {}
    return {}


def _collect_fingerprint_candidates(data: Any, *, prefix: str = "") -> dict[str, str]:
    """Collect explicit fingerprint/hash/digest fields from nested mappings."""
    candidates: dict[str, str] = {}

    if isinstance(data, dict):
        for key, value in data.items():
            key_str = str(key)
            path = f"{prefix}.{key_str}" if prefix else key_str
            lowered = key_str.lower()

            if isinstance(value, str) and (
                "fingerprint" in lowered
                or "hash" in lowered
                or "digest" in lowered
            ):
                candidates[path] = value
            elif isinstance(value, dict):
                candidates.update(_collect_fingerprint_candidates(value, prefix=path))
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    if isinstance(item, dict):
                        candidates.update(
                            _collect_fingerprint_candidates(item, prefix=f"{path}[{index}]")
                        )

    return candidates


def _fingerprint_leaf_key(path: str) -> str:
    leaf = path.rsplit(".", 1)[-1]
    return leaf.split("[", 1)[0]


def _is_comparable_fingerprint_value(value: str) -> bool:
    return isinstance(value, str) and len(value.strip()) >= 16


def _manifest_fingerprint_warnings(
    *,
    execution_graph: Any | None,
    manifest: Any | None,
) -> list[dict[str, Any]]:
    """Best-effort manifest consistency check for frozen artifacts."""
    if execution_graph is None or manifest is None:
        return []

    manifest_data = _to_mapping(manifest)
    graph_data = _to_mapping(execution_graph)
    if not manifest_data or not graph_data:
        return []

    expected_candidates = _collect_fingerprint_candidates(manifest_data)
    actual_candidates = _collect_fingerprint_candidates(graph_data)
    if not expected_candidates or not actual_candidates:
        return []

    expected_by_leaf: dict[str, tuple[str, str]] = {
        _fingerprint_leaf_key(path): (path, value)
        for path, value in expected_candidates.items()
    }
    actual_by_leaf: dict[str, tuple[str, str]] = {
        _fingerprint_leaf_key(path): (path, value)
        for path, value in actual_candidates.items()
    }

    warnings: list[dict[str, Any]] = []
    for leaf_key in sorted(set(expected_by_leaf).intersection(actual_by_leaf)):
        expected_path, expected = expected_by_leaf[leaf_key]
        actual_path, actual = actual_by_leaf[leaf_key]
        if (
            expected
            and actual
            and _is_comparable_fingerprint_value(expected)
            and _is_comparable_fingerprint_value(actual)
            and expected != actual
        ):
            warnings.append(
                {
                    "code": "fingerprint_mismatch",
                    "message": (
                        f"Fingerprint mismatch for '{leaf_key}'. Static explanation may "
                        "be inconsistent with the certified manifest."
                    ),
                    "fingerprint_key": leaf_key,
                    "manifest_path": expected_path,
                    "graph_path": actual_path,
                    "expected": expected,
                    "actual": actual,
                }
            )
    return warnings


def _status_from_evidence_with_artifacts(
    *groups: Sequence[str],
    artifacts_present: bool = False,
) -> ExplanationStatus:
    non_empty = sum(1 for group in groups if group)
    if non_empty >= 2:
        return "complete"
    if non_empty == 1:
        return "partial"
    if artifacts_present:
        return "unsupported"
    return "missing"


@dataclass(frozen=True)
class ExplanationResult:
    """Serializable, read-only explanation payload."""

    query: str
    target_id: str
    status: ExplanationStatus
    summary: str
    graph_node_ids: tuple[str, ...] = field(default_factory=tuple)
    event_ids: tuple[str, ...] = field(default_factory=tuple)
    fact_ids: tuple[str, ...] = field(default_factory=tuple)
    projection_ids: tuple[str, ...] = field(default_factory=tuple)
    constraint_ids: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[ExplainabilityWarning, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "metadata", _freeze_value(dict(self.metadata)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "target_id": self.target_id,
            "status": self.status,
            "summary": self.summary,
            "graph_node_ids": list(self.graph_node_ids),
            "event_ids": list(self.event_ids),
            "fact_ids": list(self.fact_ids),
            "projection_ids": list(self.projection_ids),
            "constraint_ids": list(self.constraint_ids),
            "warnings": [warning.to_dict() for warning in self.warnings],
            "metadata": _unfreeze_value(self.metadata),
        }


class StaticExplainer:
    """Read-only static explainer for completed CORE executions."""

    def __init__(
        self,
        *,
        execution_graph: Any | None = None,
        event_log: Any | None = None,
        knowledge_base: Any | None = None,
        replay_metadata: Any | None = None,
        audit_trail: Any | None = None,
        manifest: Any | None = None,
    ) -> None:
        self._execution_graph = execution_graph
        self._event_log_artifact = event_log
        self._knowledge_base_artifact = knowledge_base
        self._replay_metadata = replay_metadata
        self._audit_trail_artifact = audit_trail
        self._manifest = manifest
        self._artifact_warnings = tuple(
            ExplainabilityWarning(
                code=item["code"],
                message=item["message"],
                metadata={
                    key: value
                    for key, value in item.items()
                    if key not in {"code", "message"}
                },
            )
            for item in _manifest_fingerprint_warnings(
                execution_graph=execution_graph,
                manifest=manifest,
            )
        )

    def cause_of_projection(self, projection_id: str) -> ExplanationResult:
        target_id = _normalize_id(projection_id)
        native_graph = _native_graph_lookup(self._graph(), target_id)
        native_event = _native_event_lookup(self._event_log(), target_id)
        native_kb = _native_knowledge_base_lookup(self._knowledge_base(), target_id)
        native_audit = _native_audit_lookup(self._audit_trail(), target_id)

        projection_ids = _dedupe_sorted_stable(
            list(native_graph["projection_ids"])
            + list(native_event["projection_ids"])
            + list(native_kb["projection_ids"])
            + list(native_audit["projection_ids"])
            + list(self._projection_ids(target_id))
        )
        graph_node_ids = _dedupe_sorted_stable(
            list(native_graph["graph_node_ids"])
            + list(native_event["graph_node_ids"])
            + list(native_kb["graph_node_ids"])
            + list(native_audit["graph_node_ids"])
            + list(self._projection_graph_nodes(target_id))
        )
        graph_node_ids = _dedupe_sorted_stable(list(graph_node_ids) + list(self._graph_lineage(graph_node_ids)))
        event_ids = _dedupe_sorted_stable(
            list(native_graph["event_ids"])
            + list(native_event["event_ids"])
            + list(native_kb["event_ids"])
            + list(native_audit["event_ids"])
            + list(self._projection_event_ids(target_id, projection_ids))
        )
        fact_ids = _dedupe_sorted_stable(
            list(native_graph["fact_ids"])
            + list(native_event["fact_ids"])
            + list(native_kb["fact_ids"])
            + list(native_audit["fact_ids"])
            + list(self._projection_fact_ids(target_id, projection_ids))
        )
        constraint_ids = _dedupe_sorted_stable(
            list(native_graph["constraint_ids"])
            + list(native_audit["constraint_ids"])
            + list(self._constraint_ids(graph_node_ids))
        )
        status = self._status(graph_node_ids, event_ids, fact_ids, projection_ids, constraint_ids)
        return ExplanationResult(
            query="cause_of_projection",
            target_id=target_id,
            status=status,
            summary=_summary(
                "projection",
                target_id,
                status,
                graph_node_ids=graph_node_ids,
                event_ids=event_ids,
                fact_ids=fact_ids,
                projection_ids=projection_ids,
                constraint_ids=constraint_ids,
            ),
            graph_node_ids=graph_node_ids,
            event_ids=event_ids,
            fact_ids=fact_ids,
            projection_ids=projection_ids,
            constraint_ids=constraint_ids,
            warnings=self._artifact_warnings,
            metadata=self._metadata(query="cause_of_projection"),
        )

    def lineage_of_fact(self, fact_id: str) -> ExplanationResult:
        target_id = _normalize_id(fact_id)
        native_graph = _native_graph_lookup(self._graph(), target_id)
        native_event = _native_event_lookup(self._event_log(), target_id)
        native_kb = _native_knowledge_base_lookup(self._knowledge_base(), target_id)
        native_audit = _native_audit_lookup(self._audit_trail(), target_id)

        fact_ids = _dedupe_sorted_stable(
            list(native_graph["fact_ids"])
            + list(native_event["fact_ids"])
            + list(native_kb["fact_ids"])
            + list(native_audit["fact_ids"])
            + list(self._fact_ids(target_id))
        )
        graph_node_ids = _dedupe_sorted_stable(
            list(native_graph["graph_node_ids"])
            + list(native_event["graph_node_ids"])
            + list(native_kb["graph_node_ids"])
            + list(native_audit["graph_node_ids"])
            + list(self._fact_graph_nodes(target_id, fact_ids))
        )
        graph_node_ids = _dedupe_sorted_stable(list(graph_node_ids) + list(self._graph_lineage(graph_node_ids)))
        event_ids = _dedupe_sorted_stable(
            list(native_graph["event_ids"])
            + list(native_event["event_ids"])
            + list(native_kb["event_ids"])
            + list(native_audit["event_ids"])
            + list(self._fact_event_ids(target_id, fact_ids))
        )
        projection_ids = _dedupe_sorted_stable(
            list(native_graph["projection_ids"])
            + list(native_event["projection_ids"])
            + list(native_kb["projection_ids"])
            + list(native_audit["projection_ids"])
            + list(self._fact_projection_ids(target_id, fact_ids))
        )
        parent_fact_ids = _dedupe_sorted_stable(
            list(native_graph["fact_ids"])
            + list(native_event["fact_ids"])
            + list(native_kb["fact_ids"])
            + list(native_audit["fact_ids"])
            + list(self._parent_fact_ids(target_id, fact_ids))
        )
        status = self._status(graph_node_ids, event_ids, fact_ids or parent_fact_ids, projection_ids)
        return ExplanationResult(
            query="lineage_of_fact",
            target_id=target_id,
            status=status,
            summary=_summary(
                "fact",
                target_id,
                status,
                graph_node_ids=graph_node_ids,
                event_ids=event_ids,
                fact_ids=parent_fact_ids or fact_ids,
                projection_ids=projection_ids,
            ),
            graph_node_ids=graph_node_ids,
            event_ids=event_ids,
            fact_ids=parent_fact_ids or fact_ids,
            projection_ids=projection_ids,
            warnings=self._artifact_warnings,
            metadata=self._metadata(query="lineage_of_fact"),
        )

    def trace_of_event(self, event_id: str) -> ExplanationResult:
        target_id = _normalize_id(event_id)
        native_graph = _native_graph_lookup(self._graph(), target_id)
        native_event = _native_event_lookup(self._event_log(), target_id)
        native_kb = _native_knowledge_base_lookup(self._knowledge_base(), target_id)
        native_audit = _native_audit_lookup(self._audit_trail(), target_id)

        event_ids = _dedupe_sorted_stable(
            list(native_graph["event_ids"])
            + list(native_event["event_ids"])
            + list(native_kb["event_ids"])
            + list(native_audit["event_ids"])
            + list(self._event_ids(target_id))
        )
        graph_node_ids = _dedupe_sorted_stable(
            list(native_graph["graph_node_ids"])
            + list(native_event["graph_node_ids"])
            + list(native_kb["graph_node_ids"])
            + list(native_audit["graph_node_ids"])
            + list(self._event_graph_nodes(target_id, event_ids))
        )
        graph_node_ids = _dedupe_sorted_stable(list(graph_node_ids) + list(self._graph_lineage(graph_node_ids)))
        fact_ids = _dedupe_sorted_stable(
            list(native_graph["fact_ids"])
            + list(native_event["fact_ids"])
            + list(native_kb["fact_ids"])
            + list(native_audit["fact_ids"])
            + list(self._event_fact_ids(target_id, event_ids))
        )
        projection_ids = _dedupe_sorted_stable(
            list(native_graph["projection_ids"])
            + list(native_event["projection_ids"])
            + list(native_kb["projection_ids"])
            + list(native_audit["projection_ids"])
            + list(self._event_projection_ids(target_id, event_ids))
        )
        event_ids = _dedupe_sorted_stable(list(event_ids) + list(self._event_neighborhood(target_id, event_ids)))
        status = self._status(graph_node_ids, event_ids, fact_ids, projection_ids)
        return ExplanationResult(
            query="trace_of_event",
            target_id=target_id,
            status=status,
            summary=_summary(
                "event",
                target_id,
                status,
                graph_node_ids=graph_node_ids,
                event_ids=event_ids,
                fact_ids=fact_ids,
                projection_ids=projection_ids,
            ),
            graph_node_ids=graph_node_ids,
            event_ids=event_ids,
            fact_ids=fact_ids,
            projection_ids=projection_ids,
            warnings=self._artifact_warnings,
            metadata=self._metadata(query="trace_of_event"),
        )

    def origin_projection(self, output_id: str) -> ExplanationResult:
        target_id = _normalize_id(output_id)
        native_graph = _native_graph_lookup(self._graph(), target_id)
        native_event = _native_event_lookup(self._event_log(), target_id)
        native_kb = _native_knowledge_base_lookup(self._knowledge_base(), target_id)
        native_audit = _native_audit_lookup(self._audit_trail(), target_id)

        projection_ids = _dedupe_sorted_stable(
            list(native_graph["projection_ids"])
            + list(native_event["projection_ids"])
            + list(native_kb["projection_ids"])
            + list(native_audit["projection_ids"])
            + list(self._origin_projection_ids(target_id))
        )
        graph_node_ids = _dedupe_sorted_stable(
            list(native_graph["graph_node_ids"])
            + list(native_event["graph_node_ids"])
            + list(native_kb["graph_node_ids"])
            + list(native_audit["graph_node_ids"])
            + list(self._origin_projection_graph_nodes(target_id, projection_ids))
        )
        graph_node_ids = _dedupe_sorted_stable(list(graph_node_ids) + list(self._graph_lineage(graph_node_ids)))
        event_ids = _dedupe_sorted_stable(
            list(native_graph["event_ids"])
            + list(native_event["event_ids"])
            + list(native_kb["event_ids"])
            + list(native_audit["event_ids"])
            + list(self._origin_projection_event_ids(target_id, projection_ids))
        )
        fact_ids = _dedupe_sorted_stable(
            list(native_graph["fact_ids"])
            + list(native_event["fact_ids"])
            + list(native_kb["fact_ids"])
            + list(native_audit["fact_ids"])
            + list(self._origin_projection_fact_ids(target_id, projection_ids))
        )
        status = self._status(graph_node_ids, event_ids, fact_ids, projection_ids)
        return ExplanationResult(
            query="origin_projection",
            target_id=target_id,
            status=status,
            summary=_summary(
                "output",
                target_id,
                status,
                graph_node_ids=graph_node_ids,
                event_ids=event_ids,
                fact_ids=fact_ids,
                projection_ids=projection_ids,
            ),
            graph_node_ids=graph_node_ids,
            event_ids=event_ids,
            fact_ids=fact_ids,
            projection_ids=projection_ids,
            warnings=self._artifact_warnings,
            metadata=self._metadata(query="origin_projection"),
        )

    def cause_of_event(self, event_id: str) -> ExplanationResult:
        target_id = _normalize_id(event_id)
        native_audit = _native_audit_lookup(self._audit_trail(), target_id)
        native_event = _native_event_lookup(self._event_log(), target_id)
        native_graph = _native_graph_lookup(self._graph(), target_id)
        native_kb = _native_knowledge_base_lookup(self._knowledge_base(), target_id)

        event_ids = _dedupe_sorted_stable(
            [target_id]
            + list(native_audit["event_ids"])
            + list(native_event["event_ids"])
            + list(native_graph["event_ids"])
            + list(native_kb["event_ids"])
        )
        projection_ids = _dedupe_sorted_stable(
            list(native_audit["projection_ids"])
            + list(native_event["projection_ids"])
            + list(native_graph["projection_ids"])
            + list(native_kb["projection_ids"])
        )
        fact_ids = _dedupe_sorted_stable(
            list(native_audit["fact_ids"])
            + list(native_event["fact_ids"])
            + list(native_graph["fact_ids"])
            + list(native_kb["fact_ids"])
        )
        graph_node_ids = _dedupe_sorted_stable(
            list(native_audit["graph_node_ids"])
            + list(native_event["graph_node_ids"])
            + list(native_graph["graph_node_ids"])
            + list(native_kb["graph_node_ids"])
        )
        constraint_ids = _dedupe_sorted_stable(
            list(native_audit["constraint_ids"])
            + list(native_event["constraint_ids"])
            + list(native_graph["constraint_ids"])
        )
        status = self._status(graph_node_ids, event_ids, fact_ids, projection_ids, constraint_ids)
        return ExplanationResult(
            query="cause_of_event",
            target_id=target_id,
            status=status,
            summary=_summary(
                "event",
                target_id,
                status,
                graph_node_ids=graph_node_ids,
                event_ids=event_ids,
                fact_ids=fact_ids,
                projection_ids=projection_ids,
                constraint_ids=constraint_ids,
            ),
            graph_node_ids=graph_node_ids,
            event_ids=event_ids,
            fact_ids=fact_ids,
            projection_ids=projection_ids,
            constraint_ids=constraint_ids,
            warnings=self._artifact_warnings,
            metadata=self._metadata(query="cause_of_event"),
        )

    def trace_of_report(self, report_id: str) -> ExplanationResult:
        target_id = _normalize_id(report_id)
        correlation_id = target_id if target_id.startswith("report::") else report_correlation_id(target_id)
        native_audit = _native_audit_lookup(self._audit_trail(), correlation_id)

        event_ids = _dedupe_sorted_stable(list(native_audit["event_ids"]))
        projection_ids = _dedupe_sorted_stable(list(native_audit["projection_ids"]) + [correlation_id])
        fact_ids = _dedupe_sorted_stable(list(native_audit["fact_ids"]))
        graph_node_ids = _dedupe_sorted_stable(list(native_audit["graph_node_ids"]))
        constraint_ids = _dedupe_sorted_stable(list(native_audit["constraint_ids"]))
        status = self._status(graph_node_ids, event_ids, fact_ids, projection_ids, constraint_ids)
        return ExplanationResult(
            query="trace_of_report",
            target_id=target_id,
            status=status,
            summary=_summary(
                "report",
                target_id,
                status,
                graph_node_ids=graph_node_ids,
                event_ids=event_ids,
                fact_ids=fact_ids,
                projection_ids=projection_ids,
                constraint_ids=constraint_ids,
            ),
            graph_node_ids=graph_node_ids,
            event_ids=event_ids,
            fact_ids=fact_ids,
            projection_ids=projection_ids,
            constraint_ids=constraint_ids,
            warnings=self._artifact_warnings,
            metadata=self._metadata(query="trace_of_report", correlation_id=correlation_id),
        )

    def cause_of_router_selection(self, routing_id: str, expert_id: str) -> ExplanationResult:
        routing_id = _normalize_id(routing_id)
        expert_id = _normalize_id(expert_id)

        validation_event = self._router_validation_event(routing_id)
        evaluation_event = self._router_evaluation_event(routing_id)
        replay_event = self._router_replay_event(routing_id)
        report_event = self._router_report_event(routing_id)

        selected_record = self._router_expert_record(evaluation_event, "selected_experts", expert_id)
        selected_ids = self._router_record_ids(evaluation_event, "selected_expert_ids")
        reason = str(selected_record.get("reason", "")).strip() if selected_record else ""
        profile_id = str(_artifact_field(_artifact_field(evaluation_event, "payload", {}), "profile_id", "")).strip()
        report_id = self._router_report_id(report_event)
        projection_ids = _dedupe_sorted_stable([routing_id, report_id])
        event_ids = _dedupe_sorted_stable(
            list(self._event_ids_for_router_events((validation_event, evaluation_event, replay_event, report_event)))
        )
        status = self._status(event_ids, projection_ids)
        warnings = list(self._artifact_warnings)
        if evaluation_event is not None and selected_record is None:
            status = "partial"
            warnings.append(
                ExplainabilityWarning(
                    code="router_selection_record_missing",
                    message="Router evaluation evidence was found, but no explicit selected expert record matched the query.",
                    metadata={"routing_id": routing_id, "expert_id": expert_id},
                )
            )
        elif evaluation_event is None and event_ids:
            status = "partial"

        summary = _router_summary(
            "selection",
            routing_id,
            status,
            profile_id=profile_id or None,
            expert_id=expert_id,
            reason=reason or None,
            selected_count=_int_payload_field(_artifact_field(_artifact_field(evaluation_event, "payload", {}), "selected_count", None)),
            rejected_count=_int_payload_field(_artifact_field(_artifact_field(evaluation_event, "payload", {}), "rejected_count", None)),
            total_proposals=_int_payload_field(_artifact_field(_artifact_field(evaluation_event, "payload", {}), "total_proposals", None)),
            validation_found=validation_event is not None,
            report_found=report_event is not None,
            replay_status=str(_artifact_field(_artifact_field(replay_event, "payload", {}), "status", "")).strip() or None,
        )
        return ExplanationResult(
            query="cause_of_router_selection",
            target_id=f"{routing_id}::{expert_id}",
            status=status,
            summary=summary,
            projection_ids=projection_ids,
            event_ids=event_ids,
            warnings=tuple(warnings),
            metadata=self._metadata(
                query="cause_of_router_selection",
                routing_id=routing_id,
                expert_id=expert_id,
                profile_id=profile_id or None,
                selected_record=selected_record or {},
                selected_expert_ids=selected_ids,
                report_id=report_id,
                router_events=self._router_event_summaries((validation_event, evaluation_event, replay_event, report_event)),
            ),
        )

    def cause_of_router_rejection(self, routing_id: str, expert_id: str) -> ExplanationResult:
        routing_id = _normalize_id(routing_id)
        expert_id = _normalize_id(expert_id)

        validation_event = self._router_validation_event(routing_id)
        evaluation_event = self._router_evaluation_event(routing_id)
        replay_event = self._router_replay_event(routing_id)
        report_event = self._router_report_event(routing_id)

        rejected_record = self._router_expert_record(evaluation_event, "rejected_experts", expert_id)
        rejected_ids = self._router_record_ids(evaluation_event, "rejected_expert_ids")
        reason = str(rejected_record.get("reason", "")).strip() if rejected_record else ""
        profile_id = str(_artifact_field(_artifact_field(evaluation_event, "payload", {}), "profile_id", "")).strip()
        report_id = self._router_report_id(report_event)
        projection_ids = _dedupe_sorted_stable([routing_id, report_id])
        event_ids = _dedupe_sorted_stable(
            list(self._event_ids_for_router_events((validation_event, evaluation_event, replay_event, report_event)))
        )
        status = self._status(event_ids, projection_ids)
        warnings = list(self._artifact_warnings)
        if evaluation_event is not None and rejected_record is None:
            status = "partial"
            warnings.append(
                ExplainabilityWarning(
                    code="router_rejection_record_missing",
                    message="Router evaluation evidence was found, but no explicit rejected expert record matched the query.",
                    metadata={"routing_id": routing_id, "expert_id": expert_id},
                )
            )
        elif evaluation_event is None and event_ids:
            status = "partial"

        summary = _router_summary(
            "rejection",
            routing_id,
            status,
            profile_id=profile_id or None,
            expert_id=expert_id,
            reason=reason or None,
            selected_count=_int_payload_field(_artifact_field(_artifact_field(evaluation_event, "payload", {}), "selected_count", None)),
            rejected_count=_int_payload_field(_artifact_field(_artifact_field(evaluation_event, "payload", {}), "rejected_count", None)),
            total_proposals=_int_payload_field(_artifact_field(_artifact_field(evaluation_event, "payload", {}), "total_proposals", None)),
            validation_found=validation_event is not None,
            report_found=report_event is not None,
            replay_status=str(_artifact_field(_artifact_field(replay_event, "payload", {}), "status", "")).strip() or None,
        )
        return ExplanationResult(
            query="cause_of_router_rejection",
            target_id=f"{routing_id}::{expert_id}",
            status=status,
            summary=summary,
            projection_ids=projection_ids,
            event_ids=event_ids,
            warnings=tuple(warnings),
            metadata=self._metadata(
                query="cause_of_router_rejection",
                routing_id=routing_id,
                expert_id=expert_id,
                profile_id=profile_id or None,
                rejected_record=rejected_record or {},
                rejected_expert_ids=rejected_ids,
                report_id=report_id,
                router_events=self._router_event_summaries((validation_event, evaluation_event, replay_event, report_event)),
            ),
        )

    def trace_of_router_decision(self, routing_id: str) -> ExplanationResult:
        routing_id = _normalize_id(routing_id)

        validation_event = self._router_validation_event(routing_id)
        evaluation_event = self._router_evaluation_event(routing_id)
        replay_event = self._router_replay_event(routing_id)
        report_event = self._router_report_event(routing_id)
        report_id = self._router_report_id(report_event)
        projection_ids = _dedupe_sorted_stable([routing_id, report_id])
        event_ids = _dedupe_sorted_stable(
            list(self._event_ids_for_router_events((validation_event, evaluation_event, replay_event, report_event)))
        )
        status = self._status(event_ids, projection_ids)
        evaluation_payload = _artifact_field(evaluation_event, "payload", {})
        profile_id = str(_artifact_field(evaluation_payload, "profile_id", "")).strip()
        summary = _router_summary(
            "decision trace",
            routing_id,
            status,
            profile_id=profile_id or None,
            selected_count=_int_payload_field(_artifact_field(evaluation_payload, "selected_count", None)),
            rejected_count=_int_payload_field(_artifact_field(evaluation_payload, "rejected_count", None)),
            total_proposals=_int_payload_field(_artifact_field(evaluation_payload, "total_proposals", None)),
            validation_found=validation_event is not None,
            report_found=report_event is not None,
            replay_status=str(_artifact_field(_artifact_field(replay_event, "payload", {}), "status", "")).strip() or None,
        )
        return ExplanationResult(
            query="trace_of_router_decision",
            target_id=routing_id,
            status=status,
            summary=summary,
            projection_ids=projection_ids,
            event_ids=event_ids,
            warnings=self._artifact_warnings,
            metadata=self._metadata(
                query="trace_of_router_decision",
                routing_id=routing_id,
                profile_id=profile_id or None,
                selected_expert_ids=self._router_record_ids(evaluation_event, "selected_expert_ids"),
                rejected_expert_ids=self._router_record_ids(evaluation_event, "rejected_expert_ids"),
                report_id=report_id,
                router_events=self._router_event_summaries((validation_event, evaluation_event, replay_event, report_event)),
                validation_event=self._router_event_summary(validation_event),
                evaluation_event=self._router_event_summary(evaluation_event),
                replay_event=self._router_event_summary(replay_event),
                report_event=self._router_event_summary(report_event),
            ),
        )

    def trace_of_router_report(self, report_id: str) -> ExplanationResult:
        report_id = _normalize_id(report_id)
        correlation_id = report_id if report_id.startswith("report::") else report_correlation_id(report_id)
        native_audit = _native_audit_lookup(self._audit_trail(), correlation_id)
        report_event = self._router_report_event_by_report_id(report_id)
        event_ids = _dedupe_sorted_stable(
            list(native_audit["event_ids"])
            + ([self._event_identifier(report_event)] if report_event is not None else [])
        )
        projection_ids = _dedupe_sorted_stable(
            list(native_audit["projection_ids"]) + ([correlation_id] if correlation_id else [])
        )
        fact_ids = _dedupe_sorted_stable(list(native_audit["fact_ids"]))
        graph_node_ids = _dedupe_sorted_stable(list(native_audit["graph_node_ids"]))
        constraint_ids = _dedupe_sorted_stable(list(native_audit["constraint_ids"]))
        status = self._status(graph_node_ids, event_ids, fact_ids, projection_ids, constraint_ids)
        summary = _router_summary(
            "batch report",
            report_id,
            status,
            report_found=report_event is not None,
        )
        return ExplanationResult(
            query="trace_of_router_report",
            target_id=report_id,
            status=status,
            summary=summary,
            graph_node_ids=graph_node_ids,
            event_ids=event_ids,
            fact_ids=fact_ids,
            projection_ids=projection_ids,
            constraint_ids=constraint_ids,
            warnings=self._artifact_warnings,
            metadata=self._metadata(
                query="trace_of_router_report",
                correlation_id=correlation_id,
                report_id=report_id,
                report_event=self._router_event_summary(report_event),
            ),
        )

    def evidence_for_router_decision(self, routing_id: str) -> ExplanationResult:
        routing_id = _normalize_id(routing_id)

        validation_event = self._router_validation_event(routing_id)
        evaluation_event = self._router_evaluation_event(routing_id)
        replay_event = self._router_replay_event(routing_id)
        report_event = self._router_report_event(routing_id)
        report_id = self._router_report_id(report_event)
        projection_ids = _dedupe_sorted_stable([routing_id, report_id])
        event_ids = _dedupe_sorted_stable(
            list(self._event_ids_for_router_events((validation_event, evaluation_event, replay_event, report_event)))
        )
        status = self._status(event_ids, projection_ids)
        evaluation_payload = _artifact_field(evaluation_event, "payload", {})
        report_id = self._router_report_id(report_event)
        summary = _router_summary(
            "evidence bundle",
            routing_id,
            status,
            profile_id=str(_artifact_field(evaluation_payload, "profile_id", "")).strip() or None,
            selected_count=_int_payload_field(_artifact_field(evaluation_payload, "selected_count", None)),
            rejected_count=_int_payload_field(_artifact_field(evaluation_payload, "rejected_count", None)),
            total_proposals=_int_payload_field(_artifact_field(evaluation_payload, "total_proposals", None)),
            validation_found=validation_event is not None,
            report_found=report_event is not None,
            replay_status=str(_artifact_field(_artifact_field(replay_event, "payload", {}), "status", "")).strip() or None,
        )
        return ExplanationResult(
            query="evidence_for_router_decision",
            target_id=routing_id,
            status=status,
            summary=summary,
            projection_ids=projection_ids,
            event_ids=event_ids,
            warnings=self._artifact_warnings,
            metadata=self._metadata(
                query="evidence_for_router_decision",
                routing_id=routing_id,
                profile_id=str(_artifact_field(evaluation_payload, "profile_id", "")).strip() or None,
                report_id=report_id,
                fixture_file=self._router_fixture_file_from_routing_id(routing_id),
                selected_expert_ids=self._router_record_ids(evaluation_event, "selected_expert_ids"),
                rejected_expert_ids=self._router_record_ids(evaluation_event, "rejected_expert_ids"),
                router_events=self._router_event_summaries((validation_event, evaluation_event, replay_event, report_event)),
                validation_event=self._router_event_summary(validation_event),
                evaluation_event=self._router_event_summary(evaluation_event),
                replay_event=self._router_event_summary(replay_event),
                report_event=self._router_event_summary(report_event),
            ),
        )

    # ------------------------------------------------------------------
    # Internal lookup helpers
    # ------------------------------------------------------------------

    def _metadata(self, **extra: Any) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "artifacts_present": _has_any_artifact(
                self._execution_graph,
                self._event_log_artifact,
                self._knowledge_base_artifact,
                self._replay_metadata,
                self._audit_trail_artifact,
            ),
            "supported": {
                "execution_graph": _is_supported_artifact(self._execution_graph),
                "event_log": _is_supported_artifact(self._event_log_artifact),
                "knowledge_base": _is_supported_artifact(self._knowledge_base_artifact),
                "replay_metadata": _is_supported_artifact(self._replay_metadata),
                "audit_trail": _is_supported_artifact(self._audit_trail_artifact),
            },
        }
        if self._artifact_warnings:
            metadata["warnings"] = [warning.to_dict() for warning in self._artifact_warnings]
        metadata.update(extra)
        return metadata

    def _status(self, *groups: Sequence[str]) -> ExplanationStatus:
        return _status_from_evidence_with_artifacts(
            *groups,
            artifacts_present=_has_any_artifact(
                self._execution_graph,
                self._event_log_artifact,
                self._knowledge_base_artifact,
                self._replay_metadata,
                self._audit_trail_artifact,
            ),
        )

    def _graph(self) -> Any | None:
        return self._execution_graph

    def _event_log(self) -> Any | None:
        return self._event_log_artifact

    def _knowledge_base(self) -> Any | None:
        return self._knowledge_base_artifact

    def _audit_trail(self) -> Any | None:
        return self._audit_trail_artifact

    def _audit_entries(self) -> list[Any]:
        audit = self._audit_trail()
        if audit is None:
            return []
        if isinstance(audit, AuditTrailIndex):
            return list(audit.events)
        if hasattr(audit, "events"):
            try:
                entries = list(getattr(audit, "events"))
            except Exception:
                entries = []
        elif hasattr(audit, "all") and callable(getattr(audit, "all")):
            try:
                entries = list(audit.all())
            except Exception:
                entries = []
        elif isinstance(audit, Mapping):
            raw_events = audit.get("events", [])
            try:
                entries = list(raw_events)
            except Exception:
                entries = []
        else:
            entries = []
        return sorted(entries, key=_audit_event_sort_key)

    def _router_events_by_correlation(self, routing_id: str) -> list[Any]:
        correlation_id = router_correlation_id(routing_id)
        audit = self._audit_trail()
        if isinstance(audit, AuditTrailIndex):
            return list(audit.lookup_correlation(correlation_id))
        return [
            event
            for event in self._audit_entries()
            if _artifact_field(event, "correlation_id", "") == correlation_id
        ]

    def _router_events_of_type(self, event_type: str) -> list[Any]:
        audit = self._audit_trail()
        if isinstance(audit, AuditTrailIndex):
            return list(audit.lookup_type(event_type))
        return [
            event
            for event in self._audit_entries()
            if _artifact_field(event, "event_type", "") == event_type
        ]

    def _router_validation_event(self, routing_id: str) -> Any | None:
        for event in self._router_events_by_correlation(routing_id):
            if _artifact_field(event, "event_type", "") == "RouterFixtureValidated":
                return event
        return None

    def _router_evaluation_event(self, routing_id: str) -> Any | None:
        for event in self._router_events_by_correlation(routing_id):
            if _artifact_field(event, "event_type", "") == "RouterEligibilityEvaluated":
                return event
        return None

    def _router_replay_event(self, routing_id: str) -> Any | None:
        replay_events = [
            event
            for event in self._router_events_by_correlation(routing_id)
            if _artifact_field(event, "event_type", "") in {"RouterReplayCertified", "RouterReplayDiverged"}
        ]
        if replay_events:
            return replay_events[0]
        return None

    def _router_report_event(self, routing_id: str) -> Any | None:
        fixture_name = self._router_fixture_file_from_routing_id(routing_id)
        report_events = self._router_events_of_type("RouterBatchReportGenerated")
        if fixture_name:
            for event in report_events:
                payload = _artifact_field(event, "payload", {})
                fixture_files = _string_values(_artifact_field(payload, "fixture_files", []))
                if fixture_name in fixture_files:
                    return event
        if len(report_events) == 1:
            return report_events[0]
        return None

    def _router_report_event_by_report_id(self, report_id: str) -> Any | None:
        correlation_id = report_id if report_id.startswith("report::") else report_correlation_id(report_id)
        audit = self._audit_trail()
        if isinstance(audit, AuditTrailIndex):
            for event in audit.lookup_correlation(correlation_id):
                if _artifact_field(event, "event_type", "") == "RouterBatchReportGenerated":
                    return event
        for event in self._router_events_of_type("RouterBatchReportGenerated"):
            payload = _artifact_field(event, "payload", {})
            if report_id in {
                _artifact_field(payload, "report_id", ""),
                _artifact_field(event, "correlation_id", ""),
                _artifact_field(event, "event_id", ""),
            }:
                return event
        return None

    def _router_expert_record(self, event: Any | None, key: str, expert_id: str) -> dict[str, Any] | None:
        if event is None:
            return None
        payload = _artifact_field(event, "payload", {})
        records = _router_payload_records(payload, key)
        for record in records:
            if str(record.get("expert_id", "")).strip() == expert_id:
                return record
        ids_key = {
            "selected_experts": "selected_expert_ids",
            "rejected_experts": "rejected_expert_ids",
        }.get(key, "")
        if ids_key and expert_id in _string_values(_artifact_field(payload, ids_key, [])):
            fallback_reason = ""
            reason_codes = _string_values(_artifact_field(payload, "reason_codes", []))
            if len(reason_codes) == 1:
                fallback_reason = reason_codes[0]
            return {
                "decision": "selected" if key == "selected_experts" else "rejected",
                "expert_id": expert_id,
                "proposal_id": "",
                "reason": fallback_reason,
            }
        return None

    def _router_record_ids(self, event: Any | None, key: str) -> tuple[str, ...]:
        if event is None:
            return ()
        payload = _artifact_field(event, "payload", {})
        ids_key = {
            "selected_expert_ids": "selected_expert_ids",
            "rejected_expert_ids": "rejected_expert_ids",
        }.get(key, key)
        return _dedupe_sorted_stable(_string_values(_artifact_field(payload, ids_key, [])))

    def _router_event_summary(self, event: Any | None) -> dict[str, Any]:
        if event is None:
            return {}
        payload = _artifact_field(event, "payload", {})
        return {
            "event_id": self._event_identifier(event),
            "event_type": _artifact_field(event, "event_type", ""),
            "correlation_id": _artifact_field(event, "correlation_id", ""),
            "logical_tick": _artifact_field(event, "logical_tick", 0),
            "payload": _to_mapping(payload),
        }

    def _router_event_summaries(self, events: Sequence[Any | None]) -> list[dict[str, Any]]:
        return [summary for summary in (self._router_event_summary(event) for event in events) if summary]

    def _event_ids_for_router_events(self, events: Sequence[Any | None]) -> tuple[str, ...]:
        event_ids: list[str] = []
        for event in events:
            if event is None:
                continue
            event_ids.append(self._event_identifier(event))
        return _dedupe_sorted_stable(event_ids)

    def _router_report_id(self, event: Any | None) -> str:
        if event is None:
            return ""
        payload = _artifact_field(event, "payload", {})
        report_id = str(_artifact_field(payload, "report_id", "")).strip()
        if report_id:
            return report_id
        return _artifact_field(event, "correlation_id", "")

    def _router_fixture_file_from_routing_id(self, routing_id: str) -> str:
        parts = routing_id.split(":")
        if len(parts) == 3 and parts[0] == "routing" and parts[2] == "v1" and parts[1].strip():
            return f"{parts[1].strip()}_routing.json"
        return ""

    def _graph_nodes(self) -> list[Any]:
        graph = self._graph()
        if graph is None:
            return []
        if hasattr(graph, "topological_order") and callable(getattr(graph, "topological_order")):
            try:
                nodes = list(graph.topological_order())
            except Exception:
                nodes = []
            if nodes:
                return nodes
        nodes = _artifact_field(graph, "nodes", None)
        if nodes is None:
            return []
        try:
            if isinstance(nodes, Mapping):
                return list(nodes.values())
            return list(nodes)
        except TypeError:
            return []

    def _graph_edges(self) -> list[Any]:
        graph = self._graph()
        if graph is None:
            return []
        edges = _artifact_field(graph, "edges", None)
        if edges is None:
            return []
        try:
            if isinstance(edges, Mapping):
                return list(edges.values())
            return list(edges)
        except TypeError:
            return []

    def _graph_lineage(self, node_ids: Sequence[str]) -> tuple[str, ...]:
        graph = self._graph()
        if graph is None or not node_ids:
            return ()
        node_map = {_artifact_field(node, "node_id", ""): node for node in self._graph_nodes()}
        reverse: dict[str, list[str]] = {}
        for edge in self._graph_edges():
            reverse.setdefault(_artifact_field(edge, "target_id", ""), []).append(_artifact_field(edge, "source_id", ""))
        visited: set[str] = set()
        frontier = list(node_ids)
        lineage: list[str] = []
        while frontier:
            current = frontier.pop(0)
            for parent_id in sorted(reverse.get(current, [])):
                if parent_id and parent_id not in visited:
                    visited.add(parent_id)
                    lineage.append(parent_id)
                    frontier.append(parent_id)
        ordered_nodes = canonical_graph_nodes([node_map[nid] for nid in lineage if nid in node_map])
        return tuple(_artifact_field(node, "node_id", "") for node in ordered_nodes if _artifact_field(node, "node_id", ""))

    def _graph_nodes_matching(self, target_id: str, *, node_type: str | None = None) -> tuple[str, ...]:
        return self._graph_nodes_matching_any((target_id,), node_type=node_type)

    def _graph_nodes_matching_any(
        self,
        target_ids: Sequence[str],
        *,
        node_type: str | None = None,
    ) -> tuple[str, ...]:
        hits: list[str] = []
        target_set = {target_id for target_id in target_ids if isinstance(target_id, str) and target_id.strip()}
        if not target_set:
            return ()
        for node in self._graph_nodes():
            if node_type is not None and _artifact_field(node, "node_type", "") != node_type:
                continue
            candidates = {
                _artifact_field(node, "node_id", ""),
                _artifact_field(node, "node_type", ""),
                _artifact_field(node, "fingerprint", ""),
                str(_artifact_field(node, "origin_event_seq", "")),
                str(_artifact_field(node, "logical_order", "")),
            }
            candidates.update(_string_values(_artifact_field(node, "event_ids", [])))
            candidates.update(_string_values(_artifact_field(node, "fact_ids", [])))
            candidates.update(_string_values(_artifact_field(node, "projection_ids", [])))
            candidates.update(_string_values(_artifact_field(node, "constraint_ids", [])))
            if target_set.intersection(candidates) or _contains_any_target(_artifact_field(node, "payload", {}), tuple(target_set)):
                hits.append(_artifact_field(node, "node_id", ""))
        return _sorted_unique(hits)

    def _event_entries(self) -> list[Any]:
        log = self._event_log()
        if log is None:
            return []
        if hasattr(log, "all") and callable(getattr(log, "all")):
            try:
                return list(log.all())
            except Exception:
                return []
        docs = _artifact_documents(log)
        for doc in docs:
            if isinstance(doc, Mapping) and "events" in doc:
                events = doc.get("events", [])
                try:
                    if isinstance(events, Mapping):
                        return list(events.values())
                    return list(events)
                except TypeError:
                    return []
        return []

    def _event_ids(self, target_id: str) -> tuple[str, ...]:
        hits: list[str] = []
        for event in self._event_entries():
            candidates = {
                _artifact_field(event, "event_id", ""),
                str(_artifact_field(event, "seq", "")),
                _artifact_field(event, "event_type", ""),
                _artifact_field(event, "task_id", ""),
                _artifact_field(event, "domain_name", ""),
                _artifact_field(event, "fingerprint", lambda: "")() if callable(_artifact_field(event, "fingerprint", None)) else "",
            }
            if target_id in candidates or _contains_target(_artifact_field(event, "payload", {}), target_id):
                hits.append(self._event_identifier(event))
        return _sorted_unique(hits)

    def _event_identifier(self, event: Any) -> str:
        event_id = _artifact_field(event, "event_id", None)
        if event_id:
            return str(event_id)
        fingerprint = _artifact_field(event, "fingerprint", None)
        if callable(fingerprint):
            try:
                return str(fingerprint())
            except Exception:
                pass
        seq = _artifact_field(event, "seq", None)
        if seq is not None:
            return f"seq:{seq}"
        return str(_artifact_field(event, "event_type", "event"))

    def _event_neighborhood(self, target_id: str, event_ids: Sequence[str]) -> tuple[str, ...]:
        events = self._event_entries()
        if not events:
            return ()
        indexed = list(enumerate(events))
        matched_indices: list[int] = []
        for index, event in indexed:
            candidates = {
                _artifact_field(event, "event_id", ""),
                str(_artifact_field(event, "seq", "")),
                _artifact_field(event, "event_type", ""),
                _artifact_field(event, "task_id", ""),
                _artifact_field(event, "domain_name", ""),
                self._event_identifier(event),
            }
            if target_id in candidates or _contains_target(_artifact_field(event, "payload", {}), target_id):
                matched_indices.append(index)
        if not matched_indices:
            return ()
        neighbors: list[str] = []
        for index in matched_indices:
            for neighbor_index in (index - 1, index + 1):
                if 0 <= neighbor_index < len(events):
                    neighbors.append(self._event_identifier(events[neighbor_index]))
        return _sorted_unique(neighbors)

    def _facts(self) -> list[Any]:
        kb = self._knowledge_base()
        if kb is None:
            return []
        if hasattr(kb, "all_facts") and callable(getattr(kb, "all_facts")):
            try:
                return list(kb.all_facts())
            except Exception:
                return []
        if hasattr(kb, "query_relations") and callable(getattr(kb, "query_relations")):
            try:
                return list(kb.query_relations())
            except Exception:
                return []
        docs = _artifact_documents(kb)
        for doc in docs:
            if isinstance(doc, Mapping) and "facts" in doc:
                facts = doc.get("facts", [])
                try:
                    if isinstance(facts, Mapping):
                        return list(facts.values())
                    return list(facts)
                except TypeError:
                    return []
        return []

    def _fact_ids(self, target_id: str) -> tuple[str, ...]:
        hits: list[str] = []
        for fact in self._facts():
            candidates = {
                _artifact_field(fact, "fact_id", ""),
                _artifact_field(fact, "fact_hash", ""),
                _artifact_field(fact, "transaction_id", ""),
                _artifact_field(fact, "event_log_fingerprint", ""),
                _artifact_field(fact, "schema_version", ""),
                _artifact_field(fact, "fingerprint", lambda: "")() if callable(_artifact_field(fact, "fingerprint", None)) else "",
            }
            if target_id in candidates or _contains_target(_artifact_field(fact, "metadata", {}), target_id):
                hits.append(_artifact_field(fact, "fact_id", ""))
        return _sorted_unique(hits)

    def _fact_graph_nodes(self, target_id: str, fact_ids: Sequence[str]) -> tuple[str, ...]:
        hits: list[str] = []
        hits.extend(self._graph_nodes_matching(target_id))
        if fact_ids:
            hits.extend(self._graph_nodes_matching_any(fact_ids))
        return _sorted_unique(hits)

    def _fact_metadata(self, target_id: str) -> list[Any]:
        matches = []
        for fact in self._facts():
            candidates = {
                _artifact_field(fact, "fact_id", ""),
                _artifact_field(fact, "fact_hash", ""),
            }
            if target_id in candidates or _contains_target(_artifact_field(fact, "metadata", {}), target_id):
                matches.append(fact)
        return matches

    def _fact_projection_ids(self, target_id: str, fact_ids: Sequence[str]) -> tuple[str, ...]:
        projection_ids: list[str] = []
        for fact in self._fact_metadata(target_id):
            projection_ids.extend(_projection_ids_from_metadata(_artifact_field(fact, "metadata", {})))
        return _sorted_unique(projection_ids)

    def _parent_fact_ids(self, target_id: str, fact_ids: Sequence[str]) -> tuple[str, ...]:
        parent_ids: list[str] = []
        for fact in self._fact_metadata(target_id):
            parent_ids.extend(_parent_fact_ids_from_metadata(_artifact_field(fact, "metadata", {})))
        return _sorted_unique(parent_ids or list(fact_ids))

    def _fact_event_ids(self, target_id: str, fact_ids: Sequence[str]) -> tuple[str, ...]:
        event_ids: list[str] = []
        for fact in self._fact_metadata(target_id):
            event_ids.extend(_event_ids_from_metadata(_artifact_field(fact, "metadata", {})))
            event_ids.extend(_event_ids_from_metadata({"event_log_fingerprint": _artifact_field(fact, "event_log_fingerprint", "")}))
        return _sorted_unique(event_ids)

    def _projection_ids(self, target_id: str) -> tuple[str, ...]:
        hits: list[str] = []
        hits.extend(self._projection_graph_nodes(target_id))
        for fact in self._fact_metadata(target_id):
            hits.extend(_projection_ids_from_metadata(_artifact_field(fact, "metadata", {})))
        for event in self._event_entries():
            if _artifact_field(event, "event_type", "") == "ProjectionCommitted" and (
                target_id in {
                    _artifact_field(event, "event_id", ""),
                    str(_artifact_field(event, "seq", "")),
                    self._event_identifier(event),
                    _artifact_field(event, "task_id", ""),
                }
                or _contains_target(_artifact_field(event, "payload", {}), target_id)
            ):
                hits.extend(_projection_ids_from_metadata(_artifact_field(event, "payload", {})))
                hits.append(self._event_identifier(event))
        return _sorted_unique(hits)

    def _projection_graph_nodes(self, target_id: str) -> tuple[str, ...]:
        return self._graph_nodes_matching(target_id, node_type="ProjectionCommitted")

    def _projection_event_ids(self, target_id: str, projection_ids: Sequence[str]) -> tuple[str, ...]:
        hits: list[str] = []
        for event in self._event_entries():
            if _artifact_field(event, "event_type", "") != "ProjectionCommitted":
                continue
            payload = _artifact_field(event, "payload", {})
            candidates = {
                _artifact_field(event, "event_id", ""),
                str(_artifact_field(event, "seq", "")),
                self._event_identifier(event),
                _artifact_field(event, "task_id", ""),
            }
            if target_id in candidates or _contains_target(payload, target_id) or any(projection_id in _string_values(payload) for projection_id in projection_ids):
                hits.append(self._event_identifier(event))
        return _sorted_unique(hits)

    def _projection_fact_ids(self, target_id: str, projection_ids: Sequence[str]) -> tuple[str, ...]:
        hits: list[str] = []
        for fact in self._facts():
            metadata = _artifact_field(fact, "metadata", {})
            if target_id in {
                _artifact_field(fact, "fact_id", ""),
                _artifact_field(fact, "fact_hash", ""),
            } or any(projection_id in _string_values(metadata) for projection_id in projection_ids):
                hits.append(_artifact_field(fact, "fact_id", ""))
        return _sorted_unique(hits)

    def _constraint_ids(self, graph_node_ids: Sequence[str]) -> tuple[str, ...]:
        hits: list[str] = []
        graph = self._graph()
        if graph is None or not hasattr(graph, "node_by_id"):
            return ()
        for node_id in graph_node_ids:
            node = graph.node_by_id(node_id)
            if node is None:
                continue
            if _artifact_field(node, "node_type", "") == "ConstraintVerified":
                hits.append(_artifact_field(node, "node_id", ""))
        return _sorted_unique(hits)

    def _event_graph_nodes(self, target_id: str, event_ids: Sequence[str]) -> tuple[str, ...]:
        hits: list[str] = []
        event_seq_ids = {self._event_sequence_from_id(event_id) for event_id in event_ids if self._event_sequence_from_id(event_id) is not None}
        for node in self._graph_nodes():
            if _artifact_field(node, "origin_event_seq", None) in event_seq_ids:
                hits.append(_artifact_field(node, "node_id", ""))
            elif target_id in {
                _artifact_field(node, "event_id", ""),
                _artifact_field(node, "node_id", ""),
                _artifact_field(node, "fingerprint", ""),
                _artifact_field(node, "node_type", ""),
            } or target_id in _string_values(_artifact_field(node, "event_ids", [])) or target_id in _string_values(_artifact_field(node, "fact_ids", [])) or _contains_target(_artifact_field(node, "payload", {}), target_id):
                hits.append(_artifact_field(node, "node_id", ""))
        return _sorted_unique(hits)

    def _event_sequence_from_id(self, event_id: str) -> int | None:
        if event_id.startswith("seq:"):
            try:
                return int(event_id.split(":", 1)[1])
            except ValueError:
                return None
        for event in self._event_entries():
            if self._event_identifier(event) == event_id:
                seq = _artifact_field(event, "seq", None)
                return int(seq) if seq is not None else None
        return None

    def _event_fact_ids(self, target_id: str, event_ids: Sequence[str]) -> tuple[str, ...]:
        hits: list[str] = []
        event_sequences = {self._event_sequence_from_id(event_id) for event_id in event_ids if self._event_sequence_from_id(event_id) is not None}
        for fact in self._facts():
            metadata = _artifact_field(fact, "metadata", {})
            if target_id in {
                _artifact_field(fact, "fact_id", ""),
                _artifact_field(fact, "fact_hash", ""),
            } or _contains_target(metadata, target_id):
                hits.append(_artifact_field(fact, "fact_id", ""))
            elif event_sequences:
                source_event_ids = _event_ids_from_metadata(metadata)
                if any(str(seq) in source_event_ids for seq in event_sequences):
                    hits.append(_artifact_field(fact, "fact_id", ""))
        return _sorted_unique(hits)

    def _event_projection_ids(self, target_id: str, event_ids: Sequence[str]) -> tuple[str, ...]:
        hits: list[str] = []
        event_sequences = {self._event_sequence_from_id(event_id) for event_id in event_ids if self._event_sequence_from_id(event_id) is not None}
        for event in self._event_entries():
            seq = _artifact_field(event, "seq", None)
            if seq not in event_sequences and self._event_identifier(event) not in event_ids and target_id not in {
                _artifact_field(event, "event_id", ""),
                _artifact_field(event, "event_type", ""),
                _artifact_field(event, "task_id", ""),
            } and not _contains_target(_artifact_field(event, "payload", {}), target_id):
                continue
            if _artifact_field(event, "event_type", "") == "ProjectionCommitted":
                hits.extend(_projection_ids_from_metadata(_artifact_field(event, "payload", {})))
                hits.append(self._event_identifier(event))
        return _sorted_unique(hits)

    def _origin_projection_ids(self, target_id: str) -> tuple[str, ...]:
        hits: list[str] = []
        hits.extend(self._projection_graph_nodes(target_id))
        for fact in self._fact_metadata(target_id):
            hits.extend(_projection_ids_from_metadata(_artifact_field(fact, "metadata", {})))
        for event in self._event_entries():
            if _artifact_field(event, "event_type", "") == "ProjectionCommitted" and (
                target_id in {
                    _artifact_field(event, "event_id", ""),
                    str(_artifact_field(event, "seq", "")),
                    self._event_identifier(event),
                    _artifact_field(event, "task_id", ""),
                }
                or _contains_target(_artifact_field(event, "payload", {}), target_id)
            ):
                hits.extend(_projection_ids_from_metadata(_artifact_field(event, "payload", {})))
                hits.append(self._event_identifier(event))
        return _sorted_unique(hits)

    def _origin_projection_graph_nodes(self, target_id: str, projection_ids: Sequence[str]) -> tuple[str, ...]:
        hits: list[str] = []
        hits.extend(self._projection_graph_nodes(target_id))
        if projection_ids:
            hits.extend(self._graph_nodes_matching_any(projection_ids, node_type="ProjectionCommitted"))
            hits.extend(self._graph_nodes_matching_any(projection_ids))
        return _sorted_unique(hits)

    def _origin_projection_event_ids(self, target_id: str, projection_ids: Sequence[str]) -> tuple[str, ...]:
        hits: list[str] = []
        for event in self._event_entries():
            if _artifact_field(event, "event_type", "") == "ProjectionCommitted":
                payload = _artifact_field(event, "payload", {})
                if target_id in {
                    _artifact_field(event, "event_id", ""),
                    str(_artifact_field(event, "seq", "")),
                    self._event_identifier(event),
                    _artifact_field(event, "task_id", ""),
                } or _contains_target(payload, target_id) or any(projection_id in _string_values(payload) for projection_id in projection_ids):
                    hits.append(self._event_identifier(event))
        return _sorted_unique(hits)

    def _origin_projection_fact_ids(self, target_id: str, projection_ids: Sequence[str]) -> tuple[str, ...]:
        hits: list[str] = []
        for fact in self._facts():
            metadata = _artifact_field(fact, "metadata", {})
            if target_id in {
                _artifact_field(fact, "fact_id", ""),
                _artifact_field(fact, "fact_hash", ""),
            } or any(projection_id in _string_values(metadata) for projection_id in projection_ids):
                hits.append(_artifact_field(fact, "fact_id", ""))
        return _sorted_unique(hits)


def _projection_ids_from_metadata(metadata: Any) -> list[str]:
    projection_ids: list[str] = []
    if isinstance(metadata, Mapping):
        for key in ("projection_id", "projection_ids", "projection_hash", "origin_projection_id", "source_projection_id"):
            if key in metadata:
                projection_ids.extend(_string_values(metadata[key]))
    elif isinstance(metadata, Sequence) and not isinstance(metadata, (bytes, bytearray, str)):
        projection_ids.extend(_string_values(metadata))
    elif isinstance(metadata, str):
        projection_ids.append(metadata)
    return projection_ids


def _parent_fact_ids_from_metadata(metadata: Any) -> list[str]:
    parent_ids: list[str] = []
    if isinstance(metadata, Mapping):
        for key in ("parent_fact_id", "parent_fact_ids", "source_fact_id", "source_fact_ids", "upstream_fact_ids"):
            if key in metadata:
                parent_ids.extend(_string_values(metadata[key]))
    elif isinstance(metadata, Sequence) and not isinstance(metadata, (bytes, bytearray, str)):
        parent_ids.extend(_string_values(metadata))
    return parent_ids


def _event_ids_from_metadata(metadata: Any) -> list[str]:
    event_ids: list[str] = []
    if isinstance(metadata, Mapping):
        for key in ("event_id", "event_ids", "source_event_id", "source_event_ids", "origin_event_id", "origin_event_ids"):
            if key in metadata:
                event_ids.extend(_string_values(metadata[key]))
    elif isinstance(metadata, Sequence) and not isinstance(metadata, (bytes, bytearray, str)):
        event_ids.extend(_string_values(metadata))
    return event_ids


__all__ = [
    "ExplanationStatus",
    "ExplainabilityWarning",
    "ExplanationResult",
    "StaticExplainer",
]
