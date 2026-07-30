from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

from core_runtime.core.contract_evaluator import (
    SEMANTIC_VALIDATORS,
    bind_artifact_fingerprint,
    evaluate_contract_payload,
    executable_contract_versions,
    validate_contract_structure,
)
from core_runtime.core.contract_executability import audit_contract_executability
from core_runtime.core.contract_probes import (
    accepted_contract_payloads,
    executable_contract_probes,
)


ROOT = Path(__file__).resolve().parents[1]


def _codes(report: dict) -> set[str]:
    return {item["code"] for item in report["errors"]}


def test_every_generic_contract_has_an_executable_semantic_probe() -> None:
    versions = set(executable_contract_versions())
    assert versions == set(SEMANTIC_VALIDATORS)
    assert versions == set(accepted_contract_payloads())
    assert versions == {probe.schema_version for probe in executable_contract_probes()}


def test_accepted_contracts_produce_deterministic_non_authorizing_decisions() -> None:
    for version, payload in accepted_contract_payloads().items():
        first = evaluate_contract_payload(payload)
        second = evaluate_contract_payload(payload)
        assert first == second, version
        assert first["status"] == "passed", (version, first["errors"])
        assert first["decision"] == "accepted"
        assert first["truth_claimed"] is False
        assert first["execution_authorized"] is False
        assert first["deployment_authorized"] is False
        assert first["evaluated_rules"]


def test_schema_valid_semantic_negatives_are_rejected_for_every_contract() -> None:
    for probe in executable_contract_probes():
        negative = copy.deepcopy(probe.accepted)
        probe.mutate(negative)
        assert validate_contract_structure(negative) == [], probe.schema_version
        result = evaluate_contract_payload(negative)
        assert result["status"] == "failed", probe.schema_version
        assert probe.expected_error in _codes(result), probe.schema_version


def test_strict_evaluation_closes_legacy_extension_fields_without_rewriting_schema() -> None:
    payload = accepted_contract_payloads()["core.context_gate.v1"]
    payload["undeclared_extension"] = "not part of the executable contract"
    strict = evaluate_contract_payload(payload)
    compatibility = evaluate_contract_payload(payload, strict=False)
    assert "undeclared_field" in _codes(strict)
    assert compatibility["status"] == "passed"


def test_fingerprinted_contract_rejects_semantic_tampering() -> None:
    payload = accepted_contract_payloads()["core.control_decision.v1"]
    payload["reason"] = "tampered without rebinding"
    result = evaluate_contract_payload(payload)
    assert "fingerprint_mismatch" in _codes(result)


def test_executability_audit_covers_every_public_core_schema_and_is_deterministic() -> None:
    first = audit_contract_executability()
    second = audit_contract_executability()
    assert first == second
    assert first["status"] == "passed"
    assert first["contract_count"] == 19
    assert first["passed_count"] == 19
    assert first["failed_count"] == 0
    assert first["public_schema_count"] == len(list((ROOT / "schemas" / "core").glob("*.json")))
    assert all(row["mechanism"] != "unclassified" for row in first["public_schema_inventory"])


def test_contract_evaluator_cli_has_stable_standard_envelope(tmp_path: Path) -> None:
    payload = accepted_contract_payloads()["core.context_threshold.v1"]
    artifact = tmp_path / "threshold.json"
    artifact.write_text(json.dumps(payload), encoding="utf-8")
    command = [sys.executable, "scripts/evaluate_core_contract.py", str(artifact)]
    first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    assert first.returncode == 0, first.stderr
    assert first.stdout == second.stdout
    report = json.loads(first.stdout)
    assert report["schema"] == "core.contract_evaluation.v1"
    assert report["status"] == "passed"
    assert report["authority"] == "validation_only"


def test_rebinding_changes_fingerprint_but_does_not_hide_semantic_failure() -> None:
    payload = accepted_contract_payloads()["core.reversibility_policy.v1"]
    original = payload["fingerprint"]
    payload["human_approval_required"] = False
    payload = bind_artifact_fingerprint(payload)
    assert payload["fingerprint"] != original
    result = evaluate_contract_payload(payload)
    assert "responsible_approval_required" in _codes(result)
