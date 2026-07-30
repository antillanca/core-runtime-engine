"""Tests for the public CORE v10 generic contract layer."""

from __future__ import annotations

import json
from pathlib import Path

from core_runtime.core import available_contracts, contract_schema_path, load_contract_schema


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas" / "core"


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _assert_schema(schema: dict, *, title: str, schema_version: str, required: list[str]) -> None:
    assert schema["$schema"].startswith("https://json-schema.org/")
    assert schema["title"] == title
    assert schema["type"] == "object"
    assert schema["properties"]["schema_version"]["const"] == schema_version
    assert schema["required"] == required


def test_available_contracts_are_stable():
    assert available_contracts() == (
        "causal_trace.v1",
        "context_gate.v1",
        "context_threshold.v1",
        "contract_program.v1",
        "control_decision.v1",
        "effect_result.v1",
        "entropy_signal.v1",
        "execution_receipt.v1",
        "memory_artifact.v1",
        "memory_generation_result.v1",
        "operational_learning_event.v1",
        "pattern_candidate.v1",
        "physical_safety_assurance_case.v1",
        "policy_lifecycle.v1",
        "retention_manifest.v1",
        "reversibility_policy.v1",
        "state_transition.v1",
        "task_closeout.v1",
        "template_promotion_candidate.v1",
    )


def test_contract_schema_paths_resolve_into_public_schema_tree():
    assert contract_schema_path("memory_artifact.v1") == SCHEMA_DIR / "memory_artifact.v1.json"
    assert contract_schema_path("pattern_candidate.v1") == SCHEMA_DIR / "pattern_candidate.v1.json"
    assert contract_schema_path("template_promotion_candidate.v1") == SCHEMA_DIR / "template_promotion_candidate.v1.json"
    assert contract_schema_path("causal_trace.v1") == SCHEMA_DIR / "causal_trace.v1.json"
    assert contract_schema_path("contract_program.v1") == SCHEMA_DIR / "contract_program.v1.json"
    assert contract_schema_path("entropy_signal.v1") == SCHEMA_DIR / "entropy_signal.v1.json"
    assert contract_schema_path("control_decision.v1") == SCHEMA_DIR / "control_decision.v1.json"
    assert contract_schema_path("execution_receipt.v1") == SCHEMA_DIR / "execution_receipt.v1.json"
    assert contract_schema_path("policy_lifecycle.v1") == SCHEMA_DIR / "policy_lifecycle.v1.json"
    assert contract_schema_path("reversibility_policy.v1") == SCHEMA_DIR / "reversibility_policy.v1.json"
    assert contract_schema_path("state_transition.v1") == SCHEMA_DIR / "state_transition.v1.json"
    assert contract_schema_path("task_closeout.v1") == SCHEMA_DIR / "task_closeout.v1.json"
    assert contract_schema_path("effect_result.v1") == SCHEMA_DIR / "effect_result.v1.json"


def test_contract_loader_reads_generic_schema_objects():
    schema = load_contract_schema("context_gate.v1")
    assert schema["title"] == "ContextGate.v1"
    assert schema["properties"]["mode"]["enum"] == ["dry-run", "apply"]


def test_contract_program_schema_is_closed_and_validation_only():
    schema = _load_schema("contract_program.v1")
    _assert_schema(
        schema,
        title="ContractProgram.v1",
        schema_version="core.contract_program.v1",
        required=[
            "schema_version",
            "type",
            "program_id",
            "program_version",
            "authority",
            "effect_policy",
            "capabilities",
            "limits",
            "instructions",
            "source_refs",
            "declared_loss",
            "fingerprint",
        ],
    )
    assert schema["additionalProperties"] is False
    assert schema["properties"]["authority"]["const"] == "validation_only"
    assert schema["properties"]["effect_policy"]["additionalProperties"] is False


def test_memory_artifact_schema_has_reference_only_authority():
    schema = _load_schema("memory_artifact.v1")
    _assert_schema(
        schema,
        title="MemoryArtifact.v1",
        schema_version="core.memory_artifact.v1",
        required=[
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
        ],
    )
    assert schema["properties"]["authority"]["const"] == "reference_only"
    assert schema["properties"]["source_refs"]["minItems"] == 1
    assert schema["properties"]["retention"]["properties"]["retention_class"]["enum"] == [
        "keep",
        "compress",
        "forget",
        "quarantine",
    ]


def test_task_closeout_schema_is_generic():
    schema = _load_schema("task_closeout.v1")
    _assert_schema(
        schema,
        title="TaskCloseout.v1",
        schema_version="core.task_closeout.v1",
        required=["schema_version", "status", "source_type", "source_id", "summary"],
    )
    assert "report_ref" in schema["properties"]
    assert "next_context_action" in schema["properties"]


def test_effect_result_schema_is_generic():
    schema = _load_schema("effect_result.v1")
    _assert_schema(
        schema,
        title="EffectResult.v1",
        schema_version="core.effect_result.v1",
        required=["schema_version", "status", "effect_type", "dry_run", "reason"],
    )
    assert schema["properties"]["status"]["enum"] == ["dry_run", "sent", "skipped", "applied", "failed"]


def test_memory_generation_result_schema_is_generic():
    schema = _load_schema("memory_generation_result.v1")
    _assert_schema(
        schema,
        title="MemoryGenerationResult.v1",
        schema_version="core.memory_generation_result.v1",
        required=["schema_version", "status", "source_type", "source_id", "reused"],
    )
    assert "memory_id" in schema["properties"]


def test_context_threshold_schema_is_generic():
    schema = _load_schema("context_threshold.v1")
    _assert_schema(
        schema,
        title="ContextThreshold.v1",
        schema_version="core.context_threshold.v1",
        required=["schema_version", "status", "source_type", "source_id", "should_compress_now", "reason"],
    )
    assert "recommended_action" in schema["properties"]


def test_context_gate_schema_is_generic():
    schema = _load_schema("context_gate.v1")
    _assert_schema(
        schema,
        title="ContextGate.v1",
        schema_version="core.context_gate.v1",
        required=["schema_version", "status", "source_type", "source_id", "mode", "reason"],
    )
    assert schema["properties"]["mode"]["enum"] == ["dry-run", "apply"]


def test_retention_manifest_schema_is_generic():
    schema = _load_schema("retention_manifest.v1")
    _assert_schema(
        schema,
        title="RetentionManifest.v1",
        schema_version="core.retention_manifest.v1",
        required=["schema_version", "entries"],
    )
    entry_schema = schema["properties"]["entries"]["items"]
    assert entry_schema["required"] == ["source_type", "source_id", "artifact_ref", "retention_class", "reason"]
    assert entry_schema["properties"]["retention_class"]["enum"] == ["keep", "compress", "forget", "quarantine"]


def test_normalized_examples_still_fit_generic_contract_shape():
    task_closeout = {
        "schema_version": "core.task_closeout.v1",
        "status": "passed",
        "source_type": "task",
        "source_id": "task-001",
        "summary": "Task finished with dry-run effect and reusable memory.",
        "report_ref": "reports/task-001.md",
        "next_context_action": "none",
    }
    effect_result = {
        "schema_version": "core.effect_result.v1",
        "status": "dry_run",
        "effect_type": "notification",
        "dry_run": True,
        "reason": "dry_run",
        "provider": "generic",
        "target_ref": "operator",
    }
    memory_result = {
        "schema_version": "core.memory_generation_result.v1",
        "status": "passed",
        "source_type": "task",
        "source_id": "task-001",
        "reused": False,
        "memory_id": "memory-001",
    }
    threshold_result = {
        "schema_version": "core.context_threshold.v1",
        "status": "passed",
        "source_type": "workflow",
        "source_id": "workflow-001",
        "should_compress_now": False,
        "reason": "usage_below_threshold",
        "recommended_action": "none",
    }
    gate_result = {
        "schema_version": "core.context_gate.v1",
        "status": "skipped",
        "source_type": "workflow",
        "source_id": "workflow-001",
        "mode": "dry-run",
        "reason": "below_threshold",
        "proposed_action": "none",
    }
    retention_manifest = {
        "schema_version": "core.retention_manifest.v1",
        "entries": [
            {
                "source_type": "workflow",
                "source_id": "workflow-001",
                "artifact_ref": "events.jsonl",
                "retention_class": "keep",
                "reason": "audit trail",
            }
        ],
    }
    assert task_closeout["schema_version"] == "core.task_closeout.v1"
    assert effect_result["schema_version"] == "core.effect_result.v1"
    assert memory_result["schema_version"] == "core.memory_generation_result.v1"
    assert threshold_result["schema_version"] == "core.context_threshold.v1"
    assert gate_result["schema_version"] == "core.context_gate.v1"
    assert retention_manifest["schema_version"] == "core.retention_manifest.v1"
