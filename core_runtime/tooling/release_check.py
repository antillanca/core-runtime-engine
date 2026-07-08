"""Release-check wrapper around the authoritative release verification script."""

from __future__ import annotations

import json
import py_compile
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from core_runtime.tooling.diagnostics import DiagnosticCollection
from core_runtime.tooling.version_inventory import VersionInventory

DEFAULT_RELEASE_CHECK_TIMEOUT_SECONDS = 120
OUTPUT_PREVIEW_LIMIT = 2048

RELEASE_CHECK_PROFILES: dict[str, dict[str, tuple[str, ...] | str]] = {
    "fast": {
        "description": "Tooling, metadata, and tooling-test baseline.",
        "groups": ("tooling", "release-metadata", "tests-tooling"),
        "notes": ("Fast developer signal with bounded deterministic checks.",),
    },
    "local": {
        "description": "Fast profile plus bounded developer test slices.",
        "groups": ("tooling", "release-metadata", "tests-tooling", "tests-replay", "tests-integration"),
        "notes": ("Useful for local iteration without the longest contracts/core slices.",),
    },
    "full": {
        "description": "Full deterministic release surface.",
        "groups": (
            "tooling",
            "release-metadata",
            "replay",
            "tests-tooling",
            "tests-replay",
            "tests-integration",
            "tests-contracts",
            "tests-core",
        ),
        "notes": ("Matches the current bounded full release gate.",),
    },
    "release-candidate": {
        "description": "Full release surface with future tag and package metadata expectations.",
        "groups": (
            "tooling",
            "release-metadata",
            "replay",
            "tests-tooling",
            "tests-replay",
            "tests-integration",
            "tests-contracts",
            "tests-core",
        ),
        "notes": (
            "Future package metadata and tag expectation checks remain advisory-only.",
        ),
    },
}

_STRICT_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def validate_release_target(target: str) -> Optional[str]:
    """Return None when *target* is a supported release target."""
    if target.startswith("v"):
        target = target[1:]
    if not _STRICT_VERSION_RE.match(target):
        return "Invalid release target: '{0}'. Expected MAJOR.MINOR.PATCH or vMAJOR.MINOR.PATCH.".format(
            target
        )
    return None


def normalize_release_target(target: str) -> str:
    """Normalize a target to the canonical release-check form."""
    return target[1:] if target.startswith("v") else target


def release_target_argument(target: str) -> str:
    """Format the normalized target for scripts/verify_release.py."""
    return "v{0}".format(normalize_release_target(target))


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _truncate_text(text: str, limit: int = OUTPUT_PREVIEW_LIMIT) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + "…[truncated]", True


@dataclass
class SubprocessCapture:
    """Captured subprocess execution details."""

    command: list[str]
    cwd: str
    expect_json: bool
    returncode: Optional[int]
    stdout: str
    stderr: str
    timed_out: bool = False
    timeout_seconds: Optional[int] = None
    elapsed_seconds: Optional[float] = None
    json_detected: bool = False
    json_payload: dict[str, Any] | None = None
    report_path: Optional[str] = None
    target_argument: Optional[str] = None
    help_contains_target: Optional[bool] = None
    stdout_preview: str = ""
    stderr_preview: str = ""
    stdout_truncated: bool = False
    stderr_truncated: bool = False

    @property
    def status(self) -> str:
        if self.timed_out:
            return "blocked"
        if self.returncode is None:
            return "internal_error"
        if self.returncode == 0:
            if self.expect_json and not self.json_detected:
                return "internal_error"
            return "pass"
        if self.returncode == 1:
            return "error"
        if self.returncode == 2:
            return "blocked"
        return "internal_error"

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "command": self.command,
            "cwd": self.cwd,
            "expect_json": self.expect_json,
            "exit_code": self.returncode,
            "json_detected": self.json_detected,
            "status": self.status,
            "report_path": self.report_path,
            "stdout_preview": self.stdout_preview,
            "stderr_preview": self.stderr_preview,
            "stdout_truncated": self.stdout_truncated,
            "stderr_truncated": self.stderr_truncated,
            "timed_out": self.timed_out,
            "timeout_seconds": self.timeout_seconds,
        }
        if self.elapsed_seconds is not None:
            result["elapsed_seconds"] = self.elapsed_seconds
        if self.target_argument is not None:
            result["target_argument"] = self.target_argument
        if self.help_contains_target is not None:
            result["help_contains_target"] = self.help_contains_target
        if self.json_payload is not None:
            result["json_payload"] = self.json_payload
        return result


