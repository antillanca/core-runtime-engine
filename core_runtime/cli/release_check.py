"""CLI command for release-check — wrapper around verify_release.py."""

from __future__ import annotations

import json
from pathlib import Path

from core_runtime.tooling.diagnostics import ExitCode
from core_runtime.tooling.release_check import ReleaseCheckRunner


def cmd_release_check(args: object) -> int:
    """Execute the release-check command."""
    target = getattr(args, "target", None)
    fmt: str = getattr(args, "format", "json")
    output = getattr(args, "output", None)
    skip_tooling_lint: bool = getattr(args, "skip_tooling_lint", False)
    timeout_seconds: int = int(getattr(args, "timeout", 120))
    preflight_only: bool = getattr(args, "preflight_only", False)
    debug: bool = getattr(args, "debug", False)
    group = getattr(args, "group", None)
    profile = getattr(args, "profile", None)
    list_checks: bool = getattr(args, "list_checks", False)
    plan: bool = getattr(args, "plan", False)
    timing_json = getattr(args, "timing_json", None)

    repo_root = Path(__file__).resolve().parents[2]
    runner = ReleaseCheckRunner(repo_root)
    report = runner.run(
        target=target,
        skip_tooling_lint=skip_tooling_lint,
        timeout_seconds=timeout_seconds,
        preflight_only=preflight_only,
        debug=debug,
        group=group,
        profile=profile,
        list_checks=list_checks,
        plan=plan,
        timing_json=timing_json,
    )
    output_path = Path(output) if output else None

    if fmt == "json":
        payload = report.to_dict()
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        else:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
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
