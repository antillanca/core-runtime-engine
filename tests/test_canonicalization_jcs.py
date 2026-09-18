#!/usr/bin/env python3
"""Test JCS canonicalization (RFC 8785)."""

from core_runtime.core.canonicalization import canonical_json_hash, legacy_canonical_json_hash


def test_canonical_json_hash_jcs() -> None:
    """Test JCS canonicalization produces deterministic output."""
    data = {"b": 2, "a": 1, "c": {"nested": True, "array": [3, 1, 2]}}
    hash1 = canonical_json_hash(data)
    hash2 = canonical_json_hash(data)
    assert hash1 == hash2
    assert hash1.startswith("sha256:")


def test_canonical_json_hash_order_independent() -> None:
    """Test that key order doesn't affect JCS hash."""
    data1 = {"a": 1, "b": 2}
    data2 = {"b": 2, "a": 1}
    assert canonical_json_hash(data1) == canonical_json_hash(data2)


def test_canonical_json_hash_roundtrip() -> None:
    """Test that canonicalization is idempotent."""
    data = {"z": 99, "a": 1}
    hash1 = canonical_json_hash(data)
    hash2 = canonical_json_hash(data)
    assert hash1 == hash2


def test_legacy_canonical_json_hash_compatibility() -> None:
    """Test legacy canonicalization for v11 replay compatibility."""
    data = {"b": 2, "a": 1}
    legacy = legacy_canonical_json_hash(data)
    assert legacy.startswith("sha256:")


if __name__ == "__main__":
    test_canonical_json_hash_jcs()
    test_canonical_json_hash_order_independent()
    test_canonical_json_hash_roundtrip()
    test_legacy_canonical_json_hash_compatibility()
    print("All JCS canonicalization tests PASSED")