"""Diagnostic data structures and severity handling for CORE tooling."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Severity(str, Enum):
    """Diagnostic severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCKED = "blocked"

    def exit_code_weight(self) -> int:
        """Return the weight for exit code computation."""
        return {
            Severity.INFO: 0,
            Severity.WARNING: 0,
            Severity.ERROR: 1,
            Severity.BLOCKED: 2,
        }[self]


class ExitCode(Enum):
    """Exit codes for lint command."""

    OK = 0
    ERROR = 1
    BLOCKED = 2
    INTERNAL_ERROR = 3


@dataclass(frozen=True, order=False)
class Diagnostic:
    """A single diagnostic result from a check."""

    code: str
    severity: Severity
    message: str
    mutation_allowed: bool
    path: Optional[str] = None
    expected: Optional[str] = None
    actual: Optional[str] = None
    details: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "mutation_allowed": self.mutation_allowed,
        }
        if self.path is not None:
            result["path"] = self.path
        if self.expected is not None:
            result["expected"] = self.expected
        if self.actual is not None:
            result["actual"] = self.actual
        if self.details is not None:
            result["details"] = self.details
        return result


@dataclass
class DiagnosticCollection:
    """Collection of diagnostics with summary statistics."""

    diagnostics: list[Diagnostic] = field(default_factory=list)

    def add(self, diagnostic: Diagnostic) -> None:
        """Add a diagnostic."""
        self.diagnostics.append(diagnostic)

    def add_error(self, code: str, message: str, path: Optional[str] = None, **kwargs: Any) -> None:
        """Add an error severity diagnostic."""
        self.add(Diagnostic(code=code, severity=Severity.ERROR, message=message, path=path, mutation_allowed=False, **kwargs))

    def add_warning(self, code: str, message: str, path: Optional[str] = None, **kwargs: Any) -> None:
        """Add a warning severity diagnostic."""
        self.add(Diagnostic(code=code, severity=Severity.WARNING, message=message, path=path, mutation_allowed=False, **kwargs))

    def add_info(self, code: str, message: str, path: Optional[str] = None, **kwargs: Any) -> None:
        """Add an info severity diagnostic."""
        self.add(Diagnostic(code=code, severity=Severity.INFO, message=message, path=path, mutation_allowed=False, **kwargs))

    def add_blocked(self, code: str, message: str, path: Optional[str] = None, **kwargs: Any) -> None:
        """Add a blocked severity diagnostic."""
        self.add(Diagnostic(code=code, severity=Severity.BLOCKED, message=message, path=path, mutation_allowed=False, **kwargs))

    def count_by_severity(self) -> dict[str, int]:
        """Count diagnostics by severity."""
        counts = {s.value: 0 for s in Severity}
        for d in self.diagnostics:
            counts[d.severity.value] += 1
        return counts

    def has_errors(self) -> bool:
        """Check if any error or blocked diagnostics exist."""
        return any(d.severity in (Severity.ERROR, Severity.BLOCKED) for d in self.diagnostics)

    def has_blocked(self) -> bool:
        """Check if any blocked diagnostics exist."""
        return any(d.severity == Severity.BLOCKED for d in self.diagnostics)

    def compute_exit_code(self) -> ExitCode:
        """Compute exit code based on diagnostics."""
        if not self.diagnostics:
            return ExitCode.OK

        has_errors = any(d.severity == Severity.ERROR for d in self.diagnostics)
        has_blocked = any(d.severity == Severity.BLOCKED for d in self.diagnostics)

        if has_blocked:
            return ExitCode.BLOCKED
        if has_errors:
            return ExitCode.ERROR
        return ExitCode.OK

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "summary": self.count_by_severity(),
        }