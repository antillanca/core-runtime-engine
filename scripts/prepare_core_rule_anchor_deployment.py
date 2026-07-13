#!/usr/bin/env python3
"""Prepare and price a CoreRuleAnchor deployment without signing it."""

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
    ADDRESS_RE,
    UNSIGNED_DEPLOYMENT_WARNINGS,
    artifact_fingerprint,
    canonical_fingerprint,
    load_verified_rule_anchor_build,
    validate_unsigned_rule_anchor_deployment_payload,
)


def _rpc_values(
    rpc_url_file: Path,
    chain_id: int,
    deployer: str,
    creation_data: str,
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
    if int(web3.eth.chain_id) != chain_id:
        raise RuntimeError("RPC chain_id does not match requested deployment chain")
    sender = Web3.to_checksum_address(deployer)
    estimated_gas = int(
        web3.eth.estimate_gas({"from": sender, "value": 0, "data": creation_data})
    )
    gas_limit = (estimated_gas * safety_multiplier_bps + 9_999) // 10_000
    block = web3.eth.get_block("latest")
    base_fee = block.get("baseFeePerGas")
    values: dict[str, Any] = {
        "nonce": int(web3.eth.get_transaction_count(sender, "pending")),
        "gas_limit": gas_limit,
        "observed_balance_wei": int(web3.eth.get_balance(sender)),
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
        description="Prepare an unsigned external-wallet deployment of CoreRuleAnchor."
    )
    parser.add_argument("--chain-id", type=int, required=True)
    parser.add_argument("--deployer", required=True, help="Public EVM address only")
    parser.add_argument("--rpc-url-file", type=Path)
    parser.add_argument("--gas-limit", type=int)
    fees = parser.add_mutually_exclusive_group()
    fees.add_argument("--max-fee-per-gas-wei", type=int)
    fees.add_argument("--gas-price-wei", type=int)
    parser.add_argument("--max-priority-fee-per-gas-wei", type=int)
    parser.add_argument("--safety-multiplier-bps", type=int, default=12_500)
    parser.add_argument("--post-deployment-reserve-wei", type=int, default=0)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if args.chain_id <= 0:
        parser.error("chain-id must be positive")
    if not ADDRESS_RE.fullmatch(args.deployer):
        parser.error("deployer must be a public EVM address")
    if args.safety_multiplier_bps < 10_000:
        parser.error("safety-multiplier-bps cannot be below 10000")
    if args.post_deployment_reserve_wei < 0:
        parser.error("post-deployment-reserve-wei cannot be negative")
    if args.gas_limit is not None and args.gas_limit <= 0:
        parser.error("gas-limit must be positive")
    if args.max_fee_per_gas_wei is not None and args.max_fee_per_gas_wei < 0:
        parser.error("max-fee-per-gas-wei cannot be negative")
    if args.max_priority_fee_per_gas_wei is not None and args.max_priority_fee_per_gas_wei < 0:
        parser.error("max-priority-fee-per-gas-wei cannot be negative")
    if args.gas_price_wei is not None and args.gas_price_wei < 0:
        parser.error("gas-price-wei cannot be negative")
    if args.max_priority_fee_per_gas_wei is not None and args.max_fee_per_gas_wei is None:
        parser.error("max-priority-fee-per-gas-wei requires max-fee-per-gas-wei")
    if (
        args.max_priority_fee_per_gas_wei is not None
        and args.max_fee_per_gas_wei is not None
        and args.max_priority_fee_per_gas_wei > args.max_fee_per_gas_wei
    ):
        parser.error("max-priority-fee-per-gas-wei cannot exceed max-fee-per-gas-wei")

    try:
        build, creation_hex = load_verified_rule_anchor_build()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    creation_data = "0x" + creation_hex
    values: dict[str, Any] = {
        "nonce": None,
        "gas_limit": args.gas_limit,
        "max_fee_per_gas_wei": args.max_fee_per_gas_wei,
        "max_priority_fee_per_gas_wei": args.max_priority_fee_per_gas_wei,
        "gas_price_wei": args.gas_price_wei,
        "observed_balance_wei": None,
    }
    if args.rpc_url_file is not None:
        if any(
            value is not None
            for value in (
                args.gas_limit,
                args.max_fee_per_gas_wei,
                args.max_priority_fee_per_gas_wei,
                args.gas_price_wei,
            )
        ):
            parser.error("RPC pricing cannot be combined with manual gas values")
        try:
            values = _rpc_values(
                args.rpc_url_file,
                args.chain_id,
                args.deployer,
                creation_data,
                args.safety_multiplier_bps,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            parser.error(str(exc))

    fee_per_gas = (
        values["max_fee_per_gas_wei"]
        if values["max_fee_per_gas_wei"] is not None
        else values["gas_price_wei"]
    )
    deployment_cost = None
    required_balance = None
    sufficient = None
    shortfall = None
    if values["gas_limit"] is not None and fee_per_gas is not None:
        deployment_cost = int(values["gas_limit"]) * int(fee_per_gas)
        required_balance = deployment_cost + args.post_deployment_reserve_wei
        if values["observed_balance_wei"] is not None:
            sufficient = int(values["observed_balance_wei"]) >= required_balance
            shortfall = max(0, required_balance - int(values["observed_balance_wei"]))
    if sufficient is True:
        readiness = "ready"
    elif sufficient is False:
        readiness = "insufficient_balance"
    elif deployment_cost is None:
        readiness = "offline_unpriced"
    else:
        readiness = "balance_unobserved"

    request: dict[str, Any] = {
        "schema_version": "core.unsigned_rule_anchor_deployment.v1",
        "type": "unsigned_rule_anchor_deployment",
        "signing_mode": "external_wallet_only",
        "broadcast": False,
        "contract_build_fingerprint": canonical_fingerprint(build),
        "expected_runtime_bytecode_sha256": build["runtime_bytecode_sha256"],
        "transaction": {
            "from": args.deployer.lower(),
            "to": None,
            "chain_id": args.chain_id,
            "value_wei": 0,
            "data": creation_data,
            "nonce": values["nonce"],
            "gas_limit": values["gas_limit"],
            "max_fee_per_gas_wei": values["max_fee_per_gas_wei"],
            "max_priority_fee_per_gas_wei": values["max_priority_fee_per_gas_wei"],
            "gas_price_wei": values["gas_price_wei"],
        },
        "gas_reserve": {
            "unit": "native_wei",
            "deployment_max_cost_wei": deployment_cost,
            "post_deployment_reserve_wei": args.post_deployment_reserve_wei,
            "required_balance_wei": required_balance,
            "observed_balance_wei": values["observed_balance_wei"],
            "shortfall_wei": shortfall,
            "sufficient": sufficient,
        },
        "readiness": readiness,
        "warnings": list(UNSIGNED_DEPLOYMENT_WARNINGS),
    }
    request["fingerprint"] = artifact_fingerprint(request)
    validation_errors = validate_unsigned_rule_anchor_deployment_payload(request)
    if validation_errors:
        parser.error(f"generated deployment request is invalid: {validation_errors[0]['code']}")

    if args.output.exists():
        parser.error("output already exists; refusing to overwrite")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(request, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "schema": "core.rule_anchor_deployment_preparation.v1",
                "status": "blocked" if readiness == "insufficient_balance" else "passed",
                "errors": [],
                "readiness": readiness,
                "required_balance_wei": required_balance,
                "shortfall_wei": shortfall,
                "signing_mode": "external_wallet_only",
                "broadcast": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 2 if readiness == "insufficient_balance" else 0


if __name__ == "__main__":
    raise SystemExit(main())
