#!/usr/bin/env python3
"""Validate CORE external LLM sync bundle artifacts.

Accepts a single JSON file or a directory of JSON files.
Outputs a deterministic validation report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORT_SCHEMA = "core.external_llm_sync_bundle_validation.v1"
BUNDLE_SCHEMA = "core.external_llm_sync_bundle.v1"

FINGERPRINT_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
VALID_KINDS = {"llm_translation", "llm_classification", "llm_extraction"}
VALID_STATUSES = {"accepted", "rejected", "clarification_needed"}
VALID_FRESHNESS = {"fresh", "cached", "stale"}

# Rejection codes
INVALID_SCHEMA_VERSION = "invalid_schema_version"
INVALID_TYPE = "invalid_type"
MISSING_BUNDLE_ID = "missing_bundle_id"
INVALID_PRODUCER = "invalid_producer"
INVALID_PRODUCER_KIND = "invalid_producer_kind"
INVALID_CONTEXT = "invalid_context"
INVALID_QUERY_FINGERPRINT = "invalid_query_fingerprint"
INVALID_RETRIEVAL = "invalid_retrieval"
INVALID_CONTEXT_BUNDLE_FINGERPRINT = "invalid_context_bundle_fingerprint"
INVALID_FRESHNESS = "invalid_freshness"
INVALID_CANDIDATE = "invalid_candidate"
INVALID_CANDIDATE_FINGERPRINT = "invalid_candidate_fingerprint"
INVALID_EVIDENCE = "invalid_evidence"
INVALID_EVIDENCE_BUNDLE_FINGERPRINT = "invalid_evidence_bundle_fingerprint"
NON_ADVISORY_AUTHORITY = "non_advisory_authority"
PRIVATE_DATA_INCLUDED = "private_data_included"
UNBOUNDED_CONTEXT_USED = "unbounded_context_used"
TOOL_EXECUTION_REQUESTED = "tool_execution_requested"
ACCEPTED_WITH_MISSING_FACTS = "accepted_with_missing_facts"
INVALID_STATUS = "invalid_status"


def _canonical_dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)


def _report_fingerprint(report: dict[str, Any]) -> str:
    payload = {k: v for k, v in report.items() if k != "report_fingerprint"}
    return f"sha256:{hashlib.sha256(_canonical_dump(payload).encode('utf-8')).hexdigest()}"


def _error(code: str, message: str, field: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    if field is not None:
        payload["field"] = field
    return payload


def _check_fingerprint(value: Any, field_name: str) -> list[dict[str, Any]]:
    """Validate a sha256 fingerprint field."""
    if not isinstance(value, str) or not FINGERPRINT_RE.match(value):
        return [_error(
            f"invalid_{field_name}",
            f"{field_name} must match sha256:<64 hex chars>, got {value!r}.",
            field_name,
        )]
    return []


def _validate_one(bundle: dict[str, Any], source: str) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []

    # 1. schema_version
    sv = bundle.get("schema_version")
    if sv != BUNDLE_SCHEMA:
        errors.append(_error(INVALID_SCHEMA_VERSION, f"Expected schema_version {BUNDLE_SCHEMA!r}, got {sv!r}.", "schema_version"))

    # 2. type
    t = bundle.get("type")
    if t != "external_llm_sync_bundle":
        errors.append(_error(INVALID_TYPE, f"Expected type 'external_llm_sync_bundle', got {t!r}.", "type"))

    # 3. bundle_id
    bid = bundle.get("bundle_id")
    if not bid or not isinstance(bid, str) or not bid.strip():
        errors.append(_error(MISSING_BUNDLE_ID, "bundle_id must be a non-empty string.", "bundle_id"))

    # 4. producer
    producer = bundle.get("producer")
    if not isinstance(producer, dict) or not producer.get("id") or not producer.get("kind"):
        errors.append(_error(INVALID_PRODUCER, "Producer must have 'id' and 'kind'.", "producer"))
    elif producer.get("kind") not in VALID_KINDS:
        errors.append(_error(INVALID_PRODUCER_KIND, f"Unknown producer kind: {producer['kind']!r}.", "producer.kind"))

    # 5. context
    context = bundle.get("context")
    if not isinstance(context, dict) or not context.get("context_budget_ref") or not isinstance(context.get("read_refs"), list):
        errors.append(_error(INVALID_CONTEXT, "context must have 'context_budget_ref' and 'read_refs'.", "context"))
    else:
        # 5a. query_fingerprint
        errors.extend(_check_fingerprint(context.get("query_fingerprint", ""), "context.query_fingerprint"))

    # 6. retrieval
    retrieval = bundle.get("retrieval")
    if not isinstance(retrieval, dict) or not retrieval.get("retrieval_profile"):
        errors.append(_error(INVALID_RETRIEVAL, "retrieval must have 'retrieval_profile'.", "retrieval"))
    else:
        # 6a. context_bundle_fingerprint
        errors.extend(_check_fingerprint(retrieval.get("context_bundle_fingerprint", ""), "retrieval.context_bundle_fingerprint"))
        # 6b. freshness
        freshness = retrieval.get("freshness")
        if freshness not in VALID_FRESHNESS:
            errors.append(_error(INVALID_FRESHNESS, f"freshness must be one of {sorted(VALID_FRESHNESS)}, got {freshness!r}.", "retrieval.freshness"))

    # 7. candidate
    candidate = bundle.get("candidate")
    if not isinstance(candidate, dict) or not candidate.get("candidate_type") or not candidate.get("candidate_ref"):
        errors.append(_error(INVALID_CANDIDATE, "candidate must have 'candidate_type' and 'candidate_ref'.", "candidate"))
    else:
        # 7a. candidate_fingerprint
        errors.extend(_check_fingerprint(candidate.get("candidate_fingerprint", ""), "candidate.candidate_fingerprint"))

    # 8. evidence
    evidence = bundle.get("evidence")
    if not isinstance(evidence, dict) or not isinstance(evidence.get("missing_facts"), list):
        errors.append(_error(INVALID_EVIDENCE, "evidence must have 'missing_facts' as array.", "evidence"))
    else:
        # 8a. evidence_bundle_fingerprint
        errors.extend(_check_fingerprint(evidence.get("evidence_bundle_fingerprint", ""), "evidence.evidence_bundle_fingerprint"))

    # 9. safety - semantic rules
    safety = bundle.get("safety", {})
    if safety.get("authority") != "advisory_only":
        errors.append(_error(NON_ADVISORY_AUTHORITY, "authority must be 'advisory_only'. External LLMs never authorize execution.", "safety.authority"))
    if safety.get("private_data_included") is True:
        errors.append(_error(PRIVATE_DATA_INCLUDED, "private_data_included must be false. Private data is never allowed.", "safety.private_data_included"))
    if safety.get("unbounded_context_used") is True:
        errors.append(_error(UNBOUNDED_CONTEXT_USED, "unbounded_context_used must be false. All context must be budgeted.", "safety.unbounded_context_used"))
    if safety.get("tool_execution_requested") is True:
        errors.append(_error(TOOL_EXECUTION_REQUESTED, "tool_execution_requested must be false. LLMs propose, CORE disposes.", "safety.tool_execution_requested"))

    # 10. status
    status = bundle.get("status")
    if status not in VALID_STATUSES:
        errors.append(_error(INVALID_STATUS, f"status must be one of {sorted(VALID_STATUSES)}, got {status!r}.", "status"))

    # 11. Cross-field: accepted with missing_facts
    if status == "accepted" and isinstance(evidence, dict):
        missing = evidence.get("missing_facts", [])
        if isinstance(missing, list) and len(missing) > 0:
            errors.append(_error(ACCEPTED_WITH_MISSING_FACTS, "status is 'accepted' but missing_facts is non-empty. Must be 'clarification_needed' or 'rejected'.", "status"))

    passed = len(errors) == 0
    result: dict[str, Any] = {
        "source": source,
        "status": "passed" if passed else "failed",
        "errors": errors,
    }
    if passed:
        result["bundle_id"] = bid
        result["authority"] = safety.get("authority")
        result["private_data_included"] = safety.get("private_data_included")
        result["missing_facts_count"] = len(evidence.get("missing_facts", [])) if isinstance(evidence, dict) else 0
    return result


def validate_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"source": str(path), "status": "failed", "errors": [_error("invalid_json", str(exc))]}
    if not isinstance(payload, dict):
        return {"source": str(path), "status": "failed", "errors": [_error("invalid_json", "Expected a JSON object.")]}
    return _validate_one(payload, str(path))


def validate_directory(dir_path: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for json_file in sorted(dir_path.glob("*.json")):
        results.append(validate_file(json_file))
    return results


def build_report(results: list[dict[str, Any]]) -> dict[str, Any]:
    passed_count = sum(1 for r in results if r["status"] == "passed")
    failed_count = sum(1 for r in results if r["status"] == "failed")
    total = len(results)

    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "status": "passed" if failed_count == 0 else "failed",
        "total_bundles": total,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "results": results,
    }
    report["report_fingerprint"] = _report_fingerprint(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate CORE external LLM sync bundle artifacts.")
    parser.add_argument("path", type=Path, help="JSON file or directory of JSON files to validate.")
    args = parser.parse_args()

    target = args.path.resolve()
    if not target.exists():
        print(f"Error: {target} does not exist.", file=sys.stderr)
        sys.exit(1)

    if target.is_dir():
        results = validate_directory(target)
    else:
        results = [validate_file(target)]

    report = build_report(results)
    print(_canonical_dump(report))

    if report["status"] == "failed":
        sys.exit(1)


if __name__ == "__main__":
    main()
