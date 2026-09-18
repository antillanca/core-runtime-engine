"""JSON parse checks - validate JSON files parse correctly."""

from __future__ import annotations

import json
from pathlib import Path

from core_runtime.tooling.diagnostics import DiagnosticCollection


class JSONChecks:
    """Check that JSON files parse correctly."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def check_schemas(self, diagnostics: DiagnosticCollection) -> tuple[int, int]:
        """Check all schema JSON files."""
        schemas_dir = self.repo_root / "schemas"
        if not schemas_dir.is_dir():
            diagnostics.add_blocked(
                code="core.json.schemas_dir_missing",
                message="schemas/ directory not found",
                path="schemas/",
            )
            return 0, 0

        checked = 0
        errors = 0
        for json_file in schemas_dir.glob("*.json"):
            checked += 1
            if not self._check_json_file(json_file, diagnostics, "schemas"):
                errors += 1
        return checked, errors

    def check_examples(self, diagnostics: DiagnosticCollection) -> tuple[int, int]:
        """Check example JSON files."""
        examples_dir = self.repo_root / "examples"
        if not examples_dir.is_dir():
            diagnostics.add_blocked(
                code="core.json.examples_dir_missing",
                message="examples/ directory not found",
                path="examples/",
            )
            return 0, 0

        checked = 0
        errors = 0
        # Limit to avoid very long runs; focus on key areas
        for json_file in examples_dir.rglob("*.json"):
            # Skip some large generated directories
            rel = json_file.relative_to(self.repo_root)
            if any(skip in str(rel) for skip in [".pycache", "core_protocol_model/candidate_outputs_v1", "core_protocol_model/model_artifacts_v1"]):
                continue
            checked += 1
            if not self._check_json_file(json_file, diagnostics, "examples"):
                errors += 1
        return checked, errors

    def _check_json_file(self, json_file: Path, diagnostics: DiagnosticCollection, category: str) -> bool:
        """Check a single JSON file. Returns True if valid."""
        try:
            with json_file.open("r", encoding="utf-8") as f:
                json.load(f)
            return True
        except json.JSONDecodeError as e:
            rel = json_file.relative_to(self.repo_root)
            diagnostics.add_error(
                code="core.json.invalid",
                message="Invalid JSON in {0}: {1}".format(rel, e.msg),
                path=str(rel),
                details="line {0}, column {1}: {2}".format(e.lineno, e.colno, e.msg),
            )
            return False
        except OSError as e:
            rel = json_file.relative_to(self.repo_root)
            diagnostics.add_error(
                code="core.json.unreadable",
                message="Cannot read JSON file {0}: {1}".format(rel, e),
                path=str(rel),
            )
            return False

    def check_requirements_lock(self, diagnostics: DiagnosticCollection) -> bool:
        """Check requirements.lock is valid JSON (if it is JSON)."""
        lock_file = self.repo_root / "requirements.lock"
        if not lock_file.exists():
            return False
        # requirements.lock is a pip lockfile (text), not JSON
        # We just check it's readable
        try:
            lock_file.read_text(encoding="utf-8")
            return True
        except OSError as e:
            diagnostics.add_error(
                code="core.file.unreadable",
                message="Cannot read requirements.lock: {0}".format(e),
                path="requirements.lock",
            )
            return False