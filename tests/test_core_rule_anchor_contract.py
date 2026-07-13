from __future__ import annotations

import json
from pathlib import Path

from core_runtime.core.rule_anchor import ANCHOR_RULE_BATCH_SELECTOR
from scripts.compile_core_rule_anchor import build_manifest


ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "contracts" / "CoreRuleAnchor.sol"


def test_function_selector_matches_contract_signature() -> None:
    signature = b"anchorRuleBatch(bytes32,bytes32,uint32,uint8)"
    try:
        from Crypto.Hash import keccak

        digest = keccak.new(digest_bits=256)
        digest.update(signature)
        selector = digest.hexdigest()[:8]
    except ImportError:
        from web3 import Web3

        selector = Web3.keccak(signature).hex()[2:10]
    assert selector == ANCHOR_RULE_BATCH_SELECTOR


def test_contract_has_no_owner_upgrade_fee_token_or_fund_custody() -> None:
    source = CONTRACT.read_text(encoding="utf-8")
    compact = source.lower()
    assert "function anchorrulebatch(" in compact
    assert compact.count("mapping(") == 1
    for forbidden in (
        "onlyowner",
        "delegatecall",
        "selfdestruct",
        "function transferownership",
        "function withdraw",
        "function mint",
        "function pause",
        " payable",
    ):
        assert forbidden not in compact


def test_contract_rejects_zero_duplicate_and_empty_batches() -> None:
    source = CONTRACT.read_text(encoding="utf-8")
    assert "merkleRoot != bytes32(0)" in source
    assert "manifestHash != bytes32(0)" in source
    assert "ruleCount > 0" in source
    assert "manifestByRoot[merkleRoot] == bytes32(0)" in source


def test_build_manifest_matches_all_frozen_contract_artifacts() -> None:
    contract_root = ROOT / "contracts"
    abi = json.loads(
        (contract_root / "CoreRuleAnchor.abi.json").read_text(encoding="utf-8")
    )
    creation = (contract_root / "CoreRuleAnchor.bin").read_text(
        encoding="utf-8"
    ).strip()
    runtime = (contract_root / "CoreRuleAnchor.runtime.bin").read_text(
        encoding="utf-8"
    ).strip()
    frozen_build = json.loads(
        (contract_root / "CoreRuleAnchor.build.json").read_text(encoding="utf-8")
    )

    assert build_manifest(abi, creation, runtime) == frozen_build
