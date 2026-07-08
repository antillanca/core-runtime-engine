"""CORE schema and fingerprint helpers.

These helpers separate three concerns:
- operational_fingerprint: stable for replay and gating
- audit_fingerprint: stable for provenance and human inspection
- schema_fingerprint: stable for schema evolution control
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields, is_dataclass
from typing import Any, get_type_hints

from core_runtime.core.numeric_normalization import quantize_for_hash


def operational_fingerprint(payload: dict[str, Any]) -> str:
    """Fingerprint for replay and determinism gates."""
    canonical = json.dumps(
        quantize_for_hash(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def audit_fingerprint(payload: dict[str, Any]) -> str:
    """Fingerprint for provenance and audit reports."""
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def schema_fingerprint(cls: type[Any]) -> str:
    """Fingerprint the declared schema of a dataclass or typed container."""
    if is_dataclass(cls):
        schema = [
            {
                "name": f.name,
                "type": str(f.type),
                "default": repr(f.default),
                "default_factory": repr(getattr(f, "default_factory", None)),
            }
            for f in fields(cls)
        ]
    else:
        hints = get_type_hints(cls)
        schema = [
            {"name": name, "type": str(tp)}
            for name, tp in sorted(hints.items(), key=lambda item: item[0])
        ]

    canonical = json.dumps(
        schema,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
