"""Tests for core_runtime.tooling.tooling.diagnostics."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


from core_runtime.cli.main import check_stale_docs
from core_runtime.tooling.diagnostics import (
    Diagnostic,
    DiagnosticCollection,
    ExitCode,
    Severity,
)
from core_runtime.tooling.safety_checks import SafetyChecks


class TestSeverity:
    def test_severity_values(self):
        assert Severity.INFO.value == "info"
        assert Severity.WARNING.value == "warning"
        assert Severity.ERROR.value == "error"
        assert Severity.BLOCKED.value == "blocked"

    def test_exit_code_weight(self):
        assert Severity.INFO.exit_code_weight() == 0
        assert Severity.WARNING.exit_code_weight() == 0
        assert Severity.ERROR.exit_code_weight() == 1
        assert Severity.BLOCKED.exit_code_weight() == 2


class TestExitCode:
    def test_exit_code_values(self):
        assert ExitCode.OK.value == 0
        assert ExitCode.ERROR.value == 1
        assert ExitCode.BLOCKED.value == 2
        assert ExitCode.INTERNAL_ERROR.value == 3


class TestDiagnostic:
    def test_diagnostic_creation(self):
        d = Diagnostic(
            code="test.code",
            severity=Severity.ERROR,
            message="Test message",
            mutation_allowed=False,
            path="test/path.py",
            expected="1.0.0",
            actual="2.0.0",
        )
        assert d.code == "test.code"
        assert d.severity == Severity.ERROR
        assert d.path == "test/path.py"
        assert d.expected == "1.0.0"
        assert d.actual == "2.0.0"

    def test_diagnostic_to_dict(self):
        d = Diagnostic(
            code="test.code",
            severity=Severity.WARNING,
            message="Test message",
            mutation_allowed=False,
        )
        data = d.to_dict()
        assert data["code"] == "test.code"
        assert data["severity"] == "warning"
        assert data["message"] == "Test message"
        assert data["mutation_allowed"] is False
        assert "path" not in data


class TestDiagnosticCollection:
    def test_empty_collection(self):
        coll = DiagnosticCollection()
        assert coll.count_by_severity() == {"info": 0, "warning": 0, "error": 0, "blocked": 0}
        assert not coll.has_errors()
        assert not coll.has_blocked()
        assert coll.compute_exit_code() == ExitCode.OK

    def test_add_diagnostics(self):
        coll = DiagnosticCollection()
        coll.add_error("code1", "Error message", "path1.py")
        coll.add_warning("code2", "Warning message", "path2.py")
        coll.add_info("code3", "Info message")

        counts = coll.count_by_severity()
        assert counts["error"] == 1
        assert counts["warning"] == 1
        assert counts["info"] == 1
        assert counts["blocked"] == 0

    def test_exit_code_computation(self):
        # No errors/blocked -> OK
        coll = DiagnosticCollection()
        coll.add_info("code", "Info")
        assert coll.compute_exit_code() == ExitCode.OK

        # Error -> ERROR
        coll = DiagnosticCollection()
        coll.add_error("code", "Error")
        assert coll.compute_exit_code() == ExitCode.ERROR

        # Blocked -> BLOCKED (takes precedence over error)
        coll = DiagnosticCollection()
        coll.add_blocked("code", "Blocked")
        coll.add_error("code2", "Error")
        assert coll.compute_exit_code() == ExitCode.BLOCKED

        # Only warning -> OK
        coll = DiagnosticCollection()
        coll.add_warning("code", "Warning")
        assert coll.compute_exit_code() == ExitCode.OK

    def test_to_dict(self):
        coll = DiagnosticCollection()
        coll.add_error("test.code", "Test error", "test.py", expected="1.0.0", actual="2.0.0")
        data = coll.to_dict()
        assert "diagnostics" in data
        assert "summary" in data
        assert len(data["diagnostics"]) == 1
        assert data["summary"]["error"] == 1


class TestDiagnosticConvenienceMethods:
    def test_add_error(self):
        coll = DiagnosticCollection()
        coll.add_error("test.error", "Error msg", "path.py")
        assert len(coll.diagnostics) == 1
        assert coll.diagnostics[0].severity == Severity.ERROR

    def test_add_warning(self):
        coll = DiagnosticCollection()
        coll.add_warning("test.warning", "Warning msg")
        assert coll.diagnostics[0].severity == Severity.WARNING

    def test_add_info(self):
        coll = DiagnosticCollection()
        coll.add_info("test.info", "Info msg")
        assert coll.diagnostics[0].severity == Severity.INFO

    def test_add_blocked(self):
        coll = DiagnosticCollection()
        coll.add_blocked("test.blocked", "Blocked msg")
        assert coll.diagnostics[0].severity == Severity.BLOCKED


class TestToolingLintRegression:
    def test_versioning_policy_no_longer_triggers_stale_compatibility_warning(self):
        repo_root = Path(__file__).resolve().parents[1]
        diagnostics = DiagnosticCollection()

        check_stale_docs(repo_root, diagnostics)

        assert not any(d.code == "core.docs.stale_compatibility_matrix" for d in diagnostics.diagnostics)

    def test_quality_gate_no_longer_triggers_stale_quality_gate_warning(self):
        repo_root = Path(__file__).resolve().parents[1]
        diagnostics = DiagnosticCollection()

        check_stale_docs(repo_root, diagnostics)

        assert not any(d.code == "core.docs.stale_quality_gate" for d in diagnostics.diagnostics)

    def test_parametric_template_checks_does_not_trigger_template_leftover(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            scripts = repo_root / "scripts"
            scripts.mkdir()
            (scripts / "verify_release.py").write_text(
                "PARAMETRIC_TEMPLATE_CHECKS = {'run': 'ok'}\n",
                encoding="utf-8",
            )

            diagnostics = DiagnosticCollection()
            SafetyChecks(repo_root).check_todo_templates(diagnostics)

            assert not any(d.code == "core.safety.template_leftover" for d in diagnostics.diagnostics)

    def test_real_template_placeholder_still_triggers_template_leftover(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            scripts = repo_root / "scripts"
            scripts.mkdir()
            (scripts / "verify_release.py").write_text(
                "# template placeholder: replace me later\n",
                encoding="utf-8",
            )

            diagnostics = DiagnosticCollection()
            SafetyChecks(repo_root).check_todo_templates(diagnostics)

            assert any(d.code == "core.safety.template_leftover" for d in diagnostics.diagnostics)

    def test_full_tooling_lint_emits_zero_warnings(self):
        repo_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "-m", "core_runtime.cli", "lint", "--scope", "tooling", "--format", "json"],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )

        payload = json.loads(result.stdout)
        assert payload["status"] == "pass"
        assert payload["summary"] == {"info": 0, "warning": 0, "error": 0, "blocked": 0}