@dataclass
class ReleaseCheckReport:
    """Normalized release-check wrapper report."""

    mode: str
    target: str
    target_argument: str
    timeout_seconds: int
    profile: Optional[str] = None
    tool: str = "core-runtime release-check"
    status: str = "internal_error"
    mutation_performed: bool = False
    summary: dict[str, Any] = field(default_factory=dict)
    diagnostics: DiagnosticCollection = field(default_factory=DiagnosticCollection)
    profile_definition: dict[str, Any] | None = None
    profile_runs: list[SubprocessCapture] = field(default_factory=list)
    tooling_lint: SubprocessCapture | None = None
    release_gate_help: SubprocessCapture | None = None
    release_gate: SubprocessCapture | None = None
    preflight_checks: dict[str, Any] = field(default_factory=dict)
    debug: dict[str, Any] | None = None

    def _summary(self) -> dict[str, Any]:
        summary = dict(self.summary)
        summary.setdefault("tooling_lint_status", self.tooling_lint.status if self.tooling_lint else "skipped")
        summary.setdefault("release_gate_status", self.release_gate.status if self.release_gate else "skipped")
        summary.setdefault("preflight_status", self.preflight_checks.get("status", "skipped"))
        counts = self.diagnostics.count_by_severity()
        summary.setdefault("info", counts["info"])
        summary.setdefault("warning", counts["warning"])
        summary.setdefault("error", counts["error"])
        summary.setdefault("blocked", counts["blocked"])
        return summary

    def to_dict(self) -> dict[str, Any]:
        result = {
            "tool": self.tool,
            "mode": self.mode,
            "target": self.target,
            "target_argument": self.target_argument,
            "profile": self.profile,
            "status": self.status,
            "mutation_performed": self.mutation_performed,
            "summary": self._summary(),
            "diagnostics": [d.to_dict() for d in self.diagnostics.diagnostics],
            "preflight_checks": self.preflight_checks,
            "timeout_seconds": self.timeout_seconds,
        }
        if self.profile_definition is not None:
            result["profile_definition"] = self.profile_definition
        if self.profile_runs:
            result["profile_runs"] = [capture.to_dict() for capture in self.profile_runs]
        if self.tooling_lint is not None:
            result["tooling_lint"] = self.tooling_lint.to_dict()
        if self.release_gate_help is not None:
            result["release_gate_help"] = self.release_gate_help.to_dict()
        if self.release_gate is not None:
            result["release_gate"] = self.release_gate.to_dict()
        if self.debug is not None:
            result["debug"] = self.debug
        return result

    def to_markdown(self) -> str:
        counts = self.diagnostics.count_by_severity()
        summary = self._summary()
        lines: list[str] = []
        lines.append("# CORE release-check report")
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append("| Tool | core-runtime release-check |")
        lines.append("| Mode | {0} |".format(self.mode))
        lines.append("| Profile | {0} |".format(self.profile or "none"))
        lines.append("| Target | {0} |".format(self.target))
        lines.append("| Target Argument | {0} |".format(self.target_argument))
        lines.append("| Status | {0} |".format(self.status.upper()))
        lines.append("| Mutation Performed | No |")
        lines.append("| Tooling Lint | {0} |".format(summary.get("tooling_lint_status", "skipped")))
        lines.append("| Release Gate | {0} |".format(summary.get("release_gate_status", "skipped")))
        lines.append("| Preflight | {0} |".format(summary.get("preflight_status", "skipped")))
        lines.append("| Info | {0} |".format(counts["info"]))
        lines.append("| Warning | {0} |".format(counts["warning"]))
        lines.append("| Error | {0} |".format(counts["error"]))
        lines.append("| Blocked | {0} |".format(counts["blocked"]))
        lines.append("")

        lines.append("## Target")
        lines.append("")
        lines.append("- Normalized target: `{0}`".format(self.target))
        lines.append("- Release gate argument: `{0}`".format(self.target_argument))
        lines.append("")

        lines.append("## Tooling Lint Precheck")
        lines.append("")
        if self.tooling_lint is None:
            lines.append("- Skipped by request.")
        else:
            lines.append("- Command: `{0}`".format(" ".join(self.tooling_lint.command)))
            lines.append("- cwd: `{0}`".format(self.tooling_lint.cwd))
            lines.append("- Exit code: `{0}`".format(self.tooling_lint.returncode))
            lines.append("- JSON detected: `{0}`".format("yes" if self.tooling_lint.json_detected else "no"))
            lines.append("- Status: `{0}`".format(self.tooling_lint.status))
        lines.append("")

        lines.append("## Preflight Checks")
        lines.append("")
        if self.preflight_checks:
            for key, value in self.preflight_checks.items():
                lines.append("- `{0}`: {1}".format(key, value))
        else:
            lines.append("- None")
        lines.append("")

        lines.append("## Profile")
        lines.append("")
        if self.profile_definition is None:
            lines.append("- None")
        else:
            lines.append("- Name: `{0}`".format(self.profile or ""))
            lines.append("- Description: {0}".format(self.profile_definition.get("description", "")))
            groups = self.profile_definition.get("groups", ())
            if groups:
                lines.append("- Groups: {0}".format(", ".join(f"`{group}`" for group in groups)))
            notes = self.profile_definition.get("notes", ())
            for note in notes:
                lines.append("- Note: {0}".format(note))
            if self.profile_runs:
                lines.append("- Runs:")
                for capture in self.profile_runs:
                    lines.append(
                        "  - `{0}` -> `{1}` ({2})".format(
                            " ".join(capture.command),
                            capture.status,
                            capture.elapsed_seconds if capture.elapsed_seconds is not None else "n/a",
                        )
                    )
        lines.append("")

        lines.append("## Release Gate")
        lines.append("")
        if self.release_gate is None:
            lines.append("- Not run.")
        else:
            lines.append("- Script: `scripts/verify_release.py`")
            lines.append("- Command: `{0}`".format(" ".join(self.release_gate.command)))
            lines.append("- cwd: `{0}`".format(self.release_gate.cwd))
            lines.append("- Exit code: `{0}`".format(self.release_gate.returncode))
            lines.append("- JSON detected: `{0}`".format("yes" if self.release_gate.json_detected else "no"))
            lines.append("- Timed out: `{0}`".format("yes" if self.release_gate.timed_out else "no"))
            lines.append("- Status: `{0}`".format(self.release_gate.status))
            lines.append("- Stdout preview: `{0}`".format(self.release_gate.stdout_preview or ""))
            lines.append("- Stderr preview: `{0}`".format(self.release_gate.stderr_preview or ""))
        lines.append("")

        lines.append("## Diagnostics")
        lines.append("")
        if self.diagnostics.diagnostics:
            for diagnostic in self.diagnostics.diagnostics:
                lines.append("- `{0}` {1}: {2}".format(diagnostic.severity.value, diagnostic.code, diagnostic.message))
        else:
            lines.append("- None")
        lines.append("")

        lines.append("## Final Status")
        lines.append("")
        if self.status == "pass":
            lines.append("✅ **PASS** - Release-check completed successfully.")
        elif self.status == "warning":
            lines.append("⚠️ **WARNING** - Release-check completed with warnings.")
        elif self.status == "error":
            lines.append("❌ **ERROR** - Release-check failed.")
        elif self.status == "blocked":
            lines.append("🚫 **BLOCKED** - Release-check could not safely run.")
        else:
            lines.append("⚠️ **INTERNAL ERROR** - Release-check tooling failure.")
        lines.append("")
        return "\n".join(lines)


class ReleaseCheckRunner:
    """Run tooling lint precheck and the authoritative release gate."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.version_inventory = VersionInventory(repo_root)

    def resolve_target(self, target: Optional[str]) -> tuple[str, str]:
        """Return (normalized_target, gate_argument)."""
        if target is None:
            canonical = self.version_inventory.get_canonical_version()
            if canonical is None:
                raise ValueError("canonical version missing")
            target = canonical

        normalized = normalize_release_target(target)
        error = validate_release_target(normalized)
        if error is not None:
            raise ValueError(error)

        return normalized, release_target_argument(normalized)

    def run(
        self,
        target: Optional[str] = None,
        skip_tooling_lint: bool = False,
        timeout_seconds: int = DEFAULT_RELEASE_CHECK_TIMEOUT_SECONDS,
        preflight_only: bool = False,
        debug: bool = False,
        group: Optional[str] = None,
        profile: Optional[str] = None,
        list_checks: bool = False,
        plan: bool = False,
        timing_json: Optional[str] = None,
    ) -> ReleaseCheckReport:
        """Execute the release-check workflow."""
        diagnostics = DiagnosticCollection()
        if list_checks and plan:
            diagnostics.add_blocked(
                code="core.release_check.invalid_mode",
                message="List-checks and plan modes cannot be combined.",
                path="core_runtime.cli release-check",
            )
            report = ReleaseCheckReport(
                mode="blocked",
                target="",
                target_argument="",
                timeout_seconds=timeout_seconds,
                diagnostics=diagnostics,
                status="blocked",
            )
            return report

        if profile and group:
            diagnostics.add_blocked(
                code="core.release_check.invalid_mode",
                message="Profile and group modes cannot be combined.",
                path="core_runtime.cli release-check",
            )
            report = ReleaseCheckReport(
                mode="blocked",
                target="",
                target_argument="",
                timeout_seconds=timeout_seconds,
                diagnostics=diagnostics,
                status="blocked",
            )
            return report

        if profile and preflight_only:
            diagnostics.add_blocked(
                code="core.release_check.invalid_mode",
                message="Profile and preflight-only modes cannot be combined.",
                path="core_runtime.cli release-check",
            )
            report = ReleaseCheckReport(
                mode="blocked",
                target="",
                target_argument="",
                timeout_seconds=timeout_seconds,
                diagnostics=diagnostics,
                status="blocked",
            )
            return report

        if profile and profile not in RELEASE_CHECK_PROFILES:
            diagnostics.add_blocked(
                code="core.release_check.profile_unknown",
                message="Unknown release-check profile.",
                path="core_runtime.cli release-check",
                details={"profile": profile, "allowed_profiles": sorted(RELEASE_CHECK_PROFILES)},
            )
            report = ReleaseCheckReport(
                mode="blocked",
                target="",
                target_argument="",
                timeout_seconds=timeout_seconds,
                diagnostics=diagnostics,
                status="blocked",
            )
            return report

        if list_checks:
            mode = "list-checks"
        elif plan:
            mode = "plan"
        elif profile:
            mode = f"profile:{profile}"
        elif group:
            mode = f"group:{group}"
        elif preflight_only:
            mode = "preflight-only"
        else:
            mode = "full"
        report = ReleaseCheckReport(
            mode=mode,
            target="",
            target_argument="",
            timeout_seconds=timeout_seconds,
            profile=profile,
            diagnostics=diagnostics,
        )

        try:
            normalized_target, gate_target_argument = self.resolve_target(target)
        except ValueError as exc:
            diagnostics.add_blocked(
                code="core.release_check.invalid_target",
                message=str(exc),
                path="target",
            )
            report.status = "blocked"
            report.preflight_checks["status"] = "blocked"
            report.target = normalize_release_target(target) if target else (self.version_inventory.get_canonical_version() or "")
            return report

        report.target = normalized_target
        report.target_argument = gate_target_argument
        report.preflight_checks["canonical_version"] = self.version_inventory.get_canonical_version()
        report.preflight_checks["target_argument"] = gate_target_argument
        report.preflight_checks["target_valid"] = True
        if profile:
            profile_definition = self._profile_definition(profile)
            report.profile_definition = profile_definition
            report.preflight_checks["profile"] = profile
            report.preflight_checks["profile_groups"] = list(profile_definition["groups"])
            report.preflight_checks["profile_description"] = profile_definition["description"]

        if not skip_tooling_lint:
            lint_capture = self._run_tooling_lint(timeout_seconds)
            report.tooling_lint = lint_capture
            report.preflight_checks["tooling_lint"] = lint_capture.status
            if lint_capture.status == "blocked":
                diagnostics.add_blocked(
                    code="core.release_check.tooling_lint_blocked",
                    message="Tooling lint precheck was blocked; release gate not run.",
                    path="core_runtime.cli lint",
                )
                report.preflight_checks["status"] = "blocked"
                report.status = "blocked"
                return report
            if lint_capture.status == "error":
                diagnostics.add_error(
                    code="core.release_check.tooling_lint_failed",
                    message="Tooling lint precheck failed; release gate not run.",
                    path="core_runtime.cli lint",
                    details="exit_code={0}".format(lint_capture.returncode),
                )
                report.preflight_checks["status"] = "error"
                report.status = "error"
                return report
            if lint_capture.status == "internal_error":
                diagnostics.add_error(
                    code="core.release_check.tooling_lint_internal_error",
                    message="Tooling lint precheck had an internal error; release gate not run.",
                    path="core_runtime.cli lint",
                    details="exit_code={0}".format(lint_capture.returncode),
                )
                report.preflight_checks["status"] = "internal_error"
                report.status = "internal_error"
                return report
            lint_summary = lint_capture.json_payload.get("summary", {}) if lint_capture.json_payload else {}
            warnings = int(lint_summary.get("warning", 0) or 0)
            if warnings:
                diagnostics.add_warning(
                    code="core.release_check.tooling_lint_warning",
                    message="Tooling lint completed with warnings.",
                    path="core_runtime.cli lint",
                    details="warning_count={0}".format(warnings),
                )
                report.preflight_checks["tooling_lint_warnings"] = warnings
            else:
                report.preflight_checks["tooling_lint_warnings"] = 0
        else:
            report.preflight_checks["tooling_lint"] = "skipped"
            report.preflight_checks["tooling_lint_warnings"] = None

        script_path = self.repo_root / "scripts" / "verify_release.py"
        report.preflight_checks["script_path"] = str(script_path)
        script_preflight = self._check_release_script(
            script_path,
            gate_target_argument,
            timeout_seconds,
            require_help=preflight_only,
            debug=debug,
        )
        report.release_gate_help = script_preflight["help_capture"]
        report.preflight_checks["script_exists"] = script_preflight["script_exists"]
        report.preflight_checks["script_compiles"] = script_preflight["script_compiles"]
        report.preflight_checks["help_status"] = script_preflight["help_status"]
        report.preflight_checks["help_contains_target"] = script_preflight["help_contains_target"]

        if script_preflight["status"] != "pass":
            for diagnostic in script_preflight["diagnostics"]:
                diagnostics.add(diagnostic)
            report.preflight_checks["status"] = script_preflight["status"]
            report.status = script_preflight["status"]
            self._finalize_status(report)
            return report

        if preflight_only:
            report.preflight_checks["status"] = "pass"
            self._finalize_status(report)
            return report

        if list_checks or plan:
            gate_capture = self._run_release_gate(
                script_path,
                gate_target_argument,
                timeout_seconds,
                group=group,
                list_checks=list_checks,
                plan=plan,
                timing_json=timing_json,
            )
            report.release_gate = gate_capture
            report.preflight_checks["status"] = "pass"
            report.preflight_checks["release_gate"] = gate_capture.status
            self._finalize_status(report)
            return report

        if profile:
            profile_groups = list(report.profile_definition.get("groups", ())) if report.profile_definition else []
            capture = None
            for selected_group in profile_groups:
                capture = self._run_release_gate(
                    script_path,
                    gate_target_argument,
                    timeout_seconds,
                    group=selected_group,
                    list_checks=list_checks,
                    plan=plan,
                    timing_json=timing_json,
                )
                report.profile_runs.append(capture)
                report.release_gate = capture
                if capture.timed_out:
                    diagnostics.add_blocked(
                        code="core.release_check.profile_group_timeout",
                        message="Release profile subgroup did not complete within the configured timeout.",
                        path="scripts/verify_release.py",
                        details={"profile": profile, "group": selected_group, "timeout_seconds": timeout_seconds},
                    )
                    break
                if capture.status == "blocked":
                    diagnostics.add_blocked(
                        code="core.release_check.profile_group_blocked",
                        message="Release profile subgroup returned a blocked result.",
                        path="scripts/verify_release.py",
                        details={"profile": profile, "group": selected_group, "exit_code": capture.returncode},
                    )
                    break
                if capture.status == "error":
                    diagnostics.add_error(
                        code="core.release_check.profile_group_failed",
                        message="Release profile subgroup returned a failing result.",
                        path="scripts/verify_release.py",
                        details={"profile": profile, "group": selected_group, "exit_code": capture.returncode},
                    )
                    break
                if capture.status == "internal_error":
                    diagnostics.add_error(
                        code="core.release_check.profile_group_internal_error",
                        message="Release profile subgroup had an internal error.",
                        path="scripts/verify_release.py",
                        details={"profile": profile, "group": selected_group, "exit_code": capture.returncode},
                    )
                    break
            if capture is None:
                diagnostics.add_blocked(
                    code="core.release_check.profile_empty",
                    message="Release profile did not resolve to any groups.",
                    path="core_runtime.cli release-check",
                    details={"profile": profile},
                )
            report.preflight_checks["status"] = "pass"
        else:
            gate_capture = self._run_release_gate(
                script_path,
                gate_target_argument,
                timeout_seconds,
                group=group,
                list_checks=list_checks,
                plan=plan,
                timing_json=timing_json,
            )
            report.release_gate = gate_capture
            report.preflight_checks["status"] = "pass"
            report.preflight_checks["release_gate"] = gate_capture.status
            if gate_capture.timed_out:
                diagnostics.add_blocked(
                    code="core.release_check.timeout",
                    message="Release gate did not complete within the configured timeout.",
                    path="scripts/verify_release.py",
                    details={
                        "timeout_seconds": timeout_seconds,
                        "script": "scripts/verify_release.py",
                    },
                )
            elif gate_capture.status == "blocked":
                diagnostics.add_blocked(
                    code="core.release_check.release_gate_blocked",
                    message="Release gate returned a blocked result.",
                    path="scripts/verify_release.py",
                    details="exit_code={0}".format(gate_capture.returncode),
                )
            elif gate_capture.status == "error":
                diagnostics.add_error(
                    code="core.release_check.release_gate_failed",
                    message="Release gate returned a failing result.",
                    path="scripts/verify_release.py",
                    details="exit_code={0}".format(gate_capture.returncode),
                )
            elif gate_capture.status == "internal_error":
                diagnostics.add_error(
                    code="core.release_check.release_gate_internal_error",
                    message="Release gate subprocess had an internal error.",
                    path="scripts/verify_release.py",
                    details="exit_code={0}".format(gate_capture.returncode),
                )

        if debug:
            report.debug = {
                "tooling_lint_command": report.tooling_lint.command if report.tooling_lint else None,
                "release_gate_help_command": report.release_gate_help.command if report.release_gate_help else None,
                "release_gate_command": report.release_gate.command if report.release_gate else None,
                "release_gate_cwd": report.release_gate.cwd if report.release_gate else None,
                "release_gate_target_argument": gate_target_argument,
                "timeout_seconds": timeout_seconds,
                "elapsed_seconds": report.release_gate.elapsed_seconds if report.release_gate else None,
                "stdout_preview": report.release_gate.stdout_preview if report.release_gate else "",
                "stderr_preview": report.release_gate.stderr_preview if report.release_gate else "",
            }

        self._finalize_status(report)
        return report

    def _finalize_status(self, report: ReleaseCheckReport) -> None:
        counts = report.diagnostics.count_by_severity()
        report.summary.update(
            {
                "info": counts["info"],
                "warning": counts["warning"],
                "error": counts["error"],
                "blocked": counts["blocked"],
                "tooling_lint_status": report.tooling_lint.status if report.tooling_lint else report.summary.get("tooling_lint_status", "skipped"),
                "release_gate_status": report.release_gate.status if report.release_gate else report.summary.get("release_gate_status", "skipped"),
                "preflight_status": report.preflight_checks.get("status", "skipped"),
                "release_gate_target_argument": report.target_argument,
            }
        )
        if report.diagnostics.has_blocked():
            report.status = "blocked"
        elif report.diagnostics.has_errors():
            report.status = "error"
        elif counts["warning"] > 0:
            report.status = "warning"
        else:
            report.status = "pass"

    def _profile_definition(self, profile: str) -> dict[str, Any]:
        definition = RELEASE_CHECK_PROFILES[profile]
        return {
            "name": profile,
            "description": definition["description"],
            "groups": tuple(definition["groups"]),
            "notes": tuple(definition["notes"]),
        }

    def _check_release_script(
        self,
        script_path: Path,
        target_argument: str,
        timeout_seconds: int,
        require_help: bool,
        debug: bool,
    ) -> dict[str, Any]:
        diagnostics = []
        help_capture: SubprocessCapture | None = None

        if not script_path.exists():
            diagnostics.append(
                self._blocked_diagnostic(
                    code="core.release_check.release_script_missing",
                    message="Release gate script is missing.",
                    path=str(script_path.relative_to(self.repo_root)) if script_path.is_relative_to(self.repo_root) else str(script_path),
                )
            )
            return {
                "status": "blocked",
                "script_exists": False,
                "script_compiles": False,
                "help_status": "skipped",
                "help_contains_target": False,
                "help_capture": None,
                "diagnostics": diagnostics,
            }

        try:
            py_compile.compile(str(script_path), doraise=True)
        except py_compile.PyCompileError as exc:
            diagnostics.append(
                self._blocked_diagnostic(
                    code="core.release_check.release_script_compile_error",
                    message="Release gate script failed to compile.",
                    path="scripts/verify_release.py",
                    details=str(exc.msg),
                )
            )
            return {
                "status": "blocked",
                "script_exists": True,
                "script_compiles": False,
                "help_status": "skipped",
                "help_contains_target": False,
                "help_capture": None,
                "diagnostics": diagnostics,
            }

        if require_help:
            help_cmd = [sys.executable, str(script_path), "--help"]
            help_capture = self._run_command(help_cmd, timeout_seconds=timeout_seconds, expect_json=False)
            help_text = "{0}\n{1}".format(help_capture.stdout, help_capture.stderr)
            help_contains_target = "--target" in help_text
            help_capture.help_contains_target = help_contains_target
            if help_capture.status != "pass":
                diagnostics.append(
                    self._blocked_diagnostic(
                        code="core.release_check.help_check_failed",
                        message="Release gate help did not complete successfully.",
                        path="scripts/verify_release.py",
                        details={
                            "timeout_seconds": timeout_seconds,
                            "script": "scripts/verify_release.py",
                        },
                    )
                )
                return {
                    "status": "blocked",
                    "script_exists": True,
                    "script_compiles": True,
                    "help_status": help_capture.status,
                    "help_contains_target": help_contains_target,
                    "help_capture": help_capture,
                    "diagnostics": diagnostics,
                }

            if not help_contains_target:
                diagnostics.append(
                    self._blocked_diagnostic(
                        code="core.release_check.target_mapping_unverified",
                        message="Release gate help output does not advertise the expected target argument.",
                        path="scripts/verify_release.py",
                        details={
                            "expected": "vMAJOR.MINOR.PATCH",
                            "observed": "help output missing --target",
                        },
                    )
                )
                return {
                    "status": "blocked",
                    "script_exists": True,
                    "script_compiles": True,
                    "help_status": help_capture.status,
                    "help_contains_target": help_contains_target,
                    "help_capture": help_capture,
                    "diagnostics": diagnostics,
                }

            if debug:
                help_capture.stdout_preview, help_capture.stdout_truncated = _truncate_text(help_capture.stdout)
                help_capture.stderr_preview, help_capture.stderr_truncated = _truncate_text(help_capture.stderr)

            return {
                "status": "pass",
                "script_exists": True,
                "script_compiles": True,
                "help_status": help_capture.status,
                "help_contains_target": help_contains_target,
                "help_capture": help_capture,
                "diagnostics": diagnostics,
            }

        return {
            "status": "pass",
            "script_exists": True,
            "script_compiles": True,
            "help_status": "skipped",
            "help_contains_target": None,
            "help_capture": None,
            "diagnostics": diagnostics,
        }

    def _run_tooling_lint(self, timeout_seconds: int) -> SubprocessCapture:
        cmd = [
            sys.executable,
            "-m",
            "core_runtime.cli",
            "lint",
            "--scope",
            "tooling",
            "--format",
            "json",
        ]
        return self._run_command(cmd, timeout_seconds=timeout_seconds, expect_json=True)

    def _run_release_gate(
        self,
        script_path: Path,
        target_argument: str,
        timeout_seconds: int,
        group: Optional[str] = None,
        list_checks: bool = False,
        plan: bool = False,
        timing_json: Optional[str] = None,
    ) -> SubprocessCapture:
        cmd = [
            sys.executable,
            str(script_path),
            "--target",
            target_argument,
        ]
        if group:
            cmd.extend(["--group", group])
        if list_checks:
            cmd.append("--list-checks")
        if plan:
            cmd.append("--plan")
        if timing_json:
            cmd.extend(["--timing-json", timing_json])
        capture = self._run_command(cmd, timeout_seconds=timeout_seconds, expect_json=True, target_argument=target_argument)
        if capture.json_payload is not None and isinstance(capture.json_payload, dict):
            report_path = capture.json_payload.get("report_path")
            if isinstance(report_path, str):
                capture.report_path = report_path
        return capture

    def _run_command(
        self,
        command: list[str],
        timeout_seconds: int,
        expect_json: bool,
        target_argument: Optional[str] = None,
    ) -> SubprocessCapture:
        cwd = str(self.repo_root)
        start = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=self.repo_root,
                input="",
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
            elapsed = time.monotonic() - start
            stdout = _coerce_text(completed.stdout)
            stderr = _coerce_text(completed.stderr)
            json_payload: dict[str, Any] | None = None
            json_detected = False
            if expect_json and stdout.strip():
                try:
                    json_payload = json.loads(stdout)
                    json_detected = True
                except json.JSONDecodeError:
                    json_payload = None

            stdout_preview, stdout_truncated = _truncate_text(stdout)
            stderr_preview, stderr_truncated = _truncate_text(stderr)
            return SubprocessCapture(
                command=command,
                cwd=cwd,
                expect_json=expect_json,
                returncode=completed.returncode,
                stdout=stdout,
                stderr=stderr,
                timed_out=False,
                timeout_seconds=timeout_seconds,
                elapsed_seconds=elapsed,
                json_detected=json_detected,
                json_payload=json_payload,
                report_path=None,
                target_argument=target_argument,
                stdout_preview=stdout_preview,
                stderr_preview=stderr_preview,
                stdout_truncated=stdout_truncated,
                stderr_truncated=stderr_truncated,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = time.monotonic() - start
            stdout = _coerce_text(exc.output)
            stderr = _coerce_text(exc.stderr)
            stdout_preview, stdout_truncated = _truncate_text(stdout)
            stderr_preview, stderr_truncated = _truncate_text(stderr)
            return SubprocessCapture(
                command=command,
                cwd=cwd,
                expect_json=expect_json,
                returncode=None,
                stdout=stdout,
                stderr=stderr,
                timed_out=True,
                timeout_seconds=timeout_seconds,
                elapsed_seconds=elapsed,
                json_detected=False,
                json_payload=None,
                report_path=None,
                target_argument=target_argument,
                stdout_preview=stdout_preview,
                stderr_preview=stderr_preview,
                stdout_truncated=stdout_truncated,
                stderr_truncated=stderr_truncated,
            )
        except (FileNotFoundError, OSError) as exc:
            elapsed = time.monotonic() - start
            stderr = str(exc)
            stdout_preview, stdout_truncated = _truncate_text("")
            stderr_preview, stderr_truncated = _truncate_text(stderr)
            return SubprocessCapture(
                command=command,
                cwd=cwd,
                expect_json=expect_json,
                returncode=None,
                stdout="",
                stderr=stderr,
                timed_out=False,
                timeout_seconds=timeout_seconds,
                elapsed_seconds=elapsed,
                json_detected=False,
                json_payload=None,
                report_path=None,
                target_argument=target_argument,
                stdout_preview=stdout_preview,
                stderr_preview=stderr_preview,
                stdout_truncated=stdout_truncated,
                stderr_truncated=stderr_truncated,
            )

    def _blocked_diagnostic(
        self,
        code: str,
        message: str,
        path: str,
        details: Any = None,
    ):
        diag = DiagnosticCollection()
        diag.add_blocked(code=code, message=message, path=path, details=details)
        return diag.diagnostics[-1]
