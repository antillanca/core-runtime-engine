from __future__ import annotations

import json
import subprocess

import pytest

import scripts.verify_release as verify_release

# v6.9 gate: checks that must pass (v7.0+ are excluded via --target)
V69_RELEASE_METADATA_CHECKS = {
    "compileall",
    "ruff",
    "mypy_report_only",
    "audio_bridge",
    "image_bridge",
    "wifi_csi_bridge",
    "run_all_examples_deterministic",
    "skeleton_roundtrip_deterministic",
    "replay_explain_roundtrip_deterministic",
    "compatibility_matrix_deterministic",
    "protocol_model_readiness",
    "protocol_model_candidate_package_readiness",
    "protocol_model_candidate_package_certification",
    "protocol_model_candidate_output_diagnostics",
    "protocol_model_external_candidate_output_evaluation",
    "protocol_model_candidate_comparison",
    "protocol_model_external_submission_intake",
    "protocol_model_submission_comparison",
    "protocol_model_certification_dossier",
    "protocol_model_artifact_readiness",
    "protocol_model_candidate_gate",
    "protocol_model_candidate_trial",
    "development_audit_readiness",
    "protocol_model_domain_vocabulary_validation",
    "protocol_model_command_candidate_validation",
    "protocol_model_command_candidate_compilation",
    "development_audit_enforcement_runtime_core",
    "development_audit_enforcement_docs",
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
    "frozen_release_manifest_v11_1_accepted",
    "frozen_rule_set_general_accepted",
    "frozen_rule_set_personal_commitment_accepted",
    "rule_approval_general_signature_accepted",
    "rule_approval_personal_signature_accepted",
    "rule_anchor_batch_manifest_accepted",
}

V112_CHECKS = V111_CHECKS | {
    "frozen_release_manifest_v11_2_candidate_accepted",
}

V104_SLICE2_CHECKS = {
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


def _fake_completed(command: list[str], returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr=stderr)


def _install_fast_verify_release(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(verify_release, "_run", lambda command: _fake_completed(command, 0, stdout="PASS"))
    monkeypatch.setattr(verify_release, "_same_result", lambda command: ("passed", ""))


def test_verify_release_v69_gate_passes():
    payload = _run_release_metadata(target="v6.9")

    assert payload["schema"] == "core.release_verification.v1"
    assert payload["mode"] == "release-metadata"
    assert payload["target"] == "v6.9"
    assert V69_RELEASE_METADATA_CHECKS.issubset(set(payload["checks"])), (
        f"missing checks: {V69_RELEASE_METADATA_CHECKS - set(payload['checks'])}"
    )
    for name in V104_SLICE2_CHECKS:
        assert payload["checks"][name] == "pending_runtime", name


def test_verify_release_v69_gate_is_deterministic():
    first = _run_release_metadata(target="v6.9")
    second = _run_release_metadata(target="v6.9")

    assert first == second


def test_verify_release_v104_includes_slice2_checks():
    payload = _run_release_metadata(target="v10.4")

    assert payload["target"] == "v10.4"
    assert V104_SLICE2_CHECKS.issubset(set(payload["checks"])), (
        f"missing checks: {V104_SLICE2_CHECKS - set(payload['checks'])}"
    )
    for name in V104_SLICE2_CHECKS:
        assert payload["checks"][name] == "passed", name


def test_verify_release_v95_gate_includes_v9x_checks():
    payload = _run_release_metadata(target="v9.5")

    assert payload["target"] == "v9.5"
    assert V93_CHECKS.issubset(set(payload["checks"]))
    assert V94_CHECKS.issubset(set(payload["checks"]))
    assert V95_CHECKS.issubset(set(payload["checks"]))
    for name in V93_CHECKS | V94_CHECKS | V95_CHECKS:
        assert payload["checks"][name] == "passed", name


def test_verify_release_v111_runs_frozen_rule_anchor_checks():
    payload = _run_release_metadata(target="v11.1")

    assert V111_CHECKS.issubset(set(payload["checks"]))
    for name in V111_CHECKS:
        assert payload["checks"][name] == "passed", name


def test_verify_release_v112_runs_candidate_manifest_and_preserves_v111_baseline():
    payload = _run_release_metadata(target="v11.2")

    assert V112_CHECKS.issubset(set(payload["checks"]))
    assert payload["checks"]["frozen_release_manifest_v11_1_accepted"] == "historical_baseline_preserved"
    assert payload["checks"]["frozen_release_manifest_v11_2_candidate_accepted"] == "passed"


def test_target_comparison_does_not_treat_v11_as_older_than_v9() -> None:
    assert verify_release._target_at_least("v11.0.1", "v9.5")
    assert verify_release._target_at_least("v11.1.0", "v11.1")
    assert verify_release._target_at_least("v11.2.0", "v11.2")
    assert not verify_release._target_at_least("v11.0.1", "v11.1")


def _run_release_metadata(target: str) -> dict:
    monkeypatch = pytest.MonkeyPatch()
    try:
        _install_fast_verify_release(monkeypatch)
        payload = verify_release.verify(skip_full_pytest=True, target=target, stop_before_replay=True)[1]
        normalized = json.loads(json.dumps(payload))
        for timing in normalized.get("timings", []):
            timing["duration_seconds"] = 0.0
        return normalized
    finally:
        monkeypatch.undo()
