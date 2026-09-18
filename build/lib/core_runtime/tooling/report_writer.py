"""Report writer - serialize diagnostics to JSON and Markdown."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from core_runtime.tooling.diagnostics import DiagnosticCollection, ExitCode


class ReportWriter:
    """Write lint reports in JSON and Markdown formats."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def write_json(
        self,
        diagnostics: DiagnosticCollection,
        scope: str,
        output_path: Optional[Path] = None,
        version_sources: Optional[list] = None,
        file_inventory: Optional[dict] = None,
        json_checks: Optional[dict] = None,
        safety_checks: Optional[dict] = None,
    ) -> dict:
        """Generate JSON report structure."""
        exit_code = diagnostics.compute_exit_code()

        status_map = {
            ExitCode.OK: "pass",
            ExitCode.ERROR: "error",
            ExitCode.BLOCKED: "blocked",
            ExitCode.INTERNAL_ERROR: "internal_error",
        }

        report = {
            "tool": "core-runtime lint",
            "scope": scope,
            "status": status_map.get(exit_code, "internal_error"),
            "mutation_performed": False,
            "summary": diagnostics.count_by_severity(),
            "diagnostics": [d.to_dict() for d in diagnostics.diagnostics],
        }

        if version_sources is not None:
            report["version_inventory"] = [v.to_dict() if hasattr(v, "to_dict") else v for v in version_sources]

        if file_inventory is not None:
            report["file_inventory"] = file_inventory

        if json_checks is not None:
            report["json_checks"] = json_checks

        if safety_checks is not None:
            report["safety_checks"] = safety_checks

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)

        return report

    def write_markdown(
        self,
        diagnostics: DiagnosticCollection,
        scope: str,
        output_path: Optional[Path] = None,
        version_sources: Optional[list] = None,
        file_inventory: Optional[dict] = None,
        json_checks: Optional[dict] = None,
        safety_checks: Optional[dict] = None,
    ) -> str:
        """Generate Markdown report."""
        exit_code = diagnostics.compute_exit_code()
        counts = diagnostics.count_by_severity()

        status_map = {
            ExitCode.OK: "PASS",
            ExitCode.ERROR: "ERROR",
            ExitCode.BLOCKED: "BLOCKED",
            ExitCode.INTERNAL_ERROR: "INTERNAL_ERROR",
        }

        lines = []
        lines.append("# CORE Tooling Lint Report")
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append("| Tool | core-runtime lint |")
        lines.append("| Scope | {0} |".format(scope))
        lines.append("| Status | {0} |".format(status_map.get(exit_code, "UNKNOWN")))
        lines.append("| Exit Code | {0} |".format(exit_code.value))
        lines.append("| Mutation Performed | No |")
        lines.append("| Errors | {0} |".format(counts.get("error", 0)))
        lines.append("| Warnings | {0} |".format(counts.get("warning", 0)))
        lines.append("| Info | {0} |".format(counts.get("info", 0)))
        lines.append("| Blocked | {0} |".format(counts.get("blocked", 0)))
        lines.append("")

        # Diagnostics table
        if diagnostics.diagnostics:
            lines.append("## Diagnostics")
            lines.append("")
            lines.append("| Severity | Code | Path | Message |")
            lines.append("|----------|------|------|---------|")
            for d in diagnostics.diagnostics:
                path = d.path or "-"
                msg = d.message.replace("|", "\\|")
                lines.append("| {0} | {1} | {2} | {3} |".format(d.severity.value.upper(), d.code, path, msg))
            lines.append("")

        # Version Inventory
        if version_sources:
            lines.append("## Version Inventory")
            lines.append("")
            lines.append("| Source | Version | Canonical |")
            lines.append("|--------|---------|-----------|")
            for v in version_sources:
                if hasattr(v, "version"):
                    ver = v.version or "NOT FOUND"
                    canon = "Yes" if getattr(v, "is_canonical", False) else "No"
                    path = getattr(v, "path", "")
                    name = getattr(v, "name", str(path))
                    lines.append("| {0} | {1} | {2} |".format(name, ver, canon))
            lines.append("")

        # File Inventory
        if file_inventory:
            lines.append("## File Inventory")
            lines.append("")
            lines.append("| Path | Exists |")
            lines.append("|------|--------|")
            for path, exists in sorted(file_inventory.items()):
                lines.append("| {0} | {1} |".format(path, "✓" if exists else "✗"))
            lines.append("")

        # JSON Checks
        if json_checks:
            lines.append("## JSON Checks")
            lines.append("")
            for key, value in json_checks.items():
                lines.append("- **{0}**: {1}".format(key, value))
            lines.append("")

        # Safety Checks
        if safety_checks:
            lines.append("## Safety Checks")
            lines.append("")
            for key, value in safety_checks.items():
                lines.append("- **{0}**: {1}".format(key, value))
            lines.append("")

        lines.append("## Final Status")
        lines.append("")
        if exit_code == ExitCode.OK:
            lines.append("✅ **PASS** - No errors or blockers found.")
        elif exit_code == ExitCode.ERROR:
            lines.append("❌ **ERROR** - One or more errors found. Must fix before release.")
        elif exit_code == ExitCode.BLOCKED:
            lines.append("🚫 **BLOCKED** - One or more blockers found. Cannot proceed safely.")
        else:
            lines.append("⚠️ **INTERNAL ERROR** - Tooling failure.")
        lines.append("")

        markdown = "\n".join(lines)

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(markdown, encoding="utf-8")

        return markdown