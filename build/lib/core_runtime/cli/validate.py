"""CLI commands for read-only structural validation."""

from __future__ import annotations

import json
from pathlib import Path

from core_runtime.tooling.diagnostics import ExitCode
from core_runtime.tooling.validation import RepositoryValidation


_KIND_ALIASES = {
    "schema": "schemas",
    "schemas": "schemas",
    "example": "examples",
    "examples": "examples",
    "manifest": "manifests",
    "manifests": "manifests",
    "contract": "contracts",
    "contracts": "contracts",
    "domain": "domain",
    "domains": "domain",
}


def _normalize_kind(kind: str | None) -> str | None:
    if kind is None:
        return None
    return _KIND_ALIASES.get(kind.lower())


def _emit_report(report, fmt: str, output) -> None:
    payload = report.to_dict()
    if fmt == "json":
        text = json.dumps(payload, indent=2, ensure_ascii=False)
    else:
        text = report.to_markdown()
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + ("\n" if fmt == "json" else ""), encoding="utf-8")
    else:
        print(text)


def cmd_validate(args: object) -> int:
    """Run read-only structural validation."""
    raw_kind = getattr(args, "kind", None)
    name = getattr(args, "name", None)
    fmt: str = getattr(args, "format", "json")
    output = getattr(args, "output", None)
    repo_root = Path(__file__).resolve().parents[2]
    validator = RepositoryValidation(repo_root)

    kind = _normalize_kind(raw_kind)
    if raw_kind is not None and kind is None:
        kind = str(raw_kind)
    if kind is None:
        kind = "schemas"
    if kind == "domain" and not name and raw_kind not in (None, "domain", "domains"):
        name = str(raw_kind)
        kind = "domain"

    report = validator.build_report(kind=kind, name=name)
    _emit_report(report, fmt, output)
    return {
        "pass": ExitCode.OK.value,
        "warning": ExitCode.OK.value,
        "error": ExitCode.ERROR.value,
        "blocked": ExitCode.BLOCKED.value,
        "internal_error": ExitCode.INTERNAL_ERROR.value,
    }.get(report.status, ExitCode.INTERNAL_ERROR.value)

