"""Tests for validate_anchoring_submission.py

Covers: structural validation, type checks, eligibility fail-closed,
fingerprint-hash consistency, chain ID, format checks, and all fixtures.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


from scripts.validate_anchoring_submission import (
    validate_anchoring_submission,
    _fingerprint_to_bytes32,
    _error,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = PROJECT_ROOT / "examples" / "anchoring"


# ─── Helpers ─────────────────────────────────────────────────────────────

def _write_tmp(payload: dict) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(payload, f, ensure_ascii=False)
    f.flush()
    f.close()
    return Path(f.name)


def _validate(payload: dict) -> dict:
    path = _write_tmp(payload)
    result = validate_anchoring_submission(path)
    path.unlink(missing_ok=True)
    return result


def _valid_submission(**overrides) -> dict:
    base = {
        "schema_version": "v1",
        "type": "anchoring_submission",
        "submission_id": "anchor_a1b2c3d4_deadbeef1234",
        "artifact_type": "freeze_artifact",
        "artifact_fingerprint": "sha256:" + "a" * 64,
        "anchor_hash": "0x" + "a" * 64,
        "chain_id": 11155111,
        "contract_address": "0x1234567890abcdef1234567890abcdef12345678",
        "submitter": "0xabcdef0123456789abcdef0123456789abcdef01",
        "submission_timestamp": "2026-05-29T10:00:00+00:00",
        "eligibility": {
            "frozen_artifact": True,
            "hash_matches_fingerprint": True,
            "no_private_data": True,
            "no_runtime_authority_change": True,
        },
    }
    base.update(overrides)
    return base


# ─── Structural tests ────────────────────────────────────────────────────

class TestStructural:
    def test_file_not_found(self):
        result = validate_anchoring_submission(Path("/nonexistent.json"))
        assert result["status"] == "failed"
        assert any(e["code"] == "file_not_found" for e in result["errors"])

    def test_invalid_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{invalid")
        result = validate_anchoring_submission(p)
        assert result["status"] == "failed"
        assert any(e["code"] == "invalid_json" for e in result["errors"])

    def test_missing_required_field(self):
        for field in ["submission_id", "artifact_type", "eligibility"]:
            payload = _valid_submission()
            del payload[field]
            result = _validate(payload)
            assert result["status"] == "failed"
            assert any(e["code"] == "missing_required_field" and e["field"] == field for e in result["errors"])

    def test_extra_top_level_field(self):
        payload = _valid_submission(unexpected_field="oops")
        result = _validate(payload)
        assert result["status"] == "failed"
        assert any(e["code"] == "extra_field_not_allowed" for e in result["errors"])


# ─── Type and constant tests ─────────────────────────────────────────────

class TestTypeAndConstants:
    def test_invalid_schema_version(self):
        result = _validate(_valid_submission(schema_version="v2"))
        assert result["status"] == "failed"
        assert any(e["code"] == "invalid_schema_version" for e in result["errors"])

    def test_invalid_type(self):
        result = _validate(_valid_submission(type="wrong_type"))
        assert result["status"] == "failed"
        assert any(e["code"] == "invalid_type" for e in result["errors"])

    def test_invalid_submission_id_format(self):
        for bad_id in ["", "anchor_", "wrong_format_123"]:
            result = _validate(_valid_submission(submission_id=bad_id))
            assert result["status"] == "failed"
            assert any(e["code"] == "invalid_submission_id" for e in result["errors"])

    def test_invalid_artifact_type(self):
        result = _validate(_valid_submission(artifact_type="unknown_thing"))
        assert result["status"] == "failed"
        assert any(e["code"] == "invalid_artifact_type" for e in result["errors"])

    def test_valid_artifact_types(self):
        for at in ["release_manifest", "freeze_artifact", "evidence_bundle_fingerprint"]:
            result = _validate(_valid_submission(artifact_type=at))
            assert result["status"] == "passed", f"artifact_type={at} should pass"


# ─── Format tests ────────────────────────────────────────────────────────

class TestFormats:
    def test_invalid_fingerprint_format(self):
        result = _validate(_valid_submission(artifact_fingerprint="not_a_fingerprint"))
        assert result["status"] == "failed"
        assert any(e["code"] == "invalid_artifact_fingerprint" for e in result["errors"])

    def test_invalid_anchor_hash_format(self):
        result = _validate(_valid_submission(anchor_hash="not_a_hash"))
        assert result["status"] == "failed"
        assert any(e["code"] == "invalid_anchor_hash" for e in result["errors"])

    def test_invalid_contract_address(self):
        result = _validate(_valid_submission(contract_address="0x00"))
        assert result["status"] == "failed"
        assert any(e["code"] == "invalid_contract_address" for e in result["errors"])

    def test_invalid_submitter(self):
        result = _validate(_valid_submission(submitter="0x00"))
        assert result["status"] == "failed"
        assert any(e["code"] == "invalid_submitter" for e in result["errors"])

    def test_invalid_timestamp(self):
        result = _validate(_valid_submission(submission_timestamp="not-a-date"))
        assert result["status"] == "failed"
        assert any(e["code"] == "invalid_timestamp" for e in result["errors"])

    def test_timestamp_requires_timezone(self):
        result = _validate(_valid_submission(submission_timestamp="2026-05-29T10:00:00"))
        assert result["status"] == "failed"
        assert any(e["code"] == "invalid_timestamp" for e in result["errors"])


# ─── Fingerprint/hash consistency ────────────────────────────────────────

class TestHashConsistency:
    def test_fingerprint_to_bytes32(self):
        assert _fingerprint_to_bytes32("sha256:abcd1234" + "f" * 56) == "0xabcd1234" + "f" * 56

    def test_fingerprint_to_bytes32_invalid(self):
        # _fingerprint_to_bytes32 in the validator returns "" for invalid input
        result = _fingerprint_to_bytes32("not_sha256:abc")
        assert result == ""

    def test_hash_mismatch_detected(self):
        result = _validate(_valid_submission(
            artifact_fingerprint="sha256:" + "a" * 64,
            anchor_hash="0x" + "b" * 64,
        ))
        assert result["status"] == "failed"
        assert any(e["code"] == "hash_fingerprint_mismatch" for e in result["errors"])

    def test_hash_match_passes(self):
        result = _validate(_valid_submission(
            artifact_fingerprint="sha256:" + "c" * 64,
            anchor_hash="0x" + "c" * 64,
        ))
        assert result["status"] == "passed"


# ─── Chain ID tests ──────────────────────────────────────────────────────

class TestChainId:
    def test_positive_chain_ids(self):
        for cid in [1, 999, 11155111, 42161]:
            result = _validate(_valid_submission(chain_id=cid))
            assert result["status"] == "passed", f"chain_id={cid} should pass"

    def test_non_positive_or_boolean_chain_id(self):
        for cid in [0, -1, True]:
            result = _validate(_valid_submission(chain_id=cid))
            assert result["status"] == "failed"
            assert any(e["code"] == "invalid_chain_id" for e in result["errors"])


# ─── Eligibility fail-closed tests ───────────────────────────────────────

class TestEligibility:
    def test_not_frozen_rejected(self):
        elig = {"frozen_artifact": False, "hash_matches_fingerprint": True, "no_private_data": True, "no_runtime_authority_change": True}
        result = _validate(_valid_submission(eligibility=elig))
        assert result["status"] == "failed"
        assert any(e["code"] == "artifact_not_frozen" for e in result["errors"])

    def test_hash_mismatch_declared_rejected(self):
        elig = {"frozen_artifact": True, "hash_matches_fingerprint": False, "no_private_data": True, "no_runtime_authority_change": True}
        result = _validate(_valid_submission(eligibility=elig))
        assert result["status"] == "failed"
        assert any(e["code"] == "hash_mismatch_declared" for e in result["errors"])

    def test_private_data_exposed_rejected(self):
        elig = {"frozen_artifact": True, "hash_matches_fingerprint": True, "no_private_data": False, "no_runtime_authority_change": True}
        result = _validate(_valid_submission(eligibility=elig))
        assert result["status"] == "failed"
        assert any(e["code"] == "private_data_exposed" for e in result["errors"])

    def test_runtime_authority_change_rejected(self):
        elig = {"frozen_artifact": True, "hash_matches_fingerprint": True, "no_private_data": True, "no_runtime_authority_change": False}
        result = _validate(_valid_submission(eligibility=elig))
        assert result["status"] == "failed"
        assert any(e["code"] == "runtime_authority_change" for e in result["errors"])

    def test_missing_eligibility_field(self):
        elig = {"frozen_artifact": True, "hash_matches_fingerprint": True}
        result = _validate(_valid_submission(eligibility=elig))
        assert result["status"] == "failed"
        assert any(e["code"] == "missing_eligibility_field" for e in result["errors"])

    def test_extra_eligibility_field(self):
        elig = {"frozen_artifact": True, "hash_matches_fingerprint": True, "no_private_data": True, "no_runtime_authority_change": True, "extra": True}
        result = _validate(_valid_submission(eligibility=elig))
        assert result["status"] == "failed"
        assert any(e["code"] == "extra_eligibility_field" for e in result["errors"])


# ─── Metadata tests ─────────────────────────────────────────────────────

class TestMetadata:
    def test_valid_metadata(self):
        payload = _valid_submission(metadata={"release_version": "v8.5.0", "submission_reason": "test"})
        result = _validate(payload)
        assert result["status"] == "passed"

    def test_invalid_release_version(self):
        payload = _valid_submission(metadata={"release_version": "8.5.0"})
        result = _validate(payload)
        assert result["status"] == "failed"
        assert any(e["code"] == "invalid_release_version" for e in result["errors"])

    def test_extra_metadata_field(self):
        payload = _valid_submission(metadata={"release_version": "v8.5.0", "unknown": True})
        result = _validate(payload)
        assert result["status"] == "failed"
        assert any(e["code"] == "extra_metadata_field" for e in result["errors"])

    def test_artifact_path_must_be_relative_and_bounded(self):
        for path in ["/private/artifact.json", "../artifact.json", "safe/../artifact.json"]:
            result = _validate(_valid_submission(metadata={"artifact_path": path}))
            assert result["status"] == "failed"
            assert any(e["code"] == "invalid_artifact_path" for e in result["errors"])

    def test_metadata_values_are_typed(self):
        result = _validate(_valid_submission(metadata={"artifact_path": 7, "submission_reason": ""}))
        assert result["status"] == "failed"
        assert any(e["code"] == "invalid_metadata_type" for e in result["errors"])


# ─── Fixture file tests ─────────────────────────────────────────────────

class TestFixtures:
    def test_accepted_freeze_artifact(self):
        result = validate_anchoring_submission(FIXTURES_DIR / "accepted_freeze_artifact.json")
        assert result["status"] == "passed"
        assert result["submission_valid"] is True

    def test_accepted_release_manifest(self):
        result = validate_anchoring_submission(FIXTURES_DIR / "accepted_release_manifest.json")
        assert result["status"] == "passed"
        assert result["submission_valid"] is True

    def test_rejected_not_frozen(self):
        result = validate_anchoring_submission(FIXTURES_DIR / "rejected_not_frozen.json")
        assert result["status"] == "failed"
        assert any(e["code"] == "artifact_not_frozen" for e in result["errors"])

    def test_rejected_hash_mismatch(self):
        result = validate_anchoring_submission(FIXTURES_DIR / "rejected_hash_mismatch.json")
        assert result["status"] == "failed"
        assert any(e["code"] == "hash_fingerprint_mismatch" for e in result["errors"])

    def test_rejected_private_data(self):
        result = validate_anchoring_submission(FIXTURES_DIR / "rejected_private_data.json")
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "private_data_exposed" in codes
        assert "runtime_authority_change" in codes


# ─── Result structure tests ──────────────────────────────────────────────

class TestResultStructure:
    def test_result_keys_on_pass(self):
        result = _validate(_valid_submission())
        assert "schema" in result
        assert "status" in result
        assert "errors" in result
        assert "submission_valid" in result
        assert result["schema"] == "v1"

    def test_error_has_required_keys(self):
        err = _error("test_code", "test message", "test_field")
        assert "code" in err
        assert "message" in err
        assert "field" in err
