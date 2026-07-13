"""Version inventory - discover and compare all version references in the repository."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from core_runtime.tooling.diagnostics import DiagnosticCollection


@dataclass
class VersionSource:
    """A single version source file and its extracted version."""

    name: str
    path: Path
    version: Optional[str]
    pattern: str
    is_canonical: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "path": str(self.path),
            "version": self.version,
            "is_canonical": self.is_canonical,
        }


class VersionInventory:
    """Discover and compare all version references across the repository."""

    # Canonical version patterns for each file
    VERSION_PATTERNS = {
        "core_runtime/__version__.py": (
            r'__version__\s*=\s*["\'](\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?)["\']',
            True,  # is_canonical
        ),
        "pyproject.toml": (
            r'^version\s*=\s*["\'](\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?)["\']',
            False,
        ),
        "core_runtime/__init__.py": (
            r'from core_runtime\.__version__ import __version__',
            False,  # re-export, no inline version
        ),
        "README.md": (
            r"CORE\s+v(\d+\.\d+\.\d+)",
            False,
        ),
        "docs/VERSIONING_POLICY.md": (
            r"Current\*?\*?:\s*v(\d+\.\d+\.\d+)",
            False,
        ),
        "CHANGELOG.md": (
            r"^##\s+v(\d+\.\d+\.\d+)",
            False,
        ),
        "docs/CORE_RELEASE_README.md": (
            r"CORE:\s*v(\d+\.\d+\.\d+)",
            False,
        ),
    }

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def extract_version(self, file_path: Path, pattern: str) -> Optional[str]:
        """Extract version from file using regex pattern."""
        try:
            text = file_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError:
            return None

        match = re.search(pattern, text, re.MULTILINE)
        if match:
            return match.group(1)
        return None

    def check_init_reexport(self, file_path: Path) -> bool:
        """Check if __init__.py correctly re-exports from __version__."""
        try:
            text = file_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return False
        except OSError:
            return False

        return "from core_runtime.__version__ import __version__" in text

    def discover(self) -> list[VersionSource]:
        """Discover all version sources in the repository."""
        sources = []

        for rel_path, (pattern, is_canonical) in self.VERSION_PATTERNS.items():
            full_path = self.repo_root / rel_path

            if rel_path == "core_runtime/__init__.py":
                # Special case: check re-export
                has_reexport = self.check_init_reexport(full_path)
                sources.append(VersionSource(
                    name=rel_path,
                    path=full_path,
                    version="re-export" if has_reexport else None,
                    pattern="re-export check",
                    is_canonical=is_canonical,
                ))
            else:
                version = self.extract_version(full_path, pattern)
                sources.append(VersionSource(
                    name=rel_path,
                    path=full_path,
                    version=version,
                    pattern=pattern,
                    is_canonical=is_canonical,
                ))

        return sources

    def get_canonical_version(self) -> Optional[str]:
        """Get the canonical version from __version__.py."""
        for source in self.discover():
            if source.is_canonical:
                return source.version
        return None

    def check_consistency(self, diagnostics: DiagnosticCollection) -> list[VersionSource]:
        """Check version consistency across all sources."""
        sources = self.discover()
        canonical = self.get_canonical_version()

        if not canonical:
            diagnostics.add_blocked(
                code="core.version.canonical_missing",
                message="Cannot determine canonical version from core_runtime/__version__.py",
                path="core_runtime/__version__.py",
            )
            return sources

        for source in sources:
            if source.is_canonical:
                continue

            if source.name == "core_runtime/__init__.py":
                # Check re-export
                if source.version != "re-export":
                    diagnostics.add_error(
                        code="core.version.init_not_reexporting",
                        message="core_runtime/__init__.py does not re-export from __version__",
                        path=str(source.path.relative_to(self.repo_root)),
                        expected="re-export",
                        actual="inline or missing",
                    )
                continue

            if source.version is None:
                # File missing or pattern not found
                diagnostics.add_error(
                    code="core.version.missing",
                    message="Version reference not found in {0}".format(source.name),
                    path=str(source.path.relative_to(self.repo_root)),
                    expected=canonical,
                    actual="not found",
                )
                continue

            if source.version != canonical:
                # Version mismatch
                diagnostics.add_error(
                    code="core.version.inconsistent",
                    message="Version mismatch in {0}: expected {1}, found {2}".format(
                        source.name, canonical, source.version
                    ),
                    path=str(source.path.relative_to(self.repo_root)),
                    expected=canonical,
                    actual=source.version,
                )

        return sources

    def check_changelog_latest(self, diagnostics: DiagnosticCollection) -> None:
        """Check that CHANGELOG.md latest entry matches canonical version."""
        canonical = self.get_canonical_version()
        if not canonical:
            return

        changelog_path = self.repo_root / "CHANGELOG.md"
        try:
            text = changelog_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            diagnostics.add_error(
                code="core.version.changelog_missing",
                message="CHANGELOG.md not found",
                path="CHANGELOG.md",
            )
            return
        except OSError:
            return

        # Find first versioned entry
        match = re.search(r"^##\s+v(\d+\.\d+\.\d+)", text, re.MULTILINE)
        if not match:
            diagnostics.add_warning(
                code="core.version.changelog_no_entry",
                message="No versioned entry found in CHANGELOG.md",
                path="CHANGELOG.md",
            )
            return

        latest = match.group(1)
        try:
            latest_tuple = tuple(int(x) for x in latest.split("."))
            canon_tuple = tuple(int(x) for x in canonical.split("."))
            if latest_tuple > canon_tuple:
                diagnostics.add_error(
                    code="core.version.changelog_ahead",
                    message="CHANGELOG.md latest entry ({0}) is ahead of canonical version ({1})".format(
                        latest, canonical
                    ),
                    path="CHANGELOG.md",
                    expected=canonical,
                    actual=latest,
                )
            elif latest_tuple < canon_tuple:
                diagnostics.add_warning(
                    code="core.version.changelog_behind",
                    message="CHANGELOG.md latest entry ({0}) is behind canonical version ({1})".format(
                        latest, canonical
                    ),
                    path="CHANGELOG.md",
                    expected=canonical,
                    actual=latest,
                )
        except ValueError:
            pass

    def check_release_note(self, diagnostics: DiagnosticCollection) -> None:
        """Check that release note for current version exists."""
        canonical = self.get_canonical_version()
        if not canonical:
            return

        release_path = self.repo_root / "docs" / "releases" / "v{0}.md".format(canonical)
        if not release_path.exists():
            diagnostics.add_error(
                code="core.version.release_note_missing",
                message="Release note for v{0} not found at docs/releases/v{0}.md".format(canonical),
                path="docs/releases/v{0}.md".format(canonical),
                expected="exists",
                actual="missing",
            )