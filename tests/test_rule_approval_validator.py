from __future__ import annotations

import copy
import json
from pathlib import Path

from core_runtime.core.rule_anchor import (
    SECP256K1_N,
    artifact_fingerprint,
    build_rule_anchor_batch,
    validate_rule_approval_payload,
)
from scripts.validate_rule_approval import validate_rule_approval


ROOT = Path(__file__).resolve().parent.parent
APPROVAL_DIR = ROOT / "examples" / "rule_approvals"
RULE_DIR = ROOT / "examples" / "frozen_rules"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _codes(payload: dict) -> set[str]:
    return {item["code"] for item in validate_rule_approval_payload(payload)}


def test_fixture_signatures_recover_to_declared_signer() -> None:
    for name in ("general_cooperative_supply.json", "personal_commitment.json"):
        result = validate_rule_approval(APPROVAL_DIR / name)
        assert result["status"] == "passed"
        assert result["approval_valid"] is True


def test_chain_or_contract_tamper_invalidates_signed_message() -> None:
    payload = _load(APPROVAL_DIR / "general_cooperative_supply.json")
    payload["chain_id"] += 1
    payload["fingerprint"] = artifact_fingerprint(payload)
    assert "approval_message_mismatch" in _codes(payload)


def test_signature_tamper_is_rejected() -> None:
    payload = _load(APPROVAL_DIR / "general_cooperative_supply.json")
    signature = payload["signature"]
    payload["signature"] = signature[:10] + ("0" if signature[10] != "0" else "1") + signature[11:]
    payload["fingerprint"] = artifact_fingerprint(payload)
    codes = _codes(payload)
    assert {"signature_signer_mismatch", "signature_verification_failed"} & codes


def test_high_s_malleable_signature_is_rejected() -> None:
    payload = _load(APPROVAL_DIR / "general_cooperative_supply.json")
    raw = bytes.fromhex(payload["signature"][2:])
    high_s = SECP256K1_N - int.from_bytes(raw[32:64], "big")
    payload["signature"] = "0x" + raw[:32].hex() + high_s.to_bytes(32, "big").hex() + raw[64:].hex()
    payload["fingerprint"] = artifact_fingerprint(payload)
    assert "noncanonical_signature_s" in _codes(payload)


def test_batch_rejects_unauthorized_signer_even_with_valid_signature() -> None:
    rule = _load(RULE_DIR / "general_cooperative_supply.json")
    approval = _load(APPROVAL_DIR / "general_cooperative_supply.json")
    rule = copy.deepcopy(rule)
    rule["governance"]["authorized_signers"] = ["0x2222222222222222222222222222222222222222"]
    rule["fingerprint"] = artifact_fingerprint(rule)
    approval["rule_set_fingerprint"] = rule["fingerprint"]
    with __import__("pytest").raises(ValueError, match="invalid rule approval"):
        build_rule_anchor_batch([rule], [approval])

