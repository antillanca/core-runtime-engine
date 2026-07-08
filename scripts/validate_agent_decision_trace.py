#!/usr/bin/env python3
"""Validate CORE agent decision trace artifacts.

Accepts a single JSON file or a directory of JSON files.
Validates the agent_decision_trace artifact type.

Rejection codes (20):

  structural:  missing_schema_version, unknown_schema_version, invalid_type
  identity:    missing_trace_id, invalid_trace_id_format
  reference:   missing_session_ref, invalid_session_ref_format,
               invalid_plan_ref_format
  content:     empty_trace_entries, non_contiguous_entry_ids,
               duplicate_entry_id, invalid_entry_type,
               missing_entry_summary, empty_entry_summary
  evidence:    missing_evidence_hash_for_ref, invalid_evidence_hash_format
  temporal:    non_monotonic_timestamps
  governance:  governance_violation_count_mismatch, requires_review_not_set
  integrity:   missing_chain_root_hash, invalid_chain_root_hash_format,
               chain_root_hash_mismatch, immutability_guarantee_not_true,
               entry_count_mismatch
  summary:     trace_summary_entry_count_mismatch, entry_type_counts_mismatch
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "core.agent_decision_trace.v1"
ARTIFACT_TYPE = "agent_decision_trace"
VALID_ENTRY_TYPES = {"observation", "proposal", "outcome", "approval", "rejection"}
TRACE_ID_RE = re.compile(
    r"^agent_decision_trace:[a-z][a-z0-9_.-]*\.[a-z][a-z0-9_.-]*\.v[0-9]+$"
)
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REF_RE = re.compile(r"^[a-z][a-z0-9_.:-]*\.v[0-9]+$")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _rejection(code: str, message: str, field: str = "") -> dict[str, str]:
    entry = {"code": code, "message": message}
    if field:
        entry["field"] = field
    return entry


def validate_trace(data: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []

    # ── Structural ───────────────────────────────────────────────
    sv = data.get("schema_version")
    if not sv:
        errors.append(_rejection("missing_schema_version", "schema_version is required."))
        return errors
    if sv != SCHEMA_VERSION:
        errors.append(_rejection("unknown_schema_version", f"Expected '{SCHEMA_VERSION}', got '{sv}'."))
        return errors

    t = data.get("type")
    if t != ARTIFACT_TYPE:
        errors.append(_rejection("invalid_type", f"type must be '{ARTIFACT_TYPE}'.", "type"))

    # ── Identity ──────────────────────────────────────────────────
    tid = data.get("trace_id")
    if not tid:
        errors.append(_rejection("missing_trace_id", "trace_id is required."))
    elif not TRACE_ID_RE.match(tid):
        errors.append(_rejection("invalid_trace_id_format",
                                 "trace_id must match agent_decision_trace:<ns>.<desc>.vN.", "trace_id"))

    # ── Reference ─────────────────────────────────────────────────
    sref = data.get("session_ref")
    if not sref:
        errors.append(_rejection("missing_session_ref", "session_ref is required."))
    elif not REF_RE.match(str(sref)):
        errors.append(_rejection("invalid_session_ref_format", "session_ref format invalid.", "session_ref"))

    pref = data.get("plan_ref")
    if pref is not None and not REF_RE.match(str(pref)):
        errors.append(_rejection("invalid_plan_ref_format", "plan_ref format invalid.", "plan_ref"))

    # ── Content: entries ──────────────────────────────────────────
    entries = data.get("trace_entries")
    if not entries:
        errors.append(_rejection("empty_trace_entries", "trace_entries must not be empty."))
        return errors

    entry_ids = []
    for i, entry in enumerate(entries):
        eid = entry.get("entry_id")
        if eid is not None:
            entry_ids.append(eid)
        else:
            entry_ids.append(i)

        et = entry.get("entry_type")
        if et and et not in VALID_ENTRY_TYPES:
            errors.append(_rejection("invalid_entry_type",
                                     f"entry_type '{et}' not in {sorted(VALID_ENTRY_TYPES)}.",
                                     f"trace_entries[{i}].entry_type"))

        summary = entry.get("summary")
        if summary is None:
            errors.append(_rejection("missing_entry_summary", "summary is required.",
                                     f"trace_entries[{i}].summary"))
        elif not str(summary).strip():
            errors.append(_rejection("empty_entry_summary", "summary must not be empty.",
                                     f"trace_entries[{i}].summary"))

        src = entry.get("source_ref")
        eh = entry.get("evidence_hash")
        if src and not eh:
            errors.append(_rejection("missing_evidence_hash_for_ref",
                                     "source_ref present but evidence_hash missing.",
                                     f"trace_entries[{i}].evidence_hash"))
        if eh and not SHA256_RE.match(str(eh)):
            errors.append(_rejection("invalid_evidence_hash_format",
                                     "evidence_hash must be sha256:<64 hex chars>.",
                                     f"trace_entries[{i}].evidence_hash"))

    # ── Contiguous entry IDs ──────────────────────────────────────
    if entry_ids != list(range(len(entry_ids))):
        if len(set(entry_ids)) != len(entry_ids):
            errors.append(_rejection("duplicate_entry_id", "Duplicate entry_id found.", "trace_entries"))
        else:
            errors.append(_rejection("non_contiguous_entry_ids",
                                     "entry_id values must be 0..N-1 contiguous.", "trace_entries"))

    # ── Temporal: monotonic timestamps ────────────────────────────
    timestamps = []
    for i, entry in enumerate(entries):
        ts = entry.get("timestamp_iso")
        if ts:
            timestamps.append((i, ts))
    if len(timestamps) > 1:
        for j in range(1, len(timestamps)):
            if timestamps[j][1] < timestamps[j - 1][1]:
                errors.append(_rejection("non_monotonic_timestamps",
                                         f"timestamp at entry {timestamps[j][0]} < entry {timestamps[j-1][0]}.",
                                         f"trace_entries[{timestamps[j][0]}].timestamp_iso"))
                break

    # ── Governance ────────────────────────────────────────────────
    rejection_entries = [e for e in entries if e.get("entry_type") == "rejection"]
    gov_violations = sum(1 for e in rejection_entries
                        if e.get("metadata", {}).get("governance_violation", False))

    summary = data.get("trace_summary", {})
    claimed_violations = summary.get("governance_violations", 0)
    if gov_violations != claimed_violations:
        errors.append(_rejection("governance_violation_count_mismatch",
                                 f"Found {gov_violations} violation entries but summary claims {claimed_violations}.",
                                 "trace_summary.governance_violations"))

    if gov_violations > 0 and not summary.get("requires_review"):
        errors.append(_rejection("requires_review_not_set",
                                 "requires_review must be true when governance_violations > 0.",
                                 "trace_summary.requires_review"))

    # ── Integrity ─────────────────────────────────────────────────
    integrity = data.get("integrity", {})
    crh = integrity.get("chain_root_hash")
    if not crh:
        errors.append(_rejection("missing_chain_root_hash", "chain_root_hash is required."))
    elif not SHA256_RE.match(str(crh)):
        errors.append(_rejection("invalid_chain_root_hash_format",
                                 "chain_root_hash must be sha256:<64 hex chars>.",
                                 "integrity.chain_root_hash"))
    else:
        # Verify chain root hash: hash of all entry hashes in sequence
        entry_hashes = []
        for entry in entries:
            entry_copy = {k: v for k, v in entry.items() if k != "evidence_hash"}
            entry_hashes.append(_sha256_text(_canonical_json(entry_copy)))
        computed = f"sha256:{_sha256_text(''.join(entry_hashes))}"
        if computed != crh:
            errors.append(_rejection("chain_root_hash_mismatch",
                                     f"Computed {computed} != declared {crh}.",
                                     "integrity.chain_root_hash"))

    if not integrity.get("immutability_guarantee"):
        errors.append(_rejection("immutability_guarantee_not_true",
                                 "immutability_guarantee must be true.",
                                 "integrity.immutability_guarantee"))

    ec = integrity.get("entry_count")
    if ec is not None and ec != len(entries):
        errors.append(_rejection("entry_count_mismatch",
                                 f"entry_count={ec} but actual entries={len(entries)}.",
                                 "integrity.entry_count"))

    # ── Summary counts ────────────────────────────────────────────
    ts_total = summary.get("total_entries")
    if ts_total is not None and ts_total != len(entries):
        errors.append(_rejection("trace_summary_entry_count_mismatch",
                                 f"total_entries={ts_total} but actual={len(entries)}.",
                                 "trace_summary.total_entries"))

    etc = summary.get("entry_type_counts", {})
    actual_counts: dict[str, int] = {}
    for entry in entries:
        et = entry.get("entry_type", "")
        actual_counts[et] = actual_counts.get(et, 0) + 1
    if etc and etc != actual_counts:
        errors.append(_rejection("entry_type_counts_mismatch",
                                 f"Declared {etc} != actual {actual_counts}.",
                                 "trace_summary.entry_type_counts"))

    return errors


def _validate_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "source": str(path),
            "artifact_type": "agent_decision_trace",
            "status": "failed",
            "errors": [{"code": "invalid_json", "message": str(exc)}],
        }

    errors = validate_trace(data)
    status = "passed" if not errors else "failed"
    return {
        "source": str(path),
        "artifact_type": "agent_decision_trace",
        "status": status,
        "errors": errors,
    }


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <file_or_dir>", file=sys.stderr)
        sys.exit(1)

    target = Path(sys.argv[1])
    files = sorted(target.glob("*.json")) if target.is_dir() else [target]

    results = [_validate_file(f) for f in files]
    passed = sum(1 for r in results if r["status"] == "passed")
    failed = len(results) - passed
    status = "passed" if failed == 0 else "failed"

    report = {
        "schema": "core.agent_decision_trace_validation.v1",
        "status": status,
        "total_artifacts": len(results),
        "passed_count": passed,
        "failed_count": failed,
        "results": results,
        "report_fingerprint": "",
    }
    report["report_fingerprint"] = f"sha256:{_sha256_text(_canonical_json(report))}"
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
