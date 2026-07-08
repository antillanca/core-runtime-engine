from __future__ import annotations

from core_runtime.core.schema_fingerprint import audit_fingerprint


def _vector() -> dict:
    return {
        "schema_version": "core.schema_fingerprint.v1",
        "type": "fingerprint_vector",
        "meta": {
            "scope": "cross_repo",
            "version": 1,
            "tags": ["alpha", "beta"],
        },
        "payload": {
            "zeta": 9,
            "alpha": {
                "beta": 2,
                "gamma": {
                    "delta": 4,
                    "epsilon": 5,
                },
            },
            "list": [
                {"b": 2, "a": 1},
                {"y": 25, "x": 24},
            ],
        },
    }


def test_audit_fingerprint_is_stable_for_nested_payloads() -> None:
    payload_a = _vector()
    payload_b = {
        "meta": {
            "tags": ["alpha", "beta"],
            "version": 1,
            "scope": "cross_repo",
        },
        "payload": {
            "alpha": {
                "gamma": {
                    "epsilon": 5,
                    "delta": 4,
                },
                "beta": 2,
            },
            "list": [
                {"a": 1, "b": 2},
                {"x": 24, "y": 25},
            ],
            "zeta": 9,
        },
        "type": "fingerprint_vector",
        "schema_version": "core.schema_fingerprint.v1",
    }

    expected = "55219c1b9da9368318c831d3e566390a7e104e929a9e7e4a0770cbdcc3fcf1d3"

    assert audit_fingerprint(payload_a) == expected
    assert audit_fingerprint(payload_b) == expected


def test_audit_fingerprint_changes_when_payload_changes() -> None:
    payload = _vector()
    altered = _vector()
    altered["payload"]["alpha"]["beta"] = 3

    assert audit_fingerprint(payload) != audit_fingerprint(altered)
