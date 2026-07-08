"""Dry-run-first domain scaffolding preflight for CORE tooling."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core_runtime.tooling.diagnostics import DiagnosticCollection


DOMAIN_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class CreateDomainItem:
    """A planned file or artifact in a domain scaffold."""

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
class CreateDomainReport:
    """Normalized report for `core-runtime create-domain`."""

    tool: str
    command: str
    status: str
    mutation_performed: bool = False
    summary: dict[str, Any] = field(default_factory=dict)
    selection: dict[str, Any] | None = None
    items: list[CreateDomainItem] = field(default_factory=list)
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
        lines.append("# CORE create-domain plan")
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
            lines.append("## Planned Artifacts")
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


class DomainScaffolder:
    """Plan a deterministic domain scaffold without mutating the repo."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def build_plan(self, name: str, template: str = "generic", diagnostics: DiagnosticCollection | None = None) -> CreateDomainReport:
        diagnostics = diagnostics or DiagnosticCollection()
        normalized_name = name.strip()
        normalized_template = template.strip()
        selection = {"domain": normalized_name, "template": normalized_template, "mode": "dry-run"}

        if not DOMAIN_NAME_PATTERN.fullmatch(normalized_name):
            diagnostics.add_blocked(
                code="core.create_domain.invalid_name",
                message="Domain name must match ^[a-z][a-z0-9_]*$",
                path=normalized_name,
                expected="lowercase identifier",
                actual=normalized_name,
            )
            return CreateDomainReport(
                tool="core-runtime create-domain",
                command="create-domain {0} --dry-run".format(normalized_name),
                status="blocked",
                summary={"mode": "dry-run", "item_count": 0},
                selection=selection,
                diagnostics=diagnostics,
            )

        planned_items, collisions, risks = self._plan_items(normalized_name, normalized_template)
        if collisions:
            diagnostics.add_blocked(
                code="core.create_domain.collision",
                message="Domain scaffold collides with existing files or directories",
                path=collisions[0],
                expected="unused paths",
                actual=", ".join(collisions),
            )
            status = "blocked"
        else:
            status = "pass"

        if risks:
            diagnostics.add_warning(
                code="core.create_domain.review_required",
                message="Domain scaffold has reviewable design risks",
                path=normalized_name,
                expected="bounded dry-run review",
                actual=", ".join(risks),
            )
            if status == "pass":
                status = "warning"

        return CreateDomainReport(
            tool="core-runtime create-domain",
            command="create-domain {0} --dry-run".format(normalized_name),
            status=status,
            summary={
                "mode": "dry-run",
                "item_count": len(planned_items),
                "collision_count": len(collisions),
                "risk_count": len(risks),
                "template": normalized_template,
            },
            selection=selection,
            items=planned_items,
            diagnostics=diagnostics,
        )

    def _plan_items(self, name: str, template: str) -> tuple[list[CreateDomainItem], list[str], list[str]]:
        collisions: list[str] = []
        risks: list[str] = []
        items: list[CreateDomainItem] = []

        domain_dir = self.repo_root / "core_runtime" / "domains" / name
        test_path = self.repo_root / "tests" / f"test_domain_{name}.py"
        example_dir = self.repo_root / "examples" / "domains" / name
        docs_path = self.repo_root / "docs" / "domains" / f"{name}.md"

        planned_paths = [
            domain_dir,
            domain_dir / "__init__.py",
            domain_dir / "task.py",
            domain_dir / "oracle.py",
            domain_dir / "surrogate.py",
            domain_dir / "projection.py",
            domain_dir / "evaluator.py",
            domain_dir / "confidence.py",
            domain_dir / "manifest.json",
            test_path,
            example_dir / "valid_task.json",
            example_dir / "invalid_task.json",
            docs_path,
        ]

        for path in planned_paths:
            if path.exists():
                collisions.append(str(path.relative_to(self.repo_root)))
            items.append(
                CreateDomainItem(
                    kind="planned_dir" if path == domain_dir else "planned_file",
                    name=path.name,
                    path=str(path.relative_to(self.repo_root)),
                    status="planned",
                    details={
                        "template": template,
                        "exists": path.exists(),
                    },
                )
            )

        risks.extend(
            [
                "no_runtime_behavior",
                "advisory_only_manifest",
                "fixtures_must_stay_synthetic",
                "tests_require_followup",
                "docs_need_manual_review",
            ]
        )
        if template != "generic":
            risks.append(f"template:{template}")

        return items, collisions, risks
