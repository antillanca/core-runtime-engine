"""Tests for bounded reference index validator and reader.

Covers:
- Validator: index, read_window, processed_cache (valid and rejected)
- Reader: next_marker, end_of_file, max_bytes, explicit_end_marker
- Reader: error cases (missing marker, path escape, ref_id not found)
- Byte-stability of both validator and reader
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VALIDATOR = PROJECT_ROOT / "scripts" / "validate_bounded_reference_index.py"
READER = PROJECT_ROOT / "scripts" / "read_bounded_reference.py"
FIXTURES = PROJECT_ROOT / "examples" / "bounded_reference_index"
INDEX = FIXTURES / "accepted_index.json"


def _run_validator(path: str) -> dict:
    r = subprocess.run(
        [sys.executable, str(VALIDATOR), path],
        capture_output=True, text=True,
    )
    return json.loads(r.stdout), r.returncode


def _run_reader(index: str, ref_id: str, include_content: bool = False) -> tuple[dict, int]:
    cmd = [sys.executable, str(READER), index, ref_id]
    if include_content:
        cmd.append("--include-content")
    r = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(r.stdout), r.returncode


# ---- Validator: valid artifacts ----------------------------------------

def test_validate_accepted_index():
    report, rc = _run_validator(str(INDEX))
    assert rc == 0
    result = report["results"][0]
    assert result["status"] == "passed"
    assert result["artifact_type"] == "bounded_reference_index"


def test_validate_accepted_read_window():
    report, rc = _run_validator(str(FIXTURES / "accepted_read_window.json"))
    assert rc == 0
    result = report["results"][0]
    assert result["status"] == "passed"
    assert result["artifact_type"] == "bounded_read_window"


def test_validate_accepted_processed_cache():
    report, rc = _run_validator(str(FIXTURES / "accepted_processed_cache.json"))
    assert rc == 0
    result = report["results"][0]
    assert result["status"] == "passed"
    assert result["artifact_type"] == "processed_reference_cache"


def test_validate_processed_cache_accepts_optional_source_provenance():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(
            {
                "schema_version": "core.processed_reference_cache.v1",
                "type": "processed_reference_cache",
                "index_id": "synthetic.docs.v1",
                "ref_id": "chapter_a",
                "window_fingerprint": "sha256:" + "1" * 64,
                "summary_fingerprint": "sha256:" + "2" * 64,
                "classification_candidate_fingerprint": "sha256:" + "3" * 64,
                "source_refs": ["run:alpha", "run:beta"],
                "source_fingerprints": ["sha256:" + "4" * 64, "sha256:" + "5" * 64],
                "cache_status": "fresh",
            },
            f,
        )
        f.flush()
        report, rc = _run_validator(f.name)
    assert rc == 0
    result = report["results"][0]
    assert result["status"] == "passed"
    assert result["artifact_type"] == "processed_reference_cache"


def test_validate_processed_cache_rejects_source_fingerprint_mismatch():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(
            {
                "schema_version": "core.processed_reference_cache.v1",
                "type": "processed_reference_cache",
                "index_id": "synthetic.docs.v1",
                "ref_id": "chapter_a",
                "window_fingerprint": "sha256:" + "1" * 64,
                "summary_fingerprint": "sha256:" + "2" * 64,
                "classification_candidate_fingerprint": "sha256:" + "3" * 64,
                "source_refs": ["run:alpha"],
                "source_fingerprints": ["sha256:" + "4" * 64, "sha256:" + "5" * 64],
                "cache_status": "fresh",
            },
            f,
        )
        f.flush()
        report, rc = _run_validator(f.name)
    assert rc == 1
    result = report["results"][0]
    codes = [e["code"] for e in result["errors"]]
    assert "source_fingerprint_mismatch" in codes


# ---- Validator: rejected artifacts -------------------------------------

def test_validate_rejected_missing_marker():
    report, rc = _run_validator(str(FIXTURES / "rejected_missing_marker.json"))
    assert rc == 1
    result = report["results"][0]
    assert result["status"] == "failed"
    codes = [e["code"] for e in result["errors"]]
    assert "missing_start_marker" in codes


def test_validate_rejected_absolute_path():
    report, rc = _run_validator(str(FIXTURES / "rejected_absolute_path.json"))
    assert rc == 1
    result = report["results"][0]
    assert result["status"] == "failed"
    codes = [e["code"] for e in result["errors"]]
    assert "absolute_path_rejected" in codes


def test_validate_rejected_path_escape():
    report, rc = _run_validator(str(FIXTURES / "rejected_path_escape.json"))
    assert rc == 1
    result = report["results"][0]
    assert result["status"] == "failed"
    codes = [e["code"] for e in result["errors"]]
    assert "path_escape_rejected" in codes


def test_validate_rejected_stale_cache():
    report, rc = _run_validator(str(FIXTURES / "rejected_stale_cache.json"))
    assert rc == 1
    result = report["results"][0]
    assert result["status"] == "failed"
    codes = [e["code"] for e in result["errors"]]
    assert "stale_processed_cache" in codes


# ---- Validator: directory mode -----------------------------------------

def test_validate_directory():
    report, rc = _run_validator(str(FIXTURES))
    assert report["total_artifacts"] >= 7
    assert report["passed_count"] >= 3
    assert report["failed_count"] >= 4


# ---- Validator: unknown schema_version ---------------------------------

def test_validate_unknown_schema_version():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"schema_version": "core.unknown.v99", "type": "foo"}, f)
        f.flush()
        report, rc = _run_validator(f.name)
    assert rc == 1
    codes = [e["code"] for e in report["results"][0]["errors"]]
    assert "unknown_schema_version" in codes


def test_validate_missing_schema_version_with_type_inference():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({
            "type": "bounded_reference_index",
            "index_id": "test",
            "entries": [{"ref_id": "x", "path": "y.md", "start_marker": "<!-- core:index id=\"x\" -->",
                         "end_policy": "next_marker", "max_bytes": 5000,
                         "expected_window_fingerprint": "sha256:" + "a" * 64,
                         "read_mode": "text"}]
        }, f)
        f.flush()
        report, rc = _run_validator(f.name)
    # Should dispatch via type field
    assert report["results"][0]["artifact_type"] == "bounded_reference_index"


# ---- Reader: chapter_a (next_marker) -----------------------------------

def test_reader_chapter_a():
    result, rc = _run_reader(str(INDEX), "chapter_a")
    assert rc == 0
    assert result["ref_id"] == "chapter_a"
    assert result["end_reason"] == "next_marker"
    assert result["bytes_read"] > 0
    assert result["window_fingerprint"].startswith("sha256:")
    assert result["window_fingerprint"] == "sha256:f499ed739cdc0514ed558dc2c58a556fbc4d2ea64cd4d4eb683a96957207e8d1"
    assert len(result["window_fingerprint"]) == 71  # sha256: + 64 hex


def test_reader_chapter_a_fingerprint_stable():
    r1, _ = _run_reader(str(INDEX), "chapter_a")
    r2, _ = _run_reader(str(INDEX), "chapter_a")
    assert r1["window_fingerprint"] == r2["window_fingerprint"]


# ---- Reader: chapter_b (next_marker) -----------------------------------

def test_reader_chapter_b():
    result, rc = _run_reader(str(INDEX), "chapter_b")
    assert rc == 0
    assert result["ref_id"] == "chapter_b"
    assert result["end_reason"] == "next_marker"


# ---- Reader: chapter_c (end_of_file) -----------------------------------

def test_reader_chapter_c_eof():
    result, rc = _run_reader(str(INDEX), "chapter_c")
    assert rc == 0
    assert result["end_reason"] == "end_of_file"


# ---- Reader: include-content -------------------------------------------

def test_reader_include_content():
    result, rc = _run_reader(str(INDEX), "chapter_a", include_content=True)
    assert rc == 0
    assert "content" in result
    assert "Chapter A" in result["content"]


# ---- Reader: no content by default -------------------------------------

def test_reader_no_content_by_default():
    result, rc = _run_reader(str(INDEX), "chapter_a")
    assert rc == 0
    assert "content" not in result


# ---- Reader: missing ref_id --------------------------------------------

def test_reader_ref_id_not_found():
    result, rc = _run_reader(str(INDEX), "nonexistent_ref")
    assert rc == 1
    assert result.get("status") == "failed"
    assert result["error_code"] == "ref_id_not_found"


# ---- Reader: missing start marker --------------------------------------

def test_reader_missing_start_marker():
    result, rc = _run_reader(
        str(FIXTURES / "rejected_missing_marker.json"), "missing_chapter"
    )
    assert rc == 1
    assert result.get("status") == "failed"
    assert result["error_code"] == "start_marker_not_found"


# ---- Reader: absolute path rejected ------------------------------------

def test_reader_absolute_path_rejected():
    result, rc = _run_reader(
        str(FIXTURES / "rejected_absolute_path.json"), "abs_path_entry"
    )
    assert rc == 1
    assert result.get("status") == "failed"
    assert result["error_code"] == "path_escape"


# ---- Reader: max_bytes truncation --------------------------------------

def test_reader_max_bytes_truncation():
    """Create a temp index with max_bytes=50 to force truncation."""
    with tempfile.TemporaryDirectory() as td:
        # Create a document
        doc = Path(td) / "doc.md"
        doc.write_text(
            "<!-- core:index id=\"small\" -->\n"
            "# Small\n"
            + ("A" * 500)
            + "\n"
        )
        idx = Path(td) / "index.json"
        idx.write_text(json.dumps({
            "schema_version": "core.bounded_reference_index.v1",
            "type": "bounded_reference_index",
            "index_id": "test.max_bytes.v1",
            "entries": [{
                "ref_id": "small",
                "path": "doc.md",
                "start_marker": "<!-- core:index id=\"small\" -->",
                "end_policy": "max_bytes",
                "max_bytes": 50,
                "expected_window_fingerprint": "sha256:11868e4b7e89b2e72c7af76ca7650291d0254586f7255c4f0500e6af6a5f153a",
                "read_mode": "text",
            }]
        }))
        result, rc = _run_reader(str(idx), "small", include_content=True)
        assert rc == 0
        assert result["end_reason"] == "max_bytes"
        assert result["bytes_read"] <= 50


# ---- Reader: explicit_end_marker ---------------------------------------

def test_reader_explicit_end_marker():
    """Create a temp index with explicit end marker."""
    with tempfile.TemporaryDirectory() as td:
        doc = Path(td) / "doc.md"
        doc.write_text(
            "<!-- core:index id=\"exp\" -->\n"
            "# Explicit\n"
            "Content here.\n"
            "<!-- core:index:end id=\"exp\" -->\n"
            "# After\n"
        )
        idx = Path(td) / "index.json"
        idx.write_text(json.dumps({
            "schema_version": "core.bounded_reference_index.v1",
            "type": "bounded_reference_index",
            "index_id": "test.explicit.v1",
            "entries": [{
                "ref_id": "exp",
                "path": "doc.md",
                "start_marker": "<!-- core:index id=\"exp\" -->",
                "end_policy": "explicit_end_marker",
                "end_marker": "<!-- core:index:end id=\"exp\" -->",
                "max_bytes": 12000,
                "expected_window_fingerprint": "sha256:f562a736f084347b8306607860057d86bad118d547ee354a237c053b713baead",
                "read_mode": "text",
            }]
        }))
        result, rc = _run_reader(str(idx), "exp", include_content=True)
        assert rc == 0
        assert result["end_reason"] == "explicit_end_marker"
        assert "Content here" in result["content"]
        assert "After" not in result["content"]


def test_reader_detects_index_drift_on_fingerprint_mismatch():
    with tempfile.TemporaryDirectory() as td:
        doc = Path(td) / "doc.md"
        doc.write_text(
            "<!-- core:index id=\"drift\" -->\n"
            "Drift\n"
        )
        idx = Path(td) / "index.json"
        idx.write_text(json.dumps({
            "schema_version": "core.bounded_reference_index.v1",
            "type": "bounded_reference_index",
            "index_id": "test.drift.v1",
            "entries": [{
                "ref_id": "drift",
                "path": "doc.md",
                "start_marker": "<!-- core:index id=\"drift\" -->",
                "end_policy": "end_of_file",
                "max_bytes": 12000,
                "expected_window_fingerprint": "sha256:" + "0" * 64,
                "read_mode": "text",
            }]
        }))
        result, rc = _run_reader(str(idx), "drift")
        assert rc == 1
        assert result.get("status") == "failed"
        assert result["error_code"] == "index_drift_detected"
        assert result["expected_window_fingerprint"] == "sha256:" + "0" * 64
        assert result["window_fingerprint"].startswith("sha256:")


def test_reader_rejects_ambiguous_start_marker():
    with tempfile.TemporaryDirectory() as td:
        doc = Path(td) / "doc.md"
        doc.write_text(
            "<!-- core:index id=\"dup\" -->\n"
            "One\n"
            "<!-- core:index id=\"dup\" -->\n"
            "Two\n"
        )
        idx = Path(td) / "index.json"
        idx.write_text(json.dumps({
            "schema_version": "core.bounded_reference_index.v1",
            "type": "bounded_reference_index",
            "index_id": "test.ambiguous.v1",
            "entries": [{
                "ref_id": "dup",
                "path": "doc.md",
                "start_marker": "<!-- core:index id=\"dup\" -->",
                "end_policy": "end_of_file",
                "max_bytes": 12000,
                "expected_window_fingerprint": "sha256:" + "1" * 64,
                "read_mode": "text",
            }]
        }))
        result, rc = _run_reader(str(idx), "dup")
        assert rc == 1
        assert result.get("status") == "failed"
        assert result["error_code"] == "ambiguous_start_marker"


# ---- Validator byte-stability ------------------------------------------

def test_validator_byte_stable():
    import subprocess
    r1 = subprocess.run([sys.executable, str(VALIDATOR), str(FIXTURES)],
                        capture_output=True, text=True)
    r2 = subprocess.run([sys.executable, str(VALIDATOR), str(FIXTURES)],
                        capture_output=True, text=True)
    assert r1.stdout == r2.stdout


# ---- Reader byte-stability ---------------------------------------------

def test_reader_byte_stable():
    r1, _ = _run_reader(str(INDEX), "chapter_a")
    r2, _ = _run_reader(str(INDEX), "chapter_a")
    assert r1 == r2


# ---- Validator: duplicate ref_id ---------------------------------------

def test_validate_duplicate_ref_id():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({
            "schema_version": "core.bounded_reference_index.v1",
            "type": "bounded_reference_index",
            "index_id": "test.dup.v1",
            "entries": [
                {"ref_id": "dup", "path": "a.md", "start_marker": "<!-- x -->",
                 "end_policy": "next_marker", "max_bytes": 5000,
                 "expected_window_fingerprint": "sha256:" + "a" * 64, "read_mode": "text"},
                {"ref_id": "dup", "path": "b.md", "start_marker": "<!-- y -->",
                 "end_policy": "next_marker", "max_bytes": 5000,
                 "expected_window_fingerprint": "sha256:" + "b" * 64, "read_mode": "text"},
            ]
        }, f)
        f.flush()
        report, rc = _run_validator(f.name)
    assert rc == 1
    codes = [e["code"] for e in report["results"][0]["errors"]]
    assert "duplicate_ref_id" in codes


# ---- Validator: unknown end_policy -------------------------------------

def test_validate_unknown_end_policy():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({
            "schema_version": "core.bounded_reference_index.v1",
            "type": "bounded_reference_index",
            "index_id": "test.bad_ep.v1",
            "entries": [{
                "ref_id": "x", "path": "a.md", "start_marker": "<!-- x -->",
                "end_policy": "semantic_search", "max_bytes": 5000,
                "expected_window_fingerprint": "sha256:" + "a" * 64, "read_mode": "text"
            }]
        }, f)
        f.flush()
        report, rc = _run_validator(f.name)
    assert rc == 1
    codes = [e["code"] for e in report["results"][0]["errors"]]
    assert "unknown_end_policy" in codes


# ---- Validator: unsupported read_mode ----------------------------------

def test_validate_unsupported_read_mode():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({
            "schema_version": "core.bounded_reference_index.v1",
            "type": "bounded_reference_index",
            "index_id": "test.bad_rm.v1",
            "entries": [{
                "ref_id": "x", "path": "a.md", "start_marker": "<!-- x -->",
                "end_policy": "next_marker", "max_bytes": 5000,
                "expected_window_fingerprint": "sha256:" + "a" * 64, "read_mode": "binary"
            }]
        }, f)
        f.flush()
        report, rc = _run_validator(f.name)
    assert rc == 1
    codes = [e["code"] for e in report["results"][0]["errors"]]
    assert "unsupported_read_mode" in codes
