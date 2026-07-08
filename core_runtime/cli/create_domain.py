"""CLI command for `core-runtime create-domain`."""

from __future__ import annotations

import json
from pathlib import Path

from core_runtime.tooling.create_domain import CreateDomainReport, DomainScaffolder
from core_runtime.tooling.diagnostics import DiagnosticCollection, ExitCode


def cmd_create_domain(args: object) -> int:
    """Execute the dry-run-first domain scaffolding preflight."""
    fmt: str = getattr(args, "format", "json")
    output = getattr(args, "output", None)
    name = getattr(args, "name", None)
    template = getattr(args, "template", "generic")
    dry_run = bool(getattr(args, "dry_run", False))
    repo_root = Path(__file__).resolve().parents[2]
    scaffolder = DomainScaffolder(repo_root)

    if not dry_run:
        diagnostics = DiagnosticCollection()
        diagnostics.add_blocked(
            code="core.create_domain.dry_run_required",
            message="create-domain is dry-run only in this slice",
            path=name or "create-domain",
            expected="--dry-run",
            actual="missing dry-run",
        )
        report = CreateDomainReport(
            tool="core-runtime create-domain",
            command="create-domain {0}".format(name or ""),
            status="blocked",
            summary={"mode": "missing_dry_run", "item_count": 0},
            selection={"domain": name, "template": template, "mode": "missing_dry_run"},
            diagnostics=diagnostics,
        )
    else:
        report = scaffolder.build_plan(name=name, template=template)

    output_path = Path(output) if output else None
    if fmt == "json":
        payload = report.to_dict()
        text = json.dumps(payload, indent=2, ensure_ascii=False)
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(text + "\n", encoding="utf-8")
        else:
            print(text)
    else:
        markdown = report.to_markdown()
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(markdown, encoding="utf-8")
        else:
            print(markdown)

    status_to_exit = {
        "pass": ExitCode.OK.value,
        "warning": ExitCode.OK.value,
        "error": ExitCode.ERROR.value,
        "blocked": ExitCode.BLOCKED.value,
        "internal_error": ExitCode.INTERNAL_ERROR.value,
    }
    return status_to_exit.get(report.status, ExitCode.INTERNAL_ERROR.value)
