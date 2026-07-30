from __future__ import annotations

import argparse
import glob
import json
import tempfile
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core_runtime.core.audit_event import compute_operational_fingerprint  # noqa: E402
from core_runtime.tooling.release_check import SubprocessCapture  # noqa: E402

# ── Target-based gate exclusions ──────────────────────────────────
# Checks introduced in v7.0+ are excluded when --target v6.9 is used.
V7_CHECKS: set[str] = {
    "protocol_model_preintegration_package",
    "protocol_model_preintegration_readiness",
    "expert_conflict_bundle_validation",
    "pre_resolution_protocol_validation",
    "pre_resolution_report_validation",
    "human_escalation_decision_validation",
}

V8_CHECKS: set[str] = {
    "agent_session_valid_deterministic",
    "agent_session_rejects_unbounded_context",
    "agent_session_rejects_tool_execution",
    "agent_session_requires_human_approval",
}

V81_CHECKS: set[str] = {
    "agent_plan_accepted_deterministic",
    "agent_plan_rejects_autonomous_execution",
    "agent_plan_rejects_circular_dependency",
    "agent_plan_rejects_parallel_side_effects",
    "agent_plan_rejects_private_path",
}

V82_CHECKS: set[str] = {
    "tool_invocation_accepted_deterministic",
    "tool_invocation_rejects_autonomous_execution",
    "tool_invocation_rejects_risky_no_approval",
    "tool_invocation_rejects_nested_arguments",
    "tool_invocation_rejects_private_path",
}

V83_CHECKS: set[str] = {
    "agent_decision_trace_accepted_deterministic",
    "agent_decision_trace_rejects_non_contiguous_ids",
    "agent_decision_trace_rejects_review_not_set",
    "agent_decision_trace_rejects_immutability_false",
    "agent_decision_trace_rejects_non_monotonic_timestamps",
    "agent_decision_trace_rejects_summary_count_mismatch",
}

AGENT_DECISION_TRACE_CHECKS = {
    "agent_decision_trace_accepted_deterministic": [
        sys.executable,
        "scripts/validate_agent_decision_trace.py",
        "examples/agent_traces/accepted_linear_trace.json",
    ],
    "agent_decision_trace_rejects_non_contiguous_ids": [
        sys.executable,
        "scripts/validate_agent_decision_trace.py",
        "examples/agent_traces/rejected_non_contiguous_ids.json",
    ],
    "agent_decision_trace_rejects_review_not_set": [
        sys.executable,
        "scripts/validate_agent_decision_trace.py",
        "examples/agent_traces/rejected_review_not_set.json",
    ],
    "agent_decision_trace_rejects_immutability_false": [
        sys.executable,
        "scripts/validate_agent_decision_trace.py",
        "examples/agent_traces/rejected_immutability_false.json",
    ],
    "agent_decision_trace_rejects_non_monotonic_timestamps": [
        sys.executable,
        "scripts/validate_agent_decision_trace.py",
        "examples/agent_traces/rejected_non_monotonic_timestamps.json",
    ],
    "agent_decision_trace_rejects_summary_count_mismatch": [
        sys.executable,
        "scripts/validate_agent_decision_trace.py",
        "examples/agent_traces/rejected_summary_count_mismatch.json",
    ],
}

V84_CHECKS = {
    "downstream_bridge_adapter_accepted_strict",
    "downstream_bridge_adapter_accepted_emergency",
    "downstream_bridge_adapter_rejects_autonomous_execution",
    "downstream_bridge_adapter_rejects_private_namespace_leak",
    "downstream_bridge_adapter_rejects_fail_closed_false",
}

V85_CHECKS = {
    "agent_boundary_freeze_accepted",
}

V90_CHECKS = {
    "anchoring_submission_accepted_freeze",
    "anchoring_submission_accepted_manifest",
    "anchoring_submission_rejected_not_frozen",
    "anchoring_submission_rejected_hash_mismatch",
    "anchoring_submission_rejected_private_data",
}

V92_CHECKS = {
    "chain_adapter_ethereum_sepolia_accepted",
    "chain_adapter_polygon_mainnet_accepted",
    "chain_adapter_arbitrum_one_accepted",
    "chain_adapter_local_devnet_accepted",
    "chain_adapter_rejected_unsupported_family",
    "chain_adapter_rejected_local_rpc_mainnet",
    "chain_adapter_rejected_mainnet_low_confirmations",
    "chain_adapter_rejected_fingerprint_mismatch",
}

V93_CHECKS = {
    "merkle_batch_build_accepted_request",
    "merkle_batch_verify_accepted_manifest",
    "merkle_batch_rejected_empty_items",
    "merkle_batch_rejected_duplicate_fingerprints",
    "merkle_batch_rejected_tampered_root",
    "merkle_batch_rejected_tampered_path",
}

V94_CHECKS = {
    "document_issuer_registry_accepted",
    "document_attestation_accepted",
    "document_attestation_rejected_unknown_issuer",
    "document_attestation_rejected_expired_attestation",
}

V95_CHECKS = {
    "process_attestation_accepted",
    "evidence_bundle_accepted",
    "process_attestation_rejected_missing_checkpoint",
    "process_attestation_rejected_missing_approval",
    "evidence_bundle_rejected_missing_receipt",
    "process_attestation_rejected_inactive_status",
}

V111_CHECKS = {
    "contract_executability_audit",
    "frozen_release_manifest_v11_1_accepted",
    "frozen_rule_set_general_accepted",
    "frozen_rule_set_personal_commitment_accepted",
    "physical_safety_assurance_evidence_ready",
    "physical_safety_assurance_rejects_absolute_claim",
    "rule_approval_general_signature_accepted",
    "rule_approval_personal_signature_accepted",
    "rule_anchor_batch_manifest_accepted",
}

DOWNSTREAM_BRIDGE_ADAPTER_CHECKS = {
    "downstream_bridge_adapter_accepted_strict": [
        sys.executable,
        "scripts/validate_downstream_bridge_adapter.py",
        "examples/bridge_adapters/accepted_strict_bridge.json",
    ],
    "downstream_bridge_adapter_accepted_emergency": [
        sys.executable,
        "scripts/validate_downstream_bridge_adapter.py",
        "examples/bridge_adapters/accepted_emergency_bridge.json",
    ],
    "downstream_bridge_adapter_rejects_autonomous_execution": [
        sys.executable,
        "scripts/validate_downstream_bridge_adapter.py",
        "examples/bridge_adapters/rejected_autonomous_execution.json",
    ],
    "downstream_bridge_adapter_rejects_private_namespace_leak": [
        sys.executable,
        "scripts/validate_downstream_bridge_adapter.py",
        "examples/bridge_adapters/rejected_private_namespace_leak.json",
    ],
    "downstream_bridge_adapter_rejects_fail_closed_false": [
        sys.executable,
        "scripts/validate_downstream_bridge_adapter.py",
        "examples/bridge_adapters/rejected_fail_closed_false.json",
    ],
}

AGENT_BOUNDARY_FREEZE_CHECKS = {
    "agent_boundary_freeze_accepted": [
        sys.executable,
        "scripts/validate_agent_boundary_freeze.py",
        "examples/freeze/freeze_v8x.json",
    ],
}

ANCHORING_SUBMISSION_CHECKS = {
    "anchoring_submission_accepted_freeze": [
        sys.executable,
        "scripts/validate_anchoring_submission.py",
        "examples/anchoring/accepted_freeze_artifact.json",
    ],
    "anchoring_submission_accepted_manifest": [
        sys.executable,
        "scripts/validate_anchoring_submission.py",
        "examples/anchoring/accepted_release_manifest.json",
    ],
    "anchoring_submission_rejected_not_frozen": [
        sys.executable,
        "scripts/validate_anchoring_submission.py",
        "examples/anchoring/rejected_not_frozen.json",
    ],
    "anchoring_submission_rejected_hash_mismatch": [
        sys.executable,
        "scripts/validate_anchoring_submission.py",
        "examples/anchoring/rejected_hash_mismatch.json",
    ],
    "anchoring_submission_rejected_private_data": [
        sys.executable,
        "scripts/validate_anchoring_submission.py",
        "examples/anchoring/rejected_private_data.json",
    ],
}

CHAIN_ADAPTER_CHECKS = {
    "chain_adapter_ethereum_sepolia_accepted": [
        sys.executable,
        "scripts/validate_chain_adapter.py",
        "examples/anchoring/chain_adapters/ethereum_sepolia_valid.json",
    ],
    "chain_adapter_polygon_mainnet_accepted": [
        sys.executable,
        "scripts/validate_chain_adapter.py",
        "examples/anchoring/chain_adapters/polygon_mainnet_valid.json",
    ],
    "chain_adapter_arbitrum_one_accepted": [
        sys.executable,
        "scripts/validate_chain_adapter.py",
        "examples/anchoring/chain_adapters/arbitrum_one_valid.json",
    ],
    "chain_adapter_local_devnet_accepted": [
        sys.executable,
        "scripts/validate_chain_adapter.py",
        "examples/anchoring/chain_adapters/local_devnet_valid.json",
    ],
    "chain_adapter_rejected_unsupported_family": [
        sys.executable,
        "scripts/validate_chain_adapter.py",
        "examples/anchoring/chain_adapters/rejected_unsupported_family.json",
    ],
    "chain_adapter_rejected_local_rpc_mainnet": [
        sys.executable,
        "scripts/validate_chain_adapter.py",
        "examples/anchoring/chain_adapters/rejected_local_rpc_mainnet.json",
    ],
    "chain_adapter_rejected_mainnet_low_confirmations": [
        sys.executable,
        "scripts/validate_chain_adapter.py",
        "examples/anchoring/chain_adapters/rejected_mainnet_low_confirmations.json",
    ],
    "chain_adapter_rejected_fingerprint_mismatch": [
        sys.executable,
        "scripts/validate_chain_adapter.py",
        "examples/anchoring/chain_adapters/rejected_fingerprint_mismatch.json",
    ],
}

MERKLE_BATCH_CHECKS = {
    "merkle_batch_build_accepted_request": [
        sys.executable,
        "scripts/build_merkle_batch.py",
        "examples/merkle_batch/accepted_batch_request.json",
    ],
    "merkle_batch_verify_accepted_manifest": [
        sys.executable,
        "scripts/verify_merkle_proof.py",
        "examples/merkle_batch/accepted_batch_manifest.json",
    ],
    "merkle_batch_rejected_empty_items": [
        sys.executable,
        "scripts/verify_merkle_proof.py",
        "examples/merkle_batch/rejected_empty_items.json",
    ],
    "merkle_batch_rejected_duplicate_fingerprints": [
        sys.executable,
        "scripts/verify_merkle_proof.py",
        "examples/merkle_batch/rejected_duplicate_fingerprints.json",
    ],
    "merkle_batch_rejected_tampered_root": [
        sys.executable,
        "scripts/verify_merkle_proof.py",
        "examples/merkle_batch/rejected_tampered_root.json",
    ],
    "merkle_batch_rejected_tampered_path": [
        sys.executable,
        "scripts/verify_merkle_proof.py",
        "examples/merkle_batch/rejected_tampered_path.json",
    ],
}

FROZEN_RULE_ANCHOR_CHECKS = {
    "frozen_rule_set_general_accepted": [
        sys.executable,
        "scripts/validate_frozen_rule_set.py",
        "examples/frozen_rules/general_cooperative_supply.json",
    ],
    "frozen_rule_set_personal_commitment_accepted": [
        sys.executable,
        "scripts/validate_frozen_rule_set.py",
        "examples/frozen_rules/personal_commitment.json",
    ],
    "rule_approval_general_signature_accepted": [
        sys.executable,
        "scripts/validate_rule_approval.py",
        "examples/rule_approvals/general_cooperative_supply.json",
    ],
    "rule_approval_personal_signature_accepted": [
        sys.executable,
        "scripts/validate_rule_approval.py",
        "examples/rule_approvals/personal_commitment.json",
    ],
    "rule_anchor_batch_manifest_accepted": [
        sys.executable,
        "scripts/validate_rule_anchor_batch.py",
        "examples/merkle_batch/accepted_batch_manifest.json",
    ],
}

FROZEN_RELEASE_MANIFEST_CHECKS = {
    "frozen_release_manifest_v11_1_accepted": [
        sys.executable,
        "scripts/validate_frozen_release_manifest.py",
        "examples/frozen_release_manifest/accepted_v11_1_0.json",
    ],
    "frozen_release_manifest_v11_2_candidate_accepted": [
        sys.executable,
        "scripts/validate_frozen_release_manifest_v11_2.py",
        "examples/frozen_release_manifest/accepted_v11_2_1_candidate.json",
    ],
    "frozen_release_manifest_v11_2_frozen_accepted": [
        sys.executable,
        "scripts/validate_frozen_release_manifest_v11_2_frozen.py",
        "examples/frozen_release_manifest/accepted_v11_2_1.json",
    ],
}

EXECUTABLE_CONTRACT_CHECKS = {
    "contract_executability_audit": [
        sys.executable,
        "scripts/audit_contract_executability.py",
    ],
    "physical_safety_assurance_evidence_ready": [
        sys.executable,
        "-c",
        "from core_runtime.core.contract_probes import build_physical_safety_case; "
        "from core_runtime.core.contract_evaluator import evaluate_contract_payload; "
        "r=evaluate_contract_payload(build_physical_safety_case(method='hardware_in_loop')); "
        "assert r['status']=='passed'; "
        "assert r['details']['achieved_assurance_level']=='evidence_ready'; "
        "assert r['deployment_authorized'] is False; print('PASS')",
    ],
    "physical_safety_assurance_rejects_absolute_claim": [
        sys.executable,
        "-c",
        "from core_runtime.core.contract_probes import build_physical_safety_case; "
        "from core_runtime.core.contract_evaluator import bind_artifact_fingerprint,evaluate_contract_payload; "
        "p=build_physical_safety_case(); p['claim']['scope']='Guaranteed safe in all circumstances.'; "
        "p=bind_artifact_fingerprint(p); r=evaluate_contract_payload(p); "
        "assert r['status']=='failed'; "
        "assert 'absolute_safety_claim_forbidden' in {e['code'] for e in r['errors']}; print('PASS')",
    ],
}

