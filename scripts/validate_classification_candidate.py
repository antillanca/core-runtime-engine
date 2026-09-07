#!/usr/bin/env python3
"""Validate CORE classification candidate artifacts.

Accepts a single JSON file or a directory of JSON files.
Outputs a deterministic validation report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORT_SCHEMA = "core.classification_candidate_validation.v1"
CANDIDATE_SCHEMA = "core.classification_candidate.v1"

FINGERPRINT_RE = r"^sha256:[a-f0-9]{64}$"
VALID_DECISIONS = {"accepted", "clarification_required", "rejected"}
VALID_PRODUCER_KINDS = {
    "deterministic_classifier",
    "statistical_classifier",
    "llm_translation",
    "expert_proposal",
    "hybrid_pipeline",
}

# Rejection codes
MISSING_SCHEMA_VERSION = "missing_schema_version"
INVALID_TYPE = "invalid_type"
MISSING_PRODUCER = "missing_producer"
INVALID_CONFIDENCE = "invalid_confidence"
DECISION_CONFIDENCE_MISMATCH = "decision_confidence_mismatch"
UNKNOWN_DECISION = "unknown_decision"
MISSING_VOCABULARY_ID = "missing_vocabulary_id"
ACCEPTED_WITHOUT_MATCHED_FEATURES = "accepted_without_matched_features"
ACCEPTED_WITHOUT_INTENT = "accepted_without_intent"
UNSAFE_PATTERN_DETECTED = "unsafe_pattern_detected"
SLOTS_NOT_OBJECT = "slots_not_object"
INVALID_INPUT_FINGERPRINT = "invalid_input_fingerprint"
INVALID_THRESHOLDS = "invalid_thresholds"
COMMAND_VALIDATION_NOT_REQUIRED = "command_validation_not_required"


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


def _is_finite_number(value: Any) -> bool:
    """Return true only for JSON-compatible finite numeric scalars."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return not isinstance(value, float) or math.isfinite(value)


def _validate_one(candidate: dict[str, Any], source: str) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []

    # 1. schema_version
    sv = candidate.get("schema_version")
    if not sv or not isinstance(sv, str):
        errors.append(_error(MISSING_SCHEMA_VERSION, "Missing or invalid schema_version.", "schema_version"))

    # 2. type
    t = candidate.get("type")
    if t != "classification_candidate":
        errors.append(_error(INVALID_TYPE, f"Expected type 'classification_candidate', got {t!r}.", "type"))

    # 3. producer
    producer = candidate.get("producer")
    if not isinstance(producer, dict) or not producer.get("id") or not producer.get("kind"):
        errors.append(_error(MISSING_PRODUCER, "Producer must have 'id' and 'kind'.", "producer"))
    elif producer.get("kind") not in VALID_PRODUCER_KINDS:
        errors.append(_error(MISSING_PRODUCER, f"Unknown producer kind: {producer['kind']!r}.", "producer.kind"))

    # 4. input_fingerprint
    inp = candidate.get("input", {})
    fp = inp.get("input_fingerprint", "")
    if not isinstance(fp, str) or not fp.startswith("sha256:") or len(fp) != 71:
        errors.append(_error(INVALID_INPUT_FINGERPRINT, "input_fingerprint must match sha256:<64 hex chars>.", "input.input_fingerprint"))

    # 5. confidence
    classification = candidate.get("classification", {})
    confidence = classification.get("confidence")
    if not _is_finite_number(confidence) or confidence < 0.0 or confidence > 1.0:
        errors.append(_error(INVALID_CONFIDENCE, "confidence must be a number in [0.0, 1.0].", "classification.confidence"))

    # 6. decision
    decision = classification.get("decision")
    if decision not in VALID_DECISIONS:
        errors.append(_error(UNKNOWN_DECISION, f"decision must be one of {sorted(VALID_DECISIONS)}, got {decision!r}.", "classification.decision"))

    # 7. slots
    slots = classification.get("slots")
    if not isinstance(slots, dict):
        errors.append(_error(SLOTS_NOT_OBJECT, "slots must be a JSON object.", "classification.slots"))

    # 8. policy thresholds
    policy = candidate.get("policy", {})
    accept_th = policy.get("accept_threshold")
    clarify_th = policy.get("clarify_threshold")
    if not _is_finite_number(accept_th) or not _is_finite_number(clarify_th):
        errors.append(_error(INVALID_THRESHOLDS, "accept_threshold and clarify_threshold must be finite numbers.", "policy"))
    elif accept_th <= clarify_th:
        errors.append(_error(INVALID_THRESHOLDS, "accept_threshold must be greater than clarify_threshold.", "policy"))

    # 9. vocabulary_id
    vocab_id = policy.get("vocabulary_id")
    if not vocab_id or not isinstance(vocab_id, str) or not vocab_id.strip():
        errors.append(_error(MISSING_VOCABULARY_ID, "vocabulary_id must be a non-empty string.", "policy.vocabulary_id"))

    # 10. requires_command_validation
    safety = candidate.get("safety", {})
    if safety.get("requires_command_validation") is not True:
        errors.append(_error(COMMAND_VALIDATION_NOT_REQUIRED, "requires_command_validation must be true.", "safety.requires_command_validation"))

    # Cross-field validations (only if basics are present)
    if _is_finite_number(confidence) and decision in VALID_DECISIONS:
        # 11. decision_confidence_mismatch
        if decision == "accepted" and _is_finite_number(accept_th):
            if confidence < accept_th:
                errors.append(_error(
                    DECISION_CONFIDENCE_MISMATCH,
                    f"decision is 'accepted' but confidence {confidence} < accept_threshold {accept_th}.",
                    "classification.confidence",
                ))
        if decision == "clarification_required" and _is_finite_number(accept_th) and _is_finite_number(clarify_th):
            if confidence < clarify_th or confidence >= accept_th:
                errors.append(_error(
                    DECISION_CONFIDENCE_MISMATCH,
                    f"decision is 'clarification_required' but confidence {confidence} is not in [{clarify_th}, {accept_th}).",
                    "classification.confidence",
                ))
        if decision == "rejected":
            # rejected is valid for low confidence OR safety violation
            pass

    # 12. accepted requires matched_features
    if decision == "accepted":
        mf = classification.get("matched_features")
        if not isinstance(mf, list) or len(mf) == 0:
            errors.append(_error(ACCEPTED_WITHOUT_MATCHED_FEATURES, "accepted decision requires non-empty matched_features.", "classification.matched_features"))

    # 13. accepted requires intent
    if decision == "accepted":
        intent = classification.get("intent")
        if not intent or not isinstance(intent, str) or not intent.strip():
            errors.append(_error(ACCEPTED_WITHOUT_INTENT, "accepted decision requires non-empty intent.", "classification.intent"))

    # 14. unsafe_pattern_detected
    forbidden = safety.get("forbidden_patterns_detected", [])
    if isinstance(forbidden, list) and len(forbidden) > 0 and decision != "rejected":
        errors.append(_error(UNSAFE_PATTERN_DETECTED, f"forbidden_patterns_detected is non-empty but decision is {decision!r}, expected 'rejected'.", "safety.forbidden_patterns_detected"))

    passed = len(errors) == 0
    result: dict[str, Any] = {
        "source": source,
        "status": "passed" if passed else "failed",
        "errors": errors,
    }
    if passed:
        result["decision"] = decision
        result["confidence"] = confidence
        result["vocabulary_id"] = vocab_id
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
        "total_candidates": total,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "results": results,
    }
    report["report_fingerprint"] = _report_fingerprint(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate CORE classification candidate artifacts.")
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
