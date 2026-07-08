"""Tests for validate_anchoring_event.py — CORE v9.1 Deterministic Event Verifier.

Covers: schema conformity, format checks, fingerprint computation,
hash↔fingerprint consistency, metadata validation, and batch directory mode.
"""

import json
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from scripts.validate_anchoring_event import (
    validate_anchoring_event,
    _compute_event_fingerprint,
    _fingerprint_to_bytes32,
    _canonical_json,
    _sha256_text,
    KNOWN_CHAIN_IDS,
    VALID_ARTIFACT_TYPES,
    VALID_VERIFICATION_STATUSES,
    FILE_NOT_FOUND,
    INVALID_JSON,
    INVALID_SCHEMA_VERSION,
    INVALID_TYPE,
    MISSING_REQUIRED_FIELD,
    EXTRA_FIELD_NOT_ALLOWED,
    INVALID_EVENT_ID,
    INVALID_SUBMISSION_REF,
    INVALID_ANCHOR_HASH,
    INVALID_ARTIFACT_FINGERPRINT,
    INVALID_CONTRACT_ADDRESS,
    INVALID_ANCHORER,
    INVALID_TX_HASH,
    INVALID_TIMESTAMP,
    INVALID_EVENT_FINGERPRINT,
    HASH_FINGERPRINT_MISMATCH,
    INVALID_CHAIN_ID,
    INVALID_BLOCK_NUMBER,
    INVALID_ARTIFACT_TYPE,
    INVALID_CORE_VERSION,
    INVALID_LOG_INDEX,
    INVALID_VERIFICATION_STATUS,
    EXTRA_METADATA_FIELD,
)

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples" / "anchoring_event"


# ─── Helpers ─────────────────────────────────────────────────────────────

def _write_tmp_event(event: dict, tmp_path: Path, name: str = "event.json") -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(event, ensure_ascii=False), encoding="utf-8")
    return p


def _valid_event(**overrides) -> dict:
    """Build a minimally valid anchoring_event."""
    base = {
        "schema_version": "v1",
        "type": "anchoring_event",
        "event_id": "evt_a1b2c3d4_d37606cbfa0e",
        "submission_ref": "anchor_e5f60708_0e6750c4e663",
        "anchor_hash": "0x542308c5313d2ce3607b243e4067855a3f760d925382828decc0383182007c02",
        "artifact_fingerprint": "sha256:542308c5313d2ce3607b243e4067855a3f760d925382828decc0383182007c02",
        "chain_id": 11155111,
        "contract_address": "0xdead000000000000000000000000000000000000",
        "anchorer": "0xbeef000000000000000000000000000000000000",
        "block_number": 5500000,
        "tx_hash": "0xaaaa000000000000000000000000000000000000000000000000000000000001",
        "timestamp": "2026-06-01T12:00:00Z",
    }
    base.update(overrides)
    # Compute fingerprint
    copy = {k: v for k, v in base.items() if k != "event_fingerprint"}
    base["event_fingerprint"] = f"sha256:{_sha256_text(_canonical_json(copy))}"
    return base


# ─── Fixture-based tests ─────────────────────────────────────────────────

class TestAcceptedFixtures:
    def test_freeze_anchor_passes(self):
        result = validate_anchoring_event(EXAMPLES_DIR / "accepted_freeze_anchor.json")
        assert result["status"] == "passed"
        assert result["event_valid"] is True

    def test_profile_anchor_passes(self):
        result = validate_anchoring_event(EXAMPLES_DIR / "accepted_profile_anchor.json")
        assert result["status"] == "passed"
        assert result["event_valid"] is True


class TestRejectedFixtures:
    def test_fingerprint_mismatch(self):
        result = validate_anchoring_event(EXAMPLES_DIR / "rejected_fingerprint_mismatch.json")
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert INVALID_EVENT_FINGERPRINT in codes

    def test_hash_fp_mismatch(self):
        result = validate_anchoring_event(EXAMPLES_DIR / "rejected_hash_fp_mismatch.json")
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert HASH_FINGERPRINT_MISMATCH in codes

    def test_unknown_chain(self):
        result = validate_anchoring_event(EXAMPLES_DIR / "rejected_unknown_chain.json")
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert INVALID_CHAIN_ID in codes


# ─── Structural tests ────────────────────────────────────────────────────

class TestRequiredFields:
    @pytest.mark.parametrize("field", sorted([
        "schema_version", "type", "event_id", "submission_ref",
        "anchor_hash", "chain_id", "contract_address", "anchorer",
        "block_number", "tx_hash", "timestamp", "event_fingerprint",
    ]))
    def test_missing_required_field(self, field, tmp_path):
        event = _valid_event()
        del event[field]
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert MISSING_REQUIRED_FIELD in codes


