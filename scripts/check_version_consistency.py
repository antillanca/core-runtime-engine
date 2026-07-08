#!/usr/bin/env python3
"""Check that all version references in the repository are consistent.

The single source of truth is ``core_runtime/__version__.py``.
This script verifies that all other version references
(pyproject.toml, core_runtime/__init__.py, README.md,
docs/VERSIONING_POLICY.md, CHANGELOG.md, docs/releases/)
match that canonical version.

Exit code 0 = all consistent.
Exit code 1 = inconsistencies detected.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = REPO_ROOT / "core_runtime" / "__version__.py"

VERSION_RE = re.compile(r'(\d+\.\d+\.\d+)')
QUOTED_VERSION_RE = re.compile(r'["\'](\d+\.\d+\.\d+)["\']')


def canonical_version() -> str:
    """Read the canonical version from core_runtime/__version__.py.

    Matches the first <quoted semver> after the first ``__version__`` line.
    """
    text = VERSION_FILE.read_text(encoding="utf-8")
    # Find the __version__ line and read its value
    match = re.search(r'__version__\s*=\s*["\'](\d+\.\d+\.\d+)["\']', text)
    if not match:
        raise RuntimeError(f"Cannot find __version__ in {VERSION_FILE}")
    return match.group(1)


def _first_semver(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text)
    return match.group(1) if match else None


def check_pyproject_version(canon: str) -> list[str]:
    path = REPO_ROOT / "pyproject.toml"
    text = path.read_text(encoding="utf-8")
    errors = []
    match = re.search(r'^version\s*=\s*["\'](\d+\.\d+\.\d+)["\']', text, re.MULTILINE)
    if not match:
        errors.append("pyproject.toml: no version field found")
    elif match.group(1) != canon:
        errors.append(
            f"pyproject.toml version={match.group(1)!r} != canonical {canon!r}"
        )
    return errors


def check_init_version(canon: str) -> list[str]:
    path = REPO_ROOT / "core_runtime" / "__init__.py"
    text = path.read_text(encoding="utf-8")
    errors = []
    if "from core_runtime.__version__ import __version__" in text:
        return errors
    match = re.search(
        r'^__version__\s*=\s*["\'](\d+\.\d+\.\d+)["\']', text, re.MULTILINE
    )
    if not match:
        errors.append(
            "core_runtime/__init__.py has no __version__ and no re-export"
        )
    elif match.group(1) != canon:
        errors.append(
            f"core_runtime/__init__.py version={match.group(1)!r} != canonical {canon!r}"
        )
    return errors


def check_readme_version(canon: str) -> list[str]:
    path = REPO_ROOT / "README.md"
    text = path.read_text(encoding="utf-8")
    errors = []
    matches = re.findall(r"CORE\s+v(\d+\.\d+\.\d+)", text)
    if not matches:
        errors.append("README.md: no 'CORE v<version>' reference found")
    elif canon not in matches:
        errors.append(
            f"README.md: CORE versions {sorted(set(matches))} don't include canonical {canon}"
        )
    return errors


def check_versioning_policy(canon: str) -> list[str]:
    path = REPO_ROOT / "docs" / "VERSIONING_POLICY.md"
    if not path.exists():
        return ["docs/VERSIONING_POLICY.md: missing"]
    text = path.read_text(encoding="utf-8")
    errors = []
    # Match "**Current**: v<version>" or "Current: v<version>"
    match = re.search(r"Current\*\*?:\s*v(\d+\.\d+\.\d+)", text)
    if not match:
        errors.append("docs/VERSIONING_POLICY.md: no 'Current: v<version>' line")
    elif match.group(1) != canon:
        errors.append(
            f"docs/VERSIONING_POLICY.md current=v{match.group(1)} != v{canon}"
        )
    return errors


def check_changelog(canon: str) -> list[str]:
    path = REPO_ROOT / "CHANGELOG.md"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    errors = []
    match = re.search(r"^## v(\d+\.\d+\.\d+)", text, re.MULTILINE)
    if not match:
        errors.append("CHANGELOG.md: no versioned entry found")
    else:
        try:
            latest = tuple(int(x) for x in match.group(1).split("."))
            canon_tuple = tuple(int(x) for x in canon.split("."))
            if latest > canon_tuple:
                errors.append(
                    f"CHANGELOG.md latest=v{match.group(1)} > canonical v{canon}"
                )
        except ValueError:
            pass
    return errors


def main() -> int:
    canon = canonical_version()
    print(f"Canonical version: {canon}")

    all_errors: list[str] = []
    all_errors.extend(check_pyproject_version(canon))
    all_errors.extend(check_init_version(canon))
    all_errors.extend(check_readme_version(canon))
    all_errors.extend(check_versioning_policy(canon))
    all_errors.extend(check_changelog(canon))

    if all_errors:
        print("VERSION INCONSISTENCIES DETECTED:", file=sys.stderr)
        for err in all_errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("All version references are consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