DOCUMENT_ATTESTATION_CHECKS = {
    "document_issuer_registry_accepted": [
        sys.executable,
        "scripts/validate_issuer_registry.py",
        "examples/document_attestation/accepted_issuer_registry.json",
    ],
    "document_attestation_accepted": [
        sys.executable,
        "scripts/validate_document_attestation.py",
        "examples/document_attestation/accepted_document_attestation.json",
        "--issuer-registry",
        "examples/document_attestation/accepted_issuer_registry.json",
    ],
    "document_attestation_rejected_unknown_issuer": [
        sys.executable,
        "scripts/validate_document_attestation.py",
        "examples/document_attestation/rejected_unknown_issuer.json",
        "--issuer-registry",
        "examples/document_attestation/accepted_issuer_registry.json",
    ],
    "document_attestation_rejected_expired_attestation": [
        sys.executable,
        "scripts/validate_document_attestation.py",
        "examples/document_attestation/rejected_expired_attestation.json",
        "--issuer-registry",
        "examples/document_attestation/accepted_issuer_registry.json",
    ],
}

PROCESS_ATTESTATION_CHECKS = {
    "process_attestation_accepted": [
        sys.executable,
        "scripts/validate_process_attestation.py",
        "examples/process_attestation/accepted_process_attestation.json",
    ],
    "evidence_bundle_accepted": [
        sys.executable,
        "scripts/validate_evidence_bundle.py",
        "examples/process_attestation/accepted_evidence_bundle.json",
    ],
    "process_attestation_rejected_missing_checkpoint": [
        sys.executable,
        "scripts/validate_process_attestation.py",
        "examples/process_attestation/rejected_missing_checkpoint.json",
    ],
    "process_attestation_rejected_missing_approval": [
        sys.executable,
        "scripts/validate_process_attestation.py",
        "examples/process_attestation/rejected_missing_approval.json",
    ],
    "process_attestation_rejected_inactive_status": [
        sys.executable,
        "scripts/validate_process_attestation.py",
        "examples/process_attestation/rejected_inactive_status.json",
    ],
    "evidence_bundle_rejected_missing_receipt": [
        sys.executable,
        "scripts/validate_evidence_bundle.py",
        "examples/process_attestation/rejected_bundle_missing_receipt.json",
    ],
}


# ── v10+ native foundation gates ─────────────────────────────────
# Checks for v10.0 features: execution profile, OTel, lazy verification,
# composite verification (P0-B slice1).
#
# These names establish the v10.0 gate namespace. The actual feature-level
# checks (`otel_jsonl_export`, `lazy_verification_gate`, etc.) are recorded as
# `pending_runtime` until their corresponding implementations land. This is
# the structural hygiene stub mandated by CORE-V10-SCHEMA-HYGIENE-SLICE1 — it
# MUST NOT pretend unimplemented v10+ features already exist.
V10_CHECKS: set[str] = {
 "execution_profile_strategy_fields",
 "otel_jsonl_export",
 "lazy_verification_gate",
 "composite_verification_equivalence",
 "composite_verification_eligibility_gate",
 "composite_verification_cache_never_authority",
}

# Names in V10_CHECKS whose explicit implementation is scheduled for future
# v10+ slices. They are surfaced in the gate namespace but MUST NOT be
# executed as if the feature were already implemented. The execution-profile
# schema gate itself runs through EXECUTION_PROFILE_CHECKS, below, against
# the public schema artifact.
V10_PENDING_RUNTIME_NAMES: set[str] = {
 "otel_jsonl_export",
 "lazy_verification_gate",
 "composite_verification_equivalence",
 "composite_verification_eligibility_gate",
 "composite_verification_cache_never_authority",
}

# ── v10.2 lazy-verification runtime surface ─────────────────────
# These checks verify that the declared lazy-verification interval is
# consumed by the runtime surface and that the OTel export slice remains
# available as a native helper. The checks are executed for v10.2 and as
# advisory smoke tests when no specific target is requested.
V102_CHECKS: set[str] = {
    "otel_jsonl_export",
    "lazy_verification_gate",
    "lazy_verification_runtime_surface",
}

V102_CHECK_MAP: dict[str, list[str]] = {
    "otel_jsonl_export": [
        sys.executable,
        "-c",
        "import sys,json; sys.path.insert(0,'backend'); "
        "from core_runtime.execution_trace import ExecutionTrace; "
        "t=ExecutionTrace(trace_id='t1',task_id='s:mc-1',runtime_ms=1.0,"
        "oracle_runtime_ms=1.0,surrogate_runtime_ms=1.0,projection_runtime_ms=1.0,"
        "projection_iterations=1,topology_family='mc',failure_type=None,"
        "timestamp='2099-01-01T00:00:00+00:00'); "
        "obj=json.loads(t.to_otel_jsonl()); "
        "assert 'traceId' in obj and 'spanId' in obj; print('PASS')",
    ],
    "lazy_verification_gate": [
        sys.executable,
        "-c",
        "import sys; sys.path.insert(0,'core_runtime'); "
        "from core.scheduling.lazy_verification import LazyVerificationGate; "
        "e=LazyVerificationGate(strategy='eager'); "
        "assert e.should_verify(0) and e.should_verify(1); "
        "l=LazyVerificationGate(strategy='lazy',lazy_verification_interval=3); "
        "assert l.should_verify(0) and not l.should_verify(1) and l.should_verify(3); "
        "h=LazyVerificationGate(strategy='hybrid',lazy_verification_interval=4); "
        "assert h.should_verify(0) and not h.should_verify(2) and h.should_verify(4); "
        "print('PASS')",
    ],
    "lazy_verification_runtime_surface": [
        sys.executable,
        "-c",
        "import sys, torch; sys.path.insert(0,'backend'); sys.path.insert(0,'core_runtime'); "
        "from backend.circuits.dc_solver import solve_dc_circuit; "
        "from backend.circuits.graph_dataset import circuit_to_graph; "
        "from backend.circuits.models import Circuit, Resistor, VoltageSource; "
        "from backend.circuits.physics_projection import ProjectionConfig; "
        "from core_runtime.domains.circuits.projection_runtime import ProjectionRuntime; "
        "resistors=[Resistor('R1','1','2',100.0), Resistor('R2','2','3',100.0), Resistor('R3','3','0',100.0)]; "
        "vs=VoltageSource('V1', positive='1', negative='0', voltage=10.0); "
        "circuit=Circuit(name='lazy_verification_chain', ground_node='0', resistors=tuple(resistors), voltage_sources=(vs,)); "
        "solver=solve_dc_circuit(circuit); graph=circuit_to_graph(circuit, solver); "
        "init_v=torch.zeros_like(graph.target_voltages); "
        "runtime=ProjectionRuntime(ProjectionConfig(steps=5, virtual_node_enabled=True), execution_profile={'strategy':'lazy','lazy_verification_interval':3}); "
        "result=runtime.project_with_verification(graph, circuit, init_v); "
        "flags=tuple(result['verification_plan']['step_verification_flags']); "
        "reasons=tuple(result['verification_plan']['step_verification_reasons']); "
        "assert flags == (True, False, False, True, True); "
        "assert reasons == ('boundary','skipped','skipped','interval','final'); "
        "assert result['step_metrics'][0]['verification_required'] is True; "
        "assert result['step_metrics'][-1]['verification_required'] is True; print('PASS')",
    ],
}

# v10.4 slice1+2: workflow DAG + checkpoint/resume + accountability chain +
# graph IR + typed tool surface.
# These checks execute against fixture artifacts; they are NOT yet scheduled
# in any frozen release line. They are surfaced under --target v10.4 and as
# `pending_runtime` for earlier targets.
V104_CHECKS: set[str] = {
    "workflow_dag_accepted_deterministic",
    "workflow_dag_rejects_cycle",
    "workflow_dag_inline_exec_profile_accepted",
    "workflow_dag_inline_exec_profile_rejects_cycle",
    "checkpoint_record_accepted_resume",
    "checkpoint_record_accepted_accountability_linked",
    "checkpoint_record_rejects_private_path",
    "graph_ir_accepted_linear",
    "graph_ir_accepted_workflow_ref",
    "graph_ir_rejects_missing_node_ref",
    "graph_ir_rejects_duplicate_node_id",
    "graph_ir_rejects_private_path",
    "typed_tool_surface_accepted_read_only",
    "typed_tool_surface_accepted_reversible_mutation",
    "typed_tool_surface_rejects_sensitive_without_human_approval",
    "typed_tool_surface_rejects_invalid_schema_ref",
    "typed_tool_surface_rejects_private_path",
}

# v10.5 slice1: surrogate_node_descriptor contracts and link-rule
# enforcement. These checks execute against the v10.5 surrogate
# descriptor fixtures; they are NOT scheduled in any frozen release
# line. They are surfaced under --target v10.5 and as
# `pending_runtime` for earlier targets. They declare the gate
# namespace without claiming feature readiness in released branches.
V105_CHECKS: set[str] = {
    "surrogate_node_descriptor_accepted_readonly",
    "surrogate_node_descriptor_accepted_graph_linked",
    "surrogate_node_descriptor_rejects_execution_authority",
    "surrogate_node_descriptor_rejects_private_path_ref",
    "surrogate_node_descriptor_rejects_duplicate_link_rule_id",
    "surrogate_node_descriptor_rejects_missing_validation_ref",
    "surrogate_node_descriptor_rejects_irreversible_without_gate",
    "link_rule_validator_accepted_required_validation",
    "link_rule_validator_forbidden_audit",
}

V104_CHECK_MAP: dict[str, list[str]] = {
    "workflow_dag_accepted_deterministic": [
        sys.executable,
        "scripts/validate_workflow_dag.py",
        "examples/workflow_dag/accepted_workflow_profile.json",
    ],
    "workflow_dag_rejects_cycle": [
        sys.executable,
        "scripts/validate_workflow_dag.py",
        "examples/workflow_dag/rejected_workflow_cycle.json",
    ],
    "workflow_dag_inline_exec_profile_accepted": [
        sys.executable,
        "scripts/validate_execution_profile.py",
        "examples/workflow_dag/accepted_workflow_profile.json",
    ],
    "workflow_dag_inline_exec_profile_rejects_cycle": [
        sys.executable,
        "scripts/validate_execution_profile.py",
        "examples/workflow_dag/rejected_workflow_cycle.json",
    ],
    "checkpoint_record_accepted_resume": [
        sys.executable,
        "scripts/validate_checkpoint_record.py",
        "examples/checkpoint_records/accepted_resume_step.json",
    ],
    "checkpoint_record_accepted_accountability_linked": [
        sys.executable,
        "scripts/validate_checkpoint_record.py",
        "examples/checkpoint_records/accepted_accountability_linked.json",
    ],
    "checkpoint_record_rejects_private_path": [
        sys.executable,
        "scripts/validate_checkpoint_record.py",
        "examples/checkpoint_records/rejected_private_path.json",
    ],
    "graph_ir_accepted_linear": [
        sys.executable,
        "scripts/validate_graph_ir.py",
        "examples/graph_ir/accepted_linear_graph.json",
    ],
    "graph_ir_accepted_workflow_ref": [
        sys.executable,
        "scripts/validate_graph_ir.py",
        "examples/graph_ir/accepted_workflow_graph_ref.json",
    ],
    "graph_ir_rejects_missing_node_ref": [
        sys.executable,
        "scripts/validate_graph_ir.py",
        "examples/graph_ir/rejected_missing_node_ref.json",
    ],
    "graph_ir_rejects_duplicate_node_id": [
        sys.executable,
        "scripts/validate_graph_ir.py",
        "examples/graph_ir/rejected_duplicate_node_id.json",
    ],
    "graph_ir_rejects_private_path": [
        sys.executable,
        "scripts/validate_graph_ir.py",
        "examples/graph_ir/rejected_private_path.json",
    ],
    "typed_tool_surface_accepted_read_only": [
        sys.executable,
        "scripts/validate_tool_invocation.py",
        "examples/tool_invocations/accepted_typed_read_tool.json",
    ],
    "typed_tool_surface_accepted_reversible_mutation": [
        sys.executable,
        "scripts/validate_tool_invocation.py",
        "examples/tool_invocations/accepted_typed_reversible_mutation.json",
    ],
    "typed_tool_surface_rejects_sensitive_without_human_approval": [
        sys.executable,
        "scripts/validate_tool_invocation.py",
        "examples/tool_invocations/rejected_typed_sensitive_no_human_approval.json",
    ],
    "typed_tool_surface_rejects_invalid_schema_ref": [
        sys.executable,
        "scripts/validate_tool_invocation.py",
        "examples/tool_invocations/rejected_typed_invalid_schema_ref.json",
    ],
    "typed_tool_surface_rejects_private_path": [
        sys.executable,
        "scripts/validate_tool_invocation.py",
        "examples/tool_invocations/rejected_typed_private_path.json",
    ],
}

# Track the past V104 map type so maintainers can find the v10.5 block.
_intentionally_unused_marker: int = 0

V105_CHECK_MAP: dict[str, list[str]] = {
    "surrogate_node_descriptor_accepted_readonly": [
        sys.executable,
        "scripts/validate_surrogate_node_descriptor.py",
        "examples/surrogate_node_descriptors/accepted_readonly_descriptor.json",
    ],
    "surrogate_node_descriptor_accepted_graph_linked": [
        sys.executable,
        "scripts/validate_surrogate_node_descriptor.py",
        "examples/surrogate_node_descriptors/accepted_graph_linked_descriptor.json",
    ],
    # Negative checks accept the exit code (>=1) as "failed is expected".
    "surrogate_node_descriptor_rejects_execution_authority": [
        sys.executable,
        "scripts/validate_surrogate_node_descriptor.py",
        "examples/surrogate_node_descriptors/rejected_execution_authority.json",
    ],
    "surrogate_node_descriptor_rejects_private_path_ref": [
        sys.executable,
        "scripts/validate_surrogate_node_descriptor.py",
        "examples/surrogate_node_descriptors/rejected_private_path_ref.json",
    ],
    "surrogate_node_descriptor_rejects_duplicate_link_rule_id": [
        sys.executable,
        "scripts/validate_surrogate_node_descriptor.py",
        "examples/surrogate_node_descriptors/rejected_duplicate_link_rule_id.json",
    ],
    "surrogate_node_descriptor_rejects_missing_validation_ref": [
        sys.executable,
        "scripts/validate_surrogate_node_descriptor.py",
        "examples/surrogate_node_descriptors/rejected_missing_validation_ref.json",
    ],
    "surrogate_node_descriptor_rejects_irreversible_without_gate": [
        sys.executable,
        "scripts/validate_surrogate_node_descriptor.py",
        "examples/surrogate_node_descriptors/rejected_irreversible_without_gate.json",
    ],
    # Two additional ``link_rule_validator`` audit checks exercised
    # against an in-process wrapper that exercises the helper primitives
    # directly. They live as a tiny hierarchical runner alongside the
    # shared helper so the gate namespace stays consistent.
    "link_rule_validator_accepted_required_validation": [
        sys.executable,
        "-c",
        "import sys; sys.path.insert(0, '.'); from scripts.link_rule_validator import ALLOWED_RELATIONS, SENSITIVE_RELATIONS; import json; assert ALLOWED_RELATIONS and SENSITIVE_RELATIONS; print(json.dumps({'allowed_relations': sorted(ALLOWED_RELATIONS), 'sensitive_relations': sorted(SENSITIVE_RELATIONS)}, sort_keys=True))",
    ],
    "link_rule_validator_forbidden_audit": [
        sys.executable,
        "-c",
        "import sys; sys.path.insert(0, '.'); from scripts.link_rule_validator import validate_link_rule_list; errors = validate_link_rule_list([{'rule_id':'forbid_may_consult','source_ref':'core.surrogate_node:x:v1','target_ref':'core.validator:y:v1','relation':'may_consult','enforcement':'forbidden','reason':'audit'}], 'link_rules'); import json; print(json.dumps({'expected_block_count': len(errors), 'codes': sorted({e['code'] for e in errors})}, sort_keys=True)); sys.exit(1 if any(e['code']!='forbidden_authorises_authority' for e in errors) else 0)",
    ],
}

# ── execution-profile schema gate ────────────────────────────────
# Validates the public execution_profile schema artifact and its
# fixtures. This gate exists from v9.2 onwards.
EXECUTION_PROFILE_CHECKS = {
 "execution_profile_accepted_minimal": [
  sys.executable,
  "scripts/validate_execution_profile.py",
  "examples/execution_profiles/minimal_profile.json",
 ],
 "execution_profile_accepted_standard": [
  sys.executable,
  "scripts/validate_execution_profile.py",
  "examples/execution_profiles/standard_profile.json",
 ],
 "execution_profile_accepted_certified": [
  sys.executable,
  "scripts/validate_execution_profile.py",
  "examples/execution_profiles/certified_profile.json",
 ],
 "execution_profile_accepted_explainable": [
  sys.executable,
  "scripts/validate_execution_profile.py",
  "examples/execution_profiles/explainable_profile.json",
 ],
 "execution_profile_accepted_audit": [
  sys.executable,
  "scripts/validate_execution_profile.py",
  "examples/execution_profiles/audit_profile.json",
 ],
 "execution_profile_accepted_lazy_audit": [
  sys.executable,
  "scripts/validate_execution_profile.py",
  "examples/execution_profiles/lazy_audit_profile.json",
 ],
 "execution_profile_accepted_hybrid_standard": [
  sys.executable,
  "scripts/validate_execution_profile.py",
  "examples/execution_profiles/hybrid_standard_profile.json",
 ],
 "execution_profile_accepted_structural_only": [
  sys.executable,
  "scripts/validate_execution_profile.py",
  "examples/execution_profiles/structural_only_profile.json",
 ],
}

# ── v10 native feature gates ────────────────────────────────────
# Gates specific to v10.0 P0-A slice1: OTel export, lazy verification,
# and execution-profile strategy field validation.
# P0-B slice1: composite verification equivalence, eligibility, cache-never.
V10_NATIVE_CHECKS = {
 "execution_profile_strategy_fields": [
  sys.executable,
  "-c",
  "import sys; sys.path.insert(0,'core_runtime'); "
  "from core.scheduling.lazy_verification import LazyVerificationGate; "
  "g=LazyVerificationGate(strategy='lazy',lazy_verification_interval=5); "
  "assert g.should_verify(0); assert not g.should_verify(3); "
  "assert g.should_verify(5); print('PASS')",
 ],
 "otel_jsonl_export": [
  sys.executable,
  "-c",
  "import sys,json; sys.path.insert(0,'backend'); "
  "from core_runtime.execution_trace import ExecutionTrace; "
  "t=ExecutionTrace(trace_id='t1',task_id='s:mc-1',runtime_ms=1.0,"
  "oracle_runtime_ms=1.0,surrogate_runtime_ms=1.0,projection_runtime_ms=1.0,"
  "projection_iterations=1,topology_family='mc',failure_type=None,"
  "timestamp='2099-01-01T00:00:00+00:00'); "
  "obj=json.loads(t.to_otel_jsonl()); "
  "assert 'traceId' in obj and 'spanId' in obj; print('PASS')",
 ],
 "lazy_verification_gate": [
  sys.executable,
  "-c",
  "import sys; sys.path.insert(0,'core_runtime'); "
  "from core.scheduling.lazy_verification import LazyVerificationGate; "
  "e=LazyVerificationGate(strategy='eager'); "
  "assert e.should_verify(0) and e.should_verify(1); "
  "l=LazyVerificationGate(strategy='lazy',lazy_verification_interval=3); "
  "assert l.should_verify(0) and not l.should_verify(1) and l.should_verify(3); "
  "h=LazyVerificationGate(strategy='hybrid',lazy_verification_interval=4); "
  "assert h.should_verify(0) and not h.should_verify(2) and h.should_verify(4); "
  "print('PASS')",
 ],
 "composite_verification_equivalence": [
  sys.executable,
  "-c",
  "import sys,json; sys.path.insert(0,'scripts'); sys.path.insert(0,'core_runtime'); "
  "from core_runtime.core.verification.composite_verification import assert_equivalence; "
  "from pathlib import Path; "
  "r=assert_equivalence(Path('examples/expert_proposals/accepted_proposal.json'),"
  "Path('examples/execution_profiles/structural_only_profile.json')); "
  "assert r['equivalent']; assert r['eligible']; print('PASS')",
 ],
 "composite_verification_eligibility_gate": [
  sys.executable,
  "-c",
  "import sys; sys.path.insert(0,'scripts'); sys.path.insert(0,'core_runtime'); "
  "from core_runtime.core.verification.composite_verification import is_structural_only; "
  "assert is_structural_only({'requirements':{'audit_level':'structural_only'}}); "
  "assert not is_structural_only({'requirements':{'audit_level':'none'}}); "
  "assert not is_structural_only(None); assert not is_structural_only({}); "
  "print('PASS')",
 ],
 "composite_verification_cache_never_authority": [
  sys.executable,
  "-c",
  "import sys,json; sys.path.insert(0,'scripts'); sys.path.insert(0,'core_runtime'); "
  "from core_runtime.core.verification.composite_verification import composite_verify; "
  "from pathlib import Path; "
  "p=Path('examples/execution_profiles/structural_only_profile.json'); "
  "import json; orig=json.loads(p.read_text()); "
  "composite_verify(Path('examples/expert_proposals/accepted_proposal.json'),p); "
  "after=json.loads(p.read_text()); "
  "assert orig==after; print('PASS')",
 ],
}

V10_NATIVE_FLOORS = {
    "execution_profile_strategy_fields": "v10.0",
    "otel_jsonl_export": "v10.2",
    "lazy_verification_gate": "v10.2",
    "composite_verification_equivalence": "v10.3",
    "composite_verification_eligibility_gate": "v10.3",
    "composite_verification_cache_never_authority": "v10.3",
}

V103_CHECKS: set[str] = {
 "compatibility_index_schema_valid",
 "compatibility_index_cache_fingerprint",
 "compatibility_index_never_overrides_router",
 "compatibility_index_hint_propagates",
 "pdp_hint_propagates",
}

V103_CHECK_MAP: dict[str, list[str]] = {
 "compatibility_index_schema_valid": [
  sys.executable,
  "-m",
  "json.tool",
  "schemas/core/compatibility_index.v1.json",
 ],
 "compatibility_index_cache_fingerprint": [
  sys.executable,
  "scripts/compat_index_builder.py",
  "--fingerprint-check",
  "--matrix-file",
  "examples/compatibility_matrix_pairs.json",
 ],
 "compatibility_index_never_overrides_router": [
  sys.executable,
  "-c",
  "import sys; sys.path.insert(0,'core_runtime'); "
  "from core.compatibility_index import assert_cache_never_authority; "
  "assert_cache_never_authority(); print('PASS')",
 ],
 "compatibility_index_hint_propagates": [
  sys.executable,
  "-c",
  "import json,tempfile,sys; from pathlib import Path; "
  "sys.path.insert(0,'scripts'); sys.path.insert(0,'core_runtime'); "
  "from core.compatibility_index import (CompatibilityIndex, compute_cache_key, compute_hardware_profile_fingerprint, compute_policy_fingerprint, compute_profile_fingerprint, compute_proposal_fingerprint); "
  "from core.index.compatibility_index import build_index_from_matrix_file; "
  "from core_runtime.core.routing.capability_router import CapabilityRouter; "
  "from core_runtime.core.routing.execution_scheduler import ExecutionScheduler, ROUTE_STANDARD; "
  "from core_runtime.core.routing.execution_policy import ExecutionPolicy; "
  "from core_runtime.core.scheduling.confidence_runtime import ConfidenceEstimate; "
  "from core_runtime.core.runtime.task_runtime import RuntimeTask; "
  "task_type=type('T',(),{'task_id':'compatibility-index-router-smoke','domain_name':'core','input_artifact':'synthetic','metadata':{'topology_family':'radial'},'fingerprint':lambda self:'fixture:fingerprint','node_count':lambda self:3,'edge_count':lambda self:2}); "
  "task=RuntimeTask(task_id='compatibility-index-router-smoke',domain_name='core',task=task_type(),metadata={'topology_family':'radial'}); "
  "profile=json.loads(Path('examples/execution_profiles/minimal_profile.json').read_text()); "
  "proposal=json.loads(Path('examples/expert_proposals/accepted_proposal.json').read_text()); "
  "profile_fp=compute_profile_fingerprint(profile); proposal_fp=compute_proposal_fingerprint(proposal); "
  "hardware_fp=compute_hardware_profile_fingerprint(profile.get('requirements', {}).get('hardware_profile')); "
  "policy=ExecutionPolicy(); policy_fp=compute_policy_fingerprint(policy); "
  "compatibility_cache_key=compute_cache_key(profile_fp, proposal_fp, hardware_fp, policy_fp); "
  "tmpdir=tempfile.TemporaryDirectory(); "
  "index_dir=Path(tmpdir.name) / 'compatibility_index'; "
  "entries,_summary=build_index_from_matrix_file(Path('examples/compatibility_matrix_pairs.json'), output_dir=index_dir, built_at='2099-01-01T00:00:00Z'); "
  "index=CompatibilityIndex(base_dir=index_dir); "
  "[index.put(entry) for entry in entries]; "
  "confidence=ConfidenceEstimate(confidence_score=0.91, estimated_projection_iterations=3, likely_ood=False); "
  "router=CapabilityRouter(policy=policy); "
  "route=router.route(task, confidence, cache_hit=False, retrieval_similarity=0.0, compatibility_index=index, compatibility_cache_key=compatibility_cache_key); "
  "scheduler=ExecutionScheduler(policy=policy); "
  "schedule=scheduler.schedule(task, cache_hit=False, retrieval_similarity=0.0, is_degraded=False, node_count=task.node_count(), edge_count=task.edge_count(), current_sources=0, resistance_range=(1.0, 1.0), compatibility_index=index, compatibility_cache_key=compatibility_cache_key); "
  "assert route.action == 'standard_projection'; assert schedule.route == ROUTE_STANDARD; "
  "assert route.compatibility_index_hit is True; assert schedule.compatibility_index_hit is True; "
  "assert route.compatibility_index_result == {'status':'compatible','incompatible_reason':None,'profile_name':'minimal','proposal_decision':'certified'}; "
  "assert schedule.compatibility_index_result == route.compatibility_index_result; "
  "assert 'compatibility_index=hit' in route.reason; assert 'compatibility_index=hit' in schedule.reason; "
  "tmpdir.cleanup(); print('PASS')",
 ],
 "pdp_hint_propagates": [
  sys.executable,
  "-c",
  "from core_runtime.core.policy import PolicyEngine, PolicyParser; "
  "from core_runtime.core.routing.capability_router import CapabilityRouter; "
  "from core_runtime.core.routing.execution_scheduler import ExecutionScheduler, ROUTE_CACHE_HIT, ROUTE_STANDARD; "
  "from core_runtime.core.routing.execution_policy import ExecutionPolicy; "
  "from core_runtime.core.runtime.task_runtime import RuntimeTask; "
  "from core_runtime.core.scheduling.confidence_runtime import ConfidenceEstimate; "
  "dsl='''[policy]\\npolicy_id = core.policy:routing_v1\\nversion = 1.0.0\\ndescription = Policy for scheduler/router advisory integration\\n\\n[rule.allow_high_similarity]\\ncondition = retrieval_similarity >= 0.7\\ndecision = allow\\nreason = High similarity may proceed\\nreversibility_class = reversible\\n'''; "
  "task_type=type('T',(),{'task_id':'policy-router-smoke','domain_name':'core','input_artifact':'synthetic','metadata':{'topology_family':'radial'},'fingerprint':lambda self:'fixture:fingerprint','node_count':lambda self:3,'edge_count':lambda self:2}); "
  "task=RuntimeTask(task_id='policy-router-smoke',domain_name='core',task=task_type(),metadata={'topology_family':'radial'}); "
  "policy_engine=PolicyEngine(PolicyParser().parse(dsl)); "
  "confidence=ConfidenceEstimate(confidence_score=0.82, estimated_projection_iterations=3, likely_ood=False); "
  "policy_context={'retrieval_similarity':0.85,'likely_ood':False}; "
  "router=CapabilityRouter(policy=ExecutionPolicy()); "
  "route=router.route(task, confidence, cache_hit=False, retrieval_similarity=0.0, policy_engine=policy_engine, policy_context=policy_context, policy_context_ref='ctx:policy:001'); "
  "scheduler=ExecutionScheduler(policy=ExecutionPolicy()); "
  "schedule=scheduler.schedule(task, cache_hit=False, retrieval_similarity=0.0, is_degraded=False, node_count=task.node_count(), edge_count=task.edge_count(), current_sources=0, resistance_range=(1.0, 1.0), policy_engine=policy_engine, policy_context=policy_context, policy_context_ref='ctx:policy:001'); "
  "assert route.action == 'standard_projection'; assert schedule.route == ROUTE_STANDARD; "
  "assert route.policy_decision_hit is True; assert schedule.policy_decision_hit is True; "
  "assert route.policy_decision_result['decision'] == 'allow'; assert schedule.policy_decision_result['decision'] == 'allow'; "
  "assert 'policy_decision=allow' in route.reason; assert 'policy_decision=allow' in schedule.reason; "
  "cache_route=router.route(task, confidence, cache_hit=True, retrieval_similarity=0.0, policy_engine=policy_engine, policy_context=policy_context, policy_context_ref='ctx:policy:cache'); "
  "cache_schedule=scheduler.schedule(task, cache_hit=True, retrieval_similarity=0.0, is_degraded=False, node_count=task.node_count(), edge_count=task.edge_count(), current_sources=0, resistance_range=(1.0, 1.0), policy_engine=policy_engine, policy_context=policy_context, policy_context_ref='ctx:policy:cache'); "
  "assert cache_route.action == 'exact_cache_hit'; assert cache_schedule.route == ROUTE_CACHE_HIT; "
  "assert cache_route.policy_decision_hit is False; assert cache_schedule.policy_decision_hit is False; "
  "assert cache_route.policy_decision_result is None; assert cache_schedule.policy_decision_result is None; print('PASS')",
 ],
}

