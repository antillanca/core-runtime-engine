#!/usr/bin/env python3
"""Validate CORE bounded reference index, read window, and processed cache artifacts.

Accepts a single JSON file or a directory of JSON files.
Validates all three artifact types based on schema_version dispatch.

Rejection codes
---------------
Index-level:
  missing_schema_version       schema_version is missing or empty
  unknown_schema_version       schema_version not recognized
  invalid_type                 type field does not match schema
  missing_index_id             index_id is missing
  duplicate_ref_id             duplicate ref_id within entries
  absolute_path_rejected       path is absolute
  path_escape_rejected         path contains ../ that escapes repo root
  missing_start_marker         start_marker not found in referenced file
  unknown_end_policy           end_policy not in allowed set
  max_bytes_exceeded           max_bytes is missing, zero, or > 1MB
  invalid_window_fingerprint   expected_window_fingerprint malformed
  unsupported_read_mode        read_mode not in supported set

Read window:
  invalid_window_fingerprint   window_fingerprint format invalid
  unknown_end_reason           end_reason not in allowed set

Processed cache:
  stale_processed_cache        cache_status is stale
  invalid_window_fingerprint   window_fingerprint format invalid
  invalid_summary_fingerprint  summary_fingerprint format invalid
  invalid_classification_fp    classification_candidate_fingerprint format invalid
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

VALID_FP_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

# --- Rejection codes ---------------------------------------------------

MISSING_SCHEMA_VERSION = "missing_schema_version"
UNKNOWN_SCHEMA_VERSION = "unknown_schema_version"
INVALID_TYPE = "invalid_type"
MISSING_INDEX_ID = "missing_index_id"
DUPLICATE_REF_ID = "duplicate_ref_id"
ABSOLUTE_PATH_REJECTED = "absolute_path_rejected"
PATH_ESCAPE_REJECTED = "path_escape_rejected"
MISSING_START_MARKER = "missing_start_marker"
UNKNOWN_END_POLICY = "unknown_end_policy"
MAX_BYTES_EXCEEDED = "max_bytes_exceeded"
INVALID_WINDOW_FINGERPRINT = "invalid_window_fingerprint"
UNSUPPORTED_READ_MODE = "unsupported_read_mode"
UNKNOWN_END_REASON = "unknown_end_reason"
STALE_PROCESSED_CACHE = "stale_processed_cache"
INVALID_SUMMARY_FINGERPRINT = "invalid_summary_fingerprint"
INVALID_CLASSIFICATION_FP = "invalid_classification_fingerprint"

VALID_END_POLICIES = {"next_marker", "explicit_end_marker", "end_of_file", "max_bytes"}
VALID_READ_MODES = {"text"}
VALID_END_REASONS = {"explicit_end_marker", "next_marker", "max_bytes", "end_of_file"}

# --- Helpers -----------------------------------------------------------

def _error(code: str, message: str, field: str) -> dict[str, str]:
    return {"code": code, "message": message, "field": field}


def _validate_index(artifact: dict[str, Any], source: str) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    if not artifact.get("index_id"):
        errors.append(_error(MISSING_INDEX_ID, "index_id is required.", "index_id"))

    artifact_type = artifact.get("type", "")
    if artifact_type != "bounded_reference_index":
        errors.append(_error(INVALID_TYPE, f"Expected type 'bounded_reference_index', got {artifact_type!r}.", "type"))

    entries = artifact.get("entries", [])
    if not isinstance(entries, list) or len(entries) == 0:
        errors.append(_error(MISSING_INDEX_ID, "entries must be a non-empty array.", "entries"))
        return {"source": source, "artifact_type": "bounded_reference_index", "status": "failed", "errors": errors}

    # Check duplicate ref_ids
    seen_ref_ids: set[str] = set()
    for entry in entries:
        rid = entry.get("ref_id", "")
        if rid in seen_ref_ids:
            errors.append(_error(DUPLICATE_REF_ID, f"Duplicate ref_id: {rid!r}.", "entries"))
        seen_ref_ids.add(rid)

    # Resolve base dir for file checks (parent of the source file)
    source_path = Path(source)
    base_dir = source_path.parent if source_path.is_file() else source_path

    for i, entry in enumerate(entries, 1):
        prefix = f"entries[{i}]"

        # Path checks
        path_val = entry.get("path", "")
        if isinstance(path_val, str) and path_val.startswith("/"):
            errors.append(_error(ABSOLUTE_PATH_REJECTED, f"Absolute path rejected: {path_val!r}.", f"{prefix}.path"))
        elif isinstance(path_val, str) and ".." in path_val.split("/"):
            errors.append(_error(PATH_ESCAPE_REJECTED, f"Path escape rejected: {path_val!r}.", f"{prefix}.path"))

        # end_policy
        ep = entry.get("end_policy", "")
        if ep and ep not in VALID_END_POLICIES:
            errors.append(_error(UNKNOWN_END_POLICY, f"Unknown end_policy: {ep!r}.", f"{prefix}.end_policy"))

        # max_bytes
        mb = entry.get("max_bytes")
        if mb is None or not isinstance(mb, int) or mb < 1 or mb > 1048576:
            errors.append(_error(MAX_BYTES_EXCEEDED, f"max_bytes must be an integer 1-1048576, got {mb!r}.", f"{prefix}.max_bytes"))

        # expected_window_fingerprint
        ewf = entry.get("expected_window_fingerprint", "")
        if isinstance(ewf, str) and ewf and not VALID_FP_RE.match(ewf):
            errors.append(_error(INVALID_WINDOW_FINGERPRINT, f"Invalid fingerprint format: {ewf!r}.", f"{prefix}.expected_window_fingerprint"))

        # read_mode
        rm = entry.get("read_mode", "")
        if rm and rm not in VALID_READ_MODES:
            errors.append(_error(UNSUPPORTED_READ_MODE, f"Unsupported read_mode: {rm!r}.", f"{prefix}.read_mode"))

        # start_marker existence check (only if path is relative and safe)
        if (path_val and not path_val.startswith("/") and ".." not in path_val.split("/")
                and base_dir.exists()):
            target_file = base_dir / path_val
            if target_file.is_file():
                try:
                    content = target_file.read_text(encoding="utf-8")
                    sm = entry.get("start_marker", "")
                    if sm and sm not in content:
                        errors.append(_error(MISSING_START_MARKER, f"start_marker not found in {path_val!r}.", f"{prefix}.start_marker"))
                except (OSError, UnicodeDecodeError):
                    pass  # Skip file read check if file is unreadable

    status = "passed" if not errors else "failed"
    result: dict[str, Any] = {
        "source": source,
        "artifact_type": "bounded_reference_index",
        "status": status,
        "errors": errors,
    }
    if "index_id" in artifact:
        result["index_id"] = artifact["index_id"]
    return result


def _validate_read_window(artifact: dict[str, Any], source: str) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    if artifact.get("type", "") != "bounded_read_window":
        errors.append(_error(INVALID_TYPE, "Expected type 'bounded_read_window'.", "type"))

    wf = artifact.get("window_fingerprint", "")
    if isinstance(wf, str) and wf and not VALID_FP_RE.match(wf):
        errors.append(_error(INVALID_WINDOW_FINGERPRINT, f"Invalid fingerprint: {wf!r}.", "window_fingerprint"))

    er = artifact.get("end_reason", "")
    if er and er not in VALID_END_REASONS:
        errors.append(_error(UNKNOWN_END_REASON, f"Unknown end_reason: {er!r}.", "end_reason"))

    status = "passed" if not errors else "failed"
    result: dict[str, Any] = {
        "source": source,
        "artifact_type": "bounded_read_window",
        "status": status,
        "errors": errors,
    }
    if "index_id" in artifact:
        result["index_id"] = artifact["index_id"]
    if "ref_id" in artifact:
        result["ref_id"] = artifact["ref_id"]
    return result


def _validate_processed_cache(artifact: dict[str, Any], source: str) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    if artifact.get("type", "") != "processed_reference_cache":
        errors.append(_error(INVALID_TYPE, "Expected type 'processed_reference_cache'.", "type"))

    wf = artifact.get("window_fingerprint", "")
    if isinstance(wf, str) and wf and not VALID_FP_RE.match(wf):
        errors.append(_error(INVALID_WINDOW_FINGERPRINT, f"Invalid fingerprint: {wf!r}.", "window_fingerprint"))

    sf = artifact.get("summary_fingerprint", "")
    if isinstance(sf, str) and sf and not VALID_FP_RE.match(sf):
        errors.append(_error(INVALID_SUMMARY_FINGERPRINT, f"Invalid fingerprint: {sf!r}.", "summary_fingerprint"))

    cf = artifact.get("classification_candidate_fingerprint", "")
    if isinstance(cf, str) and cf and not VALID_FP_RE.match(cf):
        errors.append(_error(INVALID_CLASSIFICATION_FP, f"Invalid fingerprint: {cf!r}.", "classification_candidate_fingerprint"))

    source_refs = artifact.get("source_refs")
    source_fingerprints = artifact.get("source_fingerprints")
    if source_refs is not None or source_fingerprints is not None:
        if not isinstance(source_refs, list):
            errors.append(_error("invalid_source_refs", "source_refs must be an array when present.", "source_refs"))
        if not isinstance(source_fingerprints, list):
            errors.append(_error("invalid_source_fingerprints", "source_fingerprints must be an array when present.", "source_fingerprints"))
        if isinstance(source_refs, list) and isinstance(source_fingerprints, list):
            if len(source_refs) != len(source_fingerprints):
                errors.append(
                    _error(
                        "source_fingerprint_mismatch",
                        "source_refs and source_fingerprints must have the same length.",
                        "source_fingerprints",
                    )
                )
            for index, ref in enumerate(source_refs):
                if not isinstance(ref, str) or not ref.strip():
                    errors.append(_error("invalid_source_ref", "source_refs entries must be non-empty strings.", f"source_refs[{index}]"))
            for index, fingerprint in enumerate(source_fingerprints):
                if not isinstance(fingerprint, str) or not VALID_FP_RE.match(fingerprint):
                    errors.append(
                        _error(
                            INVALID_WINDOW_FINGERPRINT,
                            f"Invalid fingerprint: {fingerprint!r}.",
                            f"source_fingerprints[{index}]",
                        )
                    )

    # Stale cache is a validation failure for fixture correctness
    if artifact.get("cache_status") == "stale":
        errors.append(_error(STALE_PROCESSED_CACHE, "cache_status is stale.", "cache_status"))

    status = "passed" if not errors else "failed"
    result: dict[str, Any] = {
        "source": source,
        "artifact_type": "processed_reference_cache",
        "status": status,
        "errors": errors,
    }
    if "index_id" in artifact:
        result["index_id"] = artifact["index_id"]
    if "ref_id" in artifact:
        result["ref_id"] = artifact["ref_id"]
    return result


def _validate_one(artifact: dict[str, Any], source: str) -> dict[str, Any]:
    sv = artifact.get("schema_version", "")
    if not sv or not isinstance(sv, str):
        inferred = artifact.get("type", "")
        if inferred == "bounded_reference_index":
            return _validate_index(artifact, source)
        elif inferred == "bounded_read_window":
            return _validate_read_window(artifact, source)
        elif inferred == "processed_reference_cache":
            return _validate_processed_cache(artifact, source)
        else:
            return {
                "source": source,
                "artifact_type": "unknown",
                "status": "failed",
                "errors": [_error(MISSING_SCHEMA_VERSION, "Missing or invalid schema_version.", "schema_version")],
            }
    if sv == "core.bounded_reference_index.v1":
        return _validate_index(artifact, source)
    elif sv == "core.bounded_read_window.v1":
        return _validate_read_window(artifact, source)
    elif sv == "core.processed_reference_cache.v1":
        return _validate_processed_cache(artifact, source)
    else:
        return {
            "source": source,
            "artifact_type": "unknown",
            "status": "failed",
            "errors": [_error(UNKNOWN_SCHEMA_VERSION, f"Unknown schema_version: {sv!r}.", "schema_version")],
        }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Validate bounded reference index artifacts.")
    parser.add_argument("path", help="JSON file or directory to validate.")
    args = parser.parse_args()

    target = Path(args.path)
    files: list[Path] = []

    if target.is_dir():
        for p in sorted(target.rglob("*.json")):
            files.append(p)
    elif target.is_file():
        files.append(target)
    else:
        print(json.dumps({
            "schema": "core.bounded_reference_index_validation.v1",
            "status": "failed",
            "total_artifacts": 0,
            "passed_count": 0,
            "failed_count": 0,
            "results": [{"source": str(target), "artifact_type": "unknown", "status": "failed",
                         "errors": [_error("path_not_found", f"Path not found: {target}", "path")]}],
        }, indent=2))
        sys.exit(1)

    if not files:
        print(json.dumps({
            "schema": "core.bounded_reference_index_validation.v1",
            "status": "failed",
            "total_artifacts": 0,
            "passed_count": 0,
            "failed_count": 0,
            "results": [],
        }, indent=2))
        sys.exit(1)

    results: list[dict[str, Any]] = []
    for f in files:
        try:
            artifact = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            results.append({
                "source": str(f),
                "artifact_type": "unknown",
                "status": "failed",
                "errors": [{"code": "invalid_json", "message": str(exc), "field": "file"}],
            })
            continue
        results.append(_validate_one(artifact, str(f)))

    passed = sum(1 for r in results if r["status"] == "passed")
    failed = sum(1 for r in results if r["status"] == "failed")

    report_fingerprint = "sha256:" + hashlib.sha256(
        json.dumps(results, sort_keys=True).encode("utf-8")
    ).hexdigest()

    report = {
        "schema": "core.bounded_reference_index_validation.v1",
        "status": "passed" if failed == 0 else "failed",
        "total_artifacts": len(results),
        "passed_count": passed,
        "failed_count": failed,
        "report_fingerprint": report_fingerprint,
        "results": results,
    }

    print(json.dumps(report, indent=2, sort_keys=False))
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
