"""Deterministic repository inventory helpers for read-only CLI navigation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core_runtime.tooling.diagnostics import DiagnosticCollection
from core_runtime.tooling.file_inventory import FileInventory
from core_runtime.tooling.version_inventory import VersionInventory


@dataclass(frozen=True)
class InventoryItem:
    """A single repository inventory item."""

    kind: str
    name: str
    path: str
    title: str | None = None
    summary: str | None = None
    status: str = "present"
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "kind": self.kind,
            "name": self.name,
            "path": self.path,
            "status": self.status,
        }
        if self.title is not None:
            result["title"] = self.title
        if self.summary is not None:
            result["summary"] = self.summary
        if self.details:
            result["details"] = self.details
        return result


@dataclass
class InventoryReport:
    """Normalized report for `core-runtime list` and `core-runtime info`."""

    tool: str
    command: str
    status: str
    mutation_performed: bool = False
    summary: dict[str, Any] = field(default_factory=dict)
    selection: dict[str, Any] | None = None
    items: list[InventoryItem] = field(default_factory=list)
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
        lines.append("# CORE repository inventory")
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
            lines.append("## Items")
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


class RepositoryInventory:
    """Build read-only inventories for public CORE repo navigation."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.version_inventory = VersionInventory(repo_root)
        self.file_inventory = FileInventory(repo_root)

    def list_items(self, kind: str) -> list[InventoryItem]:
        kind = kind.lower()
        if kind == "schemas":
            return self._list_schemas()
        if kind == "contracts":
            return self._list_contracts()
        if kind == "domains":
            return self._list_domains()
        if kind == "adapters":
            return self._list_adapters()
        return []

    def find_item(self, kind: str, name: str) -> InventoryItem | None:
        target = name.strip().lower()
        for item in self.list_items(kind):
            candidates = {
                item.name.lower(),
                Path(item.path).name.lower(),
                Path(item.path).stem.lower(),
            }
            if target in candidates:
                return item
        return None

    def build_list_report(self, kind: str, diagnostics: DiagnosticCollection | None = None) -> InventoryReport:
        diagnostics = diagnostics or DiagnosticCollection()
        items = self.list_items(kind)
        if not items:
            diagnostics.add_blocked(
                code="core.inventory.kind_unknown",
                message="Unknown inventory kind: {0}".format(kind),
                path=kind,
                expected="schemas|contracts|domains|adapters",
                actual=kind,
            )
            status = "blocked"
        else:
            status = "pass"
        return InventoryReport(
            tool="core-runtime list",
            command="list {0}".format(kind),
            status=status,
            summary={"kind": kind, "item_count": len(items)},
            items=items,
            diagnostics=diagnostics,
        )

    def build_info_report(
        self,
        kind: str | None = None,
        name: str | None = None,
        diagnostics: DiagnosticCollection | None = None,
    ) -> InventoryReport:
        diagnostics = diagnostics or DiagnosticCollection()
        selection = {"kind": kind or "repository", "name": name or "all"}

        if kind is None:
            version_sources = self.version_inventory.discover()
            summary = {
                "repo_root": str(self.repo_root),
                "canonical_version": self.version_inventory.get_canonical_version(),
                "version_sources": len(version_sources),
                "required_files_seen": sum(1 for exists in self.file_inventory.check_all(DiagnosticCollection()).values() if exists),
                "schema_count": len(self.list_items("schemas")),
                "contract_count": len(self.list_items("contracts")),
                "domain_count": len(self.list_items("domains")),
                "adapter_count": len(self.list_items("adapters")),
                "item_count": 0,
            }
            return InventoryReport(
                tool="core-runtime info",
                command="info",
                status="pass",
                summary=summary,
                selection=selection,
                diagnostics=diagnostics,
            )

        items = self.list_items(kind)
        if not items:
            diagnostics.add_blocked(
                code="core.inventory.kind_unknown",
                message="Unknown inventory kind: {0}".format(kind),
                path=kind,
                expected="schemas|contracts|domains|adapters",
                actual=kind,
            )
            return InventoryReport(
                tool="core-runtime info",
                command="info {0}".format(kind),
                status="blocked",
                summary={"kind": kind, "item_count": 0},
                selection=selection,
                diagnostics=diagnostics,
            )

        if name is None:
            return InventoryReport(
                tool="core-runtime info",
                command="info {0}".format(kind),
                status="pass",
                summary={"kind": kind, "item_count": len(items)},
                selection=selection,
                items=items,
                diagnostics=diagnostics,
            )

        item = self.find_item(kind, name)
        if item is None:
            diagnostics.add_error(
                code="core.inventory.item_not_found",
                message="No {0} named '{1}' found".format(kind[:-1] if kind.endswith("s") else kind, name),
                path=name,
                expected=kind,
                actual="not found",
            )
            return InventoryReport(
                tool="core-runtime info",
                command="info {0} {1}".format(kind, name),
                status="error",
                summary={"kind": kind, "item_count": 0},
                selection=selection,
                diagnostics=diagnostics,
            )

        return InventoryReport(
            tool="core-runtime info",
            command="info {0} {1}".format(kind, name),
            status="pass",
            summary={"kind": kind, "item_count": 1},
            selection=selection,
            items=[item],
            diagnostics=diagnostics,
        )

    def _list_schemas(self) -> list[InventoryItem]:
        schema_dir = self.repo_root / "schemas"
        items: list[InventoryItem] = []
        if not schema_dir.is_dir():
            return items

        for path in sorted(schema_dir.rglob("*.json")):
            if not path.is_file():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            title = payload.get("title")
            schema_id = payload.get("$id")
            schema_version = None
            properties = payload.get("properties")
            if isinstance(properties, dict):
                version_prop = properties.get("schema_version")
                if isinstance(version_prop, dict):
                    schema_version = version_prop.get("const")
            items.append(
                InventoryItem(
                    kind="schema",
                    name=str(title or path.stem),
                    path=str(path.relative_to(self.repo_root)),
                    title=str(title) if isinstance(title, str) else None,
                    summary=str(schema_version or "schema"),
                    details={
                        "schema_id": schema_id,
                        "schema_version": schema_version,
                    },
                )
            )
        return items

    def _list_contracts(self) -> list[InventoryItem]:
        items: list[InventoryItem] = []
        for rel_dir in ("contracts", "docs/contracts"):
            directory = self.repo_root / rel_dir
            if not directory.is_dir():
                continue
            for path in sorted(directory.rglob("*")):
                if not path.is_file():
                    continue
                if path.name.startswith("."):
                    continue
                items.append(
                    InventoryItem(
                        kind="contract",
                        name=path.stem,
                        path=str(path.relative_to(self.repo_root)),
                        summary=path.suffix.lstrip(".") or "file",
                        details={"source_dir": rel_dir},
                    )
                )
        return items

    def _list_domains(self) -> list[InventoryItem]:
        domains_dir = self.repo_root / "core_runtime" / "domains"
        items: list[InventoryItem] = []
        if not domains_dir.is_dir():
            return items

        for path in sorted(domains_dir.iterdir()):
            if not path.is_dir() or path.name.startswith("__"):
                continue
            module_files = sorted(
                child.name for child in path.iterdir() if child.is_file() and child.suffix == ".py"
            )
            items.append(
                InventoryItem(
                    kind="domain",
                    name=path.name,
                    path=str(path.relative_to(self.repo_root)),
                    summary="{0} python module(s)".format(len(module_files)),
                    details={"modules": module_files},
                )
            )
        return items

    def _list_adapters(self) -> list[InventoryItem]:
        items: list[InventoryItem] = []

        adapter_examples = self.repo_root / "examples" / "adapters"
        if adapter_examples.is_dir():
            for path in sorted(adapter_examples.iterdir()):
                if not path.is_dir():
                    continue
                fixture_count = len(list(path.rglob("manifest.json")))
                items.append(
                    InventoryItem(
                        kind="adapter",
                        name=path.name,
                        path=str(path.relative_to(self.repo_root)),
                        summary="{0} fixture manifest(s)".format(fixture_count),
                        details={
                            "source": "examples/adapters",
                            "has_readme": (path / "README.md").is_file(),
                        },
                    )
                )

        domains_dir = self.repo_root / "core_runtime" / "domains"
        if domains_dir.is_dir():
            for domain_dir in sorted(domains_dir.iterdir()):
                if not domain_dir.is_dir() or domain_dir.name.startswith("__"):
                    continue
                adapter_file = domain_dir / "adapters.py"
                if adapter_file.is_file():
                    items.append(
                        InventoryItem(
                            kind="adapter",
                            name="{0}.adapters".format(domain_dir.name),
                            path=str(adapter_file.relative_to(self.repo_root)),
                            summary="domain adapter module",
                            details={"source": "core_runtime/domains"},
                        )
                    )

        return items
