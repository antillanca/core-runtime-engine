"""CORE v4.1 — Numeric Normalization (QUANTIZATION LAYER).

ALL float values used in fingerprints, hashes, EventLog payloads,
KB facts, projections, replay, and compliance MUST be quantized
before serialization or hashing.

Rationale:
  FFT, MFCC, RMS, filters, and any floating-point computation
  can diverge across CPUs, BLAS, SIMD, compilers, and operation
  ordering. This breaks CORE's fundamental guarantee:
  "same input = same hash".

  Quantization to a fixed decimal precision (default 8) eliminates
  float-induced non-determinism in all hash-producing paths.

  precision=8 means: round(value, 8) → stable across IEEE 754
  implementations for values with up to 8 significant decimal digits.

IMPORTANT:
  - Call quantize_float() BEFORE json.dumps() in any fingerprint/hash
  - Call quantize_vector() for any list[float] before serialization
  - Call quantize_dict() for any dict that may contain nested floats
  - NEVER skip quantization for values entering EventLog, KB, or replay
"""

from __future__ import annotations

import json
from types import MappingProxyType
from typing import Any

# Default precision: 8 decimal digits (sufficient for most engineering values)
DEFAULT_FLOAT_PRECISION = 8


def quantize_float(value: float, precision: int = DEFAULT_FLOAT_PRECISION) -> float:
    """Quantize a single float to a fixed decimal precision.

    This eliminates IEEE 754 representation differences across
    platforms, BLAS implementations, and SIMD configurations.

    Args:
        value: The float to quantize.
        precision: Number of decimal digits to keep.

    Returns:
        The quantized float (rounded to `precision` decimal places).
    """
    return round(float(value), precision)


def quantize_vector(
    values: list[float],
    precision: int = DEFAULT_FLOAT_PRECISION,
) -> list[float]:
    """Quantize a list of floats.

    Args:
        values: List of floats to quantize.
        precision: Number of decimal digits to keep.

    Returns:
        New list with quantized values.
    """
    return [quantize_float(v, precision) for v in values]


def quantize_dict(
    data: dict[str, Any],
    precision: int = DEFAULT_FLOAT_PRECISION,
) -> dict[str, Any]:
    """Recursively quantize all float values in a dict.

    Walks the dict recursively. Any float value (including those
    inside nested dicts or lists) is quantized.

    Args:
        data: Dict that may contain floats at any nesting level.
        precision: Number of decimal digits to keep.

    Returns:
        New dict with all floats quantized.
    """
    return _quantize_value(data, precision)


def _quantize_value(value: Any, precision: int) -> Any:
    """Recursively quantize floats in any nested structure."""
    if isinstance(value, float):
        return quantize_float(value, precision)
    if isinstance(value, (dict, MappingProxyType)):
        return {k: _quantize_value(v, precision) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        quantized = [_quantize_value(item, precision) for item in value]
        return type(value)(quantized)  # type: ignore[call-arg]
    # int, str, bool, None — pass through unchanged
    return value


def quantize_for_hash(data: Any, precision: int = DEFAULT_FLOAT_PRECISION) -> str:
    """Quantize any serializable data and return deterministic JSON string.

    This is the canonical way to prepare data for SHA-256 hashing.
    It quantizes all floats, sorts all keys, and produces a stable
    JSON string regardless of platform or float representation.

    Args:
        data: Any JSON-serializable data (dict, list, etc.).
        precision: Float quantization precision.

    Returns:
        Deterministic JSON string suitable for hashing.
    """
    if isinstance(data, dict):
        quantized = quantize_dict(data, precision)
    elif isinstance(data, (list, tuple)):
        quantized = _quantize_value(data, precision)
    else:
        quantized = _quantize_value(data, precision)
    return json.dumps(quantized, sort_keys=True, default=str)
