"""CORE Tooling - internal tooling package for CORE maintenance commands."""

from __future__ import annotations

from core_runtime.tooling.bump_version import BumpVersionPlanner, PlannedChange, ReplacementRule
from core_runtime.tooling.diagnostics import (
    Diagnostic,
    DiagnosticCollection,
    ExitCode,
    Severity,
)
from core_runtime.tooling.file_inventory import FileInventory, REQUIRED_FILES, REQUIRED_DIRS
from core_runtime.tooling.json_checks import JSONChecks
from core_runtime.tooling.report_writer import ReportWriter
from core_runtime.tooling.release_check import (
    ReleaseCheckReport,
    ReleaseCheckRunner,
    SubprocessCapture,
    normalize_release_target,
    release_target_argument,
    validate_release_target,
)
from core_runtime.tooling.safety_checks import SafetyChecks
from core_runtime.tooling.version_inventory import VersionInventory, VersionSource

__all__ = [
    "BumpVersionPlanner",
    "Diagnostic",
    "DiagnosticCollection",
    "ExitCode",
    "PlannedChange",
    "ReplacementRule",
    "Severity",
    "FileInventory",
    "REQUIRED_FILES",
    "REQUIRED_DIRS",
    "JSONChecks",
    "ReleaseCheckReport",
    "ReleaseCheckRunner",
    "SubprocessCapture",
    "ReportWriter",
    "normalize_release_target",
    "release_target_argument",
    "validate_release_target",
    "SafetyChecks",
    "VersionInventory",
    "VersionSource",
]
