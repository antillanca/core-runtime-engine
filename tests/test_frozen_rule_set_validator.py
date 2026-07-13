from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

from core_runtime.core.rule_anchor import (
    artifact_fingerprint,
    private_rule_commitment,
    validate_frozen_rule_set_payload,
    verify_private_rule_opening,
)
from scripts.validate_frozen_rule_set import validate_frozen_rule_set


ROOT = Path(__file__).resolve().parent.parent
GENERAL = ROOT / "examples" / "frozen_rules" / "general_cooperative_supply.json"
PERSONAL = ROOT / "examples" / "frozen_rules" / "personal_commitment.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _codes(payload: dict) -> set[str]:
    return {item["code"] for item in validate_frozen_rule_set_payload(payload)}


def test_valid_general_and_personal_fixtures() -> None:
    for path in (GENERAL, PERSONAL):
        result = validate_frozen_rule_set(path)
        assert result["status"] == "passed"
        assert result["rule_set_valid"] is True


def test_public_rule_tamper_breaks_fingerprint() -> None:
    payload = _load(GENERAL)
    payload["content"]["rules"][0]["purpose"] += " altered"
    assert "fingerprint_mismatch" in _codes(payload)


def test_personal_rule_cannot_publish_plaintext_rules() -> None:
    payload = _load(PERSONAL)
    payload["content"]["rules"] = [{"secret": "must-not-be-public"}]
    assert "schema_validation_error" in _codes(payload)


def test_general_and_personal_visibility_are_not_interchangeable() -> None:
    general = _load(GENERAL)
    general["visibility"] = "private_commitment"
    general["fingerprint"] = artifact_fingerprint(general)
    assert "general_rule_must_be_public" in _codes(general)

    personal = _load(PERSONAL)
    personal["visibility"] = "public"
    personal["fingerprint"] = artifact_fingerprint(personal)
    assert "personal_rule_must_be_private_commitment" in _codes(personal)


def test_approval_threshold_must_be_reachable() -> None:
    payload = _load(GENERAL)
    payload["governance"]["approval_threshold"] = 2
    payload["fingerprint"] = artifact_fingerprint(payload)
    assert "approval_threshold_unreachable" in _codes(payload)


def test_duplicate_steps_and_signers_are_rejected() -> None:
    payload = _load(GENERAL)
    payload["content"]["rules"][0]["steps"].append(
        copy.deepcopy(payload["content"]["rules"][0]["steps"][0])
    )
    payload["governance"]["authorized_signers"].append(
        payload["governance"]["authorized_signers"][0].upper().replace("0X", "0x")
    )
    payload["fingerprint"] = artifact_fingerprint(payload)
    codes = _codes(payload)
    assert "duplicate_step_id" in codes
    assert "duplicate_authorized_signer" in codes


def test_frozen_timestamp_requires_timezone() -> None:
    payload = _load(GENERAL)
    payload["frozen_at"] = "2026-07-13T00:00:00"
    payload["fingerprint"] = artifact_fingerprint(payload)
    assert "invalid_frozen_at" in _codes(payload)


def test_nonhuman_biological_evidence_is_supported_but_not_an_approver() -> None:
    payload = _load(GENERAL)
    sources = payload["content"]["rules"][0]["steps"][0]["accepted_evidence_sources"]
    sources.append("nonhuman_biological")
    payload["fingerprint"] = artifact_fingerprint(payload)
    assert validate_frozen_rule_set_payload(payload) == []
    assert payload["governance"]["accountability"] == "authorized_signer_set"


def test_private_commitment_is_blinded_and_openable() -> None:
    private_payload = {"preference": "synthetic-low-entropy-value"}
    nonce_a = bytes(range(32))
    nonce_b = bytes(reversed(range(32)))
    commitment_a = private_rule_commitment(private_payload, nonce_a)
    commitment_b = private_rule_commitment(private_payload, nonce_b)
    assert commitment_a != commitment_b
    assert verify_private_rule_opening(private_payload, nonce_a.hex(), commitment_a)
    assert not verify_private_rule_opening(private_payload, nonce_b.hex(), commitment_a)


def test_private_commitment_cli_keeps_opening_secret(tmp_path: Path) -> None:
    private_path = tmp_path / "private.json"
    template_path = tmp_path / "template.json"
    public_output = tmp_path / "public.json"
    opening_output = tmp_path / "opening.json"
    private_path.write_text('{"rules":[{"synthetic":true}]}\n', encoding="utf-8")
    template = _load(PERSONAL)
    template["content"]["commitment"] = "sha256:" + ("0" * 64)
    template["fingerprint"] = "sha256:" + ("0" * 64)
    template_path.write_text(json.dumps(template), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/create_private_rule_commitment.py",
            "--private-rules",
            str(private_path),
            "--public-template",
            str(template_path),
            "--public-output",
            str(public_output),
            "--opening-output",
            str(opening_output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    public_text = public_output.read_text(encoding="utf-8")
    assert "blinding_nonce_hex" not in public_text
    assert "synthetic" not in public_text
    assert os.stat(opening_output).st_mode & 0o777 == 0o600

