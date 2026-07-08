#!/usr/bin/env python3
"""Validate CORE Chain Adapter Boundary artifact.

Ensures that a chain adapter descriptor is well-formed, follows
version-specific constraints, and does not grant execution authority.
The adapter is a descriptor — it never executes submission.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_FIELDS = {
    "schema_version", "adapter_id", "chain_family", "chain_name",
    "network", "chain_id", "rpc_endpoint_kind", "contract_address",
    "contract_version", "submission_gas_limit", "confirmation_blocks",
    "timeout_ms", "fingerprint",
}

FIELD_TYPES = {
    "schema_version": str, "adapter_id": str, "chain_family": str,
    "chain_name": str, "network": str, "chain_id": int,
    "rpc_endpoint_kind": str, "contract_address": str,
    "contract_version": str, "submission_gas_limit": int,
    "confirmation_blocks": int, "timeout_ms": int,
    "fingerprint": str,
}

VALID_CHAIN_FAMILIES = {"evm", "substrate", "solana", "cosmos"}
SUPPORTED_CHAIN_FAMILIES = {"evm"}  # v9.2: only EVM supported
VALID_NETWORKS = {"mainnet", "testnet", "devnet", "local"}
VALID_RPC_ENDPOINT_KINDS = {"infura", "alchemy", "local", "custom"}

SEMVER_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")
ADAPTER_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*[a-z0-9]$")
CHAIN_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _fingerprint(payload: dict[str, Any]) -> str:
    return f"sha256:{_sha256_text(_canonical_json({k: v for k, v in payload.items() if k != 'fingerprint'}))}"


def _error(code: str, message: str, field: str, **extra: Any) -> dict[str, Any]:
    entry = {"code": code, "message": message, "field": field}
    entry.update(extra)
    return entry


def validate_chain_adapter(path: Path) -> dict[str, Any]:
    path = Path(path)
    errors: list[dict[str, Any]] = []

    if not path.is_file():
        return _result({}, errors, [_error("file_not_found", f"File not found: {path}", "path")])

    try:
        adapter = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return _result({}, errors, [_error("invalid_json", str(exc), "path")])

    # --- Structural: required fields ---
    missing = REQUIRED_FIELDS - set(adapter.keys())
    for f in sorted(missing):
        errors.append(_error("missing_required_field", f"Required field '{f}' is missing.", f))

    extra_top = set(adapter.keys()) - REQUIRED_FIELDS
    if extra_top:
        errors.append(_error("unknown_extra_field", f"Additional properties not allowed: {extra_top}", next(iter(extra_top))))

    if errors:
        return _result(adapter, errors)

    # --- Type checks ---
    for field, expected_type in FIELD_TYPES.items():
        if field in adapter and not isinstance(adapter[field], expected_type):
            errors.append(_error("invalid_field_type", f"'{field}' must be {expected_type.__name__}, got {type(adapter[field]).__name__}.", field))

    if errors:
        return _result(adapter, errors)

    # --- Schema version ---
    if not SEMVER_RE.match(adapter.get("schema_version", "")):
        errors.append(_error("invalid_schema_version", "schema_version must be valid semver (vX.Y.Z).", "schema_version"))

    # --- Adapter ID ---
    if not ADAPTER_ID_RE.match(adapter.get("adapter_id", "")):
        errors.append(_error("invalid_adapter_id", "adapter_id must match ^[a-z][a-z0-9_-]*[a-z0-9]$.", "adapter_id"))

    # --- Chain family ---
    family = adapter.get("chain_family", "")
    if family not in VALID_CHAIN_FAMILIES:
        errors.append(_error("unknown_chain_family", f"chain_family must be one of: {sorted(VALID_CHAIN_FAMILIES)}.", "chain_family"))
    elif family not in SUPPORTED_CHAIN_FAMILIES:
        errors.append(_error("unsupported_chain_family", f"chain_family '{family}' is not supported in v9.2. Supported: {sorted(SUPPORTED_CHAIN_FAMILIES)}.", "chain_family"))

    # --- Chain name ---
    if not CHAIN_NAME_RE.match(adapter.get("chain_name", "")):
        errors.append(_error("invalid_chain_name", "chain_name must match ^[a-z][a-z0-9_-]*$.", "chain_name"))

    # --- Network ---
    network = adapter.get("network", "")
    if network not in VALID_NETWORKS:
        errors.append(_error("invalid_network", f"network must be one of: {sorted(VALID_NETWORKS)}.", "network"))

    # --- Chain ID ---
    chain_id = adapter.get("chain_id", 0)
    if not isinstance(chain_id, int) or chain_id <= 0:
        errors.append(_error("chain_id_out_of_range", "chain_id must be a positive integer.", "chain_id"))

    # --- RPC endpoint kind ---
    rpc = adapter.get("rpc_endpoint_kind", "")
    if rpc not in VALID_RPC_ENDPOINT_KINDS:
        errors.append(_error("invalid_rpc_endpoint_kind", f"rpc_endpoint_kind must be one of: {sorted(VALID_RPC_ENDPOINT_KINDS)}.", "rpc_endpoint_kind"))

    # --- Cross-field: local RPC only on devnet/local ---
    if rpc == "local" and network not in ("devnet", "local"):
        errors.append(_error("local_rpc_on_non_local_network", "rpc_endpoint_kind 'local' is only allowed with network 'devnet' or 'local'.", "rpc_endpoint_kind"))

    # --- Cross-field: mainnet requires confirmation_blocks >= 3 ---
    if network == "mainnet":
        cb = adapter.get("confirmation_blocks", 0)
        if isinstance(cb, int) and cb < 3:
            errors.append(_error("mainnet_requires_confirmations", "mainnet requires confirmation_blocks >= 3.", "confirmation_blocks"))

    # --- Gas limit ---
    gas = adapter.get("submission_gas_limit", 0)
    if not isinstance(gas, int) or gas < 21000 or gas > 500000:
        errors.append(_error("gas_limit_out_of_range", "submission_gas_limit must be in [21000, 500000].", "submission_gas_limit"))

    # --- Confirmation blocks ---
    cb = adapter.get("confirmation_blocks", 0)
    if not isinstance(cb, int) or cb < 1 or cb > 256:
        errors.append(_error("confirmation_blocks_out_of_range", "confirmation_blocks must be in [1, 256].", "confirmation_blocks"))

    # --- Timeout ---
    timeout = adapter.get("timeout_ms", 0)
    if not isinstance(timeout, int) or timeout < 1000 or timeout > 60000:
        errors.append(_error("timeout_out_of_range", "timeout_ms must be in [1000, 60000].", "timeout_ms"))

    # --- Contract address format (EVM: 0x{hex40}) ---
    ca = adapter.get("contract_address", "")
    if not re.match(r"^0x[a-f0-9]{40}$", ca):
        errors.append(_error("invalid_contract_address_format", "contract_address must match 0x{hex40} for EVM adapters.", "contract_address"))

    # --- Contract version ---
    if not SEMVER_RE.match(adapter.get("contract_version", "")):
        errors.append(_error("invalid_contract_version", "contract_version must be valid semver (vX.Y.Z).", "contract_version"))

    # --- Fingerprint ---
    fp_declared = adapter.get("fingerprint", "")
    if not fp_declared:
        errors.append(_error("fingerprint_missing", "fingerprint field is required.", "fingerprint"))
    elif not re.match(r"^sha256:[a-f0-9]{64}$", fp_declared):
        errors.append(_error("fingerprint_missing", "fingerprint must match sha256:{hex64}.", "fingerprint"))
    else:
        fp_computed = _fingerprint(adapter)
        if fp_declared != fp_computed:
            errors.append(_error("fingerprint_mismatch", f"Fingerprint mismatch. Computed: {fp_computed}.", "fingerprint", computed=fp_computed, declared=fp_declared))

    return _result(adapter, errors)


def _result(adapter: dict, errors: list[dict], override_errors: list[dict] | None = None) -> dict[str, Any]:
    final_errors = override_errors if override_errors is not None else errors
    return {
        "schema": "v1",
        "status": "passed" if not final_errors else "failed",
        "adapter_id": adapter.get("adapter_id"),
        "chain_family": adapter.get("chain_family"),
        "chain_name": adapter.get("chain_name"),
        "errors": final_errors,
        "adapter_valid": not final_errors,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: validate_chain_adapter.py <path> [path2 ...]", file=sys.stderr)
        sys.exit(1)
    for target in sys.argv[1:]:
        result = validate_chain_adapter(Path(target))
        print(json.dumps(result, indent=2, ensure_ascii=False))