class TestExtraFields:
    def test_extra_top_level_field(self, tmp_path):
        event = _valid_event(extra_field="nope")
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert EXTRA_FIELD_NOT_ALLOWED in codes

    def test_extra_metadata_field(self, tmp_path):
        event = _valid_event(metadata={"core_version": "v9.1.0", "unknown_key": 42})
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert EXTRA_METADATA_FIELD in codes


# ─── Format tests ────────────────────────────────────────────────────────

class TestFormatValidation:
    def test_invalid_event_id_format(self, tmp_path):
        event = _valid_event(event_id="bad-id-format")
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        codes = [e["code"] for e in result["errors"]]
        assert INVALID_EVENT_ID in codes

    def test_invalid_submission_ref_format(self, tmp_path):
        event = _valid_event(submission_ref="bad-ref-format")
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        codes = [e["code"] for e in result["errors"]]
        assert INVALID_SUBMISSION_REF in codes

    def test_invalid_anchor_hash_format(self, tmp_path):
        event = _valid_event(anchor_hash="0xnothex")
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        codes = [e["code"] for e in result["errors"]]
        assert INVALID_ANCHOR_HASH in codes

    def test_invalid_artifact_fingerprint_format(self, tmp_path):
        event = _valid_event(artifact_fingerprint="sha256:tooshort")
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        codes = [e["code"] for e in result["errors"]]
        assert INVALID_ARTIFACT_FINGERPRINT in codes

    def test_invalid_tx_hash_format(self, tmp_path):
        event = _valid_event(tx_hash="0xbad")
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        codes = [e["code"] for e in result["errors"]]
        assert INVALID_TX_HASH in codes

    def test_invalid_timestamp(self, tmp_path):
        event = _valid_event(timestamp="not-a-date")
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        codes = [e["code"] for e in result["errors"]]
        assert INVALID_TIMESTAMP in codes

    def test_invalid_block_number_negative(self, tmp_path):
        event = _valid_event(block_number=-1)
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        codes = [e["code"] for e in result["errors"]]
        assert INVALID_BLOCK_NUMBER in codes

    def test_invalid_block_number_string(self, tmp_path):
        event = _valid_event(block_number="100")
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        codes = [e["code"] for e in result["errors"]]
        assert INVALID_BLOCK_NUMBER in codes

    def test_invalid_artifact_type(self, tmp_path):
        event = _valid_event(artifact_type="unknown_type")
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        codes = [e["code"] for e in result["errors"]]
        assert INVALID_ARTIFACT_TYPE in codes

    def test_invalid_chain_id(self, tmp_path):
        event = _valid_event(chain_id=42)
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        codes = [e["code"] for e in result["errors"]]
        assert INVALID_CHAIN_ID in codes

    def test_invalid_chain_id_string(self, tmp_path):
        event = _valid_event(chain_id="11155111")
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        codes = [e["code"] for e in result["errors"]]
        assert INVALID_CHAIN_ID in codes


# ─── Schema dispatch ─────────────────────────────────────────────────────

class TestSchemaDispatch:
    def test_wrong_schema_version(self, tmp_path):
        event = _valid_event(schema_version="v2")
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        codes = [e["code"] for e in result["errors"]]
        assert INVALID_SCHEMA_VERSION in codes

    def test_wrong_type(self, tmp_path):
        event = _valid_event(type="submission")
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        codes = [e["code"] for e in result["errors"]]
        assert INVALID_TYPE in codes


# ─── Fingerprint computation ─────────────────────────────────────────────

class TestFingerprintComputation:
    def test_correct_fingerprint_passes(self, tmp_path):
        event = _valid_event()
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        assert result["status"] == "passed"

    def test_tampered_fingerprint_fails(self, tmp_path):
        event = _valid_event()
        event["event_fingerprint"] = "sha256:ffff000000000000000000000000000000000000000000000000000000000000"
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        codes = [e["code"] for e in result["errors"]]
        assert INVALID_EVENT_FINGERPRINT in codes

    def test_canonical_json_stable(self):
        event = _valid_event()
        copy = {k: v for k, v in event.items() if k != "event_fingerprint"}
        fp1 = _compute_event_fingerprint(copy)
        fp2 = _compute_event_fingerprint(copy)
        assert fp1 == fp2


# ─── Hash ↔ fingerprint consistency ──────────────────────────────────────

class TestHashFingerprintConsistency:
    def test_matching_hash_and_fingerprint(self, tmp_path):
        event = _valid_event()
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        assert result["status"] == "passed"

    def test_mismatched_hash_and_fingerprint(self, tmp_path):
        event = _valid_event()
        event["anchor_hash"] = "0xdddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
        event["artifact_fingerprint"] = "sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
        # Recompute event_fingerprint
        copy = {k: v for k, v in event.items() if k != "event_fingerprint"}
        event["event_fingerprint"] = f"sha256:{_sha256_text(_canonical_json(copy))}"
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        codes = [e["code"] for e in result["errors"]]
        assert HASH_FINGERPRINT_MISMATCH in codes


# ─── Metadata validation ─────────────────────────────────────────────────

class TestMetadataValidation:
    def test_valid_metadata(self, tmp_path):
        event = _valid_event(metadata={
            "core_version": "v9.1.0",
            "log_index": 0,
            "verification_status": "confirmed",
        })
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        assert result["status"] == "passed"

    def test_invalid_core_version(self, tmp_path):
        event = _valid_event(metadata={"core_version": "9.1.0"})
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        codes = [e["code"] for e in result["errors"]]
        assert INVALID_CORE_VERSION in codes

    def test_negative_log_index(self, tmp_path):
        event = _valid_event(metadata={"log_index": -1})
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        codes = [e["code"] for e in result["errors"]]
        assert INVALID_LOG_INDEX in codes

    def test_invalid_verification_status(self, tmp_path):
        event = _valid_event(metadata={"verification_status": "maybe"})
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        codes = [e["code"] for e in result["errors"]]
        assert INVALID_VERIFICATION_STATUS in codes

    def test_metadata_not_object(self, tmp_path):
        event = _valid_event(metadata="not-an-object")
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        codes = [e["code"] for e in result["errors"]]
        assert EXTRA_METADATA_FIELD in codes


# ─── File & JSON errors ──────────────────────────────────────────────────

class TestFileErrors:
    def test_file_not_found(self, tmp_path):
        result = validate_anchoring_event(tmp_path / "nonexistent.json")
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert FILE_NOT_FOUND in codes

    def test_invalid_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{invalid json", encoding="utf-8")
        result = validate_anchoring_event(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert INVALID_JSON in codes

    def test_non_object_root(self, tmp_path):
        p = tmp_path / "array.json"
        p.write_text("[1, 2, 3]", encoding="utf-8")
        result = validate_anchoring_event(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert INVALID_JSON in codes


# ─── Directory batch mode ────────────────────────────────────────────────

class TestDirectoryMode:
    def test_batch_cli_directory(self):
        """Directory batch mode is CLI-only (main()), not in validate_anchoring_event()."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "scripts/validate_anchoring_event.py", str(EXAMPLES_DIR)],
            capture_output=True, text=True, cwd=str(Path(__file__).resolve().parent.parent),
        )
        # 3 rejected fixtures → exit code 1
        assert result.returncode == 1
        report = json.loads(result.stdout)
        assert report["total_artifacts"] == 5
        assert report["passed_count"] == 2
        assert report["failed_count"] == 3


# ─── Artifact types coverage ─────────────────────────────────────────────

class TestArtifactTypes:
    @pytest.mark.parametrize("atype", sorted(VALID_ARTIFACT_TYPES))
    def test_all_valid_artifact_types(self, tmp_path, atype):
        # Need unique anchor_hash per type to avoid duplicates
        h = hashlib.sha256(atype.encode()).hexdigest()
        event = _valid_event(
            artifact_type=atype,
            artifact_fingerprint=f"sha256:{h}",
            anchor_hash=f"0x{h}",
        )
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        assert result["status"] == "passed", f"artifact_type={atype} failed: {result}"


# ─── Chain IDs coverage ──────────────────────────────────────────────────

class TestChainIDs:
    @pytest.mark.parametrize("cid", sorted(KNOWN_CHAIN_IDS))
    def test_all_known_chain_ids(self, tmp_path, cid):
        event = _valid_event(chain_id=cid)
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        assert result["status"] == "passed", f"chain_id={cid} failed: {result}"


# ─── Address validation ──────────────────────────────────────────────────

class TestAddressValidation:
    def test_lowercase_address_passes(self, tmp_path):
        event = _valid_event(contract_address="0xabcdef0123456789abcdef0123456789abcdef01")
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        codes = [e["code"] for e in result["errors"]]
        assert INVALID_CONTRACT_ADDRESS not in codes

    def test_invalid_address_short(self, tmp_path):
        event = _valid_event(contract_address="0xabc")
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        codes = [e["code"] for e in result["errors"]]
        assert INVALID_CONTRACT_ADDRESS in codes

    def test_invalid_anchorer(self, tmp_path):
        event = _valid_event(anchorer="0xGGGG000000000000000000000000000000000000")
        p = _write_tmp_event(event, tmp_path)
        result = validate_anchoring_event(p)
        codes = [e["code"] for e in result["errors"]]
        assert INVALID_ANCHORER in codes
