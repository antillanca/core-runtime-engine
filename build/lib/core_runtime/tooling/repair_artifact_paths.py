"""Dry-run-first artifact path repair planning for CORE tooling."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from core_runtime.tooling.diagnostics import DiagnosticCollection


_TEXT_SUFFIXES = {
    ".json",
    ".jsonl",
    ".md",
    ".txt",
    ".csv",
    ".toml",
    ".yaml",
    ".yml",
    ".py",
}

_IMMUTABLE_PATH_HINTS = (
    "core_runtime/data/runtime_release_manifest_",
    "core_runtime/data/runtime_reports/",
    "docs/archive/",
    "docs/releases/",
    "private/reports/",
)


@dataclass(frozen=True)
class ArtifactPathRepairRule:
    """A deterministic source-to-destination path replacement rule."""

    source: str
    destination: str
    kind: str

    def to_dict(self) -> dict[str, str]:
        return {
            "source": self.source,
            "destination": self.destination,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class ArtifactRepairItem:
    """A single planned artifact repair item."""

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
class ArtifactRepairReport:
    """Normalized report for `core-runtime repair-artifact-paths`."""

    tool: str
    command: str
    status: str
    mutation_performed: bool = False
    summary: dict[str, Any] = field(default_factory=dict)
    selection: dict[str, Any] | None = None
    items: list[ArtifactRepairItem] = field(default_factory=list)
    rules: list[ArtifactPathRepairRule] = field(default_factory=list)
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
            "rules": [rule.to_dict() for rule in self.rules],
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
        lines.append("# CORE repair-artifact-paths plan")
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
        lines.append("| Planned Repairs | {0} |".format(summary.get("planned_repairs", 0)))
        lines.append("| Immutable Hits | {0} |".format(summary.get("immutable_hits", 0)))
        lines.append("| Scanned Files | {0} |".format(summary.get("scanned_files", 0)))
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

        if self.rules:
            lines.append("## Repair Rules")
            lines.append("")
            lines.append("| Kind | Source | Destination |")
            lines.append("|------|--------|-------------|")
            for rule in self.rules:
                lines.append("| {0} | {1} | {2} |".format(rule.kind, rule.source, rule.destination))
            lines.append("")

        if self.items:
            lines.append("## Planned Repairs")
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


class ArtifactPathRepairPlanner:
    """Plan artifact path repairs without mutating the repository."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def build_plan(
        self,
        *,
        dry_run: bool,
        source: str | None = None,
        destination: str | None = None,
        manifest_path: Path | None = None,
        apply: bool = False,
        diagnostics: DiagnosticCollection | None = None,
    ) -> ArtifactRepairReport:
        diagnostics = diagnostics or DiagnosticCollection()
        selection = {
            "mode": "dry-run" if dry_run else "apply",
            "source": source,
            "destination": destination,
        }

        if apply:
            diagnostics.add_blocked(
                code="core.repair_artifact_paths.apply_not_enabled",
                message="repair-artifact-paths apply mode is not enabled in this slice",
                path="repair-artifact-paths",
                expected="dry-run-only preflight",
                actual="apply requested",
            )
        if not dry_run:
            diagnostics.add_blocked(
                code="core.repair_artifact_paths.dry_run_required",
                message="repair-artifact-paths requires --dry-run in this slice",
                path="repair-artifact-paths",
                expected="--dry-run",
                actual="missing dry-run",
            )

        rules, rule_selection = self._build_rules(source=source, destination=destination, manifest_path=manifest_path, diagnostics=diagnostics)
        selection.update(rule_selection)
        if diagnostics.has_blocked():
            return ArtifactRepairReport(
                tool="core-runtime repair-artifact-paths",
                command=self._command(source=source, destination=destination, dry_run=dry_run),
                status="blocked",
                summary={"mode": selection["mode"], "item_count": 0, "planned_repairs": 0, "immutable_hits": 0, "scanned_files": 0},
                selection=selection,
                rules=rules,
                diagnostics=diagnostics,
            )

        scanned_files = list(self._scan_files())
        items: list[ArtifactRepairItem] = []
        planned_repairs = 0
        immutable_hits = 0
        mutable_hits = 0

        for path in scanned_files:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            matches = self._find_matches(text, rules)
            if not matches:
                continue

            rel_path = path.relative_to(self.repo_root).as_posix()
            immutable = self._is_immutable_path(rel_path)
            replacement_preview = self._preview_replacement(text, matches[0])
            item_details = {
                "match_count": sum(match["occurrences"] for match in matches),
                "matches": matches,
                "replacement_preview": replacement_preview,
                "immutable": immutable,
            }

            if immutable:
                immutable_hits += 1
                diagnostics.add_blocked(
                    code="core.repair_artifact_paths.immutable_reference",
                    message="Immutable artifact contains a path reference that must not be rewritten",
                    path=rel_path,
                    expected="preserve historical evidence",
                    actual=matches[0]["source"],
                    details=matches[0]["destination"],
                )
                status = "blocked"
            else:
                mutable_hits += 1
                planned_repairs += 1
                diagnostics.add_warning(
                    code="core.repair_artifact_paths.mutable_reference",
                    message="Mutable artifact contains a path reference that can be repaired in a later apply slice",
                    path=rel_path,
                    expected=matches[0]["destination"],
                    actual=matches[0]["source"],
                    details="; ".join(
                        "{0}->{1} x{2}".format(match["source"], match["destination"], match["occurrences"]) for match in matches
                    ),
                )
                status = "planned_repair"

            items.append(
                ArtifactRepairItem(
                    kind="immutable_artifact" if immutable else "mutable_artifact",
                    name=path.name,
                    path=rel_path,
                    status=status,
                    details=item_details,
                )
            )

        report_status = "pass"
        if diagnostics.has_blocked():
            report_status = "blocked"
        elif diagnostics.has_errors():
            report_status = "error"
        elif planned_repairs or mutable_hits:
            report_status = "warning"

        return ArtifactRepairReport(
            tool="core-runtime repair-artifact-paths",
            command=self._command(source=source, destination=destination, dry_run=dry_run),
            status=report_status,
            summary={
                "mode": selection["mode"],
                "item_count": len(items),
                "planned_repairs": planned_repairs,
                "immutable_hits": immutable_hits,
                "scanned_files": len(scanned_files),
                "rule_count": len(rules),
            },
            selection=selection,
            items=items,
            rules=rules,
            diagnostics=diagnostics,
        )

    def _build_rules(
        self,
        *,
        source: str | None,
        destination: str | None,
        manifest_path: Path | None,
        diagnostics: DiagnosticCollection,
    ) -> tuple[list[ArtifactPathRepairRule], dict[str, Any]]:
        selection: dict[str, Any] = {}
        if manifest_path is None:
            manifest_path = self.repo_root / "core_runtime" / "data" / "artifact_migration_manifest.json"

        if source or destination:
            if not source or not destination:
                diagnostics.add_blocked(
                    code="core.repair_artifact_paths.rule_incomplete",
                    message="Targeted repair requires both --from and --to",
                    path="repair-artifact-paths",
                    expected="paired source and destination paths",
                    actual="missing rule endpoint",
                )
                return [], selection
            rules = [ArtifactPathRepairRule(source=source, destination=destination, kind="targeted")]
            selection["rules_source"] = "explicit"
            return rules, selection

        rules = self._rules_from_manifest(manifest_path, diagnostics)
        selection["rules_source"] = str(manifest_path.relative_to(self.repo_root)) if manifest_path.exists() else str(manifest_path)
        return rules, selection

    def _rules_from_manifest(
        self,
        manifest_path: Path,
        diagnostics: DiagnosticCollection,
    ) -> list[ArtifactPathRepairRule]:
        if not manifest_path.exists():
            diagnostics.add_blocked(
                code="core.repair_artifact_paths.manifest_missing",
                message="Artifact migration manifest not found",
                path=str(manifest_path.relative_to(self.repo_root)),
                expected="artifact migration manifest",
                actual="missing",
            )
            return []

        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            diagnostics.add_blocked(
                code="core.repair_artifact_paths.manifest_invalid",
                message="Artifact migration manifest could not be parsed",
                path=str(manifest_path.relative_to(self.repo_root)),
                expected="valid JSON",
                actual=str(exc),
            )
            return []

        entries = payload.get("migrated_files", [])
        rules: list[ArtifactPathRepairRule] = []
        seen: set[tuple[str, str, str]] = set()
        for entry in entries:
            source = entry.get("source")
            destination = entry.get("destination")
            if not source or not destination:
                continue
            exact = ("exact", source, destination)
            if exact not in seen:
                seen.add(exact)
                rules.append(ArtifactPathRepairRule(source=source, destination=destination, kind="exact"))

            source_parent = Path(source).parent.as_posix()
            destination_parent = Path(destination).parent.as_posix()
            if source_parent not in {"", "."} and destination_parent not in {"", "."}:
                source_prefix = self._ensure_trailing_slash(source_parent)
                destination_prefix = self._ensure_trailing_slash(destination_parent)
                prefix = ("prefix", source_prefix, destination_prefix)
                if prefix not in seen:
                    seen.add(prefix)
                    rules.append(ArtifactPathRepairRule(source=source_prefix, destination=destination_prefix, kind="prefix"))

        rules.sort(key=lambda rule: (-len(rule.source), rule.kind, rule.source, rule.destination))
        return rules

    def _scan_files(self) -> Iterable[Path]:
        scan_roots = [
            self.repo_root / "core_runtime" / "data",
            self.repo_root / "docs",
            self.repo_root / "private" / "reports",
        ]
        for root in scan_roots:
            if not root.exists():
                continue
            for path in sorted(root.rglob("*")):
                if not path.is_file():
                    continue
                if "__pycache__" in path.parts:
                    continue
                if not self._is_text_candidate(path):
                    continue
                yield path

    def _find_matches(self, text: str, rules: list[ArtifactPathRepairRule]) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        for rule in rules:
            occurrences = text.count(rule.source)
            if occurrences:
                matches.append(
                    {
                        "source": rule.source,
                        "destination": rule.destination,
                        "kind": rule.kind,
                        "occurrences": occurrences,
                    }
                )
        return matches

    def _preview_replacement(self, text: str, match: dict[str, Any]) -> str:
        replaced = text.replace(match["source"], match["destination"], 1)
        return replaced[:240]

    def _is_text_candidate(self, path: Path) -> bool:
        if path.suffix.lower() in _TEXT_SUFFIXES:
            return True
        return path.name in {"README", "LICENSE", "Dockerfile"}

    def _is_immutable_path(self, rel_path: str) -> bool:
        return any(hint in rel_path for hint in _IMMUTABLE_PATH_HINTS)

    def _command(self, source: str | None, destination: str | None, dry_run: bool) -> str:
        if source and destination:
            base = "repair-artifact-paths --from {0} --to {1}".format(source, destination)
        else:
            base = "repair-artifact-paths"
        if dry_run:
            return base + " --dry-run"
        return base

    def _ensure_trailing_slash(self, value: str) -> str:
        return value if value.endswith("/") else value + "/"
