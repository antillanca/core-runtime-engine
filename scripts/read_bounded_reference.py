#!/usr/bin/env python3
"""Deterministic bounded reference reader for CORE.

Reads a declared reference from a bounded reference index and produces
a bounded_read_window artifact with exact offsets, fingerprint, and
end_reason.

If the index declares an expected_window_fingerprint, the reader fails
closed when the computed window fingerprint does not match.

Usage:
    python scripts/read_bounded_reference.py <index.json> <ref_id> [--include-content]

Output (JSON to stdout):
    {
      "schema_version": "core.bounded_read_window.v1",
      "type": "bounded_read_window",
      "index_id": "...",
      "ref_id": "...",
      "path": "...",
      "start_offset": N,
      "end_offset": M,
      "bytes_read": K,
      "window_fingerprint": "sha256:...",
      "end_reason": "next_marker|explicit_end_marker|max_bytes|end_of_file"
    }

With --include-content, adds a "content" field with the text read.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

MARKER_RE = re.compile(r"<!--\s*core:index\s+id=\"([^\"]+)\"\s*-->")
END_MARKER_RE = re.compile(r"<!--\s*core:index:end\s+id=\"([^\"]+)\"\s*-->")
INDEX_DRIFT_DETECTED = "index_drift_detected"
AMBIGUOUS_START_MARKER = "ambiguous_start_marker"
END_MARKER_NOT_FOUND = "end_marker_not_found"


def _find_all_markers(text: str) -> list[tuple[str, int, bool]]:
    """Return list of (marker_id, byte_offset, is_end_marker)."""
    markers: list[tuple[str, int, bool]] = []
    for m in MARKER_RE.finditer(text):
        markers.append((m.group(1), m.start(), False))
    for m in END_MARKER_RE.finditer(text):
        markers.append((m.group(1), m.start(), True))
    markers.sort(key=lambda x: x[1])
    return markers


def read_bounded_reference(
    index_path: str,
    ref_id: str,
    include_content: bool = False,
) -> dict:
    """Read a bounded reference and return a read_window artifact."""
    index_file = Path(index_path)
    if not index_file.is_file():
        return _error_result(ref_id, f"Index file not found: {index_path}", "index_not_found")

    try:
        index_data = json.loads(index_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return _error_result(ref_id, f"Invalid index JSON: {exc}", "invalid_json")

    sv = index_data.get("schema_version", "")
    if sv != "core.bounded_reference_index.v1":
        return _error_result(ref_id, f"Unsupported schema_version: {sv!r}", "unsupported_schema")

    index_id = index_data.get("index_id", "unknown")
    entries = index_data.get("entries", [])

    target_entry = None
    for entry in entries:
        if entry.get("ref_id") == ref_id:
            target_entry = entry
            break

    if target_entry is None:
        return _error_result(ref_id, f"ref_id {ref_id!r} not found in index.", "ref_id_not_found")

    path_val = target_entry.get("path", "")
    start_marker = target_entry.get("start_marker", "")
    end_policy = target_entry.get("end_policy", "next_marker")
    end_marker_str = target_entry.get("end_marker", "")
    max_bytes = target_entry.get("max_bytes", 1048576)
    expected_window_fingerprint = target_entry.get("expected_window_fingerprint", "")

    # Resolve path: respect optional index-level content_root override
    # before falling back to the index file location.
    content_root_str = index_data.get("content_root", "")
    if content_root_str:
        base_dir = Path(content_root_str)
        target_path = base_dir / path_val
    else:
        base_dir = index_file.parent
        target_path = base_dir / path_val

    # Safety: reject absolute paths and path escapes.
    # When content_root is set, escape check is against content_root;
    # otherwise against the index file directory.
    try:
        resolved = target_path.resolve()
        base_resolved = base_dir.resolve()
        if not str(resolved).startswith(str(base_resolved)):
            return _error_result(ref_id, f"Path escapes base directory: {path_val}", "path_escape")
    except (ValueError, OSError):
        return _error_result(ref_id, f"Invalid path: {path_val}", "path_escape")

    if not target_path.is_file():
        return _error_result(ref_id, f"Referenced file not found: {path_val}", "file_not_found")

    try:
        file_text = target_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return _error_result(ref_id, f"Cannot read file: {exc}", "file_read_error")

    # Find start marker position
    if not start_marker:
        return _error_result(ref_id, "start_marker missing or empty.", "start_marker_not_found")

    start_marker_count = file_text.count(start_marker)
    if start_marker_count > 1:
        return _error_result(
            ref_id,
            f"ambiguous start_marker {start_marker!r}: appears {start_marker_count} times.",
            AMBIGUOUS_START_MARKER,
        )

    start_idx = file_text.find(start_marker)
    if start_idx == -1:
        return _error_result(ref_id, f"start_marker not found: {start_marker!r}", "start_marker_not_found")

    # Content starts after the marker line
    content_start = start_idx + len(start_marker)
    # Skip trailing whitespace/newline after marker
    while content_start < len(file_text) and file_text[content_start] in "\n\r":
        content_start += 1

    # Determine end based on policy
    all_markers = _find_all_markers(file_text)
    end_offset = len(file_text)
    end_reason = "end_of_file"

    if end_policy == "next_marker":
        # Find the next start marker after our start
        for mid, moffset, is_end in all_markers:
            if moffset > start_idx and not is_end and mid != ref_id:
                end_offset = moffset
                end_reason = "next_marker"
                break
    elif end_policy == "explicit_end_marker":
        # Prefer the declared end_marker; fall back to the canonical form.
        end_marker_pattern = end_marker_str or f'<!-- core:index:end id="{ref_id}" -->'
        end_idx = file_text.find(end_marker_pattern, content_start)
        if end_idx != -1:
            end_offset = end_idx
            end_reason = "explicit_end_marker"
        else:
            return _error_result(
                ref_id,
                f"end_marker not found: {end_marker_pattern!r}",
                END_MARKER_NOT_FOUND,
            )
    elif end_policy == "max_bytes":
        end_offset = min(content_start + max_bytes, len(file_text))
        end_reason = "max_bytes"
    elif end_policy == "end_of_file":
        end_offset = len(file_text)
        end_reason = "end_of_file"

    # Strip trailing whitespace from window
    window_text = file_text[content_start:end_offset].rstrip("\n\r ")
    # Re-add stripped amounts to recalculate precise end_offset
    stripped = len(file_text[content_start:end_offset]) - len(window_text)
    actual_end_offset = end_offset - stripped

    # Apply max_bytes limit
    window_bytes = window_text.encode("utf-8")
    if len(window_bytes) > max_bytes:
        # Truncate at max_bytes, aligning to UTF-8 boundary
        window_bytes = window_bytes[:max_bytes]
        window_text = window_bytes.decode("utf-8", errors="replace")
        actual_end_offset = content_start + max_bytes
        end_reason = "max_bytes"
        window_bytes = window_text.encode("utf-8")

    # Calculate fingerprint
    fingerprint = "sha256:" + hashlib.sha256(window_bytes).hexdigest()

    if expected_window_fingerprint and fingerprint != expected_window_fingerprint:
        return {
            "schema_version": "core.bounded_read_window.v1",
            "type": "bounded_read_window",
            "index_id": index_id,
            "ref_id": ref_id,
            "path": path_val,
            "start_offset": content_start,
            "end_offset": actual_end_offset,
            "bytes_read": len(window_bytes),
            "window_fingerprint": fingerprint,
            "expected_window_fingerprint": expected_window_fingerprint,
            "status": "failed",
            "error_code": INDEX_DRIFT_DETECTED,
            "error_message": (
                "Computed window fingerprint does not match expected_window_fingerprint."
            ),
            "end_reason": end_reason,
        }

    result = {
        "schema_version": "core.bounded_read_window.v1",
        "type": "bounded_read_window",
        "index_id": index_id,
        "ref_id": ref_id,
        "path": path_val,
        "start_offset": content_start,
        "end_offset": actual_end_offset,
        "bytes_read": len(window_bytes),
        "window_fingerprint": fingerprint,
        "end_reason": end_reason,
    }

    if include_content:
        result["content"] = window_text

    return result


def _error_result(ref_id: str, message: str, code: str, **extra: object) -> dict:
    result = {
        "schema_version": "core.bounded_read_window.v1",
        "type": "bounded_read_window",
        "ref_id": ref_id,
        "status": "failed",
        "error_code": code,
        "error_message": message,
    }
    result.update(extra)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Read a bounded reference from an index.")
    parser.add_argument("index", help="Path to the bounded reference index JSON file.")
    parser.add_argument("ref_id", help="The ref_id to read from the index.")
    parser.add_argument("--include-content", action="store_true",
                        help="Include the read content in the output.")
    args = parser.parse_args()

    result = read_bounded_reference(args.index, args.ref_id, args.include_content)

    print(json.dumps(result, indent=2, sort_keys=False))
    if result.get("status") == "failed":
        sys.exit(1)


if __name__ == "__main__":
    main()
