from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "scripts" / "validate_classification_candidate.py"
FIXTURES_DIR = PROJECT_ROOT / "examples" / "classification_candidates"


def _run_single(fixture: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(FIXTURES_DIR / fixture)],
        check=False,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )


def _run_directory() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(FIXTURES_DIR)],
        check=False,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )


# === Valid fixtures ===


def test_accepted_passes() -> None:
    result = _run_single("accepted.json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    assert payload["results"][0]["decision"] == "accepted"
    assert payload["results"][0]["confidence"] == 0.92
    assert payload["results"][0]["vocabulary_id"] == "synthetic_reports.v1"


def test_clarification_required_passes() -> None:
    result = _run_single("clarification_required.json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    assert payload["results"][0]["decision"] == "clarification_required"
    assert payload["results"][0]["confidence"] == 0.72


def test_rejected_low_confidence_passes() -> None:
    result = _run_single("rejected_low_confidence.json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    assert payload["results"][0]["decision"] == "rejected"


def test_rejected_unsafe_pattern_passes() -> None:
    result = _run_single("rejected_unsafe_pattern.json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    assert payload["results"][0]["decision"] == "rejected"


# === Invalid fixtures ===


def test_invalid_confidence_mismatch_fails() -> None:
    result = _run_single("invalid_confidence_mismatch.json")
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "decision_confidence_mismatch" in codes


def test_invalid_missing_vocabulary_id_fails() -> None:
    result = _run_single("invalid_missing_vocabulary_id.json")
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "missing_vocabulary_id" in codes


# === Directory validation ===


def test_directory_validation_counts() -> None:
    result = _run_directory()
    assert result.returncode != 0  # 2 invalids
    payload = json.loads(result.stdout)
    assert payload["schema"] == "core.classification_candidate_validation.v1"
    assert payload["total_candidates"] == 6
    assert payload["passed_count"] == 4
    assert payload["failed_count"] == 2


# === Byte stability ===


def test_directory_validation_is_byte_stable() -> None:
    first = _run_directory()
    second = _run_directory()
    # Both should produce the same output (including failed status)
    assert first.stdout == second.stdout


# === Structural edge cases ===


def test_missing_schema_version() -> None:
    candidate = {
        "type": "classification_candidate",
        "producer": {"id": "test.v1", "kind": "deterministic_classifier"},
        "input": {"input_fingerprint": "sha256:" + "a" * 64, "language": "en", "normalized_text": "test"},
        "classification": {"domain": "synth", "intent": "test", "confidence": 0.9, "decision": "accepted", "slots": {}, "matched_features": ["test"]},
        "policy": {"vocabulary_id": "synth.v1", "accept_threshold": 0.85, "clarify_threshold": 0.60},
        "safety": {"forbidden_patterns_detected": [], "requires_command_validation": True},
    }
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, dir="/tmp") as f:
        json.dump(candidate, f)
        f.flush()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), f.name],
            check=False, capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "missing_schema_version" in codes


def test_invalid_type() -> None:
    candidate = {
        "schema_version": "core.classification_candidate.v1",
        "type": "wrong_type",
        "producer": {"id": "test.v1", "kind": "deterministic_classifier"},
        "input": {"input_fingerprint": "sha256:" + "a" * 64, "language": "en", "normalized_text": "test"},
        "classification": {"domain": "synth", "intent": "test", "confidence": 0.9, "decision": "accepted", "slots": {}, "matched_features": ["test"]},
        "policy": {"vocabulary_id": "synth.v1", "accept_threshold": 0.85, "clarify_threshold": 0.60},
        "safety": {"forbidden_patterns_detected": [], "requires_command_validation": True},
    }
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, dir="/tmp") as f:
        json.dump(candidate, f)
        f.flush()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), f.name],
            check=False, capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
    payload = json.loads(result.stdout)
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "invalid_type" in codes


def test_invalid_confidence_out_of_range() -> None:
    candidate = {
        "schema_version": "core.classification_candidate.v1",
        "type": "classification_candidate",
        "producer": {"id": "test.v1", "kind": "deterministic_classifier"},
        "input": {"input_fingerprint": "sha256:" + "a" * 64, "language": "en", "normalized_text": "test"},
        "classification": {"domain": "synth", "intent": "test", "confidence": 1.5, "decision": "accepted", "slots": {}, "matched_features": ["test"]},
        "policy": {"vocabulary_id": "synth.v1", "accept_threshold": 0.85, "clarify_threshold": 0.60},
        "safety": {"forbidden_patterns_detected": [], "requires_command_validation": True},
    }
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, dir="/tmp") as f:
        json.dump(candidate, f)
        f.flush()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), f.name],
            check=False, capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
    payload = json.loads(result.stdout)
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "invalid_confidence" in codes


def test_unknown_decision() -> None:
    candidate = {
        "schema_version": "core.classification_candidate.v1",
        "type": "classification_candidate",
        "producer": {"id": "test.v1", "kind": "deterministic_classifier"},
        "input": {"input_fingerprint": "sha256:" + "a" * 64, "language": "en", "normalized_text": "test"},
        "classification": {"domain": "synth", "intent": "test", "confidence": 0.9, "decision": "maybe", "slots": {}, "matched_features": ["test"]},
        "policy": {"vocabulary_id": "synth.v1", "accept_threshold": 0.85, "clarify_threshold": 0.60},
        "safety": {"forbidden_patterns_detected": [], "requires_command_validation": True},
    }
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, dir="/tmp") as f:
        json.dump(candidate, f)
        f.flush()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), f.name],
            check=False, capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
    payload = json.loads(result.stdout)
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "unknown_decision" in codes


def test_accepted_without_matched_features() -> None:
    candidate = {
        "schema_version": "core.classification_candidate.v1",
        "type": "classification_candidate",
        "producer": {"id": "test.v1", "kind": "deterministic_classifier"},
        "input": {"input_fingerprint": "sha256:" + "a" * 64, "language": "en", "normalized_text": "test"},
        "classification": {"domain": "synth", "intent": "test", "confidence": 0.9, "decision": "accepted", "slots": {}, "matched_features": []},
        "policy": {"vocabulary_id": "synth.v1", "accept_threshold": 0.85, "clarify_threshold": 0.60},
        "safety": {"forbidden_patterns_detected": [], "requires_command_validation": True},
    }
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, dir="/tmp") as f:
        json.dump(candidate, f)
        f.flush()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), f.name],
            check=False, capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
    payload = json.loads(result.stdout)
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "accepted_without_matched_features" in codes


def test_accepted_without_intent() -> None:
    candidate = {
        "schema_version": "core.classification_candidate.v1",
        "type": "classification_candidate",
        "producer": {"id": "test.v1", "kind": "deterministic_classifier"},
        "input": {"input_fingerprint": "sha256:" + "a" * 64, "language": "en", "normalized_text": "test"},
        "classification": {"domain": "synth", "intent": "", "confidence": 0.9, "decision": "accepted", "slots": {}, "matched_features": ["test"]},
        "policy": {"vocabulary_id": "synth.v1", "accept_threshold": 0.85, "clarify_threshold": 0.60},
        "safety": {"forbidden_patterns_detected": [], "requires_command_validation": True},
    }
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, dir="/tmp") as f:
        json.dump(candidate, f)
        f.flush()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), f.name],
            check=False, capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
    payload = json.loads(result.stdout)
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "accepted_without_intent" in codes


def test_unsafe_pattern_not_rejected() -> None:
    candidate = {
        "schema_version": "core.classification_candidate.v1",
        "type": "classification_candidate",
        "producer": {"id": "test.v1", "kind": "deterministic_classifier"},
        "input": {"input_fingerprint": "sha256:" + "a" * 64, "language": "en", "normalized_text": "test"},
        "classification": {"domain": "synth", "intent": "test", "confidence": 0.9, "decision": "accepted", "slots": {}, "matched_features": ["test"]},
        "policy": {"vocabulary_id": "synth.v1", "accept_threshold": 0.85, "clarify_threshold": 0.60},
        "safety": {"forbidden_patterns_detected": ["destructive_command"], "requires_command_validation": True},
    }
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, dir="/tmp") as f:
        json.dump(candidate, f)
        f.flush()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), f.name],
            check=False, capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
    payload = json.loads(result.stdout)
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "unsafe_pattern_detected" in codes


def test_slots_not_object() -> None:
    candidate = {
        "schema_version": "core.classification_candidate.v1",
        "type": "classification_candidate",
        "producer": {"id": "test.v1", "kind": "deterministic_classifier"},
        "input": {"input_fingerprint": "sha256:" + "a" * 64, "language": "en", "normalized_text": "test"},
        "classification": {"domain": "synth", "intent": "test", "confidence": 0.9, "decision": "accepted", "slots": "not_an_object", "matched_features": ["test"]},
        "policy": {"vocabulary_id": "synth.v1", "accept_threshold": 0.85, "clarify_threshold": 0.60},
        "safety": {"forbidden_patterns_detected": [], "requires_command_validation": True},
    }
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, dir="/tmp") as f:
        json.dump(candidate, f)
        f.flush()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), f.name],
            check=False, capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
    payload = json.loads(result.stdout)
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "slots_not_object" in codes


