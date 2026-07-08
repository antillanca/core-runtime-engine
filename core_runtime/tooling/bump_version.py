"""Bump-version planner and controlled mutation engine.

Slice 2: dry-run planner — compute proposed changes without mutation.
Slice 3: controlled mutation — apply version bump with safety flags.

Reuses version extraction patterns from VersionInventory to discover
current versions across the repository, then computes the exact text
replacements that would be performed by a real version bump.

Dry-run mode never writes files. Apply mode writes files only after
all validation passes, using transactional semantics.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from core_runtime.tooling.diagnostics import DiagnosticCollection, ExitCode, Severity
from core_runtime.tooling.version_inventory import VersionInventory

# ---------------------------------------------------------------------------
# SemVer validation (CORE format: MAJOR.MINOR.PATCH, no pre-release tags)
# ---------------------------------------------------------------------------
_SEMVER_CORE_RE = re.compile(r"^\d+\.\d+\.\d+$")


def validate_target_version(version: str) -> Optional[str]:
    """Return None if *version* is valid, otherwise an error message.

    CORE accepts only strict MAJOR.MINOR.PATCH — no leading ``v``, no
    pre-release suffixes, no missing components.
    """
    if not _SEMVER_CORE_RE.match(version):
        return (
            "Invalid version format: '{0}'. "
            "Expected MAJOR.MINOR.PATCH (e.g. 10.5.1). "
            "No leading 'v', no pre-release suffixes, no missing components.".format(version)
        )
    return None


def parse_version_tuple(version: str) -> tuple[int, int, int]:
    """Parse a MAJOR.MINOR.PATCH string into a comparable tuple."""
    parts = version.split(".")
    return (int(parts[0]), int(parts[1]), int(parts[2]))


def check_version_movement(current: str, target: str, diagnostics: DiagnosticCollection) -> bool:
    """Return True if target > current, otherwise add a blocked diagnostic and return False."""
    current_t = parse_version_tuple(current)
    target_t = parse_version_tuple(target)
    if target_t == current_t:
        diagnostics.add_blocked(
            code="core.bump_version.target_not_greater",
            message="Target version must be greater than current version.",
            path="target_version",
            expected="> {0}".format(current),
            actual=target,
        )
        return False
    if target_t < current_t:
        diagnostics.add_blocked(
            code="core.bump_version.target_not_greater",
            message="Target version must be greater than current version.",
            path="target_version",
            expected="> {0}".format(current),
            actual=target,
        )
        return False
    return True


# ---------------------------------------------------------------------------
# Approved mutation file set (Slice 3 allowlist)
# ---------------------------------------------------------------------------
APPROVED_MUTATION_FILES: set[str] = {
    "core_runtime/__version__.py",
    "pyproject.toml",
    "core_runtime/__init__.py",   # included via replacement rules
    "README.md",
    "docs/VERSIONING_POLICY.md",
    "docs/CORE_RELEASE_README.md",
    "CHANGELOG.md",
    "docs/releases/README.md",
}


# ---------------------------------------------------------------------------
# File change description
# ---------------------------------------------------------------------------
@dataclass
class PlannedChange:
    """A single file that would be changed by a version bump."""

    path: str
    would_change: bool
    replacement_count: int = 0
    details: str = ""

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "would_change": self.would_change,
            "replacement_count": self.replacement_count,
        }


# ---------------------------------------------------------------------------
# Applied change description (for apply report — mutable files)
# ---------------------------------------------------------------------------
@dataclass
class AppliedChange:
    """A single file that was changed by a version bump apply."""

    path: str
    changed: bool
    replacement_count: int = 0

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "changed": self.changed,
            "replacement_count": self.replacement_count,
        }


# ---------------------------------------------------------------------------
# Replacement rule — describes one regex → substitution
# ---------------------------------------------------------------------------
@dataclass
class ReplacementRule:
    """A regex-pattern + replacement pair for a single file."""

    file_rel: str
    pattern: str
    replacement_template: str  # use {old} and {new} placeholders

    def compute_replacement(self, text: str, old_version: str, new_version: str) -> tuple[int, str]:
        """Apply the replacement to *text*, returning (count, new_text)."""
        repl = self.replacement_template.format(old=old_version, new=new_version)
        new_text, count = re.subn(self.pattern, repl, text, flags=re.MULTILINE)
        return count, new_text


# ---------------------------------------------------------------------------
# BumpVersionPlanner — the main dry-run + apply engine
# ---------------------------------------------------------------------------
# Files and their replacement rules.
# Each rule is (file_rel, regex_pattern, replacement_template).
# {old} = current version, {new} = target version in the template.

DEFAULT_REPLACEMENT_RULES: list[ReplacementRule] = [
    # core_runtime/__version__.py — __version__ = "X.Y.Z"
    ReplacementRule(
        file_rel="core_runtime/__version__.py",
        pattern=r'^__version__\s*=\s*["\']\d+\.\d+\.\d+["\']',
        replacement_template='__version__ = "{new}"',
    ),
    # core_runtime/__version__.py — CORE_VERSION = "X.Y.Z"
    ReplacementRule(
        file_rel="core_runtime/__version__.py",
        pattern=r'^CORE_VERSION\s*=\s*["\']\d+\.\d+\.\d+["\']',
        replacement_template='CORE_VERSION = "{new}"',
    ),
    # pyproject.toml — version = "X.Y.Z"
    ReplacementRule(
        file_rel="pyproject.toml",
        pattern=r'^version\s*=\s*["\']\d+\.\d+\.\d+["\']',
        replacement_template='version = "{new}"',
    ),
    # core_runtime/__init__.py — Version: X.Y.Z  (docstring line)
    ReplacementRule(
        file_rel="core_runtime/__init__.py",
        pattern=r"^Version:\s*\d+\.\d+\.\d+",
        replacement_template="Version: {new}",
    ),
    # README.md — **Current version**: CORE vX.Y.Z
    ReplacementRule(
        file_rel="README.md",
        pattern=r"(\*\*Current version\*\*:\s*CORE\s+v)\d+\.\d+\.\d+",
        replacement_template=r"\g<1>{new}",
    ),
    # docs/VERSIONING_POLICY.md — **Current**: vX.Y.Z
    ReplacementRule(
        file_rel="docs/VERSIONING_POLICY.md",
        pattern=r"(\*\*Current\*\*:\s*v)\d+\.\d+\.\d+",
        replacement_template=r"\g<1>{new}",
    ),
    # docs/VERSIONING_POLICY.md — Current: vX.Y.Z  (alternate form)
    ReplacementRule(
        file_rel="docs/VERSIONING_POLICY.md",
        pattern=r"(Current\s*:\s*v)\d+\.\d+\.\d+",
        replacement_template=r"\g<1>{new}",
    ),
    # docs/VERSIONING_POLICY.md — CORE stable releases: `vX.Y.Z`
    ReplacementRule(
        file_rel="docs/VERSIONING_POLICY.md",
        pattern=r"(CORE\s+stable\s+releases:\s*`v)\d+\.\d+\.\d+(`)",
        replacement_template=r"\g<1>{new}\2",
    ),
    # CHANGELOG.md — ## vX.Y.Z  (latest entry heading) — only matches FIRST heading
    ReplacementRule(
        file_rel="CHANGELOG.md",
        pattern=r"^(##\s+v)\d+\.\d+\.\d+",
        replacement_template=r"\g<1>{new}",
    ),
    # docs/CORE_RELEASE_README.md — CORE: vX.Y.Z
    ReplacementRule(
        file_rel="docs/CORE_RELEASE_README.md",
        pattern=r"(CORE:\s*v)\d+\.\d+\.\d+",
        replacement_template=r"\g<1>{new}",
    ),
]


class BumpVersionPlanner:
    """Compute, report, and apply version bumps with controlled mutation."""

    # Files that must be inspected even if no replacement rule matches
    # (they are listed in the plan as "would be inspected").
    INSPECT_ONLY_FILES: list[str] = [
        "docs/releases/",
    ]

    def __init__(
        self,
        repo_root: Path,
        rules: Optional[list[ReplacementRule]] = None,
    ):
        self.repo_root = repo_root
        self.rules = rules if rules is not None else DEFAULT_REPLACEMENT_RULES
        self._version_inv = VersionInventory(repo_root)

    # ---- public API -------------------------------------------------------

    def plan(
        self,
        target_version: str,
        diagnostics: DiagnosticCollection,
    ) -> tuple[list[PlannedChange], dict]:
        """Compute the dry-run plan for bumping from current to *target_version*.

        Returns (changes, summary).
        """
        # 1. Validate target version
        err = validate_target_version(target_version)
        if err:
            diagnostics.add_blocked(
                code="core.bump_version.invalid_target",
                message=err,
                path="target_version",
                actual=target_version,
            )
            return [], {}

        # 2. Discover current canonical version
        current_version = self._version_inv.get_canonical_version()
        if current_version is None:
            diagnostics.add_blocked(
                code="core.bump_version.canonical_missing",
                message="Cannot determine current canonical version from core_runtime/__version__.py",
                path="core_runtime/__version__.py",
            )
            return [], {}

        # 3. Verify consistency via Slice 1 logic
        self._version_inv.check_consistency(diagnostics)
        if diagnostics.has_blocked():
            diagnostics.add_blocked(
                code="core.bump_version.version_inconsistent",
                message="Version consistency check failed — cannot proceed with dry-run",
                path="core_runtime/__version__.py",
                expected=target_version,
                actual="inconsistent",
            )
            return [], {}

        # 4. Compute replacements per file
        changes = self._compute_file_changes(current_version, target_version, diagnostics)

        # 5. Build summary
        files_checked = len(changes)
        files_that_would_change = sum(1 for c in changes if c.would_change)
        total_replacements = sum(c.replacement_count for c in changes)
        counts = diagnostics.count_by_severity()

        summary = {
            "files_checked": files_checked,
            "files_that_would_change": files_that_would_change,
            "replacement_count": total_replacements,
            "info": counts.get("info", 0),
            "warning": counts.get("warning", 0),
            "error": counts.get("error", 0),
            "blocked": counts.get("blocked", 0),
        }

        return changes, summary

    def apply(
        self,
        target_version: str,
        confirm_current: str,
        diagnostics: DiagnosticCollection,
    ) -> tuple[list[AppliedChange], dict]:
        """Apply the version bump from current to *target_version*.

        Requires *confirm_current* to match the canonical version.
        Performs transactional mutation with safety checks.

        Returns (applied_changes, summary).
        """
        # 1. Validate target version format
        err = validate_target_version(target_version)
        if err:
            diagnostics.add_blocked(
                code="core.bump_version.invalid_target",
                message=err,
                path="target_version",
                actual=target_version,
            )
            return [], {}

        # 2. Discover current canonical version
        current_version = self._version_inv.get_canonical_version()
        if current_version is None:
            diagnostics.add_blocked(
                code="core.bump_version.canonical_missing",
                message="Cannot determine current canonical version from core_runtime/__version__.py",
                path="core_runtime/__version__.py",
            )
            return [], {}

        # 3. Confirm current version matches
        if confirm_current != current_version:
            diagnostics.add_blocked(
                code="core.bump_version.confirm_current_mismatch",
                message="--confirm-current value does not match the canonical version.",
                path="core_runtime/__version__.py",
                expected=current_version,
                actual=confirm_current,
            )
            return [], {}

        # 4. Verify version consistency
        self._version_inv.check_consistency(diagnostics)
        if diagnostics.has_blocked():
            diagnostics.add_blocked(
                code="core.bump_version.version_inconsistent",
                message="Version consistency check failed — cannot proceed with apply",
                path="core_runtime/__version__.py",
                expected=target_version,
                actual="inconsistent",
            )
            return [], {}

        # 5. Check version movement (target > current)
        if not check_version_movement(current_version, target_version, diagnostics):
            return [], {}

        # 6. Git safety check — version-bearing files must be clean
        self._check_git_safety(diagnostics)
        if diagnostics.has_blocked():
            return [], {}

        # 7. Compute all new file contents in memory (transactional step)
        try:
            new_contents = self._compute_new_contents(current_version, target_version, diagnostics)
        except Exception as exc:
            diagnostics.add_blocked(
                code="core.bump_version.internal_error",
                message="Failed to compute new file contents: {0}".format(exc),
                path="internal",
            )
            return [], {}

        if diagnostics.has_blocked():
            return [], {}

        # 8. Check allowlist — all files in new_contents must be approved
        for file_rel in new_contents:
            if file_rel not in APPROVED_MUTATION_FILES:
                diagnostics.add_blocked(
                    code="core.bump_version.file_not_in_allowlist",
                    message="File is not in the approved mutation allowlist: {0}".format(file_rel),
                    path=file_rel,
                )
                return [], {}

        # 9. Write files (transactional — only after all validations pass)
        written_files: list[str] = []
        try:
            for file_rel, new_text in new_contents.items():
                full_path = self.repo_root / file_rel
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(new_text, encoding="utf-8")
                written_files.append(file_rel)
        except Exception as exc:
            # Partial mutation — report blocked and list touched files
            diagnostics.add_blocked(
                code="core.bump_version.internal_error",
                message="Partial mutation: write failed. Touched files: {0}".format(
                    ", ".join(written_files)
                ),
                path="internal",
            )
            return [], {}

        # 10. Create release note for target version (preferred path)
        release_note_path = self.repo_root / "docs" / "releases" / "v{0}.md".format(target_version)
        if not release_note_path.exists():
            self._create_release_note(target_version, release_note_path)
            written_files.append("docs/releases/v{0}.md".format(target_version))

        # 11. docs/releases/README.md already mutated in new_contents (compute-time).
        # No post-write pass here — see _compute_new_contents for the regex.

        # 12. Re-read changed files and build applied changes report
        applied: list[AppliedChange] = []
        for file_rel, new_text in new_contents.items():
            full_path = self.repo_root / file_rel
            if full_path.exists():
                after = full_path.read_text(encoding="utf-8")
                repl_count = after.count(target_version)
                applied.append(AppliedChange(
                    path=file_rel,
                    changed=True,
                    replacement_count=repl_count if repl_count > 0 else 1,
                ))
            else:
                applied.append(AppliedChange(
                    path=file_rel,
                    changed=False,
                    replacement_count=0,
                ))

        # 13. Re-run version inventory to verify consistency
        post_inv = VersionInventory(self.repo_root)
        post_diagnostics = DiagnosticCollection()
        post_inv.check_consistency(post_diagnostics)
        if post_diagnostics.has_errors() or post_diagnostics.has_blocked():
            for d in post_diagnostics.diagnostics:
                diagnostics.add_error(
                    code=d.code,
                    message="[post-apply] {0}".format(d.message),
                    path=d.path,
                )

        # Build summary
        files_changed = sum(1 for a in applied if a.changed)
        total_replacements = sum(a.replacement_count for a in applied)
        counts = diagnostics.count_by_severity()

        summary = {
            "files_checked": len(applied),
            "files_changed": files_changed,
            "replacement_count": total_replacements,
            "info": counts.get("info", 0),
            "warning": counts.get("warning", 0),
            "error": counts.get("error", 0),
            "blocked": counts.get("blocked", 0),
        }

        return applied, summary

    def report_json(
        self,
        target_version: str,
        current_version: str,
        changes: list[PlannedChange],
        summary: dict,
        diagnostics: DiagnosticCollection,
        output_path: Optional[Path] = None,
        *,
        mode: str = "dry-run",
        mutation_performed: bool = False,
        applied_changes: Optional[list[AppliedChange]] = None,
    ) -> dict:
        """Build the JSON report dict and optionally write to *output_path*."""
        exit_code = diagnostics.compute_exit_code()
        status_map = {
            ExitCode.OK: "pass",
            ExitCode.ERROR: "error",
            ExitCode.BLOCKED: "blocked",
            ExitCode.INTERNAL_ERROR: "internal_error",
        }

        change_key = "files_that_would_change" if mode == "dry-run" else "files_changed"
        report = {
            "tool": "core-runtime bump-version",
            "mode": mode,
            "status": status_map.get(exit_code, "internal_error"),
            "mutation_performed": mutation_performed,
            "current_version": current_version,
            "target_version": target_version,
            "summary": summary,
            "changes": [],
            "diagnostics": [d.to_dict() for d in diagnostics.diagnostics],
        }

        if applied_changes is not None:
            report["changes"] = [c.to_dict() for c in applied_changes]
        else:
            report["changes"] = [c.to_dict() for c in changes]

        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

        return report

    def report_markdown(
        self,
        target_version: str,
        current_version: str,
        changes: list[PlannedChange],
        summary: dict,
        diagnostics: DiagnosticCollection,
        output_path: Optional[Path] = None,
        *,
        mode: str = "dry-run",
        mutation_performed: bool = False,
        applied_changes: Optional[list[AppliedChange]] = None,
    ) -> str:
        """Build the Markdown report and optionally write to *output_path*."""
        exit_code = diagnostics.compute_exit_code()
        status_map = {
            ExitCode.OK: "PASS",
            ExitCode.ERROR: "ERROR",
            ExitCode.BLOCKED: "BLOCKED",
            ExitCode.INTERNAL_ERROR: "INTERNAL_ERROR",
        }
        status_label = status_map.get(exit_code, "UNKNOWN")

        title = "# CORE bump-version apply report" if mode == "apply" else "# CORE bump-version dry-run"

        lines: list[str] = []
        lines.append(title)
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        if mode == "apply":
            lines.append("- Files checked: {0}".format(summary.get("files_checked", 0)))
            lines.append("- Files changed: {0}".format(summary.get("files_changed", 0)))
        else:
            lines.append("- Files checked: {0}".format(summary.get("files_checked", 0)))
            lines.append("- Files that would change: {0}".format(summary.get("files_that_would_change", 0)))
        lines.append("- Total replacements: {0}".format(summary.get("replacement_count", 0)))
        lines.append("- Diagnostics: {0} info, {1} warning, {2} error, {3} blocked".format(
            summary.get("info", 0),
            summary.get("warning", 0),
            summary.get("error", 0),
            summary.get("blocked", 0),
        ))
        lines.append("")

        lines.append("## Current Version")
        lines.append("")
        lines.append("`{0}`".format(current_version))
        lines.append("")

        lines.append("## Target Version")
        lines.append("")
        lines.append("`{0}`".format(target_version))
        lines.append("")

        if applied_changes is not None:
            lines.append("## Files Changed")
            lines.append("")
            if applied_changes:
                lines.append("| File | Changed | Replacements |")
                lines.append("| --- | --- | --- |")
                for c in applied_changes:
                    ch = "Yes" if c.changed else "No"
                    lines.append("| {0} | {1} | {2} |".format(c.path, ch, c.replacement_count))
            else:
                lines.append("No changes applied.")
        else:
            lines.append("## Planned Changes")
            lines.append("")
            if changes:
                lines.append("| File | Would Change | Replacements |")
                lines.append("| --- | --- | --- |")
                for c in changes:
                    wc = "Yes" if c.would_change else "No"
                    lines.append("| {0} | {1} | {2} |".format(c.path, wc, c.replacement_count))
            else:
                lines.append("No changes computed (dry-run blocked or no files to inspect).")
        lines.append("")

        lines.append("## Diagnostics")
        lines.append("")
        diag_items = diagnostics.diagnostics
        if diag_items:
            for d in diag_items:
                lines.append("- [{0}] {1}: {2}".format(
                    d.severity.value.upper(), d.code, d.message,
                ))
        else:
            lines.append("No diagnostics.")
        lines.append("")

        lines.append("## Validation")
        lines.append("")
        lines.append("- `python -m core_runtime.cli lint --scope tooling --format json`")
        lines.append("- `python -m core_runtime.cli bump-version {0} --dry-run --format json`".format(target_version))
        lines.append("- `python -m pytest tests/test_tooling_*.py -v`")
        lines.append("")

        lines.append("## Final Status")
        lines.append("")
        mut_label = "true" if mutation_performed else "false"
        lines.append("**{0}** (mutation_performed: {1})".format(status_label, mut_label))
        lines.append("")

        md = "\n".join(lines)

        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(md, encoding="utf-8")

        return md

    # ---- internals -------------------------------------------------------

    def _compute_file_changes(
        self,
        current_version: str,
        target_version: str,
        diagnostics: DiagnosticCollection,
    ) -> list[PlannedChange]:
        """Walk replacement rules, count how many matches each file has."""
        # Group rules by file
        file_rules: dict[str, list[ReplacementRule]] = {}
        for rule in self.rules:
            file_rules.setdefault(rule.file_rel, []).append(rule)

        changes: list[PlannedChange] = []
        for file_rel, rules in file_rules.items():
            full_path = self.repo_root / file_rel

            if not full_path.is_file():
                # Directory-like paths (e.g. docs/releases/) — report only
                if full_path.is_dir():
                    changes.append(PlannedChange(
                        path=file_rel,
                        would_change=False,
                        replacement_count=0,
                        details="directory (report-only)",
                    ))
                    continue
                # Missing file
                changes.append(PlannedChange(
                    path=file_rel,
                    would_change=False,
                    replacement_count=0,
                    details="file not found",
                ))
                diagnostics.add_info(
                    code="core.bump_version.file_missing",
                    message="File not found for dry-run inspection: {0}".format(file_rel),
                    path=file_rel,
                )
                continue

            # Read file, count matches per rule
            try:
                text = full_path.read_text(encoding="utf-8")
            except OSError as exc:
                changes.append(PlannedChange(
                    path=file_rel,
                    would_change=False,
                    replacement_count=0,
                    details="read error: {0}".format(exc),
                ))
                continue

            total_hits = 0
            for rule in rules:
                matches = re.findall(rule.pattern, text, re.MULTILINE)
                total_hits += len(matches)

            changes.append(PlannedChange(
                path=file_rel,
                would_change=total_hits > 0,
                replacement_count=total_hits,
            ))

        # Add inspect-only entries
        for rel in self.INSPECT_ONLY_FILES:
            changes.append(PlannedChange(
                path=rel,
                would_change=False,
                replacement_count=0,
                details="inspect-only (no replacement rules)",
            ))

        return changes

    def _compute_new_contents(
        self,
        current_version: str,
        target_version: str,
        diagnostics: DiagnosticCollection,
    ) -> dict[str, str]:
        """Compute all new file contents in memory (no writes).

        Returns a dict mapping file_rel → new_text.
        """
        # Group rules by file
        file_rules: dict[str, list[ReplacementRule]] = {}
        for rule in self.rules:
            file_rules.setdefault(rule.file_rel, []).append(rule)

        new_contents: dict[str, str] = {}

        for file_rel, rules in file_rules.items():
            full_path = self.repo_root / file_rel
            if not full_path.is_file():
                continue

            try:
                text = full_path.read_text(encoding="utf-8")
            except OSError:
                continue

            new_text = text
            total_hits = 0
            for rule in rules:
                count, new_text = rule.compute_replacement(new_text, current_version, target_version)
                total_hits += count

            if total_hits > 0:
                new_contents[file_rel] = new_text

        # Handle CHANGELOG.md — preferred: prepend new entry (not replace header)
        # The replacement rule changes only the FIRST "## v" heading.
        # For the "Unreleased" → new version pattern in this repo, we also
        # insert a new changelog section if the file has "## Unreleased" before
        # the "## v" heading.
        changelog_path = self.repo_root / "CHANGELOG.md"
        if changelog_path.is_file() and "CHANGELOG.md" in new_contents:
            self._handle_changelog_insert(new_contents, current_version, target_version, diagnostics)

        # Handle docs/releases/README.md — update latest pointer.
        # Done here (compute-time, not write-time) so new_contents stays authoritative
        # and the mutation is reported via the AppliedChange list.
        releases_readme_rel = "docs/releases/README.md"
        releases_readme = self.repo_root / releases_readme_rel
        if releases_readme.is_file():
            try:
                text = releases_readme.read_text(encoding="utf-8")
                # Update "Latest stable release: vX.Y.Z (`docs/releases/vX.Y.Z.md`)"
                pattern = re.compile(
                    r"(\*\*Latest stable release\*\*:\s*v)\d+\.\d+\.\d+(\s+\(`docs/releases/v)"
                    r"\d+\.\d+\.\d+(\.md`\))",
                )
                new_text, count = pattern.subn(
                    r"\g<1>{0}\g<2>{0}\g<3>".format(target_version),
                    text,
                )
                if count > 0:
                    # Update "Previous stable release: vX.Y.Z" line
                    prev_pattern = re.compile(
                        r"(Previous stable release:\s*v)\d+\.\d+\.\d+",
                    )
                    new_text = prev_pattern.sub(
                        r"\g<1>{0}".format(current_version),
                        new_text,
                    )
                    new_contents[releases_readme_rel] = new_text
            except OSError:
                pass

        return new_contents

    def _handle_changelog_insert(
        self,
        new_contents: dict[str, str],
        current_version: str,
        target_version: str,
        diagnostics: DiagnosticCollection,
    ) -> None:
        """Adjust CHANGELOG.md content in new_contents dict.

        Preferred: insert a new section after "## Unreleased" heading
        for the target version. The replacement rule already changed
        the latest "## v" heading from current to new version.

        Since this repo keeps "## Unreleased" before the latest version
        heading, and the replacement rule renames the heading from
        v{current} to v{target}, the changelog is already correct for
        the simple case. But we also need to ensure "## v{current}"
        is preserved as a historical entry.

        Strategy: The replacement rule changes the first "## v10.5.0"
        heading to "## v10.5.1". This is correct because the repo uses
        "## Unreleased" as the pending section and the first versioned
        heading IS the latest release. We just need to make sure we
        don't also rewrite the historical entries.
        """
        changelog_text = new_contents.get("CHANGELOG.md", "")
        if not changelog_text:
            return

        # The replacement rule only matches the FIRST "## v" heading due to
        # MULTILINE + no count limit re.subn. However re.subn without count
        # replaces ALL matches. We need to change only the FIRST one.
        # Let's recompute: apply replacement to ONLY the first heading.
        original_path = self.repo_root / "CHANGELOG.md"
        try:
            original_text = original_path.read_text(encoding="utf-8")
        except OSError:
            return

        # Find the first "## v" heading and replace only that one
        pattern = re.compile(r"^(##\s+v)\d+\.\d+\.\d+", re.MULTILINE)
        match = pattern.search(original_text)
        if match:
            # Replace only the first match
            old_heading = match.group(0)
            new_heading = "## v{0}".format(target_version)
            new_text = original_text.replace(old_heading, new_heading, 1)
            new_contents["CHANGELOG.md"] = new_text

    def _check_git_safety(self, diagnostics: DiagnosticCollection) -> None:
        """Check that approved version-bearing files have no uncommitted changes."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"] + sorted(APPROVED_MUTATION_FILES),
                capture_output=True,
                text=True,
                cwd=str(self.repo_root),
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            # Git unavailable — emit warning but continue
            diagnostics.add_info(
                code="core.bump_version.git_unavailable",
                message="Git not available; skipping dirty file check.",
                path="internal",
            )
            return

        if result.returncode != 0:
            diagnostics.add_info(
                code="core.bump_version.git_error",
                message="git status returned non-zero; skipping dirty file check.",
                path="internal",
            )
            return

        dirty_lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
        for line in dirty_lines:
            # git status --porcelain format: XY PATH
            parts = line.strip().split(None, 1)
            if len(parts) < 2:
                continue
            filepath = parts[1].strip('"')
            # Check if this is an approved version-bearing file (or a subpath of one)
            for approved in APPROVED_MUTATION_FILES:
                if filepath == approved or filepath.startswith(approved + "/"):
                    diagnostics.add_blocked(
                        code="core.bump_version.dirty_version_file",
                        message="Version-bearing file has uncommitted changes before apply.",
                        path=filepath,
                    )
                    return

    def _create_release_note(self, target_version: str, path: Path) -> None:
        """Create a minimal release note for the target version."""
        today = date.today().isoformat()
        content = (
            "# CORE v{0}\n"
            "\n"
            "Date: {1}\n"
            "\n"
            "## Summary\n"
            "\n"
            "- Tooling release: controlled bump-version mutation support.\n"
            "\n"
            "## Validation\n"
            "\n"
            "- `python -m core_runtime.cli lint --scope tooling --format json`\n"
            "- `python -m core_runtime.cli bump-version {0} --dry-run --format json`\n"
            "- `python -m pytest tests/test_tooling_*.py -v`\n"
            "\n"
            "## Notes\n"
            "\n"
            "No runtime behavior, schema, or domain contract changes.\n"
        ).format(target_version, today)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
