"""Executable semantics for public CORE contracts.

JSON Schema answers whether an artifact has a compatible shape.  This module
answers the separate question that matters operationally: whether the values
form a coherent, evidence-bound decision under deterministic rules.

The evaluator never grants execution, deployment, legal, or moral authority.
It also never turns finite observations into universal truth.  A formal proof
may demonstrate a proposition only inside its declared model and assumptions.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import FormatChecker
from jsonschema.validators import validator_for

from core_runtime.core.canonicalization import canonical_json_hash
from core_runtime.core.contract_loader import available_contracts, load_contract_schema


FINGERPRINT_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")
ABSOLUTE_CLAIM_RE = re.compile(
    r"\b(?:unhackable|zero[ -]risk|impossible to hack|guaranteed safe|"
    r"all circumstances|cero riesgo|imposible de hackear|seguridad absoluta|"
    r"verdad absoluta)\b",
    re.IGNORECASE,
)

SAFETY_REQUIRED_SCENARIOS = frozenset(
    {
        "llm_prompt_injection",
        "network_compromise",
        "general_compute_compromise",
        "sensor_fault",
        "communication_loss",
        "power_loss",
        "update_tamper",
        "replay_attack",
        "emergency_stop",
        "out_of_distribution_input",
    }
)
SAFETY_REQUIRED_LEDGER_EVENTS = frozenset(
    {
        "safety_policy_changed",
        "hazardous_command_rejected",
        "safety_interlock_activated",
        "unexpected_physical_outcome",
        "assurance_invalidated",
    }
)
ASSURANCE_RANK = {
    "rejected": 0,
    "simulation_only": 1,
    "evidence_ready": 2,
    "independent_evidence_ready": 3,
}


Error = dict[str, Any]
SemanticResult = tuple[list[Error], list[Error], dict[str, Any]]
SemanticValidator = Callable[[dict[str, Any]], SemanticResult]


def error(code: str, message: str, field: str = "$", **extra: Any) -> Error:
    """Build a stable error or warning entry."""

    item: Error = {"code": code, "message": message, "field": field}
    item.update(extra)
    return item


def artifact_fingerprint(payload: Mapping[str, Any]) -> str:
    """Fingerprint canonical artifact content, excluding its own fingerprint."""

    body = {key: value for key, value in payload.items() if key != "fingerprint"}
    return f"sha256:{canonical_json_hash(body)}"


def input_fingerprint(payload: Any) -> str:
    """Fingerprint the exact parsed input used by the evaluator."""

    return f"sha256:{canonical_json_hash(payload)}"


def _timezone_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _schema_version_map() -> dict[str, str]:
    result: dict[str, str] = {}
    for contract_name in available_contracts():
        schema = load_contract_schema(contract_name)
        version = schema.get("properties", {}).get("schema_version", {}).get("const")
        if isinstance(version, str):
            result[version] = contract_name
    return result


def _schema_errors(payload: Any, schema: dict[str, Any]) -> list[Error]:
    validator_cls = validator_for(schema)
    validator_cls.check_schema(schema)
    validator = validator_cls(schema, format_checker=FormatChecker())
    errors: list[Error] = []
    for item in sorted(validator.iter_errors(payload), key=lambda entry: list(entry.absolute_path)):
        field = ".".join(str(part) for part in item.absolute_path) or "$"
        errors.append(error("schema_validation_error", item.message, field))
    return errors


def validate_contract_structure(payload: Any) -> list[Error]:
    """Validate only the published JSON Schema, without semantic decisions."""

    if not isinstance(payload, dict):
        return [error("invalid_artifact", "Contract artifact must be an object.")]
    version = payload.get("schema_version")
    contract_name = _schema_version_map().get(version)
    if contract_name is None:
        return [error("unknown_schema_version", f"Unknown schema_version: {version!r}.", "schema_version")]
    return _schema_errors(payload, load_contract_schema(contract_name))


def _resolve_local_ref(schema: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return schema
    current: Any = root
    for part in ref[2:].split("/"):
        token = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or token not in current:
            return schema
        current = current[token]
    return current if isinstance(current, dict) else schema


def _strict_shape_errors(
    value: Any,
    schema: dict[str, Any],
    root: dict[str, Any],
    field: str = "$",
) -> list[Error]:
    """Close legacy extension points when the strict executable profile is used."""

    schema = _resolve_local_ref(schema, root)
    errors: list[Error] = []
    if isinstance(value, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict) and properties:
            unknown = sorted(set(value) - set(properties))
            for key in unknown:
                errors.append(
                    error(
                        "undeclared_field",
                        "Strict contract evaluation rejects undeclared fields.",
                        f"{field}.{key}",
                    )
                )
            for key, child in value.items():
                child_schema = properties.get(key)
                if isinstance(child_schema, dict):
                    errors.extend(_strict_shape_errors(child, child_schema, root, f"{field}.{key}"))
    elif isinstance(value, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, child in enumerate(value):
                errors.extend(_strict_shape_errors(child, item_schema, root, f"{field}[{index}]"))
    return errors


def _unsafe_ref(value: str) -> bool:
    if not value or value.startswith("/") or WINDOWS_ABSOLUTE_RE.match(value):
        return True
    normalized = value.replace("\\", "/")
    return ".." in normalized.split("/") or "\x00" in value


def _reference_errors(value: Any, field: str = "$", key: str = "") -> list[Error]:
    errors: list[Error] = []
    if isinstance(value, dict):
        for child_key, child in value.items():
            errors.extend(_reference_errors(child, f"{field}.{child_key}", child_key))
    elif isinstance(value, list):
        if key.endswith("_refs") and all(isinstance(item, str) for item in value):
            if len(value) != len(set(value)):
                errors.append(error("duplicate_reference", "Reference arrays must be unique.", field))
        singular_key = key[:-1] if key.endswith("_refs") else key
        for index, child in enumerate(value):
            errors.extend(_reference_errors(child, f"{field}[{index}]", singular_key))
    elif isinstance(value, str) and (key.endswith("_ref") or key in {"root_ref", "before_ref", "after_ref"}):
        if _unsafe_ref(value):
            errors.append(error("unsafe_reference", "References must be bounded and relative.", field))
    return errors


def _fingerprint_errors(payload: dict[str, Any]) -> list[Error]:
    if "fingerprint" not in payload:
        return []
    declared = payload.get("fingerprint")
    if not isinstance(declared, str) or not FINGERPRINT_RE.fullmatch(declared):
        return [error("invalid_fingerprint", "fingerprint must be sha256:<64 lowercase hex>.", "fingerprint")]
    computed = artifact_fingerprint(payload)
    if declared != computed:
        return [
            error(
                "fingerprint_mismatch",
                "fingerprint does not match canonical artifact content.",
                "fingerprint",
                declared=declared,
                computed=computed,
            )
        ]
    return []


def _timestamp_error(payload: dict[str, Any], key: str) -> list[Error]:
    if key in payload and _timezone_datetime(payload.get(key)) is None:
        return [error("invalid_timestamp", "Timestamp must include an explicit timezone.", key)]
    return []


def _empty_result() -> SemanticResult:
    return [], [], {}


def _validate_causal_trace(payload: dict[str, Any]) -> SemanticResult:
    errors: list[Error] = []
    nodes = payload.get("nodes", [])
    refs: list[str] = []
    ids: list[str] = []
    if isinstance(nodes, list):
        refs = [item.get("ref") for item in nodes if isinstance(item, dict) and isinstance(item.get("ref"), str)]
        ids = [item.get("node_id") for item in nodes if isinstance(item, dict) and isinstance(item.get("node_id"), str)]
    if len(ids) != len(set(ids)):
        errors.append(error("duplicate_node_id", "node_id values must be unique.", "nodes"))
    if len(refs) != len(set(refs)):
        errors.append(error("duplicate_node_ref", "Node ref values must be unique.", "nodes"))
    if payload.get("root_ref") not in set(refs):
        errors.append(error("missing_root_node", "root_ref must resolve to a node ref.", "root_ref"))

    graph: dict[str, list[str]] = {ref: [] for ref in refs}
    for index, edge in enumerate(payload.get("edges", [])):
        if not isinstance(edge, dict):
            continue
        source = edge.get("from_ref")
        target = edge.get("to_ref")
        if source not in graph or target not in graph:
            errors.append(error("dangling_edge_ref", "Every edge endpoint must resolve to a node ref.", f"edges[{index}]"))
            continue
        if source == target:
            errors.append(error("causal_self_loop", "A causal edge cannot reference itself.", f"edges[{index}]"))
        graph[source].append(target)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(child) for child in graph.get(node, [])):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    if any(visit(node) for node in sorted(graph)):
        errors.append(error("causal_cycle", "Causal traces must be acyclic.", "edges"))
    errors.extend(_timestamp_error(payload, "created_at"))
    return errors, [], {"node_count": len(refs), "edge_count": len(payload.get("edges", []))}


def _validate_entropy_signal(payload: dict[str, Any]) -> SemanticResult:
    errors: list[Error] = []
    measurement = payload.get("measurement")
    if not isinstance(measurement, dict) or not measurement:
        errors.append(error("measurement_required", "Entropy signals require a non-empty measurement.", "measurement"))
    response = str(payload.get("suggested_response", "")).strip().lower()
    if payload.get("severity") == "critical" and response in {"ignore", "allow", "continue"}:
        errors.append(error("critical_signal_cannot_be_ignored", "A critical signal cannot recommend continuation.", "suggested_response"))
    errors.extend(_timestamp_error(payload, "timestamp"))
    return errors, [], {}


def _validate_control_decision(payload: dict[str, Any]) -> SemanticResult:
    errors: list[Error] = []
    decision = payload.get("decision")
    reversibility = payload.get("reversibility_class")
    if decision == "allow" and reversibility in {"irreversible", "unknown"}:
        errors.append(error("unsafe_allow_decision", "Unknown or irreversible actions cannot be directly allowed.", "decision"))
    if decision in {"allow", "require_confirmation"} and not payload.get("evidence_refs"):
        errors.append(error("required_evidence_missing", "A non-blocked decision must bind observed evidence.", "evidence_refs"))
    errors.extend(_timestamp_error(payload, "created_at"))
    return errors, [], {"execution_authorized": False}


def _validate_execution_receipt(payload: dict[str, Any]) -> SemanticResult:
    errors: list[Error] = []
    status = payload.get("status")
    transitions = payload.get("state_transition_refs", [])
    if status == "succeeded" and not transitions:
        errors.append(error("successful_receipt_requires_transition", "A successful effect requires at least one state transition.", "state_transition_refs"))
    if status in {"skipped", "simulated"} and transitions:
        errors.append(error("simulated_transition_forbidden", "Skipped or simulated execution cannot claim state changes.", "state_transition_refs"))
    errors.extend(_timestamp_error(payload, "created_at"))
    return errors, [], {"execution_authorized": False}


def _validate_memory_artifact(payload: dict[str, Any]) -> SemanticResult:
    errors: list[Error] = []
    retention = payload.get("retention", {})
    protected = any(payload.get(key) for key in ("stable_facts", "decisions", "invariants", "open_risks"))
    if isinstance(retention, dict) and retention.get("retention_class") == "forget" and protected:
        errors.append(error("unsafe_memory_forgetting", "Memory containing facts, decisions, invariants, or risks cannot be marked forget.", "retention.retention_class"))
    errors.extend(_timestamp_error(payload, "created_at"))
    return errors, [], {"authority": "reference_only"}


def _validate_task_closeout(payload: dict[str, Any]) -> SemanticResult:
    errors: list[Error] = []
    if payload.get("status") not in {"passed", "failed", "blocked", "partial"}:
        errors.append(error("invalid_closeout_status", "Closeout status must be passed, failed, blocked, or partial.", "status"))
    evidence_fields = ("report_ref", "events_ref", "effect_results", "memory_generation_result")
    if payload.get("status") == "passed" and not any(payload.get(key) for key in evidence_fields):
        errors.append(error("closeout_evidence_required", "A passed closeout requires an evidence-bearing result or report reference.", "status"))
    return errors, [], {}


def _validate_effect_result(payload: dict[str, Any]) -> SemanticResult:
    errors: list[Error] = []
    status = payload.get("status")
    dry_run = payload.get("dry_run")
    if (status == "dry_run") != (dry_run is True):
        errors.append(error("effect_status_dry_run_mismatch", "status=dry_run and dry_run=true must agree.", "dry_run"))
    if status in {"sent", "applied"}:
        if dry_run is not False:
            errors.append(error("applied_effect_cannot_be_dry_run", "Applied effects must declare dry_run=false.", "dry_run"))
        if not payload.get("provider") or not payload.get("target_ref"):
            errors.append(error("effect_destination_required", "Applied effects require provider and target_ref.", "target_ref"))
    if status == "failed" and not payload.get("error"):
        errors.append(error("failed_effect_requires_error", "Failed effects require an error description.", "error"))
    return errors, [], {"execution_authorized": False}


def _validate_memory_generation_result(payload: dict[str, Any]) -> SemanticResult:
    errors: list[Error] = []
    status = payload.get("status")
    if status not in {"passed", "failed", "skipped"}:
        errors.append(error("invalid_memory_result_status", "Memory result status must be passed, failed, or skipped.", "status"))
    if status == "passed" and (not payload.get("memory_id") or not payload.get("memory_ref")):
        errors.append(error("memory_reference_required", "A passed memory result requires memory_id and memory_ref.", "memory_ref"))
    if payload.get("reused") is True and (not payload.get("memory_id") or not payload.get("memory_ref")):
        errors.append(error("reused_memory_reference_required", "Reused memory must resolve to an immutable memory reference.", "memory_ref"))
    if status == "failed" and payload.get("reused") is True:
        errors.append(error("failed_memory_cannot_be_reused", "A failed result cannot claim reuse.", "reused"))
    return errors, [], {}


def _validate_operational_learning_event(payload: dict[str, Any]) -> SemanticResult:
    errors: list[Error] = []
    if payload.get("status") not in {"recorded", "candidate", "accepted", "rejected", "quarantined"}:
        errors.append(error("invalid_learning_status", "Learning status is not recognized.", "status"))
    event_payload = payload.get("payload")
    if not isinstance(event_payload, dict) or not event_payload:
        errors.append(error("learning_payload_required", "Operational learning requires a non-empty payload.", "payload"))

    def scan(value: Any, field: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_field = f"{field}.{key}"
                if key in {"auto_execute", "self_modify"} and child is True:
                    errors.append(error("learning_event_authority_escalation", "Learning events cannot grant execution or self-modification.", child_field))
                if key in {"authority", "activation_default"} and str(child).lower() in {"binding", "execution_authority", "enabled", "automatic"}:
                    errors.append(error("learning_event_authority_escalation", "Learning events remain candidate-only.", child_field))
                scan(child, child_field)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                scan(child, f"{field}[{index}]")

    scan(event_payload, "payload")
    errors.extend(_timestamp_error(payload, "timestamp"))
    return errors, [], {"authority": "candidate_only"}


def _validate_policy_lifecycle(payload: dict[str, Any]) -> SemanticResult:
    errors: list[Error] = []
    start = _timezone_datetime(payload.get("effective_from"))
    end = _timezone_datetime(payload.get("effective_to")) if payload.get("effective_to") is not None else None
    if start is None:
        errors.append(error("invalid_effective_from", "effective_from must include a timezone.", "effective_from"))
    if payload.get("effective_to") is not None and end is None:
        errors.append(error("invalid_effective_to", "effective_to must include a timezone.", "effective_to"))
    if start is not None and end is not None and end <= start:
        errors.append(error("invalid_effective_interval", "effective_to must be later than effective_from.", "effective_to"))
    if payload.get("status") in {"superseded", "retired"} and end is None:
        errors.append(error("closed_policy_requires_end", "Superseded or retired policies require effective_to.", "effective_to"))
    if payload.get("supersedes") == payload.get("policy_id"):
        errors.append(error("policy_cannot_supersede_itself", "A policy cannot supersede itself.", "supersedes"))
    return errors, [], {}


def _validate_context_threshold(payload: dict[str, Any]) -> SemanticResult:
    errors: list[Error] = []
    for key in ("current_usage_percent", "previous_usage_percent", "ema_usage_percent", "compression_threshold_percent"):
        value = payload.get(key)
        if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0 or value > 100):
            errors.append(error("invalid_percentage", "Percentages must be between 0 and 100.", key))
    current = payload.get("current_usage_percent")
    threshold = payload.get("compression_threshold_percent")
    if isinstance(current, (int, float)) and isinstance(threshold, (int, float)):
        expected = current >= threshold
        if payload.get("should_compress_now") is not expected:
            errors.append(error("threshold_decision_mismatch", "should_compress_now must be derived from current usage and threshold.", "should_compress_now"))
    if payload.get("status") not in {"passed", "failed", "skipped"}:
        errors.append(error("invalid_threshold_status", "Threshold status must be passed, failed, or skipped.", "status"))
    return errors, [], {}


def _validate_context_gate(payload: dict[str, Any]) -> SemanticResult:
    errors: list[Error] = []
    status = payload.get("status")
    mode = payload.get("mode")
    if status not in {"passed", "applied", "skipped", "blocked", "failed"}:
        errors.append(error("invalid_context_gate_status", "Context gate status is not recognized.", "status"))
    if mode == "dry-run" and status == "applied":
        errors.append(error("dry_run_cannot_apply", "A dry-run gate cannot report an applied mutation.", "status"))
    if mode == "apply" and status == "applied" and not payload.get("memory_generation_result"):
        errors.append(error("apply_result_required", "An applied gate requires the resulting memory artifact reference.", "memory_generation_result"))
    return errors, [], {"execution_authorized": False}


def _validate_retention_manifest(payload: dict[str, Any]) -> SemanticResult:
    errors: list[Error] = []
    entries = payload.get("entries", [])
    if not entries:
        errors.append(error("retention_entries_required", "A retention manifest cannot be empty.", "entries"))
    refs = [item.get("artifact_ref") for item in entries if isinstance(item, dict)]
    if len(refs) != len(set(refs)):
        errors.append(error("duplicate_artifact_ref", "Each artifact may have only one retention decision.", "entries"))
    for index, item in enumerate(entries):
        if not isinstance(item, dict):
            continue
        retention_class = item.get("retention_class")
        if retention_class in {"compress", "forget", "quarantine"} and not item.get("checksum"):
            errors.append(error("retention_checksum_required", "Mutating retention actions require the source checksum.", f"entries[{index}].checksum"))
        if retention_class in {"forget", "quarantine"} and not item.get("restore_ref"):
            errors.append(error("retention_restore_required", "Destructive or isolating retention actions require a restore reference.", f"entries[{index}].restore_ref"))
    return errors, [], {}


def _validate_reversibility_policy(payload: dict[str, Any]) -> SemanticResult:
    errors: list[Error] = []
    reversibility = payload.get("reversibility_class")
    if reversibility in {"irreversible", "unknown"} and payload.get("human_approval_required") is not True:
        errors.append(error("responsible_approval_required", "Unknown or irreversible actions require responsible-person approval.", "human_approval_required"))
    if reversibility == "compensable" and payload.get("compensation_required") is not True:
        errors.append(error("compensation_plan_required", "Compensable actions require compensation.", "compensation_required"))
    errors.extend(_timestamp_error(payload, "created_at"))
    return errors, [], {"execution_authorized": False}


def _validate_state_transition(payload: dict[str, Any]) -> SemanticResult:
    errors: list[Error] = []
    if payload.get("before_ref") == payload.get("after_ref"):
        errors.append(error("state_transition_noop", "before_ref and after_ref must differ.", "after_ref"))
    actor = str(payload.get("actor_kind", "")).lower()
    responsible_actors = {"human", "human_operator", "responsible_operator", "authorized_signer", "human_directed_software"}
    if payload.get("reversibility_class") in {"irreversible", "unknown"} and actor not in responsible_actors:
        errors.append(error("irreversible_actor_not_responsible", "Irreversible transitions require an explicitly accountable actor kind.", "actor_kind"))
    errors.extend(_timestamp_error(payload, "timestamp"))
    return errors, [], {"execution_authorized": False}


def _validate_template_promotion(payload: dict[str, Any]) -> SemanticResult:
    errors: list[Error] = []
    for key in ("required_inputs", "expected_evidence", "stop_conditions"):
        if not payload.get(key):
            errors.append(error("promotion_contract_incomplete", f"{key} cannot be empty.", key))
    if payload.get("risk_tier") in {"medium", "high"} and payload.get("human_approval_required") is not True:
        errors.append(error("promotion_approval_required", "Medium and high-risk templates require responsible approval.", "human_approval_required"))
    if payload.get("risk_tier") == "high" and not payload.get("source_refs"):
        errors.append(error("promotion_source_evidence_required", "High-risk promotion requires source_refs.", "source_refs"))
    return errors, [], {"activation_authorized": False}


def _validate_pattern_candidate(payload: dict[str, Any]) -> SemanticResult:
    errors: list[Error] = []
    signature = payload.get("normalized_signature")
    if not isinstance(signature, dict) or not signature:
        errors.append(error("normalized_signature_required", "Pattern candidates require a non-empty normalized signature.", "normalized_signature"))
    classification = payload.get("classification")
    if classification == "candidate_for_template":
        if payload.get("occurrences", 0) < 2 or payload.get("confidence", 0) < 0.8:
            errors.append(error("insufficient_pattern_support", "Template candidates require at least two occurrences and confidence >= 0.8.", "confidence"))
        if not payload.get("evidence_refs") or not payload.get("example_refs"):
            errors.append(error("pattern_evidence_required", "Template candidates require evidence_refs and example_refs.", "evidence_refs"))
    action = str(payload.get("suggested_action", "")).lower()
    if classification == "too_ambiguous" and any(token in action for token in ("promote", "activate", "auto", "template")):
        errors.append(error("ambiguous_pattern_cannot_promote", "Ambiguous patterns may request clarification only.", "suggested_action"))
    errors.extend(_timestamp_error(payload, "observed_at"))
    return errors, [], {"authority": "candidate_only"}


def _duplicate_ids(items: Any, key: str, field: str) -> tuple[set[str], list[Error]]:
    values = [item.get(key) for item in items if isinstance(item, dict) and isinstance(item.get(key), str)] if isinstance(items, list) else []
    errors = []
    if len(values) != len(set(values)):
        errors.append(error("duplicate_identifier", f"{key} values must be unique.", field))
    return set(values), errors


def _validate_physical_safety_case(payload: dict[str, Any]) -> SemanticResult:
    errors: list[Error] = []
    warnings: list[Error] = []
    claim = payload.get("claim", {})
    envelope = payload.get("observed_envelope", {})
    hazards = payload.get("hazards", [])
    barriers = payload.get("barriers", [])
    tests = payload.get("verification_tests", [])
    evidence = payload.get("evidence", [])

    evidence_ids, id_errors = _duplicate_ids(evidence, "evidence_id", "evidence")
    errors.extend(id_errors)
    barrier_ids, id_errors = _duplicate_ids(barriers, "barrier_id", "barriers")
    errors.extend(id_errors)
    hazard_ids, id_errors = _duplicate_ids(hazards, "hazard_id", "hazards")
    errors.extend(id_errors)
    test_ids, id_errors = _duplicate_ids(tests, "test_id", "verification_tests")
    errors.extend(id_errors)

    evidence_by_id = {item.get("evidence_id"): item for item in evidence if isinstance(item, dict)}
    barrier_by_id = {item.get("barrier_id"): item for item in barriers if isinstance(item, dict)}
    test_by_id = {item.get("test_id"): item for item in tests if isinstance(item, dict)}

    scope = str(claim.get("scope", "")) if isinstance(claim, dict) else ""
    if ABSOLUTE_CLAIM_RE.search(scope):
        errors.append(error("absolute_safety_claim_forbidden", "Safety scope cannot claim universal truth, zero risk, or unhackability.", "claim.scope"))
    if isinstance(claim, dict) and claim.get("claim_status") == "demonstrated_within_model":
        if not claim.get("proof_refs") or "formal_model" not in claim.get("reference_classes", []):
            errors.append(error("formal_demonstration_evidence_required", "Demonstrated-within-model claims require formal_model and proof_refs.", "claim.proof_refs"))

    extremes = envelope.get("known_extremes", []) if isinstance(envelope, dict) else []
    extreme_ids, id_errors = _duplicate_ids(extremes, "extreme_id", "observed_envelope.known_extremes")
    errors.extend(id_errors)
    directions = {item.get("direction") for item in extremes if isinstance(item, dict)}
    if len(directions) < 2:
        errors.append(error("extreme_diversity_required", "The observed envelope must preserve at least two distinct extreme directions.", "observed_envelope.known_extremes"))
    if isinstance(envelope, dict) and isinstance(envelope.get("sample_count"), int) and envelope.get("sample_count", 0) < len(extreme_ids):
        errors.append(error("sample_count_below_extremes", "sample_count cannot be smaller than the number of extreme observations.", "observed_envelope.sample_count"))

    evaluated_at = _timezone_datetime(payload.get("evaluated_at"))
    if evaluated_at is None:
        errors.append(error("invalid_evaluated_at", "evaluated_at must include a timezone.", "evaluated_at"))
    evidence_fingerprints: list[str] = []
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            continue
        fp = item.get("fingerprint")
        if isinstance(fp, str):
            evidence_fingerprints.append(fp)
            if fp == "sha256:" + ("0" * 64):
                errors.append(error("zero_evidence_fingerprint", "Evidence fingerprints cannot be all zero.", f"evidence[{index}].fingerprint"))
        captured = _timezone_datetime(item.get("captured_at"))
        if captured is None:
            errors.append(error("invalid_evidence_timestamp", "Evidence timestamps require a timezone.", f"evidence[{index}].captured_at"))
        elif evaluated_at is not None and captured > evaluated_at:
            errors.append(error("future_evidence_forbidden", "Evidence cannot be captured after evaluated_at.", f"evidence[{index}].captured_at"))
    if len(evidence_fingerprints) != len(set(evidence_fingerprints)):
        errors.append(error("duplicate_evidence_fingerprint", "Independent evidence items cannot reuse the same fingerprint.", "evidence"))

    def require_evidence_ref(ref: Any, field: str) -> None:
        if ref not in evidence_ids:
            errors.append(error("unresolved_evidence_ref", "Evidence reference does not resolve inside this frozen case.", field, ref=ref))

    for index, item in enumerate(extremes):
        if isinstance(item, dict):
            require_evidence_ref(item.get("evidence_ref"), f"observed_envelope.known_extremes[{index}].evidence_ref")
            if _timezone_datetime(item.get("observed_at")) is None:
                errors.append(error("invalid_extreme_timestamp", "Extreme observations require a timezone.", f"observed_envelope.known_extremes[{index}].observed_at"))

    if isinstance(claim, dict):
        for index, ref in enumerate(claim.get("proof_refs", [])):
            require_evidence_ref(ref, f"claim.proof_refs[{index}]")

    for index, barrier in enumerate(barriers):
        if not isinstance(barrier, dict):
            continue
        barrier_id = barrier.get("barrier_id")
        for relation_index, ref in enumerate(barrier.get("independent_from", [])):
            if ref == barrier_id:
                errors.append(error("barrier_self_independence", "A barrier cannot be independent from itself.", f"barriers[{index}].independent_from[{relation_index}]"))
            elif ref not in barrier_ids:
                errors.append(error("unresolved_barrier_ref", "independent_from must resolve to another barrier.", f"barriers[{index}].independent_from[{relation_index}]"))
            elif barrier_id not in barrier_by_id.get(ref, {}).get("independent_from", []):
                errors.append(error("asymmetric_barrier_independence", "Barrier independence must be declared by both barriers.", f"barriers[{index}].independent_from[{relation_index}]"))
        for evidence_index, ref in enumerate(barrier.get("evidence_refs", [])):
            require_evidence_ref(ref, f"barriers[{index}].evidence_refs[{evidence_index}]")

    methods_by_hazard_scenario: dict[str, dict[str, set[str]]] = {
        hazard_id: {scenario: set() for scenario in SAFETY_REQUIRED_SCENARIOS}
        for hazard_id in hazard_ids
    }
    independent_evidence_by_test: dict[str, bool] = {}
    for index, test in enumerate(tests):
        if not isinstance(test, dict):
            continue
        test_id = test.get("test_id")
        evidence_refs = test.get("evidence_refs", [])
        for evidence_index, ref in enumerate(evidence_refs):
            require_evidence_ref(ref, f"verification_tests[{index}].evidence_refs[{evidence_index}]")
        independent_evidence_by_test[str(test_id)] = any(
            isinstance(evidence_by_id.get(ref), dict)
            and evidence_by_id[ref].get("source_kind") == "independent_assessor"
            and evidence_by_id[ref].get("reference_class") == "independent_assessment"
            for ref in evidence_refs
        )
        if test.get("result") != "passed":
            errors.append(error("safety_test_not_passed", "Failed or inconclusive safety tests reject the assurance case.", f"verification_tests[{index}].result"))
        if test.get("hazardous_actuation_observed") is not False:
            errors.append(error("hazardous_actuation_observed", "Any observed hazardous actuation rejects the assurance case.", f"verification_tests[{index}].hazardous_actuation_observed"))
        if test.get("expected_safe_state") != test.get("observed_safe_state"):
            errors.append(error("safe_state_mismatch", "Observed and expected safe states must match exactly.", f"verification_tests[{index}].observed_safe_state"))
        for hazard_ref in test.get("hazard_refs", []):
            if hazard_ref not in hazard_ids:
                errors.append(error("unresolved_hazard_ref", "Test hazard_refs must resolve inside the case.", f"verification_tests[{index}].hazard_refs"))
                continue
            scenario = test.get("scenario")
            method = test.get("method")
            if scenario in SAFETY_REQUIRED_SCENARIOS and isinstance(method, str):
                methods_by_hazard_scenario[hazard_ref][scenario].add(method)

    for index, hazard in enumerate(hazards):
        if not isinstance(hazard, dict):
            continue
        hazard_id = hazard.get("hazard_id")
        resolved_barriers: list[dict[str, Any]] = []
        for barrier_index, ref in enumerate(hazard.get("barrier_refs", [])):
            barrier = barrier_by_id.get(ref)
            if not isinstance(barrier, dict):
                errors.append(error("unresolved_barrier_ref", "Hazard barrier_refs must resolve inside the case.", f"hazards[{index}].barrier_refs[{barrier_index}]"))
            else:
                resolved_barriers.append(barrier)
        for test_index, ref in enumerate(hazard.get("test_refs", [])):
            test = test_by_id.get(ref)
            if not isinstance(test, dict):
                errors.append(error("unresolved_test_ref", "Hazard test_refs must resolve inside the case.", f"hazards[{index}].test_refs[{test_index}]"))
            elif hazard_id not in test.get("hazard_refs", []):
                errors.append(error("test_hazard_link_mismatch", "Hazard and test links must be bidirectional.", f"hazards[{index}].test_refs[{test_index}]"))

        if hazard.get("severity") == "catastrophic":
            non_bypassable = [barrier for barrier in resolved_barriers if barrier.get("bypassable_by_general_compute") is False]
            domains = {barrier.get("enforcement_domain") for barrier in non_bypassable}
            kinds = {barrier.get("kind") for barrier in non_bypassable}
            if len(non_bypassable) < 2 or len(domains) < 2:
                errors.append(error("catastrophic_hazard_needs_independent_barriers", "Catastrophic hazards require at least two non-bypassable barriers in distinct enforcement domains.", f"hazards[{index}].barrier_refs"))
            if "isolated_safety_controller" not in kinds:
                errors.append(error("isolated_safety_controller_required", "Catastrophic hazards require an isolated safety controller.", f"hazards[{index}].barrier_refs"))
            if not kinds.intersection({"physical_energy_isolation", "mechanical_limit"}):
                errors.append(error("physical_isolation_required", "Catastrophic hazards require hardware energy isolation or a mechanical limit.", f"hazards[{index}].barrier_refs"))

        coverage = methods_by_hazard_scenario.get(str(hazard_id), {})
        missing = sorted(scenario for scenario in SAFETY_REQUIRED_SCENARIOS if not coverage.get(scenario))
        if missing:
            errors.append(error("required_scenario_missing", "Every hazard must cover the mandatory adversarial and fault scenarios.", f"hazards[{index}].test_refs", missing=missing))

    epistemic = payload.get("epistemic_dignity", {})
    if isinstance(epistemic, dict):
        for key in (
            "plain_language_disclosure_ref",
            "evidence_limitations_ref",
            "contestability_ref",
            "local_stop_ref",
        ):
            require_evidence_ref(epistemic.get(key), f"epistemic_dignity.{key}")
    lifecycle = payload.get("lifecycle", {})
    if isinstance(lifecycle, dict):
        for key in (
            "secure_boot_evidence_ref",
            "signed_update_evidence_ref",
            "unique_credentials_evidence_ref",
            "sbom_evidence_ref",
            "vulnerability_process_evidence_ref",
        ):
            require_evidence_ref(lifecycle.get(key), f"lifecycle.{key}")
    traceability = payload.get("traceability", {})
    if isinstance(traceability, dict):
        require_evidence_ref(traceability.get("immutable_event_ledger_ref"), "traceability.immutable_event_ledger_ref")
        recorded = set(traceability.get("recorded_event_types", []))
        missing_events = sorted(SAFETY_REQUIRED_LEDGER_EVENTS - recorded)
        if missing_events:
            errors.append(error("critical_ledger_event_missing", "The immutable ledger contract omits required safety events.", "traceability.recorded_event_types", missing=missing_events))

    achieved = "simulation_only"
    if hazard_ids and all(
        all(methods_by_hazard_scenario[hazard_id][scenario] - {"simulation"} for scenario in SAFETY_REQUIRED_SCENARIOS)
        for hazard_id in hazard_ids
    ):
        achieved = "evidence_ready"
    if hazard_ids and all(
        "independent_assessment" in methods_by_hazard_scenario[hazard_id][scenario]
        for hazard_id in hazard_ids
        for scenario in SAFETY_REQUIRED_SCENARIOS
    ):
        independent_tests = [test for test in tests if isinstance(test, dict) and test.get("method") == "independent_assessment"]
        if independent_tests and all(independent_evidence_by_test.get(str(test.get("test_id")), False) for test in independent_tests):
            achieved = "independent_evidence_ready"

    requested = payload.get("requested_assurance_level")
    if isinstance(requested, str) and ASSURANCE_RANK.get(achieved, 0) < ASSURANCE_RANK.get(requested, 0):
        errors.append(error("requested_assurance_level_not_met", "Observed evidence does not meet the requested assurance level.", "requested_assurance_level", requested=requested, achieved=achieved))
    if achieved == "simulation_only":
        warnings.append(error("simulation_is_not_deployment_evidence", "Simulation can discover hazards but cannot authorize physical deployment.", "requested_assurance_level"))

    details = {
        "requested_assurance_level": requested,
        "achieved_assurance_level": "rejected" if errors else achieved,
        "hazard_count": len(hazard_ids),
        "barrier_count": len(barrier_ids),
        "test_count": len(test_ids),
        "evidence_count": len(evidence_ids),
        "execution_authorized": False,
        "deployment_authorized": False,
    }
    return errors, warnings, details


SEMANTIC_VALIDATORS: dict[str, SemanticValidator] = {
    "core.causal_trace.v1": _validate_causal_trace,
    "core.context_gate.v1": _validate_context_gate,
    "core.context_threshold.v1": _validate_context_threshold,
    "core.control_decision.v1": _validate_control_decision,
    "core.effect_result.v1": _validate_effect_result,
    "core.entropy_signal.v1": _validate_entropy_signal,
    "core.execution_receipt.v1": _validate_execution_receipt,
    "core.memory_artifact.v1": _validate_memory_artifact,
    "core.memory_generation_result.v1": _validate_memory_generation_result,
    "core.operational_learning_event.v1": _validate_operational_learning_event,
    "core.pattern_candidate.v1": _validate_pattern_candidate,
    "core.physical_safety_assurance_case.v1": _validate_physical_safety_case,
    "core.policy_lifecycle.v1": _validate_policy_lifecycle,
    "core.retention_manifest.v1": _validate_retention_manifest,
    "core.reversibility_policy.v1": _validate_reversibility_policy,
    "core.state_transition.v1": _validate_state_transition,
    "core.task_closeout.v1": _validate_task_closeout,
    "core.template_promotion_candidate.v1": _validate_template_promotion,
}

SEMANTIC_RULE_IDS: dict[str, tuple[str, ...]] = {
    "core.causal_trace.v1": ("resolved_graph", "acyclic_graph", "timezone", "fingerprint"),
    "core.context_gate.v1": ("mode_status_consistency", "result_binding"),
    "core.context_threshold.v1": ("bounded_percentages", "derived_threshold_decision"),
    "core.control_decision.v1": ("reversibility_gate", "evidence_binding", "no_execution_authority"),
    "core.effect_result.v1": ("dry_run_consistency", "destination_binding", "failure_evidence"),
    "core.entropy_signal.v1": ("measurement_required", "critical_fail_closed", "timezone"),
    "core.execution_receipt.v1": ("status_transition_consistency", "timezone", "fingerprint"),
    "core.memory_artifact.v1": ("reference_only", "protected_retention", "timezone"),
    "core.memory_generation_result.v1": ("result_reference_binding", "reuse_consistency"),
    "core.operational_learning_event.v1": ("candidate_only", "no_self_authority", "timezone"),
    "core.pattern_candidate.v1": ("support_threshold", "ambiguity_gate", "candidate_only"),
    "core.physical_safety_assurance_case.v1": (
        "bounded_claim",
        "extreme_preservation",
        "fail_closed_out_of_distribution",
        "independent_physical_barriers",
        "mandatory_adversarial_coverage",
        "epistemic_dignity",
        "immutable_critical_trace",
        "no_deployment_authority",
    ),
    "core.policy_lifecycle.v1": ("temporal_order", "closed_policy_end", "no_self_supersession"),
    "core.retention_manifest.v1": ("unique_decision", "mutation_checksum", "restore_path"),
    "core.reversibility_policy.v1": ("responsible_approval", "compensation_gate", "no_execution_authority"),
    "core.state_transition.v1": ("actual_transition", "responsible_irreversible_actor", "timezone"),
    "core.task_closeout.v1": ("bounded_status", "passed_requires_evidence"),
    "core.template_promotion_candidate.v1": ("complete_candidate", "risk_approval", "no_auto_activation"),
}


def executable_contract_versions() -> tuple[str, ...]:
    """Return schema versions with registered semantic evaluators."""

    return tuple(sorted(SEMANTIC_VALIDATORS))


def evaluate_contract_payload(payload: Any, *, strict: bool = True) -> dict[str, Any]:
    """Evaluate structure, invariants, evidence links, and authority limits."""

    errors: list[Error] = []
    warnings: list[Error] = []
    details: dict[str, Any] = {}
    version = payload.get("schema_version") if isinstance(payload, dict) else None
    contract_name = _schema_version_map().get(version)
    if not isinstance(payload, dict):
        errors.append(error("invalid_artifact", "Contract artifact must be an object."))
    elif contract_name is None:
        errors.append(error("unknown_schema_version", f"Unknown schema_version: {version!r}.", "schema_version"))
    else:
        schema = load_contract_schema(contract_name)
        structural_errors = _schema_errors(payload, schema)
        if strict:
            structural_errors.extend(_strict_shape_errors(payload, schema, schema))
        errors.extend(structural_errors)
        errors.extend(_reference_errors(payload))
        errors.extend(_fingerprint_errors(payload))
        semantic = SEMANTIC_VALIDATORS.get(str(version))
        if semantic is None:
            errors.append(error("semantic_evaluator_missing", "Contract has no executable semantic evaluator.", "schema_version"))
        elif not structural_errors:
            semantic_errors, semantic_warnings, details = semantic(payload)
            errors.extend(semantic_errors)
            warnings.extend(semantic_warnings)

    status = "passed" if not errors else "failed"
    knowledge_status = "bounded_artifact"
    if isinstance(payload, dict) and version == "core.physical_safety_assurance_case.v1":
        claim = payload.get("claim")
        if isinstance(claim, dict):
            knowledge_status = str(claim.get("claim_status", "bounded_artifact"))
    report: dict[str, Any] = {
        "schema": "core.contract_evaluation.v1",
        "contract_schema": version,
        "status": status,
        "decision": "accepted" if status == "passed" else "rejected",
        "authority": "validation_only",
        "knowledge_status": knowledge_status,
        "truth_claimed": False,
        "execution_authorized": False,
        "deployment_authorized": False,
        "input_fingerprint": input_fingerprint(payload),
        "evaluated_rules": list(SEMANTIC_RULE_IDS.get(str(version), ())),
        "details": details,
        "errors": errors,
        "warnings": warnings,
    }
    report["report_fingerprint"] = f"sha256:{canonical_json_hash(report)}"
    return report


def evaluate_contract_file(path: Path, *, strict: bool = True) -> dict[str, Any]:
    """Read and evaluate one JSON contract artifact."""

    import json

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return evaluate_contract_payload({"schema_version": "unknown", "read_error": "file_not_found"}, strict=strict)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        result = evaluate_contract_payload({"schema_version": "unknown", "read_error": exc.__class__.__name__}, strict=strict)
        result["errors"] = [error("invalid_json", "Contract file is not valid readable JSON.", "path")]
        result["status"] = "failed"
        result["decision"] = "rejected"
        result["report_fingerprint"] = f"sha256:{canonical_json_hash({key: value for key, value in result.items() if key != 'report_fingerprint'})}"
        return result
    return evaluate_contract_payload(payload, strict=strict)


def bind_artifact_fingerprint(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deep-copied artifact with its canonical fingerprint bound."""

    result = copy.deepcopy(dict(payload))
    result["fingerprint"] = artifact_fingerprint(result)
    return result
