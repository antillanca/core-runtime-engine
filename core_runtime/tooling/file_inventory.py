"""File inventory - check presence of required files."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from core_runtime.tooling.diagnostics import DiagnosticCollection


# Required files for CORE tooling
REQUIRED_FILES = [
    "README.md",
    "pyproject.toml",
    "CHANGELOG.md",
    "core_runtime/__version__.py",
    "core_runtime/__init__.py",
    "docs/VERSIONING_POLICY.md",
    "docs/CORE_RELEASE_README.md",
    "docs/REPRODUCIBILITY.md",
    "docs/QUALITY_GATE.md",
    "docs/releases/README.md",
    "scripts/verify_release.py",
    "scripts/check_version_consistency.py",
    "scripts/bump_version.py",
    "scripts/generate_requirements_lock.py",
    "requirements.lock",
    "requirements-dev.txt",
]

# Required directories
REQUIRED_DIRS = [
    "schemas",
    "examples",
    "tests",
    ".github/workflows",
]

# Optional files (created by this implementation)
OPTIONAL_FILES = [
    "docs/CORE_TOOLING.md",
]


class FileInventory:
    """Check presence of required files and directories."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def check_file(self, rel_path: str) -> bool:
        """Check if a file exists."""
        return (self.repo_root / rel_path).is_file()

    def check_dir(self, rel_path: str) -> bool:
        """Check if a directory exists."""
        return (self.repo_root / rel_path).is_dir()

    def check_all(self, diagnostics: DiagnosticCollection) -> dict[str, bool]:
        """Check all required files and directories."""
        results = {}

        # Check required files
        for rel_path in REQUIRED_FILES:
            exists = self.check_file(rel_path)
            results[rel_path] = exists
            if not exists:
                diagnostics.add_error(
                    code="core.file.missing",
                    message="Required file missing: {0}".format(rel_path),
                    path=rel_path,
                    expected="exists",
                    actual="missing",
                )

        # Check required directories
        for rel_path in REQUIRED_DIRS:
            exists = self.check_dir(rel_path)
            results[rel_path] = exists
            if not exists:
                diagnostics.add_error(
                    code="core.dir.missing",
                    message="Required directory missing: {0}".format(rel_path),
                    path=rel_path,
                    expected="exists",
                    actual="missing",
                )

        # Check optional files (just report, don't error)
        for rel_path in OPTIONAL_FILES:
            exists = self.check_file(rel_path)
            results[rel_path] = exists
            if not exists:
                diagnostics.add_info(
                    code="core.file.optional_missing",
                    message="Optional file not yet present: {0}".format(rel_path),
                    path=rel_path,
                    expected="optional",
                    actual="missing",
                )

        return results

    def check_release_note_exists(self, version: str, diagnostics: DiagnosticCollection) -> bool:
        """Check if release note for given version exists."""
        rel_path = "docs/releases/v{0}.md".format(version)
        exists = self.check_file(rel_path)
        if not exists:
            diagnostics.add_error(
                code="core.file.release_note_missing",
                message="Release note for v{0} not found".format(version),
                path=rel_path,
                expected="exists",
                actual="missing",
            )
        return exists