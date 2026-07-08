"""Read-only structural validation helpers for CORE repository surfaces."""

from __future__ import annotations

import json
import py_compile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core_runtime.tooling.diagnostics import DiagnosticCollection


_REJECTED_PATH_MARKERS = (
    "invalid",
    "rejected",
    "negative_cases",
    "malicious",
    "not_accepted",
    "path_traversal",
    "workspace/",
    "private/",
    ".agents/",
    ".codex/",
)

@dataclass(frozen=True)
class ValidationItem:
    """A single validation result item."""

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
class ValidationReport:
    """Normalized report for read-only validation commands."""

    tool: str
    command: str
    status: str
    mutation_performed: bool = False
    summary: dict[str, Any] = field(default_factory=dict)
    selection: dict[str, Any] | None = None
    items: list[ValidationItem] = field(default_factory=list)
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
        lines.append("# CORE repository validation")
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
        lines.append("| Passed | {0} |".format(summary.get("passed", 0)))
        lines.append("| Failed | {0} |".format(summary.get("failed", 0)))
        lines.append("| Skipped | {0} |".format(summary.get("skipped", 0)))
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


def _is_rejected_path(path: Path) -> bool:
    path_text = str(path).lower()
    return any(marker in path_text for marker in _REJECTED_PATH_MARKERS)


def _walk_strings(payload: Any, prefix: str = "") -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            results.extend(_walk_strings(value, child_prefix))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            child_prefix = f"{prefix}[{index}]"
            results.extend(_walk_strings(value, child_prefix))
    elif isinstance(payload, str):
        results.append((prefix, payload))
    return results


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(payload, dict):
        return payload
    return None


class RepositoryValidation:
    """Build read-only validation reports for specific repository surfaces."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def build_report(self, kind: str, name: str | None = None, diagnostics: DiagnosticCollection | None = None) -> ValidationReport:
        diagnostics = diagnostics or DiagnosticCollection()
        normalized = kind.lower()
        selection = {"kind": normalized, "name": name}
        if normalized in {"schema", "schemas"}:
            items = self._validate_schemas(diagnostics)
            command = "validate schemas"
        elif normalized in {"example", "examples"}:
            items = self._validate_examples(diagnostics)
            command = "validate examples"
        elif normalized in {"manifest", "manifests"}:
            items = self._validate_manifests(diagnostics)
            command = "validate manifests"
        elif normalized in {"contract", "contracts"}:
            items = self._validate_contracts(diagnostics)
            command = "validate contracts"
        elif normalized in {"domain", "domains"}:
            if not name:
                diagnostics.add_blocked(
                    code="core.validate.domain_name_required",
                    message="validate domain requires a domain name",
                    path="core_runtime/domains/",
                    expected="validate domain <name>",
                    actual="missing name",
                )
                return ValidationReport(
                    tool="core-runtime validate",
                    command="validate domain",
                    status="blocked",
                    summary={"kind": "domain", "item_count": 0, "passed": 0, "failed": 1, "skipped": 0},
                    selection=selection,
                    diagnostics=diagnostics,
                )
            items = self._validate_domain(name, diagnostics)
            command = "validate domain {0}".format(name)
        else:
            diagnostics.add_blocked(
                code="core.validate.kind_unknown",
                message="Unknown validation kind: {0}".format(kind),
                path=kind,
                expected="schemas|examples|manifests|contracts|domain",
                actual=kind,
            )
            return ValidationReport(
                tool="core-runtime validate",
                command="validate {0}".format(kind),
                status="blocked",
                summary={"kind": kind, "item_count": 0, "passed": 0, "failed": 1, "skipped": 0},
                selection=selection,
                diagnostics=diagnostics,
            )

        passed = sum(1 for item in items if item.status == "passed")
        failed = sum(1 for item in items if item.status == "failed")
        skipped = sum(1 for item in items if item.status == "skipped")
        status = "pass"
        if diagnostics.has_blocked():
            status = "blocked"
        elif diagnostics.has_errors():
            status = "error"
        elif failed:
            status = "error"
        elif any(item.status == "warning" for item in items):
            status = "warning"
        return ValidationReport(
            tool="core-runtime validate",
            command=command,
            status=status,
            summary={
                "kind": normalized,
                "item_count": len(items),
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
            },
            selection=selection,
            items=items,
            diagnostics=diagnostics,
        )

    def _validate_schemas(self, diagnostics: DiagnosticCollection) -> list[ValidationItem]:
        schema_dir = self.repo_root / "schemas"
        items: list[ValidationItem] = []
        if not schema_dir.is_dir():
            diagnostics.add_blocked(
                code="core.validate.schemas_missing",
                message="schemas/ directory not found",
                path="schemas/",
            )
            return items

        for path in sorted(schema_dir.rglob("*.json")):
            if not path.is_file():
                continue
            rel = path.relative_to(self.repo_root)
            if _is_rejected_path(rel):
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                diagnostics.add_error(
                    code="core.validate.schema_invalid_json",
                    message="Invalid JSON schema file: {0}".format(rel),
                    path=str(rel),
                    details=str(exc),
                )
                items.append(ValidationItem(kind="schema", name=path.stem, path=str(rel), status="failed"))
                continue
            if not isinstance(payload, dict):
                diagnostics.add_error(
                    code="core.validate.schema_not_object",
                    message="Schema must be a JSON object: {0}".format(rel),
                    path=str(rel),
                )
                items.append(ValidationItem(kind="schema", name=path.stem, path=str(rel), status="failed"))
                continue
            errors = []
            for required_key in ("$schema", "title", "type"):
                if not isinstance(payload.get(required_key), str) or not payload.get(required_key):
                    errors.append(required_key)
            if errors:
                diagnostics.add_error(
                    code="core.validate.schema_missing_metadata",
                    message="Schema metadata missing required keys: {0}".format(", ".join(errors)),
                    path=str(rel),
                    expected="$schema,title,type",
                    actual="missing metadata",
                )
                items.append(ValidationItem(kind="schema", name=path.stem, path=str(rel), status="failed", details={"missing": errors}))
                continue
            if payload.get("type") == "object" and "additionalProperties" not in payload:
                diagnostics.add_warning(
                    code="core.validate.schema_missing_additional_properties",
                    message="Object schema should declare additionalProperties: {0}".format(rel),
                    path=str(rel),
                )
                items.append(ValidationItem(kind="schema", name=payload.get("title", path.stem), path=str(rel), status="warning"))
                continue
            items.append(
                ValidationItem(
                    kind="schema",
                    name=str(payload.get("title", path.stem)),
                    path=str(rel),
                    status="passed",
                    details={"schema_version": self._schema_version(payload)},
                )
            )
        return items

    def _validate_examples(self, diagnostics: DiagnosticCollection) -> list[ValidationItem]:
        examples_dir = self.repo_root / "examples"
        items: list[ValidationItem] = []
        if not examples_dir.is_dir():
            diagnostics.add_blocked(
                code="core.validate.examples_missing",
                message="examples/ directory not found",
                path="examples/",
            )
            return items

        for path in sorted(examples_dir.rglob("manifest.json")):
            rel = path.relative_to(self.repo_root)
            if _is_rejected_path(rel):
                continue
            item = self._validate_manifest_file(path, "example", diagnostics)
            items.append(item)
        return items

    def _validate_manifests(self, diagnostics: DiagnosticCollection) -> list[ValidationItem]:
        items: list[ValidationItem] = []
        for path in sorted(self.repo_root.rglob("*manifest*.json")):
            rel = path.relative_to(self.repo_root)
            if _is_rejected_path(rel):
                continue
            item = self._validate_manifest_file(path, "manifest", diagnostics)
            items.append(item)
        return items

    def _validate_contracts(self, diagnostics: DiagnosticCollection) -> list[ValidationItem]:
        items: list[ValidationItem] = []

        contracts_dir = self.repo_root / "contracts"
        if contracts_dir.is_dir():
            for path in sorted(contracts_dir.rglob("*.sol")):
                rel = path.relative_to(self.repo_root)
                text = path.read_text(encoding="utf-8")
                if "contract " not in text and "interface " not in text:
                    diagnostics.add_error(
                        code="core.validate.contract_missing_contract_decl",
                        message="Solidity contract declaration not found: {0}".format(rel),
                        path=str(rel),
                    )
                    items.append(ValidationItem(kind="contract", name=path.stem, path=str(rel), status="failed"))
                    continue
                items.append(ValidationItem(kind="contract", name=path.stem, path=str(rel), status="passed"))

        docs_contracts = self.repo_root / "docs" / "contracts"
        if docs_contracts.is_dir():
            for path in sorted(docs_contracts.rglob("*.json")):
                rel = path.relative_to(self.repo_root)
                item = self._validate_schema_like_json(path, "contract-doc", diagnostics)
                items.append(item)
        return items

    def _validate_domain(self, name: str, diagnostics: DiagnosticCollection) -> list[ValidationItem]:
        domain_dir = self.repo_root / "core_runtime" / "domains" / name
        items: list[ValidationItem] = []
        if not domain_dir.is_dir():
            diagnostics.add_error(
                code="core.validate.domain_missing",
                message="Domain not found: {0}".format(name),
                path=str(domain_dir.relative_to(self.repo_root)),
                expected="existing domain directory",
                actual="missing",
            )
            return items

        init_path = domain_dir / "__init__.py"
        if not init_path.is_file():
            diagnostics.add_error(
                code="core.validate.domain_missing_init",
                message="Domain package missing __init__.py: {0}".format(name),
                path=str(init_path.relative_to(self.repo_root)),
            )
            items.append(ValidationItem(kind="domain", name=name, path=str(domain_dir.relative_to(self.repo_root)), status="failed"))
        else:
            items.append(ValidationItem(kind="domain", name=name, path=str(domain_dir.relative_to(self.repo_root)), status="passed"))

        for path in sorted(domain_dir.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(self.repo_root)
            try:
                py_compile.compile(str(path), doraise=True)
            except py_compile.PyCompileError as exc:
                diagnostics.add_error(
                    code="core.validate.domain_python_compile_failed",
                    message="Python compile failed for {0}".format(rel),
                    path=str(rel),
                    details=exc.msg,
                )
                items.append(ValidationItem(kind="domain-python", name=path.stem, path=str(rel), status="failed"))
                continue
            items.append(ValidationItem(kind="domain-python", name=path.stem, path=str(rel), status="passed"))

        for path in sorted(domain_dir.rglob("*.json")):
            rel = path.relative_to(self.repo_root)
            item = self._validate_schema_like_json(path, "domain-manifest", diagnostics)
            item = ValidationItem(kind=item.kind, name=item.name, path=item.path, status=item.status, details=item.details)
            items.append(item)
        return items

    def _validate_manifest_file(self, path: Path, kind: str, diagnostics: DiagnosticCollection) -> ValidationItem:
        rel = path.relative_to(self.repo_root)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            diagnostics.add_error(
                code="core.validate.manifest_invalid_json",
                message="Invalid JSON manifest: {0}".format(rel),
                path=str(rel),
                details=str(exc),
            )
            return ValidationItem(kind=kind, name=path.stem, path=str(rel), status="failed")

        if not isinstance(payload, dict) or not payload:
            diagnostics.add_error(
                code="core.validate.manifest_not_object",
                message="Manifest must be a non-empty JSON object: {0}".format(rel),
                path=str(rel),
            )
            return ValidationItem(kind=kind, name=path.stem, path=str(rel), status="failed")

        path_issues = self._manifest_path_issues(payload)
        if path_issues:
            diagnostics.add_error(
                code="core.validate.manifest_path_invalid",
                message="Manifest contains invalid path-like references: {0}".format(rel),
                path=str(rel),
                details=", ".join(path_issues),
            )
            return ValidationItem(kind=kind, name=path.stem, path=str(rel), status="failed", details={"path_issues": path_issues})

        return ValidationItem(kind=kind, name=path.stem, path=str(rel), status="passed", details={"keys": sorted(payload)})

    def _validate_schema_like_json(self, path: Path, kind: str, diagnostics: DiagnosticCollection) -> ValidationItem:
        rel = path.relative_to(self.repo_root)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            diagnostics.add_error(
                code="core.validate.json_invalid",
                message="Invalid JSON file: {0}".format(rel),
                path=str(rel),
                details=str(exc),
            )
            return ValidationItem(kind=kind, name=path.stem, path=str(rel), status="failed")
        if not isinstance(payload, dict):
            diagnostics.add_error(
                code="core.validate.json_not_object",
                message="JSON file must be an object: {0}".format(rel),
                path=str(rel),
            )
            return ValidationItem(kind=kind, name=path.stem, path=str(rel), status="failed")
        return ValidationItem(kind=kind, name=path.stem, path=str(rel), status="passed", details={"keys": sorted(payload)})

    def _schema_version(self, payload: dict[str, Any]) -> str | None:
        properties = payload.get("properties")
        if isinstance(properties, dict):
            schema_version = properties.get("schema_version")
            if isinstance(schema_version, dict):
                const = schema_version.get("const")
                if isinstance(const, str) and const:
                    return const
        return None

    def _manifest_path_issues(self, payload: dict[str, Any]) -> list[str]:
        issues: list[str] = []
        for key, value in _walk_strings(payload):
            lower_key = key.lower()
            if not isinstance(value, str):
                continue
            if not any(token in lower_key for token in ("path", "file", "dir", "document", "artifact", "source", "output")):
                continue
            if value.startswith(("/", "\\")) or ".." in Path(value).parts:
                issues.append(f"{key}:absolute_or_traversal")
        return issues
