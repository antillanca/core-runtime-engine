from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from core_runtime.core.rule_anchor import (
    ANCHOR_RULE_BATCH_SELECTOR,
    artifact_fingerprint,
    build_unsigned_rule_anchor_request,
    encode_anchor_rule_batch_calldata,
    validate_unsigned_rule_anchor_request_payload,
)
from scripts.submit_anchoring import NOTARIZE_HASH_SELECTOR, build_unsigned_legacy_request


ROOT = Path(__file__).resolve().parent.parent
BATCH = ROOT / "examples" / "merkle_batch" / "accepted_batch_manifest.json"
LEGACY = ROOT / "examples" / "anchoring" / "accepted_release_manifest.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_rule_anchor_calldata_has_expected_selector_and_fixed_width_arguments() -> None:
    batch = _load(BATCH)
    calldata = encode_anchor_rule_batch_calldata(batch)
    assert calldata.startswith("0x" + ANCHOR_RULE_BATCH_SELECTOR)
    assert len(calldata) == 2 + 8 + (64 * 4)
    words = [calldata[10 + (64 * i) : 10 + (64 * (i + 1))] for i in range(4)]
    assert "sha256:" + words[0] == batch["merkle_root"]
    assert "sha256:" + words[1] == batch["manifest_fingerprint"]
    assert int(words[2], 16) == batch["rule_set_count"]
    assert int(words[3], 16) == batch["visibility_mask"]


def test_unsigned_request_prices_batch_and_minimum_per_rule_in_native_wei() -> None:
    request = build_unsigned_rule_anchor_request(
        _load(BATCH),
        "0x3333333333333333333333333333333333333333",
        nonce=7,
        gas_limit=80_000,
        max_fee_per_gas_wei=2_000_000_000,
        max_priority_fee_per_gas_wei=1_000_000_000,
        reserve_batches=4,
        observed_balance_wei=1_000_000_000_000_000_000,
        contract_code_verified=True,
    )
    reserve = request["gas_reserve"]
    assert request["signing_mode"] == "external_wallet_only"
    assert request["broadcast"] is False
    assert request["readiness"] == "ready"
    assert request["rule_set_count"] == 2
    assert reserve["per_batch_max_cost_wei"] == 200_000_000_000_000
    assert reserve["max_cost_per_rule_wei"] == 100_000_000_000_000
    assert reserve["required_balance_wei"] == 800_000_000_000_000
    assert reserve["unit"] == "native_wei"
    assert validate_unsigned_rule_anchor_request_payload(request) == []


def test_insufficient_balance_is_explicit_and_never_auto_funded() -> None:
    request = build_unsigned_rule_anchor_request(
        _load(BATCH),
        "0x3333333333333333333333333333333333333333",
        gas_limit=100_000,
        gas_price_wei=10,
        reserve_batches=5,
        observed_balance_wei=4_999_999,
    )
    assert request["readiness"] == "insufficient_balance"
    assert request["gas_reserve"]["shortfall_wei"] == 1_250_001
    assert request["broadcast"] is False


def test_verified_balance_without_verified_contract_fails_closed() -> None:
    request = build_unsigned_rule_anchor_request(
        _load(BATCH),
        "0x3333333333333333333333333333333333333333",
        gas_limit=80_000,
        gas_price_wei=10,
        observed_balance_wei=10_000_000,
        contract_code_verified=None,
    )
    assert request["readiness"] == "contract_unverified"
    assert validate_unsigned_rule_anchor_request_payload(request) == []


def test_unsigned_request_recomputes_reserve_and_calldata_semantics() -> None:
    request = build_unsigned_rule_anchor_request(
        _load(BATCH),
        "0x3333333333333333333333333333333333333333",
        gas_limit=80_000,
        gas_price_wei=10,
        observed_balance_wei=10_000_000,
        contract_code_verified=True,
    )
    request["gas_reserve"]["required_balance_wei"] += 1
    request["transaction"]["data"] = (
        request["transaction"]["data"][:74]
        + ("0" * 64)
        + request["transaction"]["data"][138:]
    )
    request["fingerprint"] = artifact_fingerprint(request)
    codes = {item["code"] for item in validate_unsigned_rule_anchor_request_payload(request)}
    assert "gas_reserve_mismatch" in codes
    assert "calldata_manifest_mismatch" in codes


def test_legacy_anchor_is_also_unsigned_and_nonbroadcasting() -> None:
    request = build_unsigned_legacy_request(_load(LEGACY))
    assert request["transaction"]["data"].startswith("0x" + NOTARIZE_HASH_SELECTOR)
    assert request["signing_mode"] == "external_wallet_only"
    assert request["broadcast"] is False


def test_legacy_script_has_no_secret_ingestion_or_signing_path() -> None:
    source = "\n".join(
        (ROOT / "scripts" / name).read_text(encoding="utf-8")
        for name in ("submit_anchoring.py", "core_anchor.py")
    )
    forbidden = (
        "--private-key",
        "ANCHOR_KEY",
        "from_key(",
        "sign_transaction(",
        "send_raw_transaction(",
    )
    assert not any(marker in source for marker in forbidden)


def test_legacy_cli_exposes_no_state_changing_flag() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/core_anchor.py", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--broadcast" not in result.stdout
    assert "private" not in result.stdout.lower()
