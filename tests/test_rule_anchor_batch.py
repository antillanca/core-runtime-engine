from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from core_runtime.core.rule_anchor import (
    build_rule_anchor_batch,
    validate_rule_anchor_batch_payload,
    verify_rule_anchor_proof,
)
from scripts.validate_rule_anchor_batch import validate_rule_anchor_batch


ROOT = Path(__file__).resolve().parent.parent
RULE_DIR = ROOT / "examples" / "frozen_rules"
APPROVAL_DIR = ROOT / "examples" / "rule_approvals"
BATCH_DIR = ROOT / "examples" / "merkle_batch"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _rules_and_approvals() -> tuple[list[dict], list[dict]]:
    return (
        [
            _load(RULE_DIR / "general_cooperative_supply.json"),
            _load(RULE_DIR / "personal_commitment.json"),
        ],
        [
            _load(APPROVAL_DIR / "general_cooperative_supply.json"),
            _load(APPROVAL_DIR / "personal_commitment.json"),
        ],
    )


def test_batch_fixture_and_every_proof_are_valid() -> None:
    batch = _load(BATCH_DIR / "accepted_batch_manifest.json")
    assert validate_rule_anchor_batch_payload(batch) == []
    assert all(verify_rule_anchor_proof(entry, batch["merkle_root"]) for entry in batch["entries"])


def test_batch_is_deterministic_independent_of_input_order() -> None:
    rules, approvals = _rules_and_approvals()
    first = build_rule_anchor_batch(rules, approvals)
    second = build_rule_anchor_batch(list(reversed(rules)), list(reversed(approvals)))
    assert first == second
    assert first == _load(BATCH_DIR / "accepted_batch_manifest.json")


@pytest.mark.parametrize(
    "name,expected_code",
    [
        ("rejected_empty_items.json", "schema_validation_error"),
        ("rejected_duplicate_fingerprints.json", "duplicate_rule_set_fingerprint"),
        ("rejected_tampered_root.json", "invalid_merkle_proof"),
        ("rejected_tampered_path.json", "invalid_merkle_proof"),
    ],
)
def test_rejected_batch_fixtures(name: str, expected_code: str) -> None:
    result = validate_rule_anchor_batch(BATCH_DIR / name)
    assert result["status"] == "failed"
    assert expected_code in {item["code"] for item in result["errors"]}


def test_duplicate_rule_set_or_approval_is_rejected_before_batching() -> None:
    rules, approvals = _rules_and_approvals()
    with pytest.raises(ValueError, match="duplicate frozen rule-set fingerprint"):
        build_rule_anchor_batch([rules[0], copy.deepcopy(rules[0])], [approvals[0]])
    with pytest.raises(ValueError, match="duplicate rule-approval fingerprint"):
        build_rule_anchor_batch(rules, [approvals[0], copy.deepcopy(approvals[0]), approvals[1]])


def test_missing_approval_fails_closed() -> None:
    rules, approvals = _rules_and_approvals()
    with pytest.raises(ValueError, match="approval threshold"):
        build_rule_anchor_batch(rules, [approvals[0]])

