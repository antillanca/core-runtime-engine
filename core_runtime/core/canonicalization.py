"""Canonical serialization and ordering helpers.

These helpers centralize the ordering rules used by deterministic
serializers, graph fingerprints, and regression tests.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json_dumps(payload: Any) -> str:
    """Serialize payload with canonical JSON formatting (RFC 8785 / JCS).

    No default=str — callers MUST ensure payload is JSON-serializable.
    Any non-serializable value is a contract violation and raises TypeError.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def canonical_json_hash(payload: Any) -> str:
    """Hash the canonical JSON serialization of a payload.

    Returns: "sha256:<hex>"
    """
    return "sha256:" + hashlib.sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()


def v12_envelope_fingerprint(envelope: dict[str, Any]) -> str:
    """Compute the v12 envelope fingerprint.

    Returns: "v12:<hex>"
    """
    return "v12:" + hashlib.sha256(canonical_json_dumps(envelope).encode("utf-8")).hexdigest()


def canonical_graph_node_key(node: Any) -> tuple[int, str, str]:
    """Return the canonical ordering key for graph nodes."""
    return (
        int(getattr(node, "logical_order", 0)),
        str(getattr(node, "node_type", "")),
        str(getattr(node, "node_id", "")),
    )


def canonical_graph_edge_key(edge: Any) -> tuple[str, str, str]:
    """Return the canonical ordering key for graph edges."""
    return (
        str(getattr(edge, "source_id", "")),
        str(getattr(edge, "target_id", "")),
        str(getattr(edge, "edge_type", "flow")),
    )


def canonical_graph_nodes(nodes: list[Any] | tuple[Any, ...]) -> list[Any]:
    """Return nodes ordered canonically."""
    return sorted(nodes, key=canonical_graph_node_key)


def canonical_graph_edges(edges: list[Any] | tuple[Any, ...]) -> list[Any]:
    """Return edges ordered canonically."""
    return sorted(edges, key=canonical_graph_edge_key)


def legacy_canonical_json_dumps(payload: Any) -> str:
    """Legacy canonical JSON serialization (v11 compatible).

    Uses default=str to match historical v11 canonicalization behavior.
    Only for replay certification of frozen reference datasets.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def legacy_canonical_json_hash(payload: Any) -> str:
    """Legacy canonical JSON hash (v11 compatible).

    Returns: "sha256:<hex>"
    """
    return "sha256:" + hashlib.sha256(legacy_canonical_json_dumps(payload).encode("utf-8")).hexdigest()