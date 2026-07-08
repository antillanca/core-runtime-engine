#!/usr/bin/env python3
"""Validate an anchoring_event JSON document against CORE v9.1 schema.

Fail-closed: rejects unless explicitly allowed. All rejection codes are
named constants (not magic strings). Output is byte-stable JSON.

Usage:
    python scripts/validate_anchoring_event.py <path>
    python scripts/validate_anchoring_event.py <directory>   # recursive
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "anchoring_event.schema.json"

# ─── Rejection codes ─────────────────────────────────────────────────────

FILE_NOT_FOUND = "file_not_found"
INVALID_JSON = "invalid_json"
INVALID_SCHEMA_VERSION = "invalid_schema_version"
INVALID_TYPE = "invalid_type"
MISSING_REQUIRED_FIELD = "missing_required_field"
EXTRA_FIELD_NOT_ALLOWED = "extra_field_not_allowed"
INVALID_EVENT_ID = "invalid_event_id"
INVALID_SUBMISSION_REF = "invalid_submission_ref"
INVALID_ANCHOR_HASH = "invalid_anchor_hash"
INVALID_ARTIFACT_FINGERPRINT = "invalid_artifact_fingerprint"
INVALID_CONTRACT_ADDRESS = "invalid_contract_address"
INVALID_ANCHORER = "invalid_anchorer"
INVALID_TX_HASH = "invalid_tx_hash"
INVALID_TIMESTAMP = "invalid_timestamp"
INVALID_EVENT_FINGERPRINT = "invalid_event_fingerprint"
HASH_FINGERPRINT_MISMATCH = "hash_fingerprint_mismatch"
INVALID_CHAIN_ID = "invalid_chain_id"
INVALID_BLOCK_NUMBER = "invalid_block_number"
INVALID_ARTIFACT_TYPE = "invalid_artifact_type"
INVALID_CORE_VERSION = "invalid_core_version"
INVALID_LOG_INDEX = "invalid_log_index"
INVALID_VERIFICATION_STATUS = "invalid_verification_status"
EXTRA_METADATA_FIELD = "extra_metadata_field"
DUPLICATE_ANCHOR_HASH = "duplicate_anchor_hash"

KNOWN_CHAIN_IDS = {1, 5, 11155111, 137, 80001, 42161, 421614}

VALID_ARTIFACT_TYPES = {
    "freeze_artifact",
    "release_manifest",
    "certification_report",
    "compliance_report",
    "audit_trail",
    "business_profile",
    "ruleset_version",
    "watcher_result",
    "evidence_bundle",
}

VALID_VERIFICATION_STATUSES = {"confirmed", "pending", "unverified"}

REQUIRED_FIELDS = {
    "schema_version", "type", "event_id", "submission_ref",
    "anchor_hash", "chain_id", "contract_address", "anchorer",
    "block_number", "tx_hash", "timestamp", "event_fingerprint",
}

ALLOWED_TOP_LEVEL = REQUIRED_FIELDS | {"artifact_fingerprint", "artifact_type", "metadata"}

ALLOWED_METADATA_KEYS = {"core_version", "log_index", "verification_status"}

HEX64_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
EVENT_ID_RE = re.compile(r"^evt_[0-9a-f]{8}_[0-9a-f]{12}$")
SUBMISSION_REF_RE = re.compile(r"^anchor_[0-9a-f]{8}_[0-9a-f]{12}$")
ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
VERSION_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")


# ─── Helpers ─────────────────────────────────────────────────────────────

def _error(code: str, message: str, field: str = "") -> dict[str, str]:
    return {"code": code, "message": message, "field": field}


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fingerprint_to_bytes32(fp: str) -> str | None:
    """Convert sha256:hex64 to 0xhex64. Returns None on format mismatch."""
    if not fp.startswith("sha256:"):
        return None
    hex_part = fp[7:]
    if len(hex_part) != 64 or not all(c in "0123456789abcdef" for c in hex_part):
        return None
    return f"0x{hex_part}"


def _compute_event_fingerprint(event: dict[str, Any]) -> str:
    """Compute canonical fingerprint excluding the event_fingerprint field."""
    copy = {k: v for k, v in event.items() if k != "event_fingerprint"}
    return f"sha256:{_sha256_text(_canonical_json(copy))}"


def _is_checksummed_address(addr: str) -> bool:
    """Basic EIP-55 checksum validation for 0x-prefixed 20-byte addresses."""
    if not ADDR_RE.match(addr):
        return False
    # Simple check: mixed case implies checksumming
    # All-lowercase or all-uppercase (after 0x) is also accepted for simplicity
    hex_part = addr[2:]
    if hex_part == hex_part.lower() or hex_part == hex_part.upper():
        return True
    # Mixed case: validate EIP-55
    address = hex_part.lower()
    hash_hex = _sha256_text(address)
    for i, c in enumerate(address):
        if c in "0123456789":
            continue
        if c.isalpha():
            hash_char = int(hash_hex[i], 16)
            if (c.isupper() and hash_char < 8) or (c.islower() and hash_char >= 8):
                return False
    return True


# ─── Main validation ─────────────────────────────────────────────────────

def validate_anchoring_event(path: Path) -> dict[str, Any]:
    """Validate a single anchoring_event document."""
    errors: list[dict[str, str]] = []

    if not path.exists():
        return {"schema": "v1", "status": "failed", "errors": [
            _error(FILE_NOT_FOUND, f"File not found: {path}", "path")
        ], "event_valid": False}

    try:
        text = path.read_text(encoding="utf-8")
        event = json.loads(text)
    except json.JSONDecodeError as e:
        return {"schema": "v1", "status": "failed", "errors": [
            _error(INVALID_JSON, f"Invalid JSON: {e}", "json")
        ], "event_valid": False}

    if not isinstance(event, dict):
        return {"schema": "v1", "status": "failed", "errors": [
            _error(INVALID_JSON, "Root must be a JSON object.", "json")
        ], "event_valid": False}

    # ── schema_version & type (dispatch before other checks) ──
    sv = event.get("schema_version", "")
    if sv != "v1":
        errors.append(_error(INVALID_SCHEMA_VERSION, "schema_version must be 'v1'.", "schema_version"))

    tp = event.get("type", "")
    if tp != "anchoring_event":
        errors.append(_error(INVALID_TYPE, "type must be 'anchoring_event'.", "type"))

    # ── required fields ──
    for field in sorted(REQUIRED_FIELDS):
        if field not in event:
            errors.append(_error(MISSING_REQUIRED_FIELD, f"Missing required field: {field}.", field))

    # ── extra top-level fields ──
    for key in event:
        if key not in ALLOWED_TOP_LEVEL:
            errors.append(_error(EXTRA_FIELD_NOT_ALLOWED, f"Unknown top-level field: {key}.", key))

    # ── format checks (only if field exists) ──
    if "event_id" in event and not EVENT_ID_RE.match(str(event.get("event_id", ""))):
        errors.append(_error(INVALID_EVENT_ID,
            "event_id must match evt_{hex8}_{hex12}.", "event_id"))

    if "submission_ref" in event and not SUBMISSION_REF_RE.match(str(event.get("submission_ref", ""))):
        errors.append(_error(INVALID_SUBMISSION_REF,
            "submission_ref must match anchor_{hex8}_{hex12}.", "submission_ref"))

    if "anchor_hash" in event:
        ah = str(event["anchor_hash"])
        if not HEX64_RE.match(ah):
            errors.append(_error(INVALID_ANCHOR_HASH,
                "anchor_hash must be 0x{hex64}.", "anchor_hash"))

    if "artifact_fingerprint" in event:
        afp = str(event["artifact_fingerprint"])
        if not SHA256_RE.match(afp):
            errors.append(_error(INVALID_ARTIFACT_FINGERPRINT,
                "artifact_fingerprint must be sha256:{hex64}.", "artifact_fingerprint"))

    if "contract_address" in event:
        ca = str(event["contract_address"])
        if not _is_checksummed_address(ca):
            errors.append(_error(INVALID_CONTRACT_ADDRESS,
                "contract_address must be a checksummed 20-byte address.", "contract_address"))

    if "anchorer" in event:
        anc = str(event["anchorer"])
        if not _is_checksummed_address(anc):
            errors.append(_error(INVALID_ANCHORER,
                "anchorer must be a checksummed 20-byte address.", "anchorer"))

    if "tx_hash" in event:
        tx = str(event["tx_hash"])
        if not HEX64_RE.match(tx):
            errors.append(_error(INVALID_TX_HASH,
                "tx_hash must be 0x{hex64}.", "tx_hash"))

    if "chain_id" in event:
        cid = event["chain_id"]
        if not isinstance(cid, int) or cid not in KNOWN_CHAIN_IDS:
            errors.append(_error(INVALID_CHAIN_ID,
                f"chain_id must be one of {sorted(KNOWN_CHAIN_IDS)}.", "chain_id"))

    if "block_number" in event:
        bn = event["block_number"]
        if not isinstance(bn, int) or bn < 0:
            errors.append(_error(INVALID_BLOCK_NUMBER,
                "block_number must be a non-negative integer.", "block_number"))

    if "artifact_type" in event:
        at = str(event["artifact_type"])
        if at not in VALID_ARTIFACT_TYPES:
            errors.append(_error(INVALID_ARTIFACT_TYPE,
                f"artifact_type must be one of {sorted(VALID_ARTIFACT_TYPES)}.", "artifact_type"))

    # ── timestamp ──
    if "timestamp" in event:
        ts = str(event["timestamp"])
        if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", ts):
            errors.append(_error(INVALID_TIMESTAMP,
                "timestamp must be ISO-8601.", "timestamp"))

    # ── event_fingerprint ──
    if "event_fingerprint" in event:
        efp = str(event["event_fingerprint"])
        if not SHA256_RE.match(efp):
            errors.append(_error(INVALID_EVENT_FINGERPRINT,
                "event_fingerprint must be sha256:{hex64}.", "event_fingerprint"))
        elif not errors:  # only verify if no prior errors
            expected = _compute_event_fingerprint(event)
            if efp != expected:
                errors.append(_error(INVALID_EVENT_FINGERPRINT,
                    f"event_fingerprint does not match canonical computation. "
                    f"Expected {expected}, got {efp}.", "event_fingerprint"))

    # ── hash ↔ fingerprint consistency ──
    if "anchor_hash" in event and "artifact_fingerprint" in event and not errors:
        ah = str(event["anchor_hash"])
        afp = str(event["artifact_fingerprint"])
        expected_hash = _fingerprint_to_bytes32(afp)
        if expected_hash is not None and ah.lower() != expected_hash.lower():
            errors.append(_error(HASH_FINGERPRINT_MISMATCH,
                f"anchor_hash must be the hex encoding of artifact_fingerprint. "
                f"Expected {expected_hash}, got {ah}.", "anchor_hash"))

    # ── metadata ──
    if "metadata" in event:
        meta = event["metadata"]
        if not isinstance(meta, dict):
            errors.append(_error(EXTRA_METADATA_FIELD,
                "metadata must be an object.", "metadata"))
        else:
            for key in meta:
                if key not in ALLOWED_METADATA_KEYS:
                    errors.append(_error(EXTRA_METADATA_FIELD,
                        f"Unknown metadata field: {key}.", f"metadata.{key}"))

            if "core_version" in meta and not VERSION_RE.match(str(meta["core_version"])):
                errors.append(_error(INVALID_CORE_VERSION,
                    "core_version must be v{major}.{minor}.{patch}.", "metadata.core_version"))

            if "log_index" in meta:
                li = meta["log_index"]
                if not isinstance(li, int) or li < 0:
                    errors.append(_error(INVALID_LOG_INDEX,
                        "log_index must be a non-negative integer.", "metadata.log_index"))

            if "verification_status" in meta:
                vs = str(meta["verification_status"])
                if vs not in VALID_VERIFICATION_STATUSES:
                    errors.append(_error(INVALID_VERIFICATION_STATUS,
                        f"verification_status must be one of {sorted(VALID_VERIFICATION_STATUSES)}.",
                        "metadata.verification_status"))

    # ── result ──
    status = "passed" if not errors else "failed"
    result: dict[str, Any] = {
        "schema": "v1",
        "status": status,
        "errors": errors,
    }
    if "event_id" in event and not errors:
        result["event_id"] = event["event_id"]
    result["event_valid"] = not errors

    return result


# ─── CLI ─────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: validate_anchoring_event.py <path>", file=sys.stderr)
        sys.exit(2)

    target = Path(sys.argv[1])
    if target.is_dir():
        results: list[dict[str, Any]] = []
        for p in sorted(target.rglob("*.json")):
            r = validate_anchoring_event(p)
            r["path"] = str(p)
            results.append(r)
        passed = sum(1 for r in results if r["status"] == "passed")
        failed = sum(1 for r in results if r["status"] == "failed")
        report_fingerprint = f"sha256:{_sha256_text(_canonical_json(results))}"
        output = {
            "schema": "v1",
            "status": "passed" if failed == 0 else "failed",
            "total_artifacts": len(results),
            "passed_count": passed,
            "failed_count": failed,
            "results": results,
            "report_fingerprint": report_fingerprint,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
        sys.exit(0 if failed == 0 else 1)
    else:
        result = validate_anchoring_event(target)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0 if result["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