def test_invalid_input_fingerprint() -> None:
    candidate = {
        "schema_version": "core.classification_candidate.v1",
        "type": "classification_candidate",
        "producer": {"id": "test.v1", "kind": "deterministic_classifier"},
        "input": {"input_fingerprint": "md5:abc123", "language": "en", "normalized_text": "test"},
        "classification": {"domain": "synth", "intent": "test", "confidence": 0.9, "decision": "accepted", "slots": {}, "matched_features": ["test"]},
        "policy": {"vocabulary_id": "synth.v1", "accept_threshold": 0.85, "clarify_threshold": 0.60},
        "safety": {"forbidden_patterns_detected": [], "requires_command_validation": True},
    }
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, dir="/tmp") as f:
        json.dump(candidate, f)
        f.flush()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), f.name],
            check=False, capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
    payload = json.loads(result.stdout)
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "invalid_input_fingerprint" in codes


def test_invalid_thresholds() -> None:
    candidate = {
        "schema_version": "core.classification_candidate.v1",
        "type": "classification_candidate",
        "producer": {"id": "test.v1", "kind": "deterministic_classifier"},
        "input": {"input_fingerprint": "sha256:" + "a" * 64, "language": "en", "normalized_text": "test"},
        "classification": {"domain": "synth", "intent": "test", "confidence": 0.9, "decision": "accepted", "slots": {}, "matched_features": ["test"]},
        "policy": {"vocabulary_id": "synth.v1", "accept_threshold": 0.50, "clarify_threshold": 0.60},
        "safety": {"forbidden_patterns_detected": [], "requires_command_validation": True},
    }
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, dir="/tmp") as f:
        json.dump(candidate, f)
        f.flush()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), f.name],
            check=False, capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
    payload = json.loads(result.stdout)
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "invalid_thresholds" in codes


def test_command_validation_not_required() -> None:
    candidate = {
        "schema_version": "core.classification_candidate.v1",
        "type": "classification_candidate",
        "producer": {"id": "test.v1", "kind": "deterministic_classifier"},
        "input": {"input_fingerprint": "sha256:" + "a" * 64, "language": "en", "normalized_text": "test"},
        "classification": {"domain": "synth", "intent": "test", "confidence": 0.9, "decision": "accepted", "slots": {}, "matched_features": ["test"]},
        "policy": {"vocabulary_id": "synth.v1", "accept_threshold": 0.85, "clarify_threshold": 0.60},
        "safety": {"forbidden_patterns_detected": [], "requires_command_validation": False},
    }
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, dir="/tmp") as f:
        json.dump(candidate, f)
        f.flush()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), f.name],
            check=False, capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
    payload = json.loads(result.stdout)
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "command_validation_not_required" in codes


def test_missing_producer() -> None:
    candidate = {
        "schema_version": "core.classification_candidate.v1",
        "type": "classification_candidate",
        "producer": {},
        "input": {"input_fingerprint": "sha256:" + "a" * 64, "language": "en", "normalized_text": "test"},
        "classification": {"domain": "synth", "intent": "test", "confidence": 0.9, "decision": "accepted", "slots": {}, "matched_features": ["test"]},
        "policy": {"vocabulary_id": "synth.v1", "accept_threshold": 0.85, "clarify_threshold": 0.60},
        "safety": {"forbidden_patterns_detected": [], "requires_command_validation": True},
    }
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, dir="/tmp") as f:
        json.dump(candidate, f)
        f.flush()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), f.name],
            check=False, capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
    payload = json.loads(result.stdout)
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "missing_producer" in codes


def test_nonfinite_confidence_is_rejected() -> None:
    candidate = json.loads((FIXTURES_DIR / "accepted.json").read_text(encoding="utf-8"))
    candidate["classification"]["confidence"] = float("nan")
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, dir="/tmp") as handle:
        json.dump(candidate, handle, allow_nan=True)
        handle.flush()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), handle.name],
            check=False,
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
    payload = json.loads(result.stdout)
    assert result.returncode != 0
    assert "invalid_confidence" in {
        item["code"] for item in payload["results"][0]["errors"]
    }


def test_nonfinite_threshold_is_rejected() -> None:
    candidate = json.loads((FIXTURES_DIR / "accepted.json").read_text(encoding="utf-8"))
    candidate["policy"]["accept_threshold"] = float("inf")
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, dir="/tmp") as handle:
        json.dump(candidate, handle, allow_nan=True)
        handle.flush()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), handle.name],
            check=False,
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
    payload = json.loads(result.stdout)
    assert result.returncode != 0
    assert "invalid_thresholds" in {
        item["code"] for item in payload["results"][0]["errors"]
    }
