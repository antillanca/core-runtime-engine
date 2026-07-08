#!/usr/bin/env python3
"""Validate CORE Anchoring Submission artifact.

Ensures that a request to notarize a frozen artefact hash on an external
blockchain is well-formed, eligible, and does not move validation authority
or private data on-chain.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_FIELDS = {
    "schema_version", "type", "submission_id", "artifact_type",
    "artifact_fingerprint", "anchor_hash", "chain_id",
    "contract_address", "submitter", "submission_timestamp", "eligibility",
}

FIELD_TYPES = {
    "schema_version": str, "type": str, "submission_id": str,
    "artifact_type": str, "artifact_fingerprint": str,
    "anchor_hash": str, "chain_id": int,
    "contract_address": str, "submitter": str,
    "submission_timestamp": str, "eligibility": dict,
}

ARTIFACT_TYPES = {
    "release_manifest", "audit_trail_fingerprint",
    "certification_report", "replay_certification",
    "frozen_fixture_hash", "routing_decision_fingerprint",
    "evidence_bundle_fingerprint", "freeze_artifact",
    "downstream_bridge_compliance", "preintegration_manifest",
}

ELIGIBILITY_FIELDS = {
    "frozen_artifact", "hash_matches_fingerprint",
    "no_private_data", "no_runtime_authority_change",
}

METADATA_FIELDS = {"artifact_path", "release_version", "submission_reason"}

KNOWN_CHAIN_IDS = {1, 5, 11155111, 137, 80001, 42161, 421614}


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _fingerprint(payload: dict[str, Any]) -> str:
    return f"sha256:{_sha256_text(_canonical_json({k: v for k, v in payload.items() if k != 'submission_fingerprint'}))}"


def _error(code: str, message: str, field: str, **extra: Any) -> dict[str, Any]:
    entry = {"code": code, "message": message, "field": field}
    entry.update(extra)
    return entry


def _fingerprint_to_bytes32(fp: str) -> str:
    """Convert a CORE fingerprint 'sha256:{hex64}' to '0x{hex64}'."""
    if fp.startswith("sha256:"):
        return "0x" + fp[7:]
    return ""


def validate_anchoring_submission(path: Path) -> dict[str, Any]:
    path = Path(path)
    errors: list[dict[str, Any]] = []

    if not path.is_file():
        return _result({}, errors, [_error("file_not_found", f"File not found: {path}", "path")])

    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return _result({}, errors, [_error("invalid_json", str(exc), "path")])

    # --- Structural: required fields ---
    missing = REQUIRED_FIELDS - set(manifest.keys())
    for f in sorted(missing):
        errors.append(_error("missing_required_field", f"Required field '{f}' is missing.", f))

    extra_top = set(manifest.keys()) - REQUIRED_FIELDS - {"metadata"}
    if extra_top:
        errors.append(_error("extra_field_not_allowed", f"Additional properties not allowed: {extra_top}", next(iter(extra_top))))

    if errors:
        return _result(manifest, errors)

    # --- Type checks ---
    for field, expected_type in FIELD_TYPES.items():
        if field in manifest and not isinstance(manifest[field], expected_type):
            errors.append(_error("invalid_field_type", f"'{field}' must be {expected_type.__name__}, got {type(manifest[field]).__name__}.", field))

    if "metadata" in manifest and not isinstance(manifest["metadata"], dict):
        errors.append(_error("invalid_field_type", "'metadata' must be dict.", "metadata"))

    if errors:
        return _result(manifest, errors)

    # --- Constants ---
    if manifest.get("schema_version") != "v1":
        errors.append(_error("invalid_schema_version", "schema_version must be 'v1'.", "schema_version"))

    if manifest.get("type") != "anchoring_submission":
        errors.append(_error("invalid_type", "type must be 'anchoring_submission'.", "type"))

    # --- Submission ID format ---
    sid = manifest.get("submission_id", "")
    if not re.match(r"^anchor_[a-z0-9]{8}_[a-f0-9]{12}$", sid):
        errors.append(_error("invalid_submission_id", "submission_id must match pattern anchor_{hex8}_{hex12}.", "submission_id"))

    # --- Artifact type ---
    if manifest.get("artifact_type") not in ARTIFACT_TYPES:
        errors.append(_error("invalid_artifact_type", f"artifact_type must be one of: {sorted(ARTIFACT_TYPES)}.", "artifact_type"))

    # --- Fingerprint format ---
    fp = manifest.get("artifact_fingerprint", "")
    if not re.match(r"^sha256:[a-f0-9]{64}$", fp):
        errors.append(_error("invalid_artifact_fingerprint", "artifact_fingerprint must match sha256:{hex64}.", "artifact_fingerprint"))

    # --- Anchor hash format ---
    ah = manifest.get("anchor_hash", "")
    if not re.match(r"^0x[a-f0-9]{64}$", ah):
        errors.append(_error("invalid_anchor_hash", "anchor_hash must match 0x{hex64}.", "anchor_hash"))

    # --- Fingerprint <-> anchor hash consistency ---
    if fp and ah and not errors:
        expected_hash = _fingerprint_to_bytes32(fp)
        if ah != expected_hash:
            errors.append(_error("hash_fingerprint_mismatch",
                "anchor_hash must be the hex encoding of artifact_fingerprint.",
                "anchor_hash", expected=expected_hash, actual=ah))

    # --- Chain ID ---
    chain_id = manifest.get("chain_id", 0)
    if chain_id not in KNOWN_CHAIN_IDS:
        errors.append(_error("unknown_chain_id", f"chain_id {chain_id} is not in known chains: {sorted(KNOWN_CHAIN_IDS)}.", "chain_id"))

    # --- Contract address format ---
    ca = manifest.get("contract_address", "")
    if not re.match(r"^0x[a-f0-9]{40}$", ca):
        errors.append(_error("invalid_contract_address", "contract_address must match 0x{hex40}.", "contract_address"))

    # --- Submitter format ---
    sub = manifest.get("submitter", "")
    if not re.match(r"^0x[a-f0-9]{40}$", sub):
        errors.append(_error("invalid_submitter", "submitter must match 0x{hex40}.", "submitter"))

    # --- Timestamp ---
    ts = manifest.get("submission_timestamp", "")
    if isinstance(ts, str):
        try:
            datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            errors.append(_error("invalid_timestamp", "submission_timestamp must be ISO 8601.", "submission_timestamp"))

    # --- Eligibility block ---
    elig = manifest.get("eligibility", {})
    if isinstance(elig, dict):
        missing_elig = ELIGIBILITY_FIELDS - set(elig.keys())
        for f in sorted(missing_elig):
            errors.append(_error("missing_eligibility_field", f"eligibility requires '{f}'.", f"eligibility.{f}"))

        extra_elig = set(elig.keys()) - ELIGIBILITY_FIELDS
        if extra_elig:
            errors.append(_error("extra_eligibility_field", f"eligibility has extra fields: {extra_elig}.", "eligibility"))

        for field in ELIGIBILITY_FIELDS:
            if field in elig and not isinstance(elig[field], bool):
                errors.append(_error("eligibility_not_boolean", f"eligibility.{field} must be boolean.", f"eligibility.{field}"))

        # --- Eligibility fail-closed checks ---
        if isinstance(elig.get("frozen_artifact"), bool) and not elig["frozen_artifact"]:
            errors.append(_error("artifact_not_frozen", "Cannot anchor a non-frozen artefact.", "eligibility.frozen_artifact"))

        if isinstance(elig.get("hash_matches_fingerprint"), bool) and not elig["hash_matches_fingerprint"]:
            errors.append(_error("hash_mismatch_declared", "eligibility.hash_matches_fingerprint must be true.", "eligibility.hash_matches_fingerprint"))

        if isinstance(elig.get("no_private_data"), bool) and not elig["no_private_data"]:
            errors.append(_error("private_data_exposed", "eligibility.no_private_data must be true.", "eligibility.no_private_data"))

        if isinstance(elig.get("no_runtime_authority_change"), bool) and not elig["no_runtime_authority_change"]:
            errors.append(_error("runtime_authority_change", "eligibility.no_runtime_authority_change must be true.", "eligibility.no_runtime_authority_change"))

    # --- Metadata (optional) ---
    meta = manifest.get("metadata", {})
    if isinstance(meta, dict):
        extra_meta = set(meta.keys()) - METADATA_FIELDS
        if extra_meta:
            errors.append(_error("extra_metadata_field", f"metadata has extra fields: {extra_meta}.", "metadata"))

        if "release_version" in meta and not re.match(r"^v[0-9]+\.[0-9]+\.[0-9]+$", meta["release_version"]):
            errors.append(_error("invalid_release_version", "metadata.release_version must match vX.Y.Z.", "metadata.release_version"))

    return _result(manifest, errors)


def _result(manifest: dict, errors: list[dict], override_errors: list[dict] | None = None) -> dict[str, Any]:
    final_errors = override_errors if override_errors is not None else errors
    return {
        "schema": "v1",
        "status": "passed" if not final_errors else "failed",
        "submission_id": manifest.get("submission_id"),
        "artifact_type": manifest.get("artifact_type"),
        "errors": final_errors,
        "submission_valid": not final_errors,
    }


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if target is None:
        print("Usage: validate_anchoring_submission.py <path>", file=sys.stderr)
        sys.exit(1)
    result = validate_anchoring_submission(target)
    print(json.dumps(result, indent=2, ensure_ascii=False))
