#!/usr/bin/env python3
"""Prepare, price, and balance-check a rule anchor without signing it.

RPC URLs are read only from a file because provider URLs often contain API
credentials.  The URL is never included in output.  This command never signs
or broadcasts a transaction.
"""

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
    build_unsigned_rule_anchor_request,
    encode_anchor_rule_batch_calldata,
    validate_rule_anchor_batch_payload,
)


def _connected_values(
    batch: dict[str, Any],
    submitter: str,
    rpc_url_file: Path,
    safety_multiplier_bps: int,
) -> dict[str, Any]:
    try:
        from web3 import Web3
    except ImportError as exc:
        raise RuntimeError("install CORE's anchoring extra to use RPC pricing") from exc

    rpc_url = rpc_url_file.read_text(encoding="utf-8").strip()
    if not rpc_url:
        raise ValueError("RPC URL file is empty")
    web3 = Web3(Web3.HTTPProvider(rpc_url))
    if not web3.is_connected():
        raise RuntimeError("RPC connection failed")
    if int(web3.eth.chain_id) != int(batch["chain_id"]):
        raise RuntimeError("RPC chain_id does not match the signed approval batch")

    contract = Web3.to_checksum_address(str(batch["verifying_contract"]))
    sender = Web3.to_checksum_address(submitter)
    code = bytes(web3.eth.get_code(contract))
    if not code:
        raise RuntimeError("no contract bytecode exists at verifying_contract")

    transaction = {
        "from": sender,
        "to": contract,
        "value": 0,
        "data": encode_anchor_rule_batch_calldata(batch),
    }
    estimated_gas = int(web3.eth.estimate_gas(transaction))
    gas_limit = (estimated_gas * safety_multiplier_bps + 9_999) // 10_000
    latest_block = web3.eth.get_block("latest")
    base_fee = latest_block.get("baseFeePerGas")

    values: dict[str, Any] = {
        "nonce": int(web3.eth.get_transaction_count(sender, "pending")),
        "gas_limit": gas_limit,
        "observed_balance_wei": int(web3.eth.get_balance(sender)),
        "contract_code_verified": True,
        "max_fee_per_gas_wei": None,
        "max_priority_fee_per_gas_wei": None,
        "gas_price_wei": None,
    }
    if base_fee is None:
        values["gas_price_wei"] = int(web3.eth.gas_price)
    else:
        try:
            priority_fee = int(web3.eth.max_priority_fee)
        except Exception as exc:
            raise RuntimeError("RPC did not provide a priority-fee estimate") from exc
        values["max_priority_fee_per_gas_wei"] = priority_fee
        values["max_fee_per_gas_wei"] = (2 * int(base_fee)) + priority_fee
    return values


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare an unsigned external-wallet transaction for CoreRuleAnchor."
    )
    parser.add_argument("--batch", required=True, type=Path)
    parser.add_argument("--submitter", required=True, help="Public EVM address only")
    parser.add_argument(
        "--rpc-url-file",
        type=Path,
        help="Private local file containing an RPC URL; its contents are never logged",
    )
    parser.add_argument("--gas-limit", type=int)
    fee_group = parser.add_mutually_exclusive_group()
    fee_group.add_argument("--max-fee-per-gas-wei", type=int)
    fee_group.add_argument("--gas-price-wei", type=int)
    parser.add_argument("--max-priority-fee-per-gas-wei", type=int)
    parser.add_argument("--reserve-batches", type=int, default=4)
    parser.add_argument("--safety-multiplier-bps", type=int, default=12_500)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    batch = json.loads(args.batch.read_text(encoding="utf-8"))
    batch_errors = validate_rule_anchor_batch_payload(batch)
    if batch_errors:
        parser.error(f"invalid rule-anchor batch: {batch_errors[0]['code']}")

    values: dict[str, Any] = {
        "nonce": None,
        "gas_limit": args.gas_limit,
        "max_fee_per_gas_wei": args.max_fee_per_gas_wei,
        "max_priority_fee_per_gas_wei": args.max_priority_fee_per_gas_wei,
        "gas_price_wei": args.gas_price_wei,
        "observed_balance_wei": None,
        "contract_code_verified": None,
    }
    if args.rpc_url_file is not None:
        if any(
            item is not None
            for item in (
                args.gas_limit,
                args.max_fee_per_gas_wei,
                args.max_priority_fee_per_gas_wei,
                args.gas_price_wei,
            )
        ):
            parser.error("RPC pricing cannot be combined with manual gas values")
        try:
            values = _connected_values(
                batch,
                args.submitter,
                args.rpc_url_file,
                args.safety_multiplier_bps,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            parser.error(str(exc))

    try:
        request = build_unsigned_rule_anchor_request(
            batch,
            args.submitter,
            reserve_batches=args.reserve_batches,
            safety_multiplier_bps=args.safety_multiplier_bps,
            **values,
        )
    except ValueError as exc:
        parser.error(str(exc))

    if args.output.exists():
        parser.error("output already exists; refusing to overwrite")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(request, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    blocked = request["readiness"] in {"insufficient_balance", "contract_unverified"}
    complete = request["readiness"] == "ready"
    print(
        json.dumps(
            {
                "schema": "core.rule_anchor_transaction_preparation.v1",
                "status": "blocked" if blocked else ("passed" if complete else "advisory_only"),
                "errors": [],
                "readiness": request["readiness"],
                "required_balance_wei": request["gas_reserve"]["required_balance_wei"],
                "shortfall_wei": request["gas_reserve"]["shortfall_wei"],
                "signing_mode": request["signing_mode"],
                "broadcast": request["broadcast"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 2 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
