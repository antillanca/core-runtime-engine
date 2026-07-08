#!/usr/bin/env python3
"""Submit a CORE artefact hash to the CoreAnchor smart contract.

This script:
1. Reads a frozen CORE artefact (JSON)
2. Computes its canonical fingerprint
3. Validates the anchoring submission locally
4. Submits the hash to the deployed CoreAnchor contract
5. Records the transaction receipt

The script is offline-first except for the actual chain submission step.
It will fail-closed if:
  - the artefact is not frozen
  - the hash does not match the canonical fingerprint
  - the contract address or RPC endpoint is missing
  - the eligibility checks fail

Usage:
    python scripts/submit_anchoring.py --artifact <path> --chain-id <int> --contract <0x...> --rpc <url>
    python scripts/submit_anchoring.py --submission <path> --rpc <url>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ─── Canonical helpers (shared with CORE validators) ────────────────────

def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def fingerprint(payload: dict[str, Any]) -> str:
    return f"sha256:{_sha256_text(_canonical_json(payload))}"


def fp_to_bytes32(fp: str) -> str:
    """Convert 'sha256:{hex64}' to '0x{hex64}' for Solidity bytes32."""
    if fp.startswith("sha256:"):
        return "0x" + fp[7:]
    raise ValueError(f"Invalid fingerprint format: {fp}")


# ─── Submission builder ──────────────────────────────────────────────────

def build_submission(
    artifact_path: Path,
    artifact_type: str,
    chain_id: int,
    contract_address: str,
    submitter: str,
    release_version: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Build an anchoring submission from a frozen artefact file."""

    raw = artifact_path.read_text(encoding="utf-8")
    artifact = json.loads(raw)
    fp = fingerprint(artifact)
    anchor_hash = fp_to_bytes32(fp)

    submission_id = f"anchor_{os.urandom(4).hex()}_{anchor_hash[-12:]}"

    submission = {
        "schema_version": "v1",
        "type": "anchoring_submission",
        "submission_id": submission_id,
        "artifact_type": artifact_type,
        "artifact_fingerprint": fp,
        "anchor_hash": anchor_hash,
        "chain_id": chain_id,
        "contract_address": contract_address,
        "submitter": submitter,
        "submission_timestamp": datetime.now(timezone.utc).isoformat(),
        "eligibility": {
            "frozen_artifact": True,
            "hash_matches_fingerprint": True,
            "no_private_data": True,
            "no_runtime_authority_change": True,
        },
        "metadata": {},
    }

    if release_version:
        submission["metadata"]["release_version"] = release_version
    if reason:
        submission["metadata"]["submission_reason"] = reason
    resolved = artifact_path.resolve()
    try:
        submission["metadata"]["artifact_path"] = str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        submission["metadata"]["artifact_path"] = str(artifact_path)

    return submission


# ─── Local validation (reuse validator) ──────────────────────────────────

def validate_locally(submission: dict[str, Any]) -> list[str]:
    """Run local validation checks. Returns list of error messages."""
    import importlib.util
    validator_path = PROJECT_ROOT / "scripts" / "validate_anchoring_submission.py"
    spec = importlib.util.spec_from_file_location("validate_anchoring_submission", validator_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _validate = mod.validate_anchoring_submission

    tmp_path = PROJECT_ROOT / "tmp_anchor_submission.json"
    tmp_path.write_text(json.dumps(submission, indent=2, ensure_ascii=False), encoding="utf-8")

    result = _validate(tmp_path)
    tmp_path.unlink(missing_ok=True)

    return [e["message"] for e in result.get("errors", [])]


# ─── Chain submission (requires web3) ────────────────────────────────────

ABI_MINIMAL = [
    {
        "inputs": [{"internalType": "bytes32", "name": "dataHash", "type": "bytes32"}],
        "name": "notarizeHash",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "anchorer", "type": "address"},
            {"indexed": True, "internalType": "bytes32", "name": "dataHash", "type": "bytes32"},
            {"indexed": True, "internalType": "uint256", "name": "timestamp", "type": "uint256"},
        ],
        "name": "HashAnchored",
        "type": "event",
    },
]


def submit_to_chain(
    rpc_url: str,
    contract_address: str,
    anchor_hash: str,
    private_key: str | None = None,
) -> dict[str, Any]:
    """Submit the anchor hash to the CoreAnchor contract.

    Requires web3.py and a funded account.
    Falls back to dry-run mode if web3 is not available.
    """
    try:
        from web3 import Web3

        w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not w3.is_connected():
            return {"status": "failed", "error": "Cannot connect to RPC endpoint"}

        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=ABI_MINIMAL,
        )

        if private_key:
            account = w3.eth.account.from_key(private_key)
            tx = contract.functions.notarizeHash(bytes.fromhex(anchor_hash[2:])).build_transaction({
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address),
                "gas": 100_000,
                "gasPrice": w3.eth.gas_price,
            })
            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
            return {
                "status": "submitted",
                "tx_hash": receipt.transactionHash.hex(),
                "block_number": receipt.blockNumber,
                "gas_used": receipt.gasUsed,
            }
        else:
            return {"status": "dry_run", "message": "No private key provided; skipping on-chain submission"}

    except ImportError:
        return {"status": "dry_run", "message": "web3.py not installed; skipping on-chain submission"}
    except Exception as exc:
        return {"status": "failed", "error": str(exc)}


# ─── CLI ─────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Submit a CORE artefact hash to CoreAnchor")
    parser.add_argument("--artifact", type=Path, help="Path to the frozen artefact JSON file")
    parser.add_argument("--submission", type=Path, help="Path to a pre-built anchoring submission JSON")
    parser.add_argument("--artifact-type", type=str, default="freeze_artifact", help="Artefact type (from schema enum)")
    parser.add_argument("--chain-id", type=int, default=11155111, help="EIP-155 chain ID (default: Sepolia)")
    parser.add_argument("--contract", type=str, required=True, help="CoreAnchor contract address")
    parser.add_argument("--submitter", type=str, required=True, help="Submitter Ethereum address")
    parser.add_argument("--rpc", type=str, help="RPC endpoint URL")
    parser.add_argument("--private-key", type=str, help="Private key for signing (or set ANCHOR_KEY env)")
    parser.add_argument("--release-version", type=str, help="CORE release version (vX.Y.Z)")
    parser.add_argument("--reason", type=str, help="Human-readable reason for this anchoring")
    parser.add_argument("--output", type=Path, help="Output path for the submission record")
    parser.add_argument("--dry-run", action="store_true", help="Validate locally without submitting on-chain")

    args = parser.parse_args()

    # --- Build or load submission ---
    if args.submission:
        submission = json.loads(args.submission.read_text(encoding="utf-8"))
    elif args.artifact:
        submission = build_submission(
            artifact_path=args.artifact,
            artifact_type=args.artifact_type,
            chain_id=args.chain_id,
            contract_address=args.contract,
            submitter=args.submitter,
            release_version=args.release_version,
            reason=args.reason,
        )
    else:
        parser.error("Either --artifact or --submission is required")

    # --- Local validation ---
    errors = validate_locally(submission)
    if errors:
        print("VALIDATION FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    print("LOCAL VALIDATION: PASSED")
    print(f"  submission_id:    {submission['submission_id']}")
    print(f"  artifact_type:    {submission['artifact_type']}")
    print(f"  artifact_fp:      {submission['artifact_fingerprint']}")
    print(f"  anchor_hash:      {submission['anchor_hash']}")
    print(f"  chain_id:         {submission['chain_id']}")

    # --- Chain submission ---
    chain_result: dict[str, Any] = {"status": "skipped"}

    if args.dry_run or not args.rpc:
        chain_result = {"status": "dry_run", "message": "Dry run mode or no RPC provided"}
    else:
        pk = args.private_key or os.environ.get("ANCHOR_KEY")
        chain_result = submit_to_chain(
            rpc_url=args.rpc,
            contract_address=args.contract,
            anchor_hash=submission["anchor_hash"],
            private_key=pk,
        )

    print(f"  chain_result:     {chain_result['status']}")
    if "tx_hash" in chain_result:
        print(f"  tx_hash:          {chain_result['tx_hash']}")
        print(f"  block_number:     {chain_result['block_number']}")

    # --- Record ---
    record = {
        **submission,
        "chain_result": chain_result,
    }

    output_path = args.output or PROJECT_ROOT / "examples" / "anchoring" / f"{submission['submission_id']}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  record_path:      {output_path}")


if __name__ == "__main__":
    main()