TARGET_EXCLUSIONS: dict[str, set[str]] = {
    "v6.9": V7_CHECKS | V8_CHECKS | V81_CHECKS | V82_CHECKS | V83_CHECKS | V84_CHECKS | V85_CHECKS | V90_CHECKS | V92_CHECKS | V93_CHECKS | V94_CHECKS | V95_CHECKS,
    "v7.8": V8_CHECKS | V81_CHECKS | V82_CHECKS | V83_CHECKS | V84_CHECKS | V85_CHECKS | V90_CHECKS | V92_CHECKS | V93_CHECKS | V94_CHECKS | V95_CHECKS,
    "v8.0": V81_CHECKS | V82_CHECKS | V83_CHECKS | V84_CHECKS | V85_CHECKS | V90_CHECKS | V92_CHECKS | V93_CHECKS | V94_CHECKS | V95_CHECKS,
    "v8.1": V82_CHECKS | V83_CHECKS | V84_CHECKS | V85_CHECKS | V90_CHECKS | V92_CHECKS | V93_CHECKS | V94_CHECKS | V95_CHECKS,
    "v8.2": V83_CHECKS | V84_CHECKS | V85_CHECKS | V90_CHECKS | V92_CHECKS | V93_CHECKS | V94_CHECKS | V95_CHECKS,
    "v8.3": V84_CHECKS | V85_CHECKS | V90_CHECKS | V92_CHECKS | V93_CHECKS | V94_CHECKS | V95_CHECKS,
    "v8.4": V85_CHECKS | V90_CHECKS | V92_CHECKS | V93_CHECKS | V94_CHECKS | V95_CHECKS,
    "v8.5": V90_CHECKS | V92_CHECKS | V93_CHECKS | V94_CHECKS | V95_CHECKS,
    "v9.0": V92_CHECKS | V93_CHECKS | V94_CHECKS | V95_CHECKS,
    "v9.1": V92_CHECKS | V93_CHECKS | V94_CHECKS | V95_CHECKS,
    "v9.2": V93_CHECKS | V94_CHECKS | V95_CHECKS,
    "v9.3": V94_CHECKS | V95_CHECKS,
    "v9.4": V95_CHECKS,
    "v9.5": set(),
}

TARGET_ORDER = [
    "v6.9",
    "v7.8",
    "v8.0",
    "v8.1",
    "v8.2",
    "v8.3",
    "v8.4",
    "v8.5",
    "v9.0",
    "v9.1",
    "v9.2",
    "v9.3",
    "v9.4",
    "v9.5",
    "v10.0",
    "v10.0.1",
    "v10.1",
    "v10.2",
    "v10.3",
    "v10.4",
    "v10.5",
    "v11.0",
    "v11.0.1",
    "v11.1",
    "v11.2",
]

TARGET_RANK = {name: index for index, name in enumerate(TARGET_ORDER)}


def _target_at_least(target: str | None, floor: str) -> bool:
    if target is None:
        return True
    def numeric_version(value: str) -> tuple[int, int, int]:
        parts = value.removeprefix("v").split(".")
        if not 2 <= len(parts) <= 3 or not all(part.isdigit() for part in parts):
            return (-1, -1, -1)
        numbers = [int(part) for part in parts]
        while len(numbers) < 3:
            numbers.append(0)
        return (numbers[0], numbers[1], numbers[2])

    return numeric_version(target) >= numeric_version(floor)


BRIDGES = {
    "audio_bridge": {
        "adapter": "examples/adapters/audio_envelope_wav",
        "fixture": "examples/adapters/audio_envelope_wav/fixtures/audio_envelope_wav_v1",
    },
    "image_bridge": {
        "adapter": "examples/adapters/image_brightness_motion",
        "fixture": "examples/adapters/image_brightness_motion/fixtures/image_brightness_motion_v1",
    },
    "wifi_csi_bridge": {
        "adapter": "examples/adapters/wifi_csi_synthetic_bridge",
        "fixture": "examples/adapters/wifi_csi_synthetic_bridge/fixtures/wifi_csi_synthetic_v1",
    },
}

CLASSIFICATION_CANDIDATE_CHECKS = {
 "classification_candidate_accepted_deterministic": [
 sys.executable,
 "scripts/validate_classification_candidate.py",
 "examples/classification_candidates/accepted.json",
 ],
 "classification_candidate_clarification_required_deterministic": [
 sys.executable,
 "scripts/validate_classification_candidate.py",
 "examples/classification_candidates/clarification_required.json",
 ],
 "classification_candidate_rejected_low_confidence_deterministic": [
 sys.executable,
 "scripts/validate_classification_candidate.py",
 "examples/classification_candidates/rejected_low_confidence.json",
 ],
 "classification_candidate_rejected_unsafe_pattern_deterministic": [
 sys.executable,
 "scripts/validate_classification_candidate.py",
 "examples/classification_candidates/rejected_unsafe_pattern.json",
 ],
}

PARAMETRIC_TEMPLATE_CHECKS = {
 "parametric_template_valid_read_deterministic": [
 sys.executable,
 "scripts/validate_parametric_template.py",
 "examples/parametric_templates/valid_read_template.json",
 ],
 "parametric_template_valid_write_deterministic": [
 sys.executable,
 "scripts/validate_parametric_template.py",
 "examples/parametric_templates/valid_write_template.json",
 ],
 "parametric_template_valid_binding_deterministic": [
 sys.executable,
 "scripts/validate_parametric_template.py",
 "examples/parametric_templates/valid_binding_read.json",
 ],
 "parametric_template_invalid_command_validation_deterministic": [
 sys.executable,
 "scripts/validate_parametric_template.py",
 "examples/parametric_templates/invalid_command_validation_false.json",
 ],
 "parametric_template_invalid_fingerprint_deterministic": [
 sys.executable,
 "scripts/validate_parametric_template.py",
 "examples/parametric_templates/invalid_fingerprint_format.json",
 ],
    "parametric_template_invalid_enum_empty_deterministic": [
        sys.executable,
        "scripts/validate_parametric_template.py",
        "examples/parametric_templates/invalid_enum_empty_values.json",
    ],
}

BOUNDED_REFERENCE_INDEX_CHECKS = {
    "bounded_reference_index_validation": [
        sys.executable,
        "scripts/validate_bounded_reference_index.py",
        "examples/bounded_reference_index/accepted_index.json",
    ],
    "bounded_read_window_validation": [
        sys.executable,
        "scripts/validate_bounded_reference_index.py",
        "examples/bounded_reference_index/accepted_read_window.json",
    ],
    "processed_reference_cache_validation": [
        sys.executable,
        "scripts/validate_bounded_reference_index.py",
        "examples/bounded_reference_index/accepted_processed_cache.json",
    ],
}

HUMAN_APPROVED_EXECUTION_GATE_CHECKS = {
    "human_execution_proposal_validation": [
        sys.executable,
        "scripts/validate_human_approved_execution_gate.py",
        "examples/human_approved_execution_gate/accepted_execution_proposal.json",
    ],
    "advisory_review_bundle_validation": [
        sys.executable,
        "scripts/validate_human_approved_execution_gate.py",
        "examples/human_approved_execution_gate/accepted_multi_expert_review_bundle.json",
    ],
    "human_approval_record_validation": [
        sys.executable,
        "scripts/validate_human_approved_execution_gate.py",
        "examples/human_approved_execution_gate/accepted_human_approval_record.json",
    ],
    "sandbox_execution_record_validation": [
        sys.executable,
        "scripts/validate_human_approved_execution_gate.py",
        "examples/human_approved_execution_gate/accepted_sandbox_execution_record.json",
    ],
    "skill_promotion_candidate_validation": [
        sys.executable,
        "scripts/validate_human_approved_execution_gate.py",
        "examples/human_approved_execution_gate/accepted_skill_promotion_candidate.json",
    ],
}

PRIVATE_DOMAIN_CANDIDATE_CHECKS = {
    "private_domain_candidate_accepted_deterministic": [
        sys.executable,
        "scripts/validate_private_domain_candidate.py",
        "examples/private_domain_integration/command_candidates/accepted.json",
        "--vocab-dir",
        "examples/private_domain_integration/vocabularies",
    ],
    "private_domain_candidate_rejected_private_data_deterministic": [
        sys.executable,
        "scripts/validate_private_domain_candidate.py",
        "examples/private_domain_integration/command_candidates/rejected_private_data.json",
        "--vocab-dir",
        "examples/private_domain_integration/vocabularies",
    ],
    "private_domain_candidate_rejected_unknown_command_deterministic": [
        sys.executable,
        "scripts/validate_private_domain_candidate.py",
        "examples/private_domain_integration/command_candidates/rejected_unknown_command.json",
        "--vocab-dir",
        "examples/private_domain_integration/vocabularies",
    ],
}

EXPERT_CONFLICT_PRE_RESOLUTION_CHECKS = {
    "expert_conflict_bundle_validation": [
        sys.executable,
        "scripts/validate_expert_conflict_pre_resolution.py",
        "examples/expert_conflict_pre_resolution/accepted_conflict_bundle.json",
    ],
    "pre_resolution_protocol_validation": [
        sys.executable,
        "scripts/validate_expert_conflict_pre_resolution.py",
        "examples/expert_conflict_pre_resolution/accepted_pre_resolution_protocol.json",
    ],
    "pre_resolution_report_validation": [
        sys.executable,
        "scripts/validate_expert_conflict_pre_resolution.py",
        "examples/expert_conflict_pre_resolution/accepted_pre_resolution_report.json",
    ],
    "human_escalation_decision_validation": [
        sys.executable,
        "scripts/validate_expert_conflict_pre_resolution.py",
        "examples/expert_conflict_pre_resolution/accepted_human_escalation_decision.json",
    ],
}

AGENT_SESSION_CHECKS = {
    "agent_session_valid_deterministic": [
        sys.executable,
        "scripts/validate_agent_session.py",
        "examples/agent_sessions/accepted_read_and_propose.json",
    ],
    "agent_session_rejects_unbounded_context": [
        sys.executable,
        "scripts/validate_agent_session.py",
        "examples/agent_sessions/rejected_unbounded_context.json",
    ],
    "agent_session_rejects_tool_execution": [
        sys.executable,
        "scripts/validate_agent_session.py",
        "examples/agent_sessions/rejected_tool_execution.json",
    ],
    "agent_session_requires_human_approval": [
        sys.executable,
        "scripts/validate_agent_session.py",
        "examples/agent_sessions/rejected_autonomous_execution.json",
    ],
}

AGENT_PLAN_CHECKS = {
    "agent_plan_accepted_deterministic": [
        sys.executable,
        "scripts/validate_agent_plan.py",
        "examples/agent_plans/accepted_linear_plan.json",
    ],
    "agent_plan_rejects_autonomous_execution": [
        sys.executable,
        "scripts/validate_agent_plan.py",
        "examples/agent_plans/rejected_autonomous_plan.json",
    ],
    "agent_plan_rejects_circular_dependency": [
        sys.executable,
        "scripts/validate_agent_plan.py",
        "examples/agent_plans/rejected_circular_plan.json",
    ],
    "agent_plan_rejects_parallel_side_effects": [
        sys.executable,
        "scripts/validate_agent_plan.py",
        "examples/agent_plans/rejected_parallel_side_effects.json",
    ],
    "agent_plan_rejects_private_path": [
        sys.executable,
        "scripts/validate_agent_plan.py",
        "examples/agent_plans/rejected_private_path_plan.json",
    ],
}

TOOL_INVOCATION_CHECKS = {
    "tool_invocation_accepted_deterministic": [
        sys.executable,
        "scripts/validate_tool_invocation.py",
        "examples/tool_invocations/accepted_read_tool.json",
    ],
    "tool_invocation_rejects_autonomous_execution": [
        sys.executable,
        "scripts/validate_tool_invocation.py",
        "examples/tool_invocations/rejected_autonomous_write.json",
    ],
    "tool_invocation_rejects_risky_no_approval": [
        sys.executable,
        "scripts/validate_tool_invocation.py",
        "examples/tool_invocations/rejected_risky_no_approval.json",
    ],
    "tool_invocation_rejects_nested_arguments": [
        sys.executable,
        "scripts/validate_tool_invocation.py",
        "examples/tool_invocations/rejected_nested_arguments.json",
    ],
    "tool_invocation_rejects_private_path": [
        sys.executable,
        "scripts/validate_tool_invocation.py",
        "examples/tool_invocations/rejected_private_path.json",
    ],
}

STATE_WATCHER_CHECKS = {
    "state_watcher_validator_deterministic": [
        sys.executable,
        "scripts/validate_state_watcher.py",
        "examples/state_watchers/registrations",
    ],
    "state_watcher_event_derivation_deterministic": [
        sys.executable,
        "scripts/derive_business_event.py",
        "examples/state_watchers/registrations/valid_threshold_watcher.json",
        "examples/state_watchers/observations/scalar_observations_v1",
    ],
}

