"""CLI command for `core-runtime sync-template`."""

from __future__ import annotations

import json
from pathlib import Path

from core_runtime.tooling.diagnostics import DiagnosticCollection, ExitCode
from core_runtime.tooling.sync_template import SyncTemplateReport, TemplateSyncPlanner


def cmd_sync_template(args: object) -> int:
    """Execute the dry-run template synchronization planner."""
    fmt: str = getattr(args, "format", "json")
    output = getattr(args, "output", None)
    domain = getattr(args, "domain", None)
    all_domains = bool(getattr(args, "all", False))
    template = getattr(args, "template", "generic")
    dry_run = bool(getattr(args, "dry_run", False))
    repo_root = Path(__file__).resolve().parents[2]
    planner = TemplateSyncPlanner(repo_root)

    if not dry_run:
        diagnostics = DiagnosticCollection()
        diagnostics.add_blocked(
            code="core.sync_template.dry_run_required",
            message="sync-template is dry-run only in this slice",
            path=domain or "sync-template",
            expected="--dry-run",
            actual="missing dry-run",
        )
        report = SyncTemplateReport(
            tool="core-runtime sync-template",
            command=planner._command(domain=domain, all_domains=all_domains),
            status="blocked",
            summary={"mode": "missing_dry_run", "item_count": 0},
            selection={"domain": domain, "all": all_domains, "template": template, "mode": "missing_dry_run"},
            diagnostics=diagnostics,
        )
    else:
        report = planner.build_plan(domain=domain, all_domains=all_domains, template=template)

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
