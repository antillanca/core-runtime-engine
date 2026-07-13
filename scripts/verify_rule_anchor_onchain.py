#!/usr/bin/env python3
"""Verify a CoreRuleAnchor transaction and event without changing chain state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core_runtime.core.rule_anchor import (  # noqa: E402
    artifact_fingerprint,
    bytes32_hex,
    encode_anchor_rule_batch_calldata,
    validate_rule_anchor_batch_payload,
    validate_rule_anchor_chain_evidence_payload,
)


CORE_RULE_ANCHOR_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "anchorer", "type": "address"},
            {"indexed": True, "name": "merkleRoot", "type": "bytes32"},
            {"indexed": True, "name": "manifestHash", "type": "bytes32"},
            {"indexed": False, "name": "ruleCount", "type": "uint32"},
            {"indexed": False, "name": "visibilityMask", "type": "uint8"},
            {"indexed": False, "name": "timestamp", "type": "uint256"},
        ],
        "name": "RuleBatchAnchored",
        "type": "event",
    },
    {
        "inputs": [{"name": "", "type": "bytes32"}],
        "name": "manifestByRoot",
        "outputs": [{"name": "", "type": "bytes32"}],
        "stateMutability": "view",
        "type": "function",
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a confirmed CoreRuleAnchor event.")
    parser.add_argument("--batch", required=True, type=Path)
    parser.add_argument("--tx-hash", required=True)
    parser.add_argument("--rpc-url-file", required=True, type=Path)
    parser.add_argument("--confirmations", type=int, default=3)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if args.confirmations < 1:
        parser.error("confirmations must be at least 1")
    try:
        from web3 import Web3
    except ImportError:
        parser.error("install CORE's anchoring extra for on-chain verification")

    batch = json.loads(args.batch.read_text(encoding="utf-8"))
    batch_errors = validate_rule_anchor_batch_payload(batch)
    if batch_errors:
        parser.error(f"invalid rule-anchor batch: {batch_errors[0]['code']}")

    rpc_url = args.rpc_url_file.read_text(encoding="utf-8").strip()
    if not rpc_url:
        parser.error("RPC URL file is empty")
    web3 = Web3(Web3.HTTPProvider(rpc_url))
    if not web3.is_connected():
        parser.error("RPC connection failed")
    if int(web3.eth.chain_id) != int(batch["chain_id"]):
        parser.error("RPC chain_id does not match the batch")

    try:
        receipt = web3.eth.get_transaction_receipt(args.tx_hash)
        transaction = web3.eth.get_transaction(args.tx_hash)
    except Exception:
        parser.error("transaction or receipt is unavailable")
    if int(receipt["status"]) != 1:
        parser.error("transaction execution failed")

    contract_address = Web3.to_checksum_address(batch["verifying_contract"])
    if str(transaction["to"]).lower() != contract_address.lower():
        parser.error("transaction target does not match verifying_contract")
    transaction_data = transaction.get("input", transaction.get("data", ""))
    normalized_data = (
        transaction_data.hex() if hasattr(transaction_data, "hex") else str(transaction_data)
    )
    if normalized_data.lower() != encode_anchor_rule_batch_calldata(batch):
        parser.error("transaction calldata does not match the frozen batch")

    latest_block = int(web3.eth.block_number)
    included_block = int(receipt["blockNumber"])
    confirmations = latest_block - included_block + 1
    if confirmations < args.confirmations:
        print(
            json.dumps(
                {
                    "schema": "core.rule_anchor_chain_verification.v1",
                    "status": "pending",
                    "errors": [],
                    "confirmations": confirmations,
                    "required_confirmations": args.confirmations,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 2

    contract = web3.eth.contract(address=contract_address, abi=CORE_RULE_ANCHOR_ABI)
    events = contract.events.RuleBatchAnchored().process_receipt(receipt)
    if len(events) != 1:
        parser.error("receipt must contain exactly one RuleBatchAnchored event")
    event_args = events[0]["args"]
    expected_root = bytes.fromhex(bytes32_hex(batch["merkle_root"])[2:])
    expected_manifest = bytes.fromhex(bytes32_hex(batch["manifest_fingerprint"])[2:])
    if bytes(event_args["merkleRoot"]) != expected_root:
        parser.error("event Merkle root does not match the batch")
    if bytes(event_args["manifestHash"]) != expected_manifest:
        parser.error("event manifest hash does not match the batch")
    if int(event_args["ruleCount"]) != int(batch["rule_set_count"]):
        parser.error("event rule count does not match the batch")
    if int(event_args["visibilityMask"]) != int(batch["visibility_mask"]):
        parser.error("event visibility mask does not match the batch")

    stored_manifest = bytes(contract.functions.manifestByRoot(expected_root).call())
    if stored_manifest != expected_manifest:
        parser.error("contract state does not map the root to this manifest")

    evidence: dict[str, Any] = {
        "schema_version": "core.rule_anchor_chain_evidence.v1",
        "type": "rule_anchor_chain_evidence",
        "batch_manifest_fingerprint": batch["manifest_fingerprint"],
        "merkle_root": batch["merkle_root"],
        "chain_id": batch["chain_id"],
        "contract_address": batch["verifying_contract"],
        "transaction_hash": transaction["hash"].hex(),
        "block_number": included_block,
        "block_hash": receipt["blockHash"].hex(),
        "anchorer": str(event_args["anchorer"]).lower(),
        "block_timestamp": int(event_args["timestamp"]),
        "confirmations": confirmations,
        "required_confirmations": args.confirmations,
        "contract_state_verified": True,
        "calldata_verified": True,
        "event_verified": True,
    }
    evidence["fingerprint"] = artifact_fingerprint(evidence)
    evidence_errors = validate_rule_anchor_chain_evidence_payload(evidence)
    if evidence_errors:
        parser.error(f"generated chain evidence is invalid: {evidence_errors[0]['code']}")
    if args.output.exists():
        parser.error("output already exists; refusing to overwrite")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "schema": "core.rule_anchor_chain_verification.v1",
                "status": "passed",
                "errors": [],
                "confirmations": confirmations,
                "evidence_fingerprint": evidence["fingerprint"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
