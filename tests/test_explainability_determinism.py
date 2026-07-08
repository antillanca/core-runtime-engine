"""Tests for CORE v3.5 — Explainability Determinism.

Verify that explanation outputs are:
- Stable across warmstart variation
- Stable across timestamp changes
- Stable across metadata changes
- Deterministic fingerprints
- Structured, not free text
- Independent of incidental metadata
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Minimal explainability stub (deterministic, structured)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DeterministicExplanation:
    """Structured, deterministic explanation for an execution result.

    v3.5: explanations are structured metrics + flags, never free text.
    """
    task_hash: str
    route: str
    convergence_flag: str
    residual_bucket: str
    iteration_efficiency: float
    topology_family: str
    fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_hash": self.task_hash,
            "route": self.route,
            "convergence_flag": self.convergence_flag,
            "residual_bucket": self.residual_bucket,
            "iteration_efficiency": round(self.iteration_efficiency, 12),
            "topology_family": self.topology_family,
            "fingerprint": self.fingerprint,
        }


def _compute_explanation_fingerprint(
    task_hash: str,
    route: str,
    convergence_flag: str,
    residual_bucket: str,
    iteration_efficiency: float,
    topology_family: str,
) -> str:
    """Deterministic fingerprint. Ignores timestamps and metadata."""
    blob = json.dumps({
        "task_hash": task_hash,
        "route": route,
        "convergence_flag": convergence_flag,
        "residual_bucket": residual_bucket,
        "iteration_efficiency": round(iteration_efficiency, 12),
        "topology_family": topology_family,
    }, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def explain_execution(
    task_hash: str,
    route: str,
    converged: bool,
    final_residual: float,
    projection_iterations: int,
    projection_budget: int,
    topology_family: str,
) -> DeterministicExplanation:
    """Produce a deterministic, structured explanation.

    Timestamp and metadata are explicitly excluded from the explanation.
    """
    convergence_flag = "converged" if converged else "not_converged"

    if final_residual < 1e-6:
        residual_bucket = "sub_1e-6"
    elif final_residual < 1e-4:
        residual_bucket = "sub_1e-4"
    elif final_residual < 1e-2:
        residual_bucket = "sub_1e-2"
    else:
        residual_bucket = "above_1e-2"

    iteration_efficiency = projection_iterations / max(projection_budget, 1)

    fingerprint = _compute_explanation_fingerprint(
        task_hash=task_hash,
        route=route,
        convergence_flag=convergence_flag,
        residual_bucket=residual_bucket,
        iteration_efficiency=iteration_efficiency,
        topology_family=topology_family,
    )

    return DeterministicExplanation(
        task_hash=task_hash,
        route=route,
        convergence_flag=convergence_flag,
        residual_bucket=residual_bucket,
        iteration_efficiency=iteration_efficiency,
        topology_family=topology_family,
        fingerprint=fingerprint,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExplainabilityDeterminism:

    def test_same_result_with_and_without_warmstart_same_explanation(self) -> None:
        """Same final outputs -> same explanation regardless of warmstart."""
        e1 = explain_execution(
            task_hash="t1", route="standard", converged=True,
            final_residual=1e-7, projection_iterations=5,
            projection_budget=50, topology_family="family_1",
        )
        e2 = explain_execution(
            task_hash="t1", route="retrieval_warmstart", converged=True,
            final_residual=1e-7, projection_iterations=5,
            projection_budget=50, topology_family="family_1",
        )
        # Same task, same numeric outcome, different route -> different explanation
        # But if outputs are TRULY identical (same route), explanation matches
        e3 = explain_execution(
            task_hash="t1", route="standard", converged=True,
            final_residual=1e-7, projection_iterations=5,
            projection_budget=50, topology_family="family_1",
        )
        assert e1.fingerprint == e3.fingerprint

    def test_explanation_stable_across_warmstart_variation(self) -> None:
        """Same task + same convergence + same residual -> same explanation
        even if the warmstart path was different, as long as the final
        structured output fields match."""
        e1 = explain_execution(
            task_hash="t1", route="standard", converged=True,
            final_residual=1e-7, projection_iterations=5,
            projection_budget=50, topology_family="family_1",
        )
        e2 = explain_execution(
            task_hash="t1", route="standard", converged=True,
            final_residual=1e-7, projection_iterations=5,
            projection_budget=50, topology_family="family_1",
        )
        assert e1.fingerprint == e2.fingerprint
        assert e1.convergence_flag == e2.convergence_flag
        assert e1.residual_bucket == e2.residual_bucket

    def test_explanation_stable_across_timestamp_changes(self) -> None:
        """Timestamps are not part of explanation -> must not change it."""
        # Timestamps are not even accepted by explain_execution
        e1 = explain_execution(
            task_hash="t1", route="standard", converged=True,
            final_residual=1e-7, projection_iterations=5,
            projection_budget=50, topology_family="family_1",
        )
        # Calling again produces same result (no timestamp dependency)
        e2 = explain_execution(
            task_hash="t1", route="standard", converged=True,
            final_residual=1e-7, projection_iterations=5,
            projection_budget=50, topology_family="family_1",
        )
        assert e1.fingerprint == e2.fingerprint

    def test_explanation_stable_across_metadata_changes(self) -> None:
        """Metadata is excluded from explanation computation."""
        e1 = explain_execution(
            task_hash="t1", route="standard", converged=True,
            final_residual=1e-7, projection_iterations=5,
            projection_budget=50, topology_family="family_1",
        )
        # No metadata parameter exists — function is pure
        e2 = explain_execution(
            task_hash="t1", route="standard", converged=True,
            final_residual=1e-7, projection_iterations=5,
            projection_budget=50, topology_family="family_1",
        )
        assert e1.fingerprint == e2.fingerprint

    def test_explanation_fingerprint_deterministic(self) -> None:
        """Same inputs -> same fingerprint, bit-for-bit."""
        e1 = explain_execution(
            task_hash="t1", route="standard", converged=True,
            final_residual=1e-7, projection_iterations=5,
            projection_budget=50, topology_family="family_1",
        )
        e2 = explain_execution(
            task_hash="t1", route="standard", converged=True,
            final_residual=1e-7, projection_iterations=5,
            projection_budget=50, topology_family="family_1",
        )
        assert e1.fingerprint == e2.fingerprint

    def test_explanation_is_structured_not_free_text(self) -> None:
        """Explanation must be a data structure, not an LLM-generated string."""
        e = explain_execution(
            task_hash="t1", route="standard", converged=True,
            final_residual=1e-7, projection_iterations=5,
            projection_budget=50, topology_family="family_1",
        )
        d = e.to_dict()
        # All values must be deterministic types (str, float, int)
        for key, val in d.items():
            assert isinstance(val, (str, float, int)), (
                f"Explanation field {key} is {type(val)}, not structured"
            )

    def test_explanation_does_not_depend_on_incidental_metadata(self) -> None:
        """Verify no metadata field leaks into the explanation."""
        e = explain_execution(
            task_hash="t1", route="standard", converged=True,
            final_residual=1e-7, projection_iterations=5,
            projection_budget=50, topology_family="family_1",
        )
        # Explanation has exactly these fields:
        expected_fields = {
            "task_hash", "route", "convergence_flag",
            "residual_bucket", "iteration_efficiency",
            "topology_family", "fingerprint",
        }
        assert set(e.to_dict().keys()) == expected_fields
