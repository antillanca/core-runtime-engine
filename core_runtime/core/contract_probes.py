"""Deterministic positive and semantic-negative probes for CORE contracts."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable

from core_runtime.core.contract_evaluator import bind_artifact_fingerprint


Mutator = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class ContractProbe:
    schema_version: str
    accepted: dict[str, Any]
    mutate: Mutator
    expected_error: str


def _fp(label: str) -> str:
    import hashlib

    return f"sha256:{hashlib.sha256(label.encode('utf-8')).hexdigest()}"


def build_physical_safety_case(
    *,
    method: str = "simulation",
    requested_level: str | None = None,
) -> dict[str, Any]:
    """Build a complete one-hazard safety case for executable probes."""

    if requested_level is None:
        if method == "independent_assessment":
            requested_level = "independent_evidence_ready"
        elif method == "simulation":
            requested_level = "simulation_only"
        else:
            requested_level = "evidence_ready"

    method_reference = {
        "simulation": "simulation",
        "bench": "laboratory",
        "hardware_in_loop": "hardware_in_loop",
        "field_observation": "field_observation",
        "independent_assessment": "independent_assessment",
    }[method]
    test_source_kind = "independent_assessor" if method == "independent_assessment" else "human_directed_software"
    evidence_labels = (
        "extreme-low",
        "extreme-high",
        "controller",
        "isolation",
        "test-suite",
        "plain-language",
        "limitations",
        "contestability",
        "local-stop",
        "secure-boot",
        "signed-update",
        "credentials",
        "sbom",
        "vulnerability-process",
        "ledger",
    )
    evidence: list[dict[str, Any]] = []
    for label in evidence_labels:
        source_kind = test_source_kind if label == "test-suite" else "human_directed_software"
        reference_class = method_reference if label == "test-suite" else "laboratory"
        evidence.append(
            {
                "evidence_id": f"evidence:{label}",
                "kind": label,
                "fingerprint": _fp(f"physical-safety:{method}:{label}"),
                "source_kind": source_kind,
                "source_ref": f"source:{label}",
                "reference_class": reference_class,
                "captured_at": "2026-07-13T10:00:00+00:00",
            }
        )

    scenarios = (
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
    )
    tests = [
        {
            "test_id": f"test:{scenario.replace('_', '-')}",
            "hazard_refs": ["hazard:unintended-motion"],
            "scenario": scenario,
            "method": method,
            "result": "passed",
            "expected_safe_state": "Hazardous energy is isolated and motion is stopped.",
            "observed_safe_state": "Hazardous energy is isolated and motion is stopped.",
            "hazardous_actuation_observed": False,
            "evidence_refs": ["evidence:test-suite"],
        }
        for scenario in scenarios
    ]

    reference_classes = [method_reference]
    if "simulation" not in reference_classes:
        reference_classes.append("simulation")
    payload: dict[str, Any] = {
        "schema_version": "core.physical_safety_assurance_case.v1",
        "type": "physical_safety_assurance_case",
        "case_id": "safety-case:domestic-actuator-v1",
        "system": {
            "system_id": "system:domestic-actuator",
            "system_version": "1.0.0",
            "release_fingerprint": _fp("release:domestic-actuator:1.0.0"),
            "deployment_fingerprint": _fp("deployment:lab-bench:001"),
            "physical_actuation": True,
        },
        "claim": {
            "claim_status": "observed",
            "truth_claim": False,
            "zero_risk_claim": False,
            "scope": "This case covers the declared actuator, release, deployment, hazards, and evidence envelope only.",
            "assumptions": [
                "The recorded hardware identifiers match the evaluated deployment.",
                "Evidence fingerprints resolve to immutable local artifacts.",
            ],
            "limitations": [
                "Unobserved extremes and changed components remain unknown.",
                "Passing this gate does not authorize deployment.",
            ],
            "reference_classes": reference_classes,
        },
        "observed_envelope": {
            "aggregation": "mixed",
            "sample_count": 100,
            "average_only": False,
            "known_extremes": [
                {
                    "extreme_id": "extreme:minimum-load",
                    "direction": "lower",
                    "value": 0,
                    "unit": "percent_load",
                    "source_ref": "source:lab-bench",
                    "evidence_ref": "evidence:extreme-low",
                    "observed_at": "2026-07-13T09:00:00+00:00",
                },
                {
                    "extreme_id": "extreme:adversarial-maximum",
                    "direction": "adversarial",
                    "value": 100,
                    "unit": "percent_load",
                    "source_ref": "source:adversarial-bench",
                    "evidence_ref": "evidence:extreme-high",
                    "observed_at": "2026-07-13T09:30:00+00:00",
                },
            ],
            "out_of_distribution_policy": "fail_closed",
            "unknown_extremes_acknowledged": True,
            "records_are_observed_bounds_only": True,
        },
        "authority_boundary": {
            "llm_role": "advisory_only",
            "direct_llm_actuation": False,
            "general_compute_direct_actuation": False,
            "core_role": "deterministic_validation_only",
            "core_authorizes_deployment": False,
            "responsible_party_ref": "responsible-party:system-owner",
        },
        "hazards": [
            {
                "hazard_id": "hazard:unintended-motion",
                "severity": "catastrophic",
                "hazardous_action": "Unexpected movement while a person is inside the reachable work envelope.",
                "safe_state": "Hazardous energy is isolated and motion is stopped.",
                "barrier_refs": ["barrier:safety-controller", "barrier:energy-isolation"],
                "test_refs": [item["test_id"] for item in tests],
            }
        ],
        "barriers": [
            {
                "barrier_id": "barrier:safety-controller",
                "kind": "isolated_safety_controller",
                "enforcement_domain": "isolated_controller",
                "independent_from": ["barrier:energy-isolation"],
                "fail_closed": True,
                "llm_controlled": False,
                "bypassable_by_general_compute": False,
                "evidence_refs": ["evidence:controller"],
            },
            {
                "barrier_id": "barrier:energy-isolation",
                "kind": "physical_energy_isolation",
                "enforcement_domain": "electrical_hardware",
                "independent_from": ["barrier:safety-controller"],
                "fail_closed": True,
                "llm_controlled": False,
                "bypassable_by_general_compute": False,
                "evidence_refs": ["evidence:isolation"],
            },
        ],
        "verification_tests": tests,
        "epistemic_dignity": {
            "plain_language_disclosure_ref": "evidence:plain-language",
            "evidence_limitations_ref": "evidence:limitations",
            "contestability_ref": "evidence:contestability",
            "local_stop_ref": "evidence:local-stop",
            "technical_expertise_required_to_stop": False,
            "uncertainty_disclosed": True,
            "challenge_response_policy": "answer_with_evidence_or_explicit_unknown",
            "automated_moral_authority": False,
        },
        "lifecycle": {
            "secure_boot_evidence_ref": "evidence:secure-boot",
            "signed_update_evidence_ref": "evidence:signed-update",
            "unique_credentials_evidence_ref": "evidence:credentials",
            "sbom_evidence_ref": "evidence:sbom",
            "vulnerability_process_evidence_ref": "evidence:vulnerability-process",
            "safety_policy_fingerprint": _fp("policy:physical-safety:v1"),
            "change_invalidates_assurance": True,
        },
        "evidence": evidence,
        "traceability": {
            "immutable_event_ledger_ref": "evidence:ledger",
            "recorded_event_types": [
                "safety_policy_changed",
                "hazardous_command_rejected",
                "safety_interlock_activated",
                "unexpected_physical_outcome",
                "assurance_invalidated",
                "emergency_stop_activated",
                "security_boundary_breached",
            ],
            "ordinary_telemetry_excluded": True,
        },
        "requested_assurance_level": requested_level,
        "evaluated_at": "2026-07-13T12:00:00+00:00",
        "fingerprint": _fp("placeholder"),
    }
    return bind_artifact_fingerprint(payload)


def accepted_contract_payloads() -> dict[str, dict[str, Any]]:
    """Return one semantically coherent artifact per executable contract."""

    payloads: dict[str, dict[str, Any]] = {
        "core.causal_trace.v1": {
            "schema_version": "core.causal_trace.v1",
            "type": "causal_trace",
            "trace_id": "trace:001",
            "root_ref": "decision:001",
            "nodes": [
                {"node_id": "node:decision", "kind": "decision", "ref": "decision:001"},
                {"node_id": "node:receipt", "kind": "receipt", "ref": "receipt:001"},
            ],
            "edges": [{"from_ref": "decision:001", "to_ref": "receipt:001", "relation": "produces"}],
            "source_refs": ["source:intent:001"],
            "evidence_refs": ["evidence:decision:001"],
            "created_at": "2026-07-13T00:00:00+00:00",
            "fingerprint": _fp("placeholder"),
        },
        "core.context_gate.v1": {
            "schema_version": "core.context_gate.v1",
            "status": "passed",
            "source_type": "workflow",
            "source_id": "workflow:001",
            "mode": "dry-run",
            "reason": "threshold_exceeded",
            "proposed_action": "compress",
        },
        "core.context_threshold.v1": {
            "schema_version": "core.context_threshold.v1",
            "status": "passed",
            "source_type": "workflow",
            "source_id": "workflow:001",
            "should_compress_now": True,
            "reason": "usage_at_or_above_threshold",
            "current_usage_percent": 85,
            "previous_usage_percent": 75,
            "ema_usage_percent": 80,
            "compression_threshold_percent": 80,
            "recommended_action": "compress",
        },
        "core.control_decision.v1": {
            "schema_version": "core.control_decision.v1",
            "type": "control_decision",
            "decision_id": "decision:001",
            "intent_ref": "intent:001",
            "target_ref": "target:001",
            "decision": "require_confirmation",
            "reason": "irreversible_action",
            "policy_refs": ["policy:001"],
            "entropy_signal_refs": [],
            "reversibility_class": "irreversible",
            "evidence_required": ["responsible_approval"],
            "source_refs": ["source:intent:001"],
            "evidence_refs": ["evidence:approval:001"],
            "created_at": "2026-07-13T00:00:00+00:00",
            "fingerprint": _fp("placeholder"),
        },
        "core.effect_result.v1": {
            "schema_version": "core.effect_result.v1",
            "status": "dry_run",
            "effect_type": "notification",
            "dry_run": True,
            "reason": "operator_preview",
            "provider": "local",
            "target_ref": "operator:001",
        },
        "core.entropy_signal.v1": {
            "schema_version": "core.entropy_signal.v1",
            "type": "entropy_signal",
            "signal_id": "signal:001",
            "source_type": "workflow",
            "source_id": "workflow:001",
            "signal_type": "missing_evidence",
            "severity": "high",
            "confidence": 0.9,
            "measurement": {"missing_count": 1},
            "suggested_response": "manual_review",
            "source_refs": ["source:workflow:001"],
            "evidence_refs": ["evidence:gap:001"],
            "timestamp": "2026-07-13T00:00:00+00:00",
            "fingerprint": _fp("placeholder"),
        },
        "core.execution_receipt.v1": {
            "schema_version": "core.execution_receipt.v1",
            "type": "execution_receipt",
            "receipt_id": "receipt:001",
            "executor_ref": "executor:bounded:001",
            "decision_ref": "decision:001",
            "command_ref": "command:001",
            "status": "succeeded",
            "state_transition_refs": ["transition:001"],
            "evidence_refs": ["evidence:receipt:001"],
            "source_refs": ["source:command:001"],
            "created_at": "2026-07-13T00:00:00+00:00",
            "fingerprint": _fp("placeholder"),
        },
        "core.memory_artifact.v1": {
            "schema_version": "core.memory_artifact.v1",
            "memory_id": "memory:001",
            "source_refs": ["source:run:001"],
            "authority": "reference_only",
            "summary": "Bounded run summary.",
            "stable_facts": ["A fixture passed its declared validator."],
            "decisions": [],
            "invariants": ["No execution authority is stored in memory."],
            "open_risks": ["Unobserved cases remain unknown."],
            "next_actions": ["Review the bounded evidence."],
            "retention": {"retention_class": "keep", "reason": "Supports replay."},
            "created_at": "2026-07-13T00:00:00+00:00",
        },
        "core.memory_generation_result.v1": {
            "schema_version": "core.memory_generation_result.v1",
            "status": "passed",
            "source_type": "run",
            "source_id": "run:001",
            "reused": False,
            "memory_id": "memory:001",
            "memory_ref": "artifact:memory:001",
            "reason": "generated",
        },
        "core.operational_learning_event.v1": {
            "schema_version": "core.operational_learning_event.v1",
            "event_id": "learning:001",
            "event_type": "candidate_observed",
            "source_type": "run",
            "source_id": "run:001",
            "status": "candidate",
            "timestamp": "2026-07-13T00:00:00+00:00",
            "payload": {"candidate_ref": "pattern:001", "authority": "advisory_only"},
            "source_refs": ["source:run:001"],
        },
        "core.pattern_candidate.v1": {
            "schema_version": "core.pattern_candidate.v1",
            "type": "pattern_candidate",
            "pattern_id": "pattern:001",
            "source_type": "run",
            "source_id": "run:001",
            "classification": "candidate_for_template",
            "confidence": 0.9,
            "occurrences": 3,
            "normalized_signature": {"operation": "bounded_read"},
            "source_refs": ["source:run:001"],
            "example_refs": ["example:001", "example:002"],
            "suggested_action": "request_responsible_review",
            "observed_at": "2026-07-13T00:00:00+00:00",
            "evidence_refs": ["evidence:pattern:001"],
        },
        "core.policy_lifecycle.v1": {
            "schema_version": "core.policy_lifecycle.v1",
            "type": "policy_lifecycle",
            "policy_id": "policy:001",
            "policy_version": "1.0.0",
            "status": "active",
            "effective_from": "2026-07-13T00:00:00+00:00",
            "effective_to": None,
            "supersedes": None,
            "scope": {"system": "system:001"},
            "change_reason": "initial_release",
            "approval_refs": ["approval:001"],
            "fingerprint": _fp("placeholder"),
        },
        "core.retention_manifest.v1": {
            "schema_version": "core.retention_manifest.v1",
            "entries": [
                {
                    "source_type": "run",
                    "source_id": "run:001",
                    "artifact_ref": "artifact:evidence:001",
                    "retention_class": "keep",
                    "reason": "Supports replay and accountability.",
                }
            ],
        },
        "core.reversibility_policy.v1": {
            "schema_version": "core.reversibility_policy.v1",
            "type": "reversibility_policy",
            "policy_id": "policy:reversibility:001",
            "action_family": "physical_actuation",
            "reversibility_class": "irreversible",
            "compensation_required": False,
            "human_approval_required": True,
            "stop_conditions": ["uncertainty_detected"],
            "evidence_required": ["responsible_approval", "safety_interlock"],
            "notes": ["Approval does not override a CORE rejection."],
            "source_refs": ["source:policy:001"],
            "evidence_refs": ["evidence:policy:001"],
            "created_at": "2026-07-13T00:00:00+00:00",
            "fingerprint": _fp("placeholder"),
        },
        "core.state_transition.v1": {
            "schema_version": "core.state_transition.v1",
            "type": "state_transition",
            "transition_id": "transition:001",
            "source_type": "system",
            "source_id": "system:001",
            "before_ref": "state:armed",
            "after_ref": "state:safe",
            "cause_refs": ["cause:emergency-stop"],
            "effect_refs": ["effect:energy-isolated"],
            "actor_kind": "human_operator",
            "timestamp": "2026-07-13T00:00:00+00:00",
            "reversibility_class": "irreversible",
            "source_refs": ["source:operator:001"],
            "evidence_refs": ["evidence:transition:001"],
            "fingerprint": _fp("placeholder"),
        },
        "core.task_closeout.v1": {
            "schema_version": "core.task_closeout.v1",
            "status": "passed",
            "source_type": "task",
            "source_id": "task:001",
            "summary": "Task completed with bounded evidence.",
            "report_ref": "report:task:001",
            "next_context_action": "none",
        },
        "core.template_promotion_candidate.v1": {
            "schema_version": "core.template_promotion_candidate.v1",
            "type": "template_promotion_candidate",
            "template_candidate_id": "template:001",
            "source_pattern_id": "pattern:001",
            "required_inputs": ["bounded_source"],
            "output_contract": "core.contract_evaluation.v1",
            "expected_evidence": ["accepted_probe", "semantic_negative_probe"],
            "risk_tier": "high",
            "stop_conditions": ["missing_evidence", "scope_expansion"],
            "human_approval_required": True,
            "source_refs": ["source:pattern:001"],
        },
        "core.physical_safety_assurance_case.v1": build_physical_safety_case(),
    }
    for version in (
        "core.causal_trace.v1",
        "core.control_decision.v1",
        "core.entropy_signal.v1",
        "core.execution_receipt.v1",
        "core.policy_lifecycle.v1",
        "core.reversibility_policy.v1",
        "core.state_transition.v1",
    ):
        payloads[version] = bind_artifact_fingerprint(payloads[version])
    return payloads


def _rebind(payload: dict[str, Any]) -> None:
    if "fingerprint" in payload:
        payload["fingerprint"] = bind_artifact_fingerprint(payload)["fingerprint"]


def executable_contract_probes() -> tuple[ContractProbe, ...]:
    """Return schema-valid mutations that must fail semantic evaluation."""

    accepted = accepted_contract_payloads()

    def causal(payload: dict[str, Any]) -> None:
        payload["edges"][0]["to_ref"] = "receipt:missing"
        _rebind(payload)

    def context_gate(payload: dict[str, Any]) -> None:
        payload["mode"] = "apply"
        payload["status"] = "applied"

    def context_threshold(payload: dict[str, Any]) -> None:
        payload["should_compress_now"] = False

    def control(payload: dict[str, Any]) -> None:
        payload["decision"] = "allow"
        _rebind(payload)

    def effect(payload: dict[str, Any]) -> None:
        payload["status"] = "applied"

    def entropy(payload: dict[str, Any]) -> None:
        payload["measurement"] = {}
        _rebind(payload)

    def receipt(payload: dict[str, Any]) -> None:
        payload["status"] = "simulated"
        _rebind(payload)

    def memory(payload: dict[str, Any]) -> None:
        payload["retention"]["retention_class"] = "forget"

    def memory_result(payload: dict[str, Any]) -> None:
        payload["reused"] = True
        payload.pop("memory_ref")

    def learning(payload: dict[str, Any]) -> None:
        payload["payload"]["auto_execute"] = True

    def pattern(payload: dict[str, Any]) -> None:
        payload["classification"] = "too_ambiguous"
        payload["suggested_action"] = "auto_promote_template"

    def policy(payload: dict[str, Any]) -> None:
        payload["effective_to"] = "2026-07-12T00:00:00+00:00"
        _rebind(payload)

    def retention(payload: dict[str, Any]) -> None:
        payload["entries"].append(copy.deepcopy(payload["entries"][0]))

    def reversibility(payload: dict[str, Any]) -> None:
        payload["human_approval_required"] = False
        _rebind(payload)

    def transition(payload: dict[str, Any]) -> None:
        payload["after_ref"] = payload["before_ref"]
        _rebind(payload)

    def closeout(payload: dict[str, Any]) -> None:
        payload.pop("report_ref")

    def promotion(payload: dict[str, Any]) -> None:
        payload["human_approval_required"] = False

    def safety(payload: dict[str, Any]) -> None:
        removed = payload["verification_tests"].pop()
        payload["hazards"][0]["test_refs"].remove(removed["test_id"])
        _rebind(payload)

    specs: tuple[tuple[str, Mutator, str], ...] = (
        ("core.causal_trace.v1", causal, "dangling_edge_ref"),
        ("core.context_gate.v1", context_gate, "apply_result_required"),
        ("core.context_threshold.v1", context_threshold, "threshold_decision_mismatch"),
        ("core.control_decision.v1", control, "unsafe_allow_decision"),
        ("core.effect_result.v1", effect, "effect_status_dry_run_mismatch"),
        ("core.entropy_signal.v1", entropy, "measurement_required"),
        ("core.execution_receipt.v1", receipt, "simulated_transition_forbidden"),
        ("core.memory_artifact.v1", memory, "unsafe_memory_forgetting"),
        ("core.memory_generation_result.v1", memory_result, "reused_memory_reference_required"),
        ("core.operational_learning_event.v1", learning, "learning_event_authority_escalation"),
        ("core.pattern_candidate.v1", pattern, "ambiguous_pattern_cannot_promote"),
        ("core.physical_safety_assurance_case.v1", safety, "required_scenario_missing"),
        ("core.policy_lifecycle.v1", policy, "invalid_effective_interval"),
        ("core.retention_manifest.v1", retention, "duplicate_artifact_ref"),
        ("core.reversibility_policy.v1", reversibility, "responsible_approval_required"),
        ("core.state_transition.v1", transition, "state_transition_noop"),
        ("core.task_closeout.v1", closeout, "closeout_evidence_required"),
        ("core.template_promotion_candidate.v1", promotion, "promotion_approval_required"),
    )
    return tuple(
        ContractProbe(
            schema_version=version,
            accepted=copy.deepcopy(accepted[version]),
            mutate=mutator,
            expected_error=expected_error,
        )
        for version, mutator, expected_error in specs
    )
