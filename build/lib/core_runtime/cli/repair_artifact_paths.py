"""CLI command for artifact path repair preflight."""

from __future__ import annotations

import json
from pathlib import Path

from core_runtime.tooling.diagnostics import ExitCode
from core_runtime.tooling.repair_artifact_paths import ArtifactPathRepairPlanner


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


def cmd_repair_artifact_paths(args: object) -> int:
    """Plan artifact path repairs without mutating the repository."""
    repo_root = Path(__file__).resolve().parents[2]
    planner = ArtifactPathRepairPlanner(repo_root)

    report = planner.build_plan(
        dry_run=getattr(args, "dry_run", False),
        source=getattr(args, "source_path", None),
        destination=getattr(args, "destination_path", None),
        manifest_path=getattr(args, "manifest", None),
        apply=getattr(args, "apply", False),
    )
    fmt: str = getattr(args, "format", "json")
    output = getattr(args, "output", None)
    _emit_report(report, fmt, output)

    return {
        "pass": ExitCode.OK.value,
        "warning": ExitCode.OK.value,
        "error": ExitCode.ERROR.value,
        "blocked": ExitCode.BLOCKED.value,
        "internal_error": ExitCode.INTERNAL_ERROR.value,
    }.get(report.status, ExitCode.INTERNAL_ERROR.value)
