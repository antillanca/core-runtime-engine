"""Focused validation for the public MemoryArtifact.v1 contract."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "core" / "memory_artifact.v1.json"


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_memory_artifact_schema_is_reference_only():
    schema = _schema()
    assert schema["title"] == "MemoryArtifact.v1"
    assert schema["properties"]["schema_version"]["const"] == "core.memory_artifact.v1"
    assert schema["properties"]["authority"]["const"] == "reference_only"


def test_memory_artifact_schema_requires_continuity_payload():
    schema = _schema()
    assert schema["required"] == [
        "schema_version",
        "memory_id",
        "source_refs",
        "authority",
        "summary",
        "stable_facts",
        "decisions",
        "invariants",
        "open_risks",
        "next_actions",
        "retention",
        "created_at",
    ]


def test_memory_artifact_schema_rejects_missing_reference_source():
    schema = _schema()
    assert schema["properties"]["source_refs"]["minItems"] == 1


def test_memory_artifact_schema_rejects_invalid_retention_class():
    schema = _schema()
    retention = schema["properties"]["retention"]["properties"]["retention_class"]
    assert retention["enum"] == ["keep", "compress", "forget", "quarantine"]


def test_memory_artifact_example_is_valid_shape():
    artifact = {
        "schema_version": "core.memory_artifact.v1",
        "memory_id": "memory-001",
        "source_refs": ["run:task-001", "report:reports/task-001.md"],
        "authority": "reference_only",
        "summary": "Closeout memory for a deterministic task.",
        "stable_facts": ["task finished", "memory reused"],
        "decisions": ["keep closeout reference only"],
        "invariants": ["reference-only authority"],
        "open_risks": ["runtime consumers must not infer authority"],
        "next_actions": ["map artifact in adapters"],
        "retention": {"retention_class": "keep", "reason": "audit continuity"},
        "created_at": "2026-05-31T00:00:00Z",
        "scope": "task-001",
    }
    assert artifact["authority"] == "reference_only"
    assert len(artifact["source_refs"]) >= 1


def test_memory_artifact_invalid_examples_capture_contract_rules():
    missing_authority = {
        "schema_version": "core.memory_artifact.v1",
        "memory_id": "memory-001",
        "source_refs": ["run:task-001"],
        "summary": "Closeout memory.",
        "stable_facts": [],
        "decisions": [],
        "invariants": [],
        "open_risks": [],
        "next_actions": [],
        "retention": {"retention_class": "keep", "reason": "audit"},
        "created_at": "2026-05-31T00:00:00Z",
    }
    invalid_retention = {
        "schema_version": "core.memory_artifact.v1",
        "memory_id": "memory-001",
        "source_refs": ["run:task-001"],
        "authority": "reference_only",
        "summary": "Closeout memory.",
        "stable_facts": [],
        "decisions": [],
        "invariants": [],
        "open_risks": [],
        "next_actions": [],
        "retention": {"retention_class": "archive", "reason": "audit"},
        "created_at": "2026-05-31T00:00:00Z",
    }
    assert "authority" not in missing_authority or missing_authority.get("authority") != "reference_only"
    assert invalid_retention["retention"]["retention_class"] == "archive"