_TMP_PREFIX = "/tmp/"
TESTS_GROUP_TIMEOUT_SECONDS = 120
OUTPUT_PREVIEW_LIMIT = 2048


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_command(
    command: list[str],
    timeout_seconds: int | None = None,
    expect_json: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _truncate_text(text: str, limit: int = OUTPUT_PREVIEW_LIMIT) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + "…[truncated]", True


def _status(result: subprocess.CompletedProcess[str]) -> str:
    return "passed" if result.returncode == 0 else "failed"


def _sanitize(text: str) -> str:
    repo_root = str(Path.cwd())
    return text.replace(repo_root, "<repo>").replace(_TMP_PREFIX, "<tmp>/")


def _detail(result: subprocess.CompletedProcess[str]) -> str:
    return _sanitize((result.stderr.strip() or result.stdout.strip()))


_MISSING_RUNTIME_SURFACE_MARKERS = (
    "can't open file",
    "no such file or directory",
    "no module named",
    "modulenotfounderror",
    "importerror",
)


def _is_missing_runtime_surface(detail: str) -> bool:
    lowered = detail.lower()
    return any(marker in lowered for marker in _MISSING_RUNTIME_SURFACE_MARKERS)


_OUTPUT_FLAGS = frozenset({"--output", "--out", "-o", "--output-dir", "--write", "--output-path"})


def _missing_input_fixtures(command: list[str]) -> list[str]:
    """A check whose command references a `.json` fixture argument that does
    not exist on disk was never actually exercised, regardless of what the
    subprocess printed. Detecting this structurally (path existence) is more
    precise than pattern-matching each script's own missing-file wording.

    Arguments that follow an output flag are skipped: an output path is
    *expected* not to exist yet, so treating it as a missing input would
    silently mark a working check `pending_runtime` — reintroducing, in
    mirror image, the false-status bug this whole guard exists to prevent.
    No current check declares one, but nothing stops a future check from
    doing so.
    """
    missing: list[str] = []
    for index, arg in enumerate(command):
        if not arg.endswith(".json") or (index and command[index - 1] in _OUTPUT_FLAGS):
            continue
        if not Path(arg).is_file():
            missing.append(arg)
    return missing


def _checks_summary(checks: dict[str, str]) -> dict[str, Any]:
    """Report how many declared checks actually ran.

    `status: passed` alone cannot distinguish "every check ran and passed"
    from "most checks never ran", so every release-verification payload
    carries this breakdown. Only `passed`, `failed` and `blocked` count as
    executed; `pending_runtime`, `skipped`, `excluded` and
    `historical_baseline_preserved` are declared-but-not-run.
    """
    by_status: dict[str, int] = {}
    for status in checks.values():
        by_status[status] = by_status.get(status, 0) + 1
    executed = sum(by_status.get(state, 0) for state in ("passed", "failed", "blocked"))
    return {
        "declared_count": len(checks),
        "executed_count": executed,
        "by_status": dict(sorted(by_status.items())),
    }


def _record_check_result(
    checks: dict[str, str],
    details: dict[str, str],
    name: str,
    status: str,
    detail: str,
    allow_missing_surface: bool = False,
) -> None:
    if allow_missing_surface and status == "failed" and _is_missing_runtime_surface(detail):
        checks[name] = "pending_runtime"
    else:
        checks[name] = status
    if detail:
        details[name] = detail


def _same_output(command: list[str]) -> tuple[str, str]:
    missing = _missing_input_fixtures(command)
    if missing:
        return "pending_runtime", f"input fixture(s) not found: {', '.join(missing)}"

    first = _run(command)
    second = _run(command)

    if first.returncode != 0:
        return "failed", _detail(first)
    if second.returncode != 0:
        return "failed", _detail(second)
    if first.stdout != second.stdout:
        return "failed", "outputs differ"

    return "passed", ""


def _same_result(command: list[str]) -> tuple[str, str]:
    """Reproducible non-zero exit is the expected outcome for a negative
    check (the validator correctly rejected its input), so it is normally
    reported as "passed". But a non-zero exit caused by a missing script,
    module or input fixture is not a rejection verdict — it is the check
    never having run at all — so that case must be classified as
    "pending_runtime" instead, matching the callers' `allow_missing_surface`
    intent."""
    missing = _missing_input_fixtures(command)
    if missing:
        return "pending_runtime", f"input fixture(s) not found: {', '.join(missing)}"

    first = _run(command)
    second = _run(command)

    if first.returncode != second.returncode:
        return "failed", "return codes differ"
    if first.stdout != second.stdout:
        return "failed", "outputs differ"

    if first.returncode != 0:
        detail = _detail(first)
        if _is_missing_runtime_surface(detail):
            return "pending_runtime", detail
        return "passed", detail

    return "passed", ""


def _check_name_list(mapping: dict[str, Any]) -> list[str]:
    if hasattr(mapping, "keys"):
        return sorted(mapping.keys())  # type: ignore[return-value]
    return sorted(mapping)


def _write_timing_json(timing_json: str | None, payload: dict[str, Any]) -> None:
    if not timing_json:
        return
    Path(timing_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _timing_record(
    name: str,
    group: str,
    status: str,
    started: float,
    diagnostics: list[dict[str, Any]] | None = None,
    command: list[str] | None = None,
    timeout_seconds: int | None = None,
    stdout_preview: str | None = None,
    stderr_preview: str | None = None,
    subgroup: str | None = None,
) -> dict[str, Any]:
    record = {
        "name": name,
        "group": group,
        "status": status,
        "duration_seconds": round(time.monotonic() - started, 6),
        "diagnostics": diagnostics or [],
    }
    if command is not None:
        record["command"] = command
    if timeout_seconds is not None:
        record["timeout_seconds"] = timeout_seconds
    if stdout_preview is not None:
        record["stdout_preview"] = stdout_preview
    if stderr_preview is not None:
        record["stderr_preview"] = stderr_preview
    if subgroup is not None:
        record["subgroup"] = subgroup
    return record


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _discover_test_targets(repo_root: Path) -> list[str]:
    discovered: list[str] = []
    ignored_parts = {".git", ".venv", "__pycache__", "private", "node_modules", ".pytest_cache", "scratch"}
    for path in sorted(repo_root.rglob("test_*.py")):
        if not path.is_file():
            continue
        if any(part in ignored_parts for part in path.parts):
            continue
        discovered.append(str(path.relative_to(repo_root)))
    return discovered


def _test_group_for_target(target: str) -> str:
    name = Path(target).name
    if "tooling" in name:
        return "tests-tooling"
    if "run_all_examples" in name:
        return "tests-integration"
    if "replay" in name or "verify_release" in name or "run_all_examples" in name:
        return "tests-replay"
    if target.startswith("examples/") or any(token in name for token in ("example", "e2e", "integration", "pipeline")):
        return "tests-integration"
    if any(
        token in name
        for token in (
            "validator",
            "contract",
            "schema",
            "report",
            "readiness",
            "audit",
            "compliance",
            "manifest",
            "policy",
            "fixture",
            "sandbox",
            "import",
        )
    ):
        return "tests-contracts"
    return "tests-core"


def _build_tests_subgroups(repo_root: Path) -> list[dict[str, Any]]:
    discovered = _discover_test_targets(repo_root)
    grouped: dict[str, list[str]] = {
        "tests-tooling": [],
        "tests-replay": [],
        "tests-integration": [],
        "tests-contracts": [],
        "tests-core": [],
    }
    for target in discovered:
        grouped[_test_group_for_target(target)].append(target)

    subgroups = []
    for name in ("tests-tooling", "tests-replay", "tests-integration", "tests-contracts", "tests-core"):
        targets = grouped[name]
        subgroups.append(
            {
                "name": name,
                "targets": targets,
                "required_for_full_release": True,
            }
        )
    return subgroups


def _tests_subgroup_catalog_payload(repo_root: Path) -> list[dict[str, Any]]:
    return _build_tests_subgroups(repo_root)


def _resolve_test_targets(repo_root: Path, targets: list[str]) -> list[str]:
    resolved: list[str] = []
    seen: set[str] = set()
    for target in targets:
        matches = glob.glob(str(repo_root / target), recursive=True)
        if matches:
            for match in sorted(matches):
                path = Path(match)
                if not path.is_file():
                    continue
                rel = str(path.relative_to(repo_root))
                if rel not in seen:
                    seen.add(rel)
                    resolved.append(rel)
            continue
        path = repo_root / target
        if path.is_file():
            rel = str(path.relative_to(repo_root))
            if rel not in seen:
                seen.add(rel)
                resolved.append(rel)
    return resolved


def _tests_planned_subgroups(repo_root: Path, selected: str | None = None) -> list[dict[str, Any]]:
    subgroups = _build_tests_subgroups(repo_root)
    if selected in {None, "tests", "tests-full"}:
        return subgroups
    return [subgroup for subgroup in subgroups if subgroup["name"] == selected]


def verify(
    skip_full_pytest: bool,
    target: str | None = None,
    stop_after_tooling: bool = False,
    stop_before_replay: bool = False,
    timing_json: str | None = None,
) -> tuple[int, dict[str, Any]]:
    exclusions = TARGET_EXCLUSIONS.get(target, set()) if target else set()

    checks: dict[str, str] = {}
    details: dict[str, str] = {}
    diagnostics: list[dict[str, Any]] = []
    timings: list[dict[str, Any]] = []
    overall_start = time.monotonic()

    commands = {
        "compileall": [sys.executable, "-m", "compileall", "core_runtime", "examples", "scripts", "tests"],
        "ruff": [
            sys.executable,
            "-m",
            "core_runtime.cli",
            "lint",
            "--scope",
            "tooling",
            "--format",
            "json",
        ],
        "mypy_report_only": [
            "mypy",
            "--follow-imports=skip",
            "core_runtime/core/sensor_evidence.py",
            "core_runtime/core/explainability.py",
        ],
    }

    for name, command in commands.items():
        result = _run(command)
        checks[name] = _status(result)
        if result.returncode != 0:
            details[name] = _detail(result)

    timings.append(_timing_record("tooling", "tooling", "passed" if not any(status == "failed" for status in checks.values()) else "failed", overall_start))

    if stop_after_tooling:
        failed = [name for name, status in checks.items() if status == "failed"]
        payload: dict[str, Any] = {
            "schema": "core.release_verification.v1",
            "mode": "tooling",
            "target": target,
            "status": "passed" if not failed else "failed",
            "checks": dict(sorted(checks.items())),
            "details": dict(sorted(details.items())),
            "timings": timings,
            "checks_summary": _checks_summary(checks),
        }
        _write_timing_json(timing_json, payload)
        return (0 if not failed else 1), payload

    for bridge_name, paths in BRIDGES.items():
        fixture = paths["fixture"]
        adapter = paths["adapter"]

        bridge_passed = True
        bridge_details: list[str] = []

        for command in (
            [sys.executable, "scripts/validate_sensor_manifest.py", fixture],
            [sys.executable, "scripts/certify_sensor_fixture.py", fixture],
            [sys.executable, "scripts/check_adapter_compliance.py", adapter],
        ):
            result = _run(command)
            if result.returncode != 0:
                bridge_passed = False
                bridge_details.append(_detail(result))

        checks[bridge_name] = "passed" if bridge_passed else "failed"
        if bridge_details:
            details[bridge_name] = "\n".join(bridge_details)

    for name, command in {
        "run_all_examples_deterministic": [sys.executable, "scripts/run_all_examples.py"],
        "skeleton_roundtrip_deterministic": [
            sys.executable,
            "examples/workflows/skeleton_roundtrip_demo/run_demo.py",
        ],
        "replay_explain_roundtrip_deterministic": [
            sys.executable,
            "examples/workflows/replay_explain_roundtrip/run_demo.py",
        ],
        "compatibility_matrix_deterministic": [
            sys.executable,
            "scripts/report_compatibility_matrix.py",
            "--allow-expected-incompatible",
        ],
        "protocol_model_readiness": [
            sys.executable,
            "scripts/report_protocol_model_readiness.py",
        ],
        "protocol_model_candidate_package_readiness": [
            sys.executable,
            "scripts/report_protocol_model_candidate_package_readiness.py",
        ],
        "protocol_model_external_candidate_output_evaluation": [
            sys.executable,
            "scripts/report_external_candidate_output_evaluation.py",
        ],
        "protocol_model_candidate_comparison": [
            sys.executable,
            "scripts/report_protocol_model_candidate_comparison.py",
        ],
        "protocol_model_external_submission_intake": [
            sys.executable,
            "scripts/report_protocol_model_external_submission_intake.py",
        ],
        "protocol_model_submission_comparison": [
            sys.executable,
            "scripts/report_protocol_model_submission_comparison.py",
        ],
        "protocol_model_certification_dossier": [
            sys.executable,
            "scripts/report_protocol_model_certification_dossier.py",
        ],
        "protocol_model_candidate_package_certification": [
            sys.executable,
            "scripts/certify_protocol_model_candidate_package.py",
        ],
        "protocol_model_candidate_output_diagnostics": [
            sys.executable,
            "scripts/report_protocol_model_candidate_output_diagnostics.py",
        ],
        "protocol_model_artifact_readiness": [
            sys.executable,
            "scripts/report_protocol_model_artifact_readiness.py",
        ],
        "protocol_model_candidate_gate": [
            sys.executable,
            "scripts/report_protocol_model_candidate_gate.py",
        ],
        "protocol_model_candidate_trial": [
            sys.executable,
            "scripts/report_protocol_model_candidate_trial.py",
        ],
        "development_audit_readiness": [
            sys.executable,
            "scripts/report_development_audit_readiness.py",
        ],
        "protocol_model_domain_vocabulary_validation": [
            sys.executable,
            "scripts/validate_domain_vocabulary.py",
        ],
        "protocol_model_command_candidate_validation": [
            sys.executable,
            "scripts/validate_command_candidate.py",
        ],
        "protocol_model_command_candidate_compilation": [
            sys.executable,
            "scripts/compile_command_candidate.py",
        ],
        "protocol_model_preintegration_package": [
            sys.executable,
            "scripts/validate_protocol_model_preintegration_package.py",
        ],
        "protocol_model_preintegration_readiness": [
            sys.executable,
            "scripts/report_protocol_model_preintegration_readiness.py",
        ],
    }.items():
        status, detail = _same_output(command)
        _record_check_result(checks, details, name, status, detail, allow_missing_surface=True)

    for name, command in {
        "development_audit_enforcement_runtime_core": [
            sys.executable,
            "scripts/check_development_audit_enforcement.py",
            "examples/development_audit/proposals/runtime_mutation_rejected.json",
        ],
        "development_audit_enforcement_docs": [
            sys.executable,
            "scripts/check_development_audit_enforcement.py",
            "examples/development_audit/proposals/docs_only_accepted.json",
        ],
    }.items():
        status, detail = _same_result(command)
        _record_check_result(checks, details, name, status, detail, allow_missing_surface=True)

    for name, command in STATE_WATCHER_CHECKS.items():
        status, detail = _same_result(command)
        _record_check_result(checks, details, name, status, detail)

    for name, command in PRIVATE_DOMAIN_CANDIDATE_CHECKS.items():
        status, detail = _same_result(command)
        _record_check_result(checks, details, name, status, detail)

    for name, command in CLASSIFICATION_CANDIDATE_CHECKS.items():
        status, detail = _same_result(command)
        _record_check_result(checks, details, name, status, detail)

    for name, command in PARAMETRIC_TEMPLATE_CHECKS.items():
        status, detail = _same_result(command)
        _record_check_result(checks, details, name, status, detail)

    for name, command in BOUNDED_REFERENCE_INDEX_CHECKS.items():
        status, detail = _same_result(command)
        _record_check_result(checks, details, name, status, detail)

    for name, command in HUMAN_APPROVED_EXECUTION_GATE_CHECKS.items():
        status, detail = _same_result(command)
        _record_check_result(checks, details, name, status, detail)

    for name, command in EXPERT_CONFLICT_PRE_RESOLUTION_CHECKS.items():
        status, detail = _same_result(command)
        _record_check_result(checks, details, name, status, detail)

    for name, command in AGENT_SESSION_CHECKS.items():
        status, detail = _same_result(command)
        _record_check_result(checks, details, name, status, detail)

    for name, command in AGENT_PLAN_CHECKS.items():
        status, detail = _same_result(command)
        _record_check_result(checks, details, name, status, detail)

    for name, command in TOOL_INVOCATION_CHECKS.items():
        status, detail = _same_result(command)
        _record_check_result(checks, details, name, status, detail)

    for name, command in AGENT_DECISION_TRACE_CHECKS.items():
        status, detail = _same_result(command)
        _record_check_result(checks, details, name, status, detail)

    for name, command in DOWNSTREAM_BRIDGE_ADAPTER_CHECKS.items():
        status, detail = _same_result(command)
        _record_check_result(checks, details, name, status, detail)

    for name, command in AGENT_BOUNDARY_FREEZE_CHECKS.items():
        status, detail = _same_result(command)
        _record_check_result(checks, details, name, status, detail, allow_missing_surface=True)

    for name, command in ANCHORING_SUBMISSION_CHECKS.items():
        status, detail = _same_result(command)
        _record_check_result(checks, details, name, status, detail)

    for name, command in CHAIN_ADAPTER_CHECKS.items():
        status, detail = _same_result(command)
        _record_check_result(checks, details, name, status, detail)

    for name, command in MERKLE_BATCH_CHECKS.items():
        if name in exclusions:
            checks[name] = "skipped"
            continue
        if _target_at_least(target, "v9.3"):
            status, detail = _same_result(command)
            _record_check_result(checks, details, name, status, detail, allow_missing_surface=True)
        else:
            checks[name] = "pending_runtime"

    for name, command in FROZEN_RULE_ANCHOR_CHECKS.items():
        if _target_at_least(target, "v11.1"):
            status, detail = _same_output(command)
            _record_check_result(checks, details, name, status, detail)
        else:
            checks[name] = "pending_runtime"

    for name, command in FROZEN_RELEASE_MANIFEST_CHECKS.items():
        if name == "frozen_release_manifest_v11_1_accepted" and _target_at_least(target, "v11.2"):
            # v11.1 is a historical immutable baseline. Its byte inventory is
            # intentionally not re-evaluated against the v11.2 working tree.
            checks[name] = "historical_baseline_preserved"
            continue
        if name == "frozen_release_manifest_v11_2_candidate_accepted" and not _target_at_least(target, "v11.2"):
            checks[name] = "pending_runtime"
            continue
        if _target_at_least(target, "v11.1"):
            status, detail = _same_output(command)
            _record_check_result(checks, details, name, status, detail)
        else:
            checks[name] = "pending_runtime"

    for name, command in EXECUTABLE_CONTRACT_CHECKS.items():
        if _target_at_least(target, "v11.1"):
            status, detail = _same_output(command)
            _record_check_result(checks, details, name, status, detail)
        else:
            checks[name] = "pending_runtime"

    for name, command in DOCUMENT_ATTESTATION_CHECKS.items():
        if name in exclusions:
            checks[name] = "skipped"
            continue
        if _target_at_least(target, "v9.4"):
            status, detail = _same_result(command)
            _record_check_result(checks, details, name, status, detail, allow_missing_surface=True)
        else:
            checks[name] = "pending_runtime"

    for name, command in PROCESS_ATTESTATION_CHECKS.items():
        if name in exclusions:
            checks[name] = "skipped"
            continue
        if _target_at_least(target, "v9.5"):
            status, detail = _same_result(command)
            _record_check_result(checks, details, name, status, detail, allow_missing_surface=True)
        else:
            checks[name] = "pending_runtime"

    # ── v10+ structural-hygiene iteration ─────────────────────────
    # EXECUTION_PROFILE_CHECKS validates the public execution_profile
    # schema artifact and its fixtures. This is the structural gate
    # introduced by CORE-V10-SCHEMA-HYGIENE-SLICE1: every accepted fixture
    # must round-trip through `scripts/validate_execution_profile.py`.
    # It exposes check names that mirror the renamed v10 CHECKS namespace.
    for name, command in EXECUTION_PROFILE_CHECKS.items():
        if name in exclusions:
            checks[name] = "skipped"
            continue
        status, detail = _same_result(command)
        _record_check_result(checks, details, name, status, detail)

    # ── v10.3 compatibility-index slice 1 ───────────────────────
    # These checks exercise the first public compatibility-index surface. They
    # are deterministic, cache-only and do not touch the scheduler.
    for name in sorted(V103_CHECKS):
        if name in exclusions:
            checks[name] = "skipped"
            continue
        if _target_at_least(target, "v10.3"):
            command = V103_CHECK_MAP[name]
            status, detail = _same_result(command)
            _record_check_result(checks, details, name, status, detail, allow_missing_surface=True)
        else:
            checks[name] = "pending_runtime"

    # V10_NATIVE_CHECKS contains runner expressions against v10+ runtime
    # modules (LazyVerificationGate, ExecutionTrace.to_otel_jsonl, composite
    # verification). Until those modules are landed, surface each name as
    # `pending_runtime` per CORE-V10-SCHEMA-HYGIENE-SLICE1 — the slice
    # establishes the gate namespace without claiming feature readiness.
    if _target_at_least(target, "v10.0"):
        for name in V10_CHECKS:
            if name in exclusions:
                checks[name] = "skipped"
                continue
            if name in V10_PENDING_RUNTIME_NAMES:
                checks[name] = "pending_runtime"
            elif name == "execution_profile_strategy_fields":
                # Already covered structurally by EXECUTION_PROFILE_CHECKS
                # iterating the fixtures; record as pending to avoid
                # double-counting in the report.
                checks[name] = "pending_runtime"

    for name, command in V10_NATIVE_CHECKS.items():
        if name in exclusions:
            checks[name] = "skipped"
            continue
        if _target_at_least(target, V10_NATIVE_FLOORS[name]):
            status, detail = _same_result(command)
            _record_check_result(checks, details, name, status, detail)
        else:
            checks[name] = "pending_runtime"

    # ── v10.2 lazy-verification runtime surface ─────────────────
    # These checks are the first concrete v10.2 runtime slice. They
    # verify that the declared interval is consumed by the runtime
    # projection surface and that the OTel export helper remains
    # available. For target v10.2 (and advisory mode) they run directly;
    # for other frozen targets they remain pending_runtime to avoid
    # overstating readiness.
    for name in V102_CHECKS:
        if name in exclusions:
            checks[name] = "skipped"
            continue
        if _target_at_least(target, "v10.2"):
            command = V102_CHECK_MAP[name]
            status, detail = _same_result(command)
            _record_check_result(checks, details, name, status, detail)
        else:
            checks[name] = "pending_runtime"

    # ── v10.4 slice1: workflow DAG + checkpoint/resume + accountability ──
    # When target == "v10.4" (or no target, advisory mode), execute the
    # v10.4 check commands against fixture artifacts. For all other frozen
    # target lines, these names are surfaced as `pending_runtime` to keep
    # the gate namespace stable without claiming feature readiness in
    # released branches.
    for name in V104_CHECKS:
        if name in exclusions:
            checks[name] = "skipped"
            continue
        if _target_at_least(target, "v10.4"):
            command = V104_CHECK_MAP[name]
            status, detail = _same_result(command)
            _record_check_result(checks, details, name, status, detail, allow_missing_surface=True)
        else:
            checks[name] = "pending_runtime"

    # ── v10.5 slice1: surrogate_node_descriptor + link rules ──
    # When target == "v10.5" (or no target, advisory mode), execute the
    # v10.5 check commands against fixture artifacts and the shared
    # link-rule helper. For all other frozen target lines, these
    # names are surfaced as ``pending_runtime``.
    for name in V105_CHECKS:
        if name in exclusions:
            checks[name] = "skipped"
            continue
        if _target_at_least(target, "v10.5"):
            command = V105_CHECK_MAP[name]
            status, detail = _same_result(command)
            _record_check_result(checks, details, name, status, detail, allow_missing_surface=True)
        else:
            checks[name] = "pending_runtime"

    if stop_before_replay:
        failed = [name for name, status in checks.items() if status == "failed"]
        payload = {
            "schema": "core.release_verification.v1",
            "mode": "release-metadata",
            "target": target,
            "status": "passed" if not failed else "failed",
            "checks": dict(sorted(checks.items())),
            "details": dict(sorted(details.items())),
            "timings": timings,
            "checks_summary": _checks_summary(checks),
        }
        _write_timing_json(timing_json, payload)
        return (0 if not failed else 1), payload

    replay_start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="core_release_verify_audit_") as audit_dir:
        audit_root = Path(audit_dir)
        report_path = audit_root / "compatibility_matrix_report.json"
        manifest_path = audit_root / "source_manifest.json"

        report_result = _run_command(
            [
                sys.executable,
                "scripts/report_compatibility_matrix.py",
                "--allow-expected-incompatible",
            ]
        )
        report_detail = _detail(report_result)
        if report_result.returncode == 0:
            report_path.write_text(report_result.stdout, encoding="utf-8")
            report_payload = json.loads(report_result.stdout)
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": "4.9.0",
                        "source_artifacts": [
                            {
                                "artifact_type": "compatibility_matrix",
                                "path": str(report_path.relative_to(audit_root)),
                                "fingerprint": compute_operational_fingerprint(report_payload),
                                "stable_name": "compatibility_matrix_report",
                            }
                        ],
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            audit_a = audit_root / "audit_a"
            audit_b = audit_root / "audit_b"
            derive_a = _run_command(
                [
                    sys.executable,
                    "scripts/derive_audit_trail.py",
                    "--source-manifest",
                    str(manifest_path),
                    "--source-type",
                    "compatibility_matrix",
                    "--output-dir",
                    str(audit_a),
                ]
            )
            derive_b = _run_command(
                [
                    sys.executable,
                    "scripts/derive_audit_trail.py",
                    "--source-manifest",
                    str(manifest_path),
                    "--source-type",
                    "compatibility_matrix",
                    "--output-dir",
                    str(audit_b),
                ]
            )

            trail_a = audit_a / "audit_trail.json"
            trail_b = audit_b / "audit_trail.json"
            manifest_a = audit_a / "audit_manifest.json"
            manifest_b = audit_b / "audit_manifest.json"

            if (
                derive_a.returncode == 0
                and derive_b.returncode == 0
                and trail_a.read_bytes() == trail_b.read_bytes()
                and manifest_a.read_bytes() == manifest_b.read_bytes()
            ):
                checks["audit_trail_deterministic"] = "passed"
                audit_manifest_payload = json.loads(manifest_a.read_text(encoding="utf-8"))
                checks["audit_manifest_valid"] = (
                    "passed"
                    if (
                        audit_manifest_payload.get("schema_version") == "4.9.0"
                        and audit_manifest_payload.get("audit_fingerprint")
                        == json.loads(trail_a.read_text(encoding="utf-8")).get("audit_fingerprint")
                        and audit_manifest_payload.get("event_count")
                        == json.loads(trail_a.read_text(encoding="utf-8")).get("event_count")
                        and isinstance(audit_manifest_payload.get("source_artifacts"), list)
                        and audit_manifest_payload.get("source_artifacts")
                    )
                    else "failed"
                )
                if checks["audit_manifest_valid"] != "passed":
                    details["audit_manifest_valid"] = "audit manifest validation failed"

                unknown_source = _run_command(
                    [
                        sys.executable,
                        "scripts/derive_audit_trail.py",
                        "--source-manifest",
                        str(manifest_path),
                        "--source-type",
                        "unknown_thing",
                        "--output-dir",
                        str(audit_root / "audit_invalid"),
                    ]
                )
                if unknown_source.returncode != 0 and "Unsupported --source-type" in _detail(unknown_source):
                    checks["audit_trail_unknown_source_type_rejected"] = "passed"
                else:
                    checks["audit_trail_unknown_source_type_rejected"] = "failed"
                    details["audit_trail_unknown_source_type_rejected"] = _detail(unknown_source)
            elif any(
                candidate.returncode != 0 and _is_missing_runtime_surface(_detail(candidate))
                for candidate in (derive_a, derive_b)
            ):
                checks["audit_trail_deterministic"] = "pending_runtime"
                details["audit_trail_deterministic"] = "\n".join(
                    _detail(candidate)
                    for candidate in (derive_a, derive_b)
                    if candidate.returncode != 0 and _is_missing_runtime_surface(_detail(candidate))
                )
            else:
                checks["audit_trail_deterministic"] = "failed"
                details["audit_trail_deterministic"] = "\n".join(
                    part
                    for part in (
                        _detail(report_result) if report_result.returncode != 0 else "",
                        _detail(derive_a) if derive_a.returncode != 0 else "",
                        _detail(derive_b) if derive_b.returncode != 0 else "",
                        "audit trail bytes differ"
                        if derive_a.returncode == 0 and derive_b.returncode == 0
                        else "",
                    )
                    if part
                )
        elif _is_missing_runtime_surface(report_detail):
            checks["audit_trail_deterministic"] = "pending_runtime"
            details["audit_trail_deterministic"] = report_detail
        else:
            checks["audit_trail_deterministic"] = "failed"
            details["audit_trail_deterministic"] = report_detail

    with tempfile.TemporaryDirectory(prefix="core_release_verify_router_audit_") as router_audit_dir:
        router_root = Path(router_audit_dir)
        router_artifacts = router_root / "artifacts"
        router_artifacts.mkdir(parents=True, exist_ok=True)

        validation_path = router_artifacts / "router_validation.json"
        evaluation_path = router_artifacts / "router_evaluation.json"
        report_path = router_artifacts / "router_report.json"
        replay_path = router_artifacts / "router_replay.json"

        validation_result = _run(
            [
                sys.executable,
                "scripts/validate_expert_router.py",
                "examples/expert_router/routing_fixtures/minimal_routing.json",
            ]
        )
        evaluation_result = _run(
            [
                sys.executable,
                "scripts/evaluate_expert_router.py",
                "examples/expert_router/routing_fixtures/minimal_routing.json",
            ]
        )
        report_result = _run(
            [
                sys.executable,
                "scripts/report_expert_router.py",
                "--output",
                str(report_path),
            ]
        )
        replay_result = _run(
            [
                sys.executable,
                "scripts/certify_router_replay.py",
                "--fixture",
                "examples/expert_router/routing_fixtures/minimal_routing.json",
                "--output",
                str(replay_path),
            ]
        )

        if any(
            result.returncode != 0 and _is_missing_runtime_surface(_detail(result))
            for result in (validation_result, evaluation_result, report_result, replay_result)
        ):
            checks["router_audit_trail_deterministic"] = "pending_runtime"
            details["router_audit_trail_deterministic"] = "\n".join(
                _detail(result)
                for result in (validation_result, evaluation_result, report_result, replay_result)
                if result.returncode != 0 and _is_missing_runtime_surface(_detail(result))
            )
        elif (
            validation_result.returncode == 0
            and evaluation_result.returncode == 0
            and report_result.returncode == 0
            and replay_result.returncode == 0
        ):
            validation_path.write_text(validation_result.stdout, encoding="utf-8")
            evaluation_path.write_text(evaluation_result.stdout, encoding="utf-8")

            validation_payload = json.loads(validation_result.stdout)
            evaluation_payload = json.loads(evaluation_result.stdout)
            report_payload = json.loads(report_path.read_text(encoding="utf-8"))
            replay_payload = json.loads(replay_path.read_text(encoding="utf-8"))

            manifest_path = router_root / "source_manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": "4.9.0",
                        "source_artifacts": [
                            {
                                "artifact_type": "expert_router_validation",
                                "path": str(validation_path.relative_to(router_root)),
                                "fingerprint": compute_operational_fingerprint(validation_payload),
                                "stable_name": "expert_router_validation_minimal",
                            },
                            {
                                "artifact_type": "expert_router_evaluation",
                                "path": str(evaluation_path.relative_to(router_root)),
                                "fingerprint": compute_operational_fingerprint(evaluation_payload),
                                "stable_name": "expert_router_evaluation_minimal",
                            },
                            {
                                "artifact_type": "expert_router_report",
                                "path": str(report_path.relative_to(router_root)),
                                "fingerprint": compute_operational_fingerprint(report_payload),
                                "stable_name": "expert_router_batch_report",
                            },
                            {
                                "artifact_type": "expert_router_replay_certification",
                                "path": str(replay_path.relative_to(router_root)),
                                "fingerprint": compute_operational_fingerprint(replay_payload),
                                "stable_name": "expert_router_replay_certification_minimal",
                            },
                        ],
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            router_a = router_root / "router_a"
            router_b = router_root / "router_b"
            router_derive_a = _run_command(
                [
                    sys.executable,
                    "scripts/derive_audit_trail.py",
                    "--source-manifest",
                    str(manifest_path),
                    "--source-type",
                    "expert_router",
                    "--output-dir",
                    str(router_a),
                ]
            )
            router_derive_b = _run_command(
                [
                    sys.executable,
                    "scripts/derive_audit_trail.py",
                    "--source-manifest",
                    str(manifest_path),
                    "--source-type",
                    "expert_router",
                    "--output-dir",
                    str(router_b),
                ]
            )

            router_trail_a = router_a / "audit_trail.json"
            router_trail_b = router_b / "audit_trail.json"
            router_manifest_a = router_a / "audit_manifest.json"
            router_manifest_b = router_b / "audit_manifest.json"

            if (
                router_derive_a.returncode == 0
                and router_derive_b.returncode == 0
                and router_trail_a.read_bytes() == router_trail_b.read_bytes()
                and router_manifest_a.read_bytes() == router_manifest_b.read_bytes()
            ):
                checks["router_audit_trail_deterministic"] = "passed"
                router_manifest_payload = json.loads(router_manifest_a.read_text(encoding="utf-8"))
                router_trail_payload = json.loads(router_trail_a.read_text(encoding="utf-8"))
                checks["router_audit_manifest_valid"] = (
                    "passed"
                    if (
                        router_manifest_payload.get("schema_version") == "4.9.0"
                        and router_manifest_payload.get("audit_fingerprint")
                        == router_trail_payload.get("audit_fingerprint")
                        and router_manifest_payload.get("event_count")
                        == router_trail_payload.get("event_count")
                        and isinstance(router_manifest_payload.get("source_artifacts"), list)
                        and router_manifest_payload.get("source_artifacts")
                    )
                    else "failed"
                )
                if checks["router_audit_manifest_valid"] != "passed":
                    details["router_audit_manifest_valid"] = "router audit manifest validation failed"

                router_unknown_source = _run_command(
                    [
                        sys.executable,
                        "scripts/derive_audit_trail.py",
                        "--source-manifest",
                        str(manifest_path),
                        "--source-type",
                        "unknown_thing",
                        "--output-dir",
                        str(router_root / "router_invalid"),
                    ]
                )
                if router_unknown_source.returncode != 0 and "Unsupported --source-type" in _detail(router_unknown_source):
                    checks["router_audit_trail_unknown_source_type_rejected"] = "passed"
                else:
                    checks["router_audit_trail_unknown_source_type_rejected"] = "failed"
                    details["router_audit_trail_unknown_source_type_rejected"] = _detail(router_unknown_source)
            elif any(
                candidate.returncode != 0 and _is_missing_runtime_surface(_detail(candidate))
                for candidate in (router_derive_a, router_derive_b)
            ):
                checks["router_audit_trail_deterministic"] = "pending_runtime"
                details["router_audit_trail_deterministic"] = "\n".join(
                    _detail(candidate)
                    for candidate in (router_derive_a, router_derive_b)
                    if candidate.returncode != 0 and _is_missing_runtime_surface(_detail(candidate))
                )
            else:
                checks["router_audit_trail_deterministic"] = "failed"
                details["router_audit_trail_deterministic"] = "\n".join(
                    part
                    for part in (
                        _detail(validation_result) if validation_result.returncode != 0 else "",
                        _detail(evaluation_result) if evaluation_result.returncode != 0 else "",
                        _detail(report_result) if report_result.returncode != 0 else "",
                        _detail(replay_result) if replay_result.returncode != 0 else "",
                        _detail(router_derive_a) if router_derive_a.returncode != 0 else "",
                        _detail(router_derive_b) if router_derive_b.returncode != 0 else "",
                        "router audit trail bytes differ"
                        if router_derive_a.returncode == 0 and router_derive_b.returncode == 0
                        else "",
                    )
                    if part
                )
        else:
            checks["router_audit_trail_deterministic"] = "failed"
            details["router_audit_trail_deterministic"] = "\n".join(
                part
                for part in (
                    _detail(validation_result) if validation_result.returncode != 0 else "",
                    _detail(evaluation_result) if evaluation_result.returncode != 0 else "",
                    _detail(report_result) if report_result.returncode != 0 else "",
                    _detail(replay_result) if replay_result.returncode != 0 else "",
                )
                if part
            )

    with tempfile.NamedTemporaryFile(
        prefix="core_release_verify_replay_",
        suffix=".json",
        delete=False,
    ) as handle:
        replay_output = Path(handle.name)

        replay_result = _run(
            [
                sys.executable,
                "scripts/replay_certification.py",
                "--reference-dir",
                "tests/reference_data",
                "--output",
                str(replay_output),
            ]
        )
    replay_detail = _detail(replay_result)
    checks["replay_certification"] = (
        "pending_runtime" if replay_result.returncode != 0 and _is_missing_runtime_surface(replay_detail) else _status(replay_result)
    )
    if replay_result.returncode != 0:
        details["replay_certification"] = replay_detail

    router_replay_status, router_replay_detail = _same_output(
        [
            sys.executable,
            "scripts/certify_router_replay.py",
            "--all",
        ]
    )
    if router_replay_status == "failed" and _is_missing_runtime_surface(router_replay_detail):
        router_replay_status = "pending_runtime"
    checks["router_replay_certification"] = router_replay_status
    if router_replay_detail:
        details["router_replay_certification"] = router_replay_detail

    try:
        replay_output.unlink()
    except FileNotFoundError:
        pass

    timings.append(_timing_record("replay", "replay", "passed" if not any(status == "failed" for status in checks.values()) else "failed", replay_start))

    if skip_full_pytest:
        checks["pytest"] = "skipped"
        timings.append({"name": "tests", "group": "tests", "status": "skipped", "duration_seconds": 0.0, "diagnostics": []})
    else:
        tests_exit_code, tests_payload = _run_tests_suite(
            target=target,
            timing_json=None,
            selected_group="tests-full",
            mode="full",
            timeout_seconds=TESTS_GROUP_TIMEOUT_SECONDS,
        )
        checks["pytest"] = tests_payload["status"]
        if tests_payload.get("details"):
            details["pytest"] = json.dumps(tests_payload["details"], sort_keys=True)
        timings.extend(tests_payload["timings"])
        if tests_payload.get("diagnostics"):
            diagnostics.extend(tests_payload["diagnostics"])
        if tests_exit_code == 2:
            details["tests"] = "blocked"
        elif tests_exit_code == 1:
            details["tests"] = "failed"

    failed = [name for name, status in checks.items() if status == "failed"]
    blocked = any(status == "blocked" for status in checks.values()) or any(
        diagnostic.get("severity") == "blocked" for diagnostic in diagnostics
    )

    # ── Target-based exclusion ────────────────────────────────────
    if exclusions:
        for exc_name in exclusions:
            if exc_name in checks:
                checks[exc_name] = "excluded"
                details.pop(exc_name, None)
        failed = [name for name, status in checks.items() if status == "failed"]

    payload: dict[str, Any] = {
        "schema": "core.release_verification.v1",
        "mode": "full",
        "target": target,
        "status": "blocked" if blocked else ("passed" if not failed else "failed"),
        "checks": dict(sorted(checks.items())),
        "details": dict(sorted(details.items())),
        "diagnostics": diagnostics,
        "timings": timings,
        "checks_summary": _checks_summary(checks),
    }
    _write_timing_json(timing_json, payload)
    return (0 if not failed else 1), payload


def verify_replay_only(target: str | None = None, timing_json: str | None = None) -> tuple[int, dict[str, Any]]:
    """Run the replay certification phase only."""
    timings: list[dict[str, Any]] = []
    checks: dict[str, str] = {}
    details: dict[str, str] = {}

    with tempfile.NamedTemporaryFile(
        prefix="core_release_verify_replay_",
        suffix=".json",
        delete=False,
    ) as handle:
        replay_output = Path(handle.name)

    replay_start = time.monotonic()
    replay_result = _run(
        [
            sys.executable,
            "scripts/replay_certification.py",
            "--reference-dir",
            "tests/reference_data",
            "--output",
            str(replay_output),
        ]
    )
    replay_detail = _detail(replay_result)
    checks["replay_certification"] = (
        "pending_runtime" if replay_result.returncode != 0 and _is_missing_runtime_surface(replay_detail) else _status(replay_result)
    )
    if replay_result.returncode != 0:
        details["replay_certification"] = replay_detail
    timings.append(_timing_record("replay_certification", "replay", checks["replay_certification"], replay_start))

    router_start = time.monotonic()
    router_replay_status, router_replay_detail = _same_output(
        [
            sys.executable,
            "scripts/certify_router_replay.py",
            "--all",
        ]
    )
    if router_replay_status == "failed" and _is_missing_runtime_surface(router_replay_detail):
        router_replay_status = "pending_runtime"
    checks["router_replay_certification"] = router_replay_status
    if router_replay_detail:
        details["router_replay_certification"] = router_replay_detail
    timings.append(_timing_record("router_replay_certification", "replay", router_replay_status, router_start))

    try:
        replay_output.unlink()
    except FileNotFoundError:
        pass

    failed = [name for name, status in checks.items() if status == "failed"]
    payload: dict[str, Any] = {
        "schema": "core.release_verification.v1",
        "mode": "replay",
        "target": target,
        "status": "passed" if not failed else "failed",
        "checks": dict(sorted(checks.items())),
        "details": dict(sorted(details.items())),
        "timings": timings,
    }
    _write_timing_json(timing_json, payload)
    return (0 if not failed else 1), payload


def verify_tests_only(target: str | None = None, timing_json: str | None = None) -> tuple[int, dict[str, Any]]:
    """Run only the pytest phase."""
    exit_code, payload = _run_tests_suite(
        target=target,
        timing_json=timing_json,
        selected_group="tests-full",
        mode="tests-full",
    )
    return exit_code, payload


def _tests_timeout_diagnostic(subgroup: str, timeout_seconds: int) -> dict[str, Any]:
    return {
        "code": "core.release_gate.tests_subgroup_timeout",
        "severity": "blocked",
        "path": "tests/",
        "message": "Pytest subgroup exceeded configured timeout.",
        "mutation_allowed": False,
        "details": {
            "subgroup": subgroup,
            "timeout_seconds": timeout_seconds,
        },
    }


def _pytest_capture_for_subgroup(
    repo_root: Path,
    subgroup: dict[str, Any],
    timeout_seconds: int,
) -> tuple[SubprocessCapture, list[dict[str, Any]]]:
    targets = _resolve_test_targets(repo_root, subgroup["targets"])
    command = [sys.executable, "-m", "pytest", "-q", *targets]
    diagnostics: list[dict[str, Any]] = []
    if not targets:
        diagnostics.append(
            {
                "code": "core.release_gate.pytest_target_missing",
                "severity": "blocked",
                "path": "tests/",
                "message": "Pytest subgroup has no matching targets.",
                "mutation_allowed": False,
                "details": {
                    "subgroup": subgroup["name"],
                },
            }
        )
        capture = SubprocessCapture(
            command=command,
            cwd=str(repo_root),
            expect_json=False,
            returncode=2,
            stdout="",
            stderr="",
            timed_out=False,
            timeout_seconds=timeout_seconds,
            elapsed_seconds=0.0,
            json_detected=False,
            json_payload=None,
            report_path=None,
            target_argument=None,
            stdout_preview="",
            stderr_preview="",
            stdout_truncated=False,
            stderr_truncated=False,
        )
        return capture, diagnostics

    try:
        completed = _run_command(command, timeout_seconds=timeout_seconds, expect_json=False)
    except subprocess.TimeoutExpired as exc:
        capture = SubprocessCapture(
            command=command,
            cwd=str(repo_root),
            expect_json=False,
            returncode=None,
            stdout=_coerce_text(exc.output),
            stderr=_coerce_text(exc.stderr),
            timed_out=True,
            timeout_seconds=timeout_seconds,
            elapsed_seconds=float(timeout_seconds),
            json_detected=False,
            json_payload=None,
            report_path=None,
            target_argument=None,
            stdout_preview=_truncate_text(_coerce_text(exc.output))[0],
            stderr_preview=_truncate_text(_coerce_text(exc.stderr))[0],
            stdout_truncated=len(_coerce_text(exc.output)) > OUTPUT_PREVIEW_LIMIT,
            stderr_truncated=len(_coerce_text(exc.stderr)) > OUTPUT_PREVIEW_LIMIT,
        )
        return capture, [_tests_timeout_diagnostic(subgroup["name"], timeout_seconds)]
    except (FileNotFoundError, OSError) as exc:
        capture = SubprocessCapture(
            command=command,
            cwd=str(repo_root),
            expect_json=False,
            returncode=None,
            stdout="",
            stderr=str(exc),
            timed_out=False,
            timeout_seconds=timeout_seconds,
            elapsed_seconds=0.0,
            json_detected=False,
            json_payload=None,
            report_path=None,
            target_argument=None,
            stdout_preview="",
            stderr_preview=_truncate_text(str(exc))[0],
            stdout_truncated=False,
            stderr_truncated=len(str(exc)) > OUTPUT_PREVIEW_LIMIT,
        )
        return capture, [
            {
                "code": "core.release_gate.pytest_command_failed",
                "severity": "blocked",
                "path": "tests/",
                "message": "Pytest subgroup invocation failed.",
                "mutation_allowed": False,
                "details": {
                    "subgroup": subgroup["name"],
                    "error": str(exc),
                },
            }
        ]

    if isinstance(completed, SubprocessCapture):
        capture = completed
    else:
        stdout = _coerce_text(completed.stdout)
        stderr = _coerce_text(completed.stderr)
        capture = SubprocessCapture(
            command=command,
            cwd=str(repo_root),
            expect_json=False,
            returncode=completed.returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=False,
            timeout_seconds=timeout_seconds,
            elapsed_seconds=0.0,
            json_detected=False,
            json_payload=None,
            report_path=None,
            target_argument=None,
            stdout_preview=_truncate_text(stdout)[0],
            stderr_preview=_truncate_text(stderr)[0],
            stdout_truncated=len(stdout) > OUTPUT_PREVIEW_LIMIT,
            stderr_truncated=len(stderr) > OUTPUT_PREVIEW_LIMIT,
        )
    if capture.timed_out:
        diagnostics.append(_tests_timeout_diagnostic(subgroup["name"], timeout_seconds))
    elif capture.returncode == 2:
        diagnostics.append(
            {
                "code": "core.release_gate.pytest_collect_failed",
                "severity": "blocked",
                "path": "tests/",
                "message": "Pytest collection failed for subgroup.",
                "mutation_allowed": False,
                "details": {
                    "subgroup": subgroup["name"],
                    "exit_code": capture.returncode,
                },
            }
        )
    elif capture.returncode not in (0, None):
        diagnostics.append(
            {
                "code": "core.release_gate.tests_subgroup_failed",
                "severity": "error",
                "path": "tests/",
                "message": "Pytest subgroup failed.",
                "mutation_allowed": False,
                "details": {
                    "subgroup": subgroup["name"],
                    "exit_code": capture.returncode,
                },
            }
        )
    return capture, diagnostics


def _run_tests_suite(
    target: str | None,
    timing_json: str | None,
    selected_group: str | None,
    mode: str,
    timeout_seconds: int = TESTS_GROUP_TIMEOUT_SECONDS,
) -> tuple[int, dict[str, Any]]:
    repo_root = _repo_root()
    subgroups = _build_tests_subgroups(repo_root)
    if selected_group in {None, "tests", "tests-full"}:
        selected = subgroups
    else:
        selected = [subgroup for subgroup in subgroups if subgroup["name"] == selected_group]

    if selected_group is not None and not selected:
        payload = {
            "schema": "core.release_verification.v1",
            "mode": mode,
            "group": selected_group,
            "target": target,
            "status": "blocked",
            "diagnostics": [
                {
                    "code": "core.release_gate.group_unknown",
                    "severity": "blocked",
                    "message": "Unknown release gate group.",
                    "mutation_allowed": False,
                }
            ],
            "test_subgroups": [],
            "timings": [],
        }
        _write_timing_json(timing_json, payload)
        return 2, payload

    selected_names = [subgroup["name"] for subgroup in selected]
    timings: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    details: dict[str, str] = {}
    subgroup_results: list[dict[str, Any]] = []
    overall_status = "passed"
    exit_code = 0

    for subgroup in selected:
        start = time.monotonic()
        capture, subgroup_diagnostics = _pytest_capture_for_subgroup(repo_root, subgroup, timeout_seconds)
        subgroup_status = capture.status
        if subgroup_status == "internal_error":
            overall_status = "failed"
            exit_code = 3
            diagnostics.extend(subgroup_diagnostics)
        elif subgroup_status == "blocked":
            overall_status = "blocked"
            exit_code = 2
            diagnostics.extend(subgroup_diagnostics)
        elif subgroup_status == "error":
            overall_status = "failed"
            exit_code = 1
            diagnostics.extend(subgroup_diagnostics)

        subgroup_results.append(
            {
                "name": subgroup["name"],
                "targets": subgroup["targets"],
                "required_for_full_release": subgroup["required_for_full_release"],
                "status": subgroup_status,
                "exit_code": capture.returncode,
            }
        )
        timings.append(
            _timing_record(
                subgroup["name"],
                "tests",
                subgroup_status,
                start,
                diagnostics=subgroup_diagnostics,
                command=capture.command,
                timeout_seconds=timeout_seconds,
                stdout_preview=capture.stdout_preview,
                stderr_preview=capture.stderr_preview,
                subgroup=subgroup["name"],
            )
        )
        if subgroup_status == "blocked":
            details["tests"] = "subgroup={0}; timeout_seconds={1}".format(subgroup["name"], timeout_seconds)
            break
        if subgroup_status == "error":
            details["tests"] = "subgroup={0}; exit_code={1}".format(subgroup["name"], capture.returncode)
            break
        if subgroup_status == "internal_error":
            details["tests"] = "subgroup={0}; internal_error".format(subgroup["name"])
            break

    if selected_group in {None, "tests", "tests-full"}:
        mode_status = "passed" if overall_status == "passed" else ("blocked" if overall_status == "blocked" else "failed")
    else:
        mode_status = "passed" if overall_status == "passed" else ("blocked" if overall_status == "blocked" else "failed")

    payload: dict[str, Any] = {
        "schema": "core.release_verification.v1",
        "mode": mode,
        "group": selected_group or "tests-full",
        "target": target,
        "status": mode_status,
        "checks": {"pytest": mode_status},
        "details": details,
        "test_subgroups": subgroup_results,
        "timings": timings,
        "test_subgroup_names": selected_names,
    }
    if diagnostics:
        payload["diagnostics"] = diagnostics
    _write_timing_json(timing_json, payload)
    return exit_code if exit_code else 0, payload


def _catalog_group_checks() -> dict[str, list[str]]:
    repo_root = _repo_root()
    test_subgroups = _build_tests_subgroups(repo_root)
    test_group_names = [subgroup["name"] for subgroup in test_subgroups]
    release_metadata_checks = _check_name_list(BRIDGES)
    release_metadata_checks.extend(
        [
            "run_all_examples_deterministic",
            "skeleton_roundtrip_deterministic",
            "replay_explain_roundtrip_deterministic",
            "compatibility_matrix_deterministic",
            "protocol_model_readiness",
            "protocol_model_candidate_package_readiness",
            "protocol_model_external_candidate_output_evaluation",
            "protocol_model_candidate_comparison",
            "protocol_model_external_submission_intake",
            "protocol_model_submission_comparison",
            "protocol_model_certification_dossier",
            "protocol_model_candidate_package_certification",
            "protocol_model_candidate_output_diagnostics",
            "protocol_model_artifact_readiness",
            "protocol_model_candidate_gate",
            "protocol_model_candidate_trial",
            "development_audit_readiness",
            "development_audit_enforcement_runtime_core",
            "development_audit_enforcement_docs",
        ]
    )
    release_metadata_checks.extend(_check_name_list(STATE_WATCHER_CHECKS))
    release_metadata_checks.extend(_check_name_list(PRIVATE_DOMAIN_CANDIDATE_CHECKS))
    release_metadata_checks.extend(_check_name_list(CLASSIFICATION_CANDIDATE_CHECKS))
    release_metadata_checks.extend(_check_name_list(PARAMETRIC_TEMPLATE_CHECKS))
    release_metadata_checks.extend(_check_name_list(BOUNDED_REFERENCE_INDEX_CHECKS))
    release_metadata_checks.extend(_check_name_list(HUMAN_APPROVED_EXECUTION_GATE_CHECKS))
    release_metadata_checks.extend(_check_name_list(EXPERT_CONFLICT_PRE_RESOLUTION_CHECKS))
    release_metadata_checks.extend(_check_name_list(AGENT_SESSION_CHECKS))
    release_metadata_checks.extend(_check_name_list(AGENT_PLAN_CHECKS))
    release_metadata_checks.extend(_check_name_list(TOOL_INVOCATION_CHECKS))
    release_metadata_checks.extend(_check_name_list(AGENT_DECISION_TRACE_CHECKS))
    release_metadata_checks.extend(_check_name_list(DOWNSTREAM_BRIDGE_ADAPTER_CHECKS))
    release_metadata_checks.extend(_check_name_list(AGENT_BOUNDARY_FREEZE_CHECKS))
    release_metadata_checks.extend(_check_name_list(ANCHORING_SUBMISSION_CHECKS))
    release_metadata_checks.extend(_check_name_list(CHAIN_ADAPTER_CHECKS))
    release_metadata_checks.extend(_check_name_list(MERKLE_BATCH_CHECKS))
    release_metadata_checks.extend(_check_name_list(FROZEN_RULE_ANCHOR_CHECKS))
    release_metadata_checks.extend(_check_name_list(FROZEN_RELEASE_MANIFEST_CHECKS))
    release_metadata_checks.extend(_check_name_list(EXECUTABLE_CONTRACT_CHECKS))
    release_metadata_checks.extend(_check_name_list(DOCUMENT_ATTESTATION_CHECKS))
    release_metadata_checks.extend(_check_name_list(PROCESS_ATTESTATION_CHECKS))
    release_metadata_checks.extend(_check_name_list(EXECUTION_PROFILE_CHECKS))
    release_metadata_checks.extend(_check_name_list(V103_CHECKS))
    release_metadata_checks.extend(_check_name_list(V10_NATIVE_CHECKS))
    release_metadata_checks.extend(_check_name_list(V102_CHECKS))
    release_metadata_checks.extend(_check_name_list(V104_CHECKS))
    release_metadata_checks.extend(_check_name_list(V105_CHECKS))

    return {
        "tooling": _check_name_list({
            "compileall": None,
            "ruff": None,
            "mypy_report_only": None,
        }),
        "release-metadata": sorted(dict.fromkeys(release_metadata_checks)),
        "docs": sorted(dict.fromkeys(release_metadata_checks)),
        "replay": [
            "replay_certification",
            "router_replay_certification",
        ],
        "tests": test_group_names,
        "tests-tooling": test_subgroups[0]["targets"],
        "tests-replay": test_subgroups[1]["targets"],
        "tests-integration": test_subgroups[2]["targets"],
        "tests-contracts": test_subgroups[3]["targets"],
        "tests-core": test_subgroups[4]["targets"],
        "tests-full": test_group_names,
        "full": [],
    }


def _list_checks_payload(target: str | None) -> dict[str, Any]:
    groups = _catalog_group_checks()
    flat_checks = sorted(
        dict.fromkeys(
            check
            for group_name, checks in groups.items()
            if group_name != "full"
            for check in checks
        )
    )
    return {
        "schema": "core.release_verification.v1",
        "mode": "list-checks",
        "target": target,
        "status": "passed",
        "groups": {name: checks for name, checks in groups.items() if name != "full"},
        "checks": flat_checks,
    }


def _plan_payload(target: str | None, group: str | None = None) -> dict[str, Any]:
    groups = _catalog_group_checks()
    if group in {None, "tests", "tests-full"}:
        return {
            "schema": "core.release_verification.v1",
            "mode": "plan",
            "target": target,
            "status": "passed",
            "group": group or "tests",
            "test_subgroups": _tests_planned_subgroups(_repo_root(), selected=group),
        }
    if group and group.startswith("tests-"):
        return {
            "schema": "core.release_verification.v1",
            "mode": "plan",
            "target": target,
            "status": "passed",
            "group": group,
            "test_subgroups": _tests_planned_subgroups(_repo_root(), selected=group),
        }
    selected = [group] if group else [name for name in groups.keys() if name != "full"]
    plan_groups = []
    for group_name in selected:
        checks = groups.get(group_name)
        if checks is None:
            continue
        plan_groups.append(
            {
                "group": group_name,
                "status": "planned",
                "checks": checks,
            }
        )
    return {
        "schema": "core.release_verification.v1",
        "mode": "plan",
        "target": target,
        "status": "passed",
        "plan": plan_groups,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a CORE release locally.")
    parser.add_argument("--output", default=None)
    parser.add_argument("--skip-full-pytest", action="store_true")
    parser.add_argument("--target", default=None,
                        help="Release target (e.g. v6.9). Excludes checks from later versions.")
    parser.add_argument("--group", default=None)
    parser.add_argument("--list-checks", action="store_true")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--timing-json", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    valid_groups = set(_catalog_group_checks().keys()) - {"full"}
    if args.group is not None and args.group not in valid_groups:
        payload = {
            "schema": "core.release_verification.v1",
            "mode": "error",
            "target": args.target,
            "status": "blocked",
            "diagnostics": [
                {
                    "code": "core.release_gate.group_unknown",
                    "severity": "blocked",
                    "message": "Unknown release gate group.",
                    "mutation_allowed": False,
                }
            ],
        }
        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
        else:
            print(text, end="")
        return 2

    if args.list_checks:
        payload = _list_checks_payload(args.target)
        exit_code = 0
    elif args.plan:
        payload = _plan_payload(args.target, group=args.group)
        exit_code = 0
    elif args.group == "tooling":
        exit_code, payload = verify(
            skip_full_pytest=args.skip_full_pytest,
            target=args.target,
            stop_after_tooling=True,
            timing_json=args.timing_json,
        )
    elif args.group in {"release-metadata", "docs"}:
        exit_code, payload = verify(
            skip_full_pytest=args.skip_full_pytest,
            target=args.target,
            stop_before_replay=True,
            timing_json=args.timing_json,
        )
    elif args.group == "replay":
        exit_code, payload = verify_replay_only(target=args.target, timing_json=args.timing_json)
    elif args.group in {"tests", "tests-full", "tests-tooling", "tests-replay", "tests-integration", "tests-contracts", "tests-core"}:
        exit_code, payload = _run_tests_suite(
            target=args.target,
            timing_json=args.timing_json,
            selected_group=args.group,
            mode="tests" if args.group == "tests" else args.group,
        )
    else:
        exit_code, payload = verify(
            skip_full_pytest=args.skip_full_pytest,
            target=args.target,
            timing_json=args.timing_json,
        )
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
