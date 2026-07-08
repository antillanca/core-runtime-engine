from __future__ import annotations

import pytest

from core_runtime.core.audit_event import AuditEvent, EventAuthority
from core_runtime.core.audit_trail_index import AuditTrailIndex


def test_audit_event_is_deterministic():
    payload = {
        "decision": "accepted",
        "details": {"confidence": 0.123456789},
        "pair_id": "accepted_standard",
    }

    event_a = AuditEvent(
        event_id="",
        event_type="CompatibilityAccepted",
        authority=EventAuthority.DERIVED,
        logical_tick=7,
        correlation_id="pair::accepted_standard",
        payload=payload,
    )
    event_b = AuditEvent(
        event_id="",
        event_type="CompatibilityAccepted",
        authority=EventAuthority.DERIVED,
        logical_tick=7,
        correlation_id="pair::accepted_standard",
        payload=payload,
    )

    assert event_a.event_id == event_b.event_id
    assert event_a.fingerprint == event_b.fingerprint
    assert event_a.to_dict() == event_b.to_dict()
    assert event_a.to_dict()["schema_version"] == "4.9.0"
    assert event_a.to_dict()["payload"]["details"]["confidence"] == 0.12345679


def test_audit_event_requires_semantic_correlation_namespace():
    with pytest.raises(ValueError):
        AuditEvent(
            event_id="",
            event_type="CompatibilityAccepted",
            authority=EventAuthority.DERIVED,
            logical_tick=0,
            correlation_id="accepted_standard",
            payload={},
        )


def test_audit_trail_index_groups_events():
    events = [
        AuditEvent(
            event_id="",
            event_type="CompatibilityChecked",
            authority=EventAuthority.DERIVED,
            logical_tick=0,
            correlation_id="pair::accepted_standard",
            payload={"pair_id": "accepted_standard"},
        ),
        AuditEvent(
            event_id="",
            event_type="CompatibilityAccepted",
            authority=EventAuthority.DERIVED,
            logical_tick=1,
            correlation_id="pair::accepted_standard",
            payload={"pair_id": "accepted_standard"},
        ),
    ]

    index = AuditTrailIndex.from_events(events)
    fingerprint = index.fingerprint()

    assert index.lookup_event(events[0].event_id) == events[0]
    assert index.lookup_correlation("pair::accepted_standard") == tuple(events)
    assert index.lookup_type("CompatibilityAccepted") == (events[1],)
    assert index.lookup_tick(1) == (events[1],)
    assert fingerprint == index.fingerprint()
