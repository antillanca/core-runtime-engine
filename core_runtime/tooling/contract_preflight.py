"""Advisory-only contract preflight helpers for CORE tooling."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core_runtime.tooling.diagnostics import DiagnosticCollection


@dataclass(frozen=True)
class ContractItem:
    """A single contract review item."""

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
class ContractPreflightReport:
    """Normalized report for `core-runtime contract-preflight`."""

    tool: str
    command: str
    status: str
    mutation_performed: bool = False
    summary: dict[str, Any] = field(default_factory=dict)
    selection: dict[str, Any] | None = None
    items: list[ContractItem] = field(default_factory=list)
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
        lines.append("# CORE contract preflight")
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


class RepositoryContractPreflight:
    """Build advisory-only contract review reports from public CORE schemas."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def build_candidate_report(self, name: str, diagnostics: DiagnosticCollection | None = None) -> ContractPreflightReport:
        diagnostics = diagnostics or DiagnosticCollection()
        contract = self._resolve_contract(name)
        selection = {"mode": "candidate", "candidate": name}

        if contract is None:
            diagnostics.add_blocked(
                code="core.contract_preflight.contract_unknown",
                message="Unknown contract candidate: {0}".format(name),
                path=name,
                expected="known CORE contract name",
                actual=name,
            )
            return ContractPreflightReport(
                tool="core-runtime contract-preflight",
                command="contract-preflight --candidate {0}".format(name),
                status="blocked",
                summary={"mode": "candidate", "item_count": 0},
                selection=selection,
                diagnostics=diagnostics,
            )

        item = self._contract_item(contract)
        return ContractPreflightReport(
            tool="core-runtime contract-preflight",
            command="contract-preflight --candidate {0}".format(name),
            status="pass",
            summary={
                "mode": "candidate",
                "item_count": 1,
                "required_field_count": len(item.details.get("required_fields", [])),
                "property_count": len(item.details.get("property_names", [])),
            },
            selection=selection,
            items=[item],
            diagnostics=diagnostics,
        )

    def build_compare_report(
        self,
        left: str,
        right: str,
        diagnostics: DiagnosticCollection | None = None,
    ) -> ContractPreflightReport:
        diagnostics = diagnostics or DiagnosticCollection()
        left_contract = self._resolve_contract(left)
        right_contract = self._resolve_contract(right)
        selection = {"mode": "compare", "left": left, "right": right}

        missing: list[str] = []
        if left_contract is None:
            missing.append(left)
        if right_contract is None:
            missing.append(right)
        if missing:
            diagnostics.add_blocked(
                code="core.contract_preflight.contract_unknown",
                message="Unknown contract candidate(s): {0}".format(", ".join(missing)),
                path=", ".join(missing),
                expected="known CORE contract name",
                actual=", ".join(missing),
            )
            return ContractPreflightReport(
                tool="core-runtime contract-preflight",
                command="contract-preflight --compare {0} {1}".format(left, right),
                status="blocked",
                summary={"mode": "compare", "item_count": 0},
                selection=selection,
                diagnostics=diagnostics,
            )

        left_item = self._contract_item(left_contract)
        right_item = self._contract_item(right_contract)
        left_required = set(left_item.details.get("required_fields", []))
        right_required = set(right_item.details.get("required_fields", []))
        shared_required = sorted(left_required & right_required)
        left_only = sorted(left_required - right_required)
        right_only = sorted(right_required - left_required)
        status = "pass"
        if left_item.details.get("schema_version") != right_item.details.get("schema_version"):
            status = "warning"

        return ContractPreflightReport(
            tool="core-runtime contract-preflight",
            command="contract-preflight --compare {0} {1}".format(left, right),
            status=status,
            summary={
                "mode": "compare",
                "item_count": 2,
                "shared_required_fields": len(shared_required),
                "left_only_required_fields": len(left_only),
                "right_only_required_fields": len(right_only),
                "same_schema_version": left_item.details.get("schema_version") == right_item.details.get("schema_version"),
            },
            selection=selection,
            items=[left_item, right_item],
            diagnostics=diagnostics,
        )

    def _resolve_contract(self, name: str) -> dict[str, Any] | None:
        normalized = name.strip().lower()
        for path in sorted((self.repo_root / "schemas" / "core").glob("*.json")):
            contract = self._load_contract(path)
            if contract is None:
                continue
            candidates = {
                contract.get("title", "").lower(),
                contract.get("schema_version", "").lower(),
                path.stem.lower(),
            }
            if normalized in candidates:
                return contract
        return None

    def _load_contract(self, path: Path) -> dict[str, Any] | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        required = payload.get("required")
        properties = payload.get("properties")
        if not isinstance(properties, dict):
            properties = {}
        return {
            "path": path,
            "title": payload.get("title"),
            "schema_version": self._schema_version(payload),
            "required": required if isinstance(required, list) else [],
            "properties": properties,
            "additionalProperties": payload.get("additionalProperties"),
        }

    def _schema_version(self, payload: dict[str, Any]) -> str | None:
        properties = payload.get("properties")
        if isinstance(properties, dict):
            schema_version = properties.get("schema_version")
            if isinstance(schema_version, dict):
                const = schema_version.get("const")
                if isinstance(const, str) and const:
                    return const
        return None

    def _contract_item(self, contract: dict[str, Any]) -> ContractItem:
        properties = contract.get("properties", {})
        property_names = sorted(properties.keys()) if isinstance(properties, dict) else []
        required_fields = sorted(str(value) for value in contract.get("required", []))
        return ContractItem(
            kind="contract",
            name=str(contract.get("title") or Path(contract["path"]).stem),
            path=str(Path(contract["path"]).relative_to(self.repo_root)),
            status="passed",
            details={
                "schema_version": contract.get("schema_version"),
                "required_fields": required_fields,
                "property_names": property_names,
                "additional_properties": contract.get("additionalProperties"),
            },
        )
