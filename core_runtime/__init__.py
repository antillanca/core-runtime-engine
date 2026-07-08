"""CORE — deterministic contract, schema and validation engine.

CORE validates artifacts against public contracts: schemas, fingerprints,
manifests and bounded evidence. It never executes domain logic, never
holds private semantics and never decides legal truth.
"""

from core_runtime.__version__ import __version__

__all__ = ["__version__"]
