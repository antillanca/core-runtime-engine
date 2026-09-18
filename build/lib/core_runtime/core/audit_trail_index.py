"""Immutable in-memory index for derived audit trails."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from core_runtime.core.audit_event import (
    AuditEvent,
    compute_audit_fingerprint,
    canonical_event_sort_key,
)


def _freeze_event_group_map(groups: dict[Any, tuple[AuditEvent, ...]]) -> Mapping[Any, tuple[AuditEvent, ...]]:
    return MappingProxyType(dict(sorted(groups.items(), key=lambda item: str(item[0]))))


@dataclass(frozen=True)
class AuditTrailIndex:
    events: tuple[AuditEvent, ...] = field(default_factory=tuple)
    by_id: Mapping[str, AuditEvent] = field(default_factory=dict)
    by_correlation: Mapping[str, tuple[AuditEvent, ...]] = field(default_factory=dict)
    by_type: Mapping[str, tuple[AuditEvent, ...]] = field(default_factory=dict)
    by_tick: Mapping[int, tuple[AuditEvent, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        events = tuple(sorted(self.events, key=canonical_event_sort_key))

        by_id: dict[str, AuditEvent] = {}
        by_correlation: dict[str, list[AuditEvent]] = {}
        by_type: dict[str, list[AuditEvent]] = {}
        by_tick: dict[int, list[AuditEvent]] = {}

        for event in events:
            if event.event_id in by_id:
                raise ValueError(f"Duplicate audit event_id detected: {event.event_id}")
            by_id[event.event_id] = event
            by_correlation.setdefault(event.correlation_id, []).append(event)
            by_type.setdefault(event.event_type, []).append(event)
            by_tick.setdefault(event.logical_tick, []).append(event)

        object.__setattr__(self, "events", events)
        object.__setattr__(self, "by_id", MappingProxyType(by_id))
        object.__setattr__(self, "by_correlation", _freeze_event_group_map({
            key: tuple(sorted(value, key=canonical_event_sort_key))
            for key, value in by_correlation.items()
        }))
        object.__setattr__(self, "by_type", _freeze_event_group_map({
            key: tuple(sorted(value, key=canonical_event_sort_key))
            for key, value in by_type.items()
        }))
        object.__setattr__(self, "by_tick", MappingProxyType({
            key: tuple(sorted(value, key=canonical_event_sort_key))
            for key, value in sorted(by_tick.items(), key=lambda item: item[0])
        }))

    @classmethod
    def from_events(cls, events: Iterable[AuditEvent]) -> "AuditTrailIndex":
        return cls(events=tuple(events))

    def lookup_event(self, event_id: str) -> AuditEvent | None:
        return self.by_id.get(event_id)

    def lookup_correlation(self, correlation_id: str) -> tuple[AuditEvent, ...]:
        return self.by_correlation.get(correlation_id, ())

    def lookup_type(self, event_type: str) -> tuple[AuditEvent, ...]:
        return self.by_type.get(event_type, ())

    def lookup_tick(self, logical_tick: int) -> tuple[AuditEvent, ...]:
        return self.by_tick.get(logical_tick, ())

    def to_dict(self) -> dict[str, Any]:
        return {
            "events": [event.to_dict() for event in self.events],
            "by_id": {event_id: event.to_dict() for event_id, event in self.by_id.items()},
            "by_correlation": {
                correlation_id: [event.to_dict() for event in events]
                for correlation_id, events in self.by_correlation.items()
            },
            "by_type": {
                event_type: [event.to_dict() for event in events]
                for event_type, events in self.by_type.items()
            },
            "by_tick": {
                str(logical_tick): [event.to_dict() for event in events]
                for logical_tick, events in self.by_tick.items()
            },
            "fingerprint": self.fingerprint(),
        }

    def fingerprint(self) -> str:
        return compute_audit_fingerprint(
            {
                "events": [event.to_dict() for event in self.events],
                "schema_version": "4.9.0",
            }
        )
