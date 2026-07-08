"""Dry-run-first template synchronization planning for CORE tooling."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core_runtime.tooling.create_domain import DomainScaffolder
from core_runtime.tooling.diagnostics import DiagnosticCollection


@dataclass(frozen=True)
class SyncTemplateItem:
    """A planned template sync artifact."""

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
class SyncTemplateReport:
    """Normalized report for `core-runtime sync-template`."""

    tool: str
    command: str
    status: str
    mutation_performed: bool = False
    summary: dict[str, Any] = field(default_factory=dict)
    selection: dict[str, Any] | None = None
    items: list[SyncTemplateItem] = field(default_factory=list)
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
            "selection": self.selection,
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
        lines.append("# CORE sync-template plan")
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append("| Tool | {0} |".format(self.tool))
        lines.append("| Command | {0} |".format(self.command))
        lines.append("| Status | {0} |".format(self.status.upper()))
        lines.append("| Mutation Performed | No |")
        lines.append("| Items | {0} |".format(summary.get("item_count", len(self.items))))
        lines.append("| Info | {0} |".format(counts["info"]))
        lines.append("| Warning | {0} |".format(counts["warning"]))
        lines.append("| Error | {0} |".format(counts["error"]))
        lines.append("| Blocked | {0} |".format(counts["blocked"]))
        lines.append("")

        if self.selection is not None:
            lines.append("## Selection")
            lines.append("")
            for key, value in self.selection.items():
                lines.append("- **{0}**: {1}".format(key, value))
            lines.append("")

        if self.items:
            lines.append("## Planned Changes")
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


class TemplateSyncPlanner:
    """Compare existing domains against a canonical scaffold template."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.scaffolder = DomainScaffolder(repo_root)

    def build_plan(
        self,
        domain: str | None = None,
        all_domains: bool = False,
        template: str = "generic",
        diagnostics: DiagnosticCollection | None = None,
    ) -> SyncTemplateReport:
        diagnostics = diagnostics or DiagnosticCollection()
        if not domain and not all_domains:
            diagnostics.add_blocked(
                code="core.sync_template.mode_required",
                message="sync-template requires --domain or --all",
                path="sync-template",
                expected="--domain <name> or --all",
                actual="missing mode",
            )
            return SyncTemplateReport(
                tool="core-runtime sync-template",
                command="sync-template",
                status="blocked",
                summary={"mode": "missing", "item_count": 0},
                selection={"mode": "missing"},
                diagnostics=diagnostics,
            )

        domain_names = self._domain_names(domain=domain, all_domains=all_domains)
        if not domain_names:
            diagnostics.add_blocked(
                code="core.sync_template.domain_missing",
                message="No domains available for template sync",
                path="core_runtime/domains",
                expected="at least one domain",
                actual="empty",
            )
            return SyncTemplateReport(
                tool="core-runtime sync-template",
                command=self._command(domain=domain, all_domains=all_domains),
                status="blocked",
                summary={"mode": "missing", "item_count": 0},
                selection={"mode": "missing"},
                diagnostics=diagnostics,
            )

        items: list[SyncTemplateItem] = []
        additions = 0
        preserved = 0
        collisions = 0
        for domain_name in domain_names:
            plan_items, domain_additions, domain_preserved, domain_collisions = self._plan_domain(
                domain_name, template, diagnostics
            )
            items.extend(plan_items)
            additions += domain_additions
            preserved += domain_preserved
            collisions += domain_collisions

        status = "pass"
        if collisions:
            status = "blocked"
        elif additions or preserved:
            status = "warning"

        return SyncTemplateReport(
            tool="core-runtime sync-template",
            command=self._command(domain=domain, all_domains=all_domains),
            status=status,
            summary={
                "mode": "all" if all_domains else "domain",
                "item_count": len(items),
                "planned_additions": additions,
                "preserved_custom": preserved,
                "collisions": collisions,
                "template": template,
            },
            selection={"domain": domain, "all": all_domains, "template": template},
            items=items,
            diagnostics=diagnostics,
        )

    def _domain_names(self, domain: str | None, all_domains: bool) -> list[str]:
        domains_dir = self.repo_root / "core_runtime" / "domains"
        if all_domains:
            if not domains_dir.is_dir():
                return []
            return sorted(
                path.name
                for path in domains_dir.iterdir()
                if path.is_dir() and not path.name.startswith("__")
            )
        if domain is None:
            return []
        return [domain]

    def _plan_domain(
        self,
        domain_name: str,
        template: str,
        diagnostics: DiagnosticCollection,
    ) -> tuple[list[SyncTemplateItem], int, int, int]:
        expected_plan, _, _ = self.scaffolder._plan_items(domain_name, template)
        expected_paths = {Path(item.path).as_posix() for item in expected_plan}
        domain_dir = self.repo_root / "core_runtime" / "domains" / domain_name
        items: list[SyncTemplateItem] = []
        additions = 0
        preserved = 0
        collisions = 0

        if not domain_dir.exists():
            collisions += 1
            diagnostics.add_blocked(
                code="core.sync_template.domain_missing",
                message="Domain not found for template sync",
                path=str(domain_dir.relative_to(self.repo_root)),
                expected="existing domain directory",
                actual="missing",
            )
            items.append(
                SyncTemplateItem(
                    kind="domain",
                    name=domain_name,
                    path=str(domain_dir.relative_to(self.repo_root)),
                    status="blocked",
                    details={"reason": "domain_missing"},
                )
            )
            return items, additions, preserved, collisions

        actual_files = sorted(
            path for path in domain_dir.rglob("*") if path.is_file() and "__pycache__" not in path.parts
        )
        actual_paths = {path.relative_to(self.repo_root).as_posix() for path in actual_files}

        for item in expected_plan:
            exists = item.details.get("exists", False)
            if exists:
                preserved += 1
                status = "preserved"
            else:
                additions += 1
                status = "planned_addition"
            items.append(
                SyncTemplateItem(
                    kind=item.kind,
                    name=item.name,
                    path=item.path,
                    status=status,
                    details=item.details,
                )
            )

        custom_paths = sorted(actual_paths - expected_paths)
        for rel_path in custom_paths:
            preserved += 1
            items.append(
                SyncTemplateItem(
                    kind="custom_file",
                    name=Path(rel_path).name,
                    path=rel_path,
                    status="preserved",
                    details={"reason": "custom_domain_file"},
                )
            )

        return items, additions, preserved, collisions

    def _command(self, domain: str | None, all_domains: bool) -> str:
        if all_domains:
            return "sync-template --all --dry-run"
        return "sync-template --domain {0} --dry-run".format(domain or "")
