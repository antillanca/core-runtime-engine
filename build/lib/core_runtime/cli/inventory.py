"""CLI commands for read-only repository inventory navigation."""

from __future__ import annotations

import json
from pathlib import Path

from core_runtime.tooling.diagnostics import ExitCode
from core_runtime.tooling.repository_inventory import RepositoryInventory


_KIND_ALIASES = {
    "schema": "schemas",
    "schemas": "schemas",
    "contract": "contracts",
    "contracts": "contracts",
    "adapter": "adapters",
    "adapters": "adapters",
    "domain": "domains",
    "domains": "domains",
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


def cmd_list(args: object) -> int:
    """List repository inventory items by kind."""
    raw_kind = getattr(args, "kind", None)
    kind = _normalize_kind(raw_kind)
    fmt: str = getattr(args, "format", "json")
    output = getattr(args, "output", None)
    repo_root = Path(__file__).resolve().parents[2]
    inventory = RepositoryInventory(repo_root)

    if raw_kind is None:
        kind = "schemas"
    elif kind is None:
        kind = str(raw_kind)

    report = inventory.build_list_report(kind)
    _emit_report(report, fmt, output)
    return ExitCode.BLOCKED.value if report.status == "blocked" else ExitCode.OK.value


def cmd_info(args: object) -> int:
    """Show inventory summary or item details."""
    raw_kind = getattr(args, "kind", None)
    kind = _normalize_kind(raw_kind)
    name = getattr(args, "name", None)
    fmt: str = getattr(args, "format", "json")
    output = getattr(args, "output", None)
    repo_root = Path(__file__).resolve().parents[2]
    inventory = RepositoryInventory(repo_root)

    if raw_kind is not None and kind is None:
        kind = str(raw_kind)

    report = inventory.build_info_report(kind=kind, name=name)
    _emit_report(report, fmt, output)

    return {
        "pass": ExitCode.OK.value,
        "warning": ExitCode.OK.value,
        "error": ExitCode.ERROR.value,
        "blocked": ExitCode.BLOCKED.value,
        "internal_error": ExitCode.INTERNAL_ERROR.value,
    }.get(report.status, ExitCode.INTERNAL_ERROR.value)
