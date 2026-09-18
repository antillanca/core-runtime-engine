"""Read-only environment diagnostics for CORE tooling."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core_runtime.tooling.diagnostics import DiagnosticCollection
from core_runtime.tooling.version_inventory import VersionInventory


@dataclass(frozen=True)
class DoctorItem:
    """A single environment readiness check."""

    kind: str
    name: str
    path: str
    status: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "kind": self.kind,
            "name": self.name,
            "path": self.path,
            "status": self.status,
        }
        if self.details:
            result["details"] = self.details
        return result


@dataclass
class DoctorReport:
    """Normalized report for `core-runtime doctor`."""

    tool: str
    command: str
    status: str
    mutation_performed: bool = False
    summary: dict[str, Any] = field(default_factory=dict)
    items: list[DoctorItem] = field(default_factory=list)
    diagnostics: DiagnosticCollection = field(default_factory=DiagnosticCollection)

    def to_dict(self) -> dict[str, Any]:
        counts = self.diagnostics.count_by_severity()
        summary = dict(self.summary)
        summary.setdefault("info", counts["info"])
        summary.setdefault("warning", counts["warning"])
        summary.setdefault("error", counts["error"])
        summary.setdefault("blocked", counts["blocked"])
        return {
            "tool": self.tool,
            "command": self.command,
            "status": self.status,
            "mutation_performed": self.mutation_performed,
            "summary": summary,
            "items": [item.to_dict() for item in self.items],
            "diagnostics": [d.to_dict() for d in self.diagnostics.diagnostics],
        }

    def to_markdown(self) -> str:
        counts = self.diagnostics.count_by_severity()
        summary = dict(self.summary)
        summary.setdefault("info", counts["info"])
        summary.setdefault("warning", counts["warning"])
        summary.setdefault("error", counts["error"])
        summary.setdefault("blocked", counts["blocked"])
        lines: list[str] = []
        lines.append("# CORE doctor report")
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append("| Tool | {0} |".format(self.tool))
        lines.append("| Command | {0} |".format(self.command))
        lines.append("| Status | {0} |".format(self.status.upper()))
        lines.append("| Mutation Performed | No |")
        lines.append("| Checks | {0} |".format(summary.get("item_count", len(self.items))))
        lines.append("| Info | {0} |".format(counts["info"]))
        lines.append("| Warning | {0} |".format(counts["warning"]))
        lines.append("| Error | {0} |".format(counts["error"]))
        lines.append("| Blocked | {0} |".format(counts["blocked"]))
        lines.append("")

        if self.items:
            lines.append("## Checks")
            lines.append("")
            lines.append("| Kind | Name | Path | Status |")
            lines.append("|------|------|------|--------|")
            for item in self.items:
                lines.append("| {0} | {1} | {2} | {3} |".format(item.kind, item.name, item.path, item.status))
            lines.append("")

        if self.diagnostics.diagnostics:
            lines.append("## Diagnostics")
            lines.append("")
            lines.append("| Severity | Code | Path | Message |")
            lines.append("|----------|------|------|---------|")
            for diagnostic in self.diagnostics.diagnostics:
                path = diagnostic.path or "-"
                message = diagnostic.message.replace("|", "\\|")
                lines.append(
                    "| {0} | {1} | {2} | {3} |".format(
                        diagnostic.severity.value.upper(),
                        diagnostic.code,
                        path,
                        message,
                    )
                )
            lines.append("")

        return "\n".join(lines)


class RepositoryDoctor:
    """Build deterministic environment diagnostics for local CORE tooling."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.version_inventory = VersionInventory(repo_root)

    def build_report(self, diagnostics: DiagnosticCollection | None = None) -> DoctorReport:
        diagnostics = diagnostics or DiagnosticCollection()
        items: list[DoctorItem] = []

        python_version = self._check_python_version(diagnostics, items)
        git_info = self._check_git(diagnostics, items)
        self._check_tools(diagnostics, items)
        self._check_verify_release_help(diagnostics, items)
        self._check_release_report_permissions(diagnostics, items)
        self._check_version_bearing_files(git_info, diagnostics, items)

        passed = sum(1 for item in items if item.status == "passed")
        warnings = sum(1 for item in items if item.status == "warning")
        skipped = sum(1 for item in items if item.status == "skipped")
        status = "pass"
        if diagnostics.has_blocked():
            status = "blocked"
        elif diagnostics.has_errors():
            status = "error"
        elif warnings:
            status = "warning"

        summary = {
            "item_count": len(items),
            "passed": passed,
            "warnings": warnings,
            "skipped": skipped,
            "python_version": python_version,
            "repo_root": str(self.repo_root),
        }
        if git_info is not None:
            summary["git_branch"] = git_info["branch"]
            summary["git_version"] = git_info["version"]

        return DoctorReport(
            tool="core-runtime doctor",
            command="doctor",
            status=status,
            summary=summary,
            items=items,
            diagnostics=diagnostics,
        )

    def _check_python_version(self, diagnostics: DiagnosticCollection, items: list[DoctorItem]) -> str:
        current = platform.python_version()
        required = "3.11"
        status = "passed"
        if sys.version_info < (3, 11):
            diagnostics.add_warning(
                code="core.doctor.python_version_too_low",
                message="Python version is below the supported baseline",
                path="python",
                expected=">= 3.11",
                actual=current,
            )
            status = "warning"
        items.append(
            DoctorItem(
                kind="environment",
                name="python",
                path="python",
                status=status,
                details={"version": current, "required": required},
            )
        )
        return current

    def _check_tools(self, diagnostics: DiagnosticCollection, items: list[DoctorItem]) -> None:
        for tool in ("pytest", "ruff", "mypy"):
            version = self._tool_version(tool)
            if version is None:
                diagnostics.add_warning(
                    code=f"core.doctor.{tool}_missing",
                    message=f"Required development tool not found: {tool}",
                    path=tool,
                    expected="installed",
                    actual="missing",
                )
                items.append(
                    DoctorItem(
                        kind="tool",
                        name=tool,
                        path=tool,
                        status="warning",
                        details={"version": None, "available": False},
                    )
                )
                continue
            items.append(
                DoctorItem(
                    kind="tool",
                    name=tool,
                    path=tool,
                    status="passed",
                    details={"version": version, "available": True},
                )
            )

    def _check_git(self, diagnostics: DiagnosticCollection, items: list[DoctorItem]) -> dict[str, str] | None:
        version = self._tool_version("git")
        if version is None:
            diagnostics.add_warning(
                code="core.doctor.git_missing",
                message="Git is not available in PATH",
                path="git",
                expected="installed",
                actual="missing",
            )
            items.append(
                DoctorItem(
                    kind="tool",
                    name="git",
                    path="git",
                    status="warning",
                    details={"version": None, "available": False},
                )
            )
            return None

        branch = self._git_branch()
        if branch is None:
            diagnostics.add_warning(
                code="core.doctor.git_branch_unavailable",
                message="Git branch could not be determined",
                path=str(self.repo_root),
                expected="branch name",
                actual="unknown",
            )
            status = "warning"
            branch = "unknown"
        elif branch == "HEAD":
            diagnostics.add_warning(
                code="core.doctor.git_detached_head",
                message="Git repository is in detached HEAD state",
                path=str(self.repo_root),
                expected="named branch",
                actual="HEAD",
            )
            status = "warning"
        else:
            status = "passed"

        items.append(
            DoctorItem(
                kind="tool",
                name="git",
                path="git",
                status=status,
                details={"version": version, "branch": branch, "available": True},
            )
        )
        return {"version": version, "branch": branch}

    def _check_verify_release_help(self, diagnostics: DiagnosticCollection, items: list[DoctorItem]) -> None:
        script = self.repo_root / "scripts" / "verify_release.py"
        if not script.is_file():
            diagnostics.add_warning(
                code="core.doctor.verify_release_missing",
                message="verify_release.py script is missing",
                path="scripts/verify_release.py",
                expected="exists",
                actual="missing",
            )
            items.append(
                DoctorItem(
                    kind="script",
                    name="verify_release.py",
                    path="scripts/verify_release.py",
                    status="warning",
                    details={"available": False},
                )
            )
            return

        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            diagnostics.add_warning(
                code="core.doctor.verify_release_help_failed",
                message="verify_release.py --help did not exit cleanly",
                path="scripts/verify_release.py",
                expected="exit 0",
                actual=str(result.returncode),
            )
            status = "warning"
        else:
            status = "passed"
        items.append(
            DoctorItem(
                kind="script",
                name="verify_release.py",
                path="scripts/verify_release.py",
                status=status,
                details={"available": True, "returncode": result.returncode},
            )
        )

    def _check_release_report_permissions(self, diagnostics: DiagnosticCollection, items: list[DoctorItem]) -> None:
        releases_dir = self.repo_root / "docs" / "releases"
        if not releases_dir.is_dir():
            diagnostics.add_warning(
                code="core.doctor.release_dir_missing",
                message="Release notes directory is missing",
                path="docs/releases",
                expected="directory",
                actual="missing",
            )
            items.append(
                DoctorItem(
                    kind="path",
                    name="release-notes",
                    path="docs/releases",
                    status="warning",
                    details={"exists": False, "writable": False},
                )
            )
            return

        writable = os.access(releases_dir, os.W_OK)
        if not writable:
            diagnostics.add_warning(
                code="core.doctor.release_dir_not_writable",
                message="Release notes directory is not writable",
                path="docs/releases",
                expected="writable",
                actual="read-only",
            )
            status = "warning"
        else:
            status = "passed"

        items.append(
            DoctorItem(
                kind="path",
                name="release-notes",
                path="docs/releases",
                status=status,
                details={"exists": True, "writable": writable},
            )
        )

    def _check_version_bearing_files(
        self,
        git_info: dict[str, str] | None,
        diagnostics: DiagnosticCollection,
        items: list[DoctorItem],
    ) -> None:
        sources = self.version_inventory.discover()
        version_paths = [str(source.path.relative_to(self.repo_root)) for source in sources]
        missing = [source.name for source in sources if not source.path.exists()]
        if missing:
            diagnostics.add_warning(
                code="core.doctor.version_source_missing",
                message="One or more version-bearing files are missing",
                path=missing[0],
                expected="exists",
                actual=", ".join(missing),
            )
            items.append(
                DoctorItem(
                    kind="repo",
                    name="version-bearing-files",
                    path="version-bearing-files",
                    status="warning",
                    details={"missing": missing, "dirty": []},
                )
            )
            return

        if git_info is None:
            items.append(
                DoctorItem(
                    kind="repo",
                    name="version-bearing-files",
                    path="version-bearing-files",
                    status="skipped",
                    details={"dirty": [], "reason": "git unavailable"},
                )
            )
            diagnostics.add_warning(
                code="core.doctor.version_dirty_unknown",
                message="Cannot inspect version-bearing files without git",
                path="version-bearing-files",
                expected="git available",
                actual="git missing",
            )
            return

        result = subprocess.run(
            ["git", "-C", str(self.repo_root), "status", "--porcelain", "--", *version_paths],
            capture_output=True,
            text=True,
            check=False,
        )
        dirty: list[str] = []
        for line in result.stdout.splitlines():
            if len(line) < 4:
                continue
            dirty.append(line[3:].strip())

        if dirty:
            diagnostics.add_warning(
                code="core.doctor.version_dirty",
                message="Version-bearing files have uncommitted changes",
                path=dirty[0],
                expected="clean",
                actual=", ".join(dirty),
            )
            status = "warning"
        else:
            status = "passed"

        items.append(
            DoctorItem(
                kind="repo",
                name="version-bearing-files",
                path="version-bearing-files",
                status=status,
                details={"dirty": dirty, "checked": version_paths},
            )
        )

    def _tool_version(self, tool: str) -> str | None:
        resolved = shutil.which(tool)
        if not resolved:
            return None
        result = subprocess.run(
            [resolved, "--version"],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip() or result.stderr.strip() or "unknown"

    def _git_branch(self) -> str | None:
        result = subprocess.run(
            ["git", "-C", str(self.repo_root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None
