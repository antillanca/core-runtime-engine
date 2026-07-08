"""CLI command for bump-version — dry-run and controlled apply."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from core_runtime.tooling.bump_version import BumpVersionPlanner, validate_target_version
from core_runtime.tooling.diagnostics import DiagnosticCollection, ExitCode
from core_runtime.tooling.version_inventory import VersionInventory


def cmd_bump_version(args: object) -> int:
    """Execute the bump-version command (dry-run or controlled apply)."""
    # Access args safely (argparse Namespace or test mock)
    target_version_raw = getattr(args, "target_version", None)
    dry_run: bool = getattr(args, "dry_run", False)
    apply_mode: bool = getattr(args, "apply", False)
    confirm_current: str | None = getattr(args, "confirm_current", None)
    fmt: str = getattr(args, "format", "json")
    output = getattr(args, "output", None)

    diagnostics = DiagnosticCollection()

    # ---- Mutual exclusion: --dry-run and --apply cannot both be set ----
    if dry_run and apply_mode:
        blocked_msg = {
            "code": "core.bump_version.mutual_exclusion",
            "severity": "blocked",
            "message": "--dry-run and --apply are mutually exclusive. Specify one.",
            "mutation_allowed": False,
        }
        if fmt == "json":
            print(json.dumps(blocked_msg, indent=2, ensure_ascii=False))
        else:
            print("# BLOCKED")
            print("")
            print("--dry-run and --apply are mutually exclusive. Specify one.")
        return ExitCode.BLOCKED.value

    # ---- Default mode: if neither flag is set, default to dry-run ----
    if not dry_run and not apply_mode:
        dry_run = True

    # ---- Apply mode: --confirm-current is required ----
    if apply_mode and not confirm_current:
        blocked_msg = {
            "code": "core.bump_version.confirm_current_required",
            "severity": "blocked",
            "message": "--confirm-current is required when using --apply.",
            "mutation_allowed": False,
        }
        if fmt == "json":
            print(json.dumps(blocked_msg, indent=2, ensure_ascii=False))
        else:
            print("# BLOCKED")
            print("")
            print("--confirm-current is required when using --apply.")
            print("Usage: python -m core_runtime.cli bump-version <target> --apply --confirm-current <current>")
        return ExitCode.BLOCKED.value

    # Guard against None (argparse should always provide this)
    if target_version_raw is None:
        print("Error: target_version is required", file=sys.stderr)
        return ExitCode.INTERNAL_ERROR.value

    target_version: str = target_version_raw

    repo_root = Path(__file__).resolve().parents[2]  # core_runtime/cli/ -> repo_root

    # Discover current version before planning/applying
    version_inv = VersionInventory(repo_root)
    current_version = version_inv.get_canonical_version()
    if current_version is None:
        diagnostics.add_blocked(
            code="core.bump_version.canonical_missing",
            message="Cannot determine current canonical version",
            path="core_runtime/__version__.py",
        )
        base_report = {
            "tool": "core-runtime bump-version",
            "mode": "apply" if apply_mode else "dry-run",
            "status": "blocked",
            "mutation_performed": False,
            "current_version": None,
            "target_version": target_version,
            "summary": {"files_checked": 0, "files_that_would_change": 0,
                        "replacement_count": 0, "info": 0, "warning": 0,
                        "error": 0, "blocked": 1},
            "changes": [],
            "diagnostics": [d.to_dict() for d in diagnostics.diagnostics],
        }
        if fmt == "json":
            print(json.dumps(base_report, indent=2, ensure_ascii=False))
        else:
            print("# BLOCKED: Cannot determine current version")
        return ExitCode.BLOCKED.value

    planner = BumpVersionPlanner(repo_root)
    output_path = Path(output) if output else None

    # ================================================================
    # DRY-RUN MODE
    # ================================================================
    if dry_run:
        changes, summary = planner.plan(target_version, diagnostics)
        if fmt == "json":
            report = planner.report_json(
                target_version=target_version,
                current_version=current_version,
                changes=changes,
                summary=summary,
                diagnostics=diagnostics,
                output_path=output_path,
                mode="dry-run",
                mutation_performed=False,
            )
            if not output_path:
                print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            md = planner.report_markdown(
                target_version=target_version,
                current_version=current_version,
                changes=changes,
                summary=summary,
                diagnostics=diagnostics,
                output_path=output_path,
                mode="dry-run",
                mutation_performed=False,
            )
            if not output_path:
                print(md)
        return diagnostics.compute_exit_code().value

    # ================================================================
    # APPLY MODE
    # ================================================================
    if apply_mode:
        applied_changes, summary = planner.apply(
            target_version=target_version,
            confirm_current=confirm_current,  # type: ignore[arg-type]
            diagnostics=diagnostics,
        )
        if fmt == "json":
            report = planner.report_json(
                target_version=target_version,
                current_version=current_version,
                changes=[],  # not used in apply mode
                summary=summary,
                diagnostics=diagnostics,
                output_path=output_path,
                mode="apply",
                mutation_performed=(diagnostics.compute_exit_code() == ExitCode.OK),
                applied_changes=applied_changes,
            )
            if not output_path:
                print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            md = planner.report_markdown(
                target_version=target_version,
                current_version=current_version,
                changes=[],  # not used in apply mode
                summary=summary,
                diagnostics=diagnostics,
                output_path=output_path,
                mode="apply",
                mutation_performed=(diagnostics.compute_exit_code() == ExitCode.OK),
                applied_changes=applied_changes,
            )
            if not output_path:
                print(md)
        return diagnostics.compute_exit_code().value

    # Should never reach here
    return ExitCode.INTERNAL_ERROR.value
