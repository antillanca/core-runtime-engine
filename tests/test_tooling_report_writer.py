"""Tests for core_runtime.tooling.report_writer."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


from core_runtime.tooling.diagnostics import Diagnostic, DiagnosticCollection, Severity
from core_runtime.tooling.report_writer import ReportWriter
from core_runtime.tooling.version_inventory import VersionSource


class TestReportWriter:
    def setup_method(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.repo_root = Path(tmp)
            self.writer = ReportWriter(self.repo_root)

    def test_write_json_basic(self):
        diagnostics = DiagnosticCollection()
        diagnostics.add_error("test.error", "Test error", "test.py")
        diagnostics.add_warning("test.warning", "Test warning")

        report = self.writer.write_json(diagnostics, scope="tooling")

        assert report["tool"] == "core-runtime lint"
        assert report["scope"] == "tooling"
        assert report["status"] == "error"
        assert report["mutation_performed"] is False
        assert report["summary"]["error"] == 1
        assert report["summary"]["warning"] == 1
        assert len(report["diagnostics"]) == 2

    def test_write_json_with_output_file(self):
        diagnostics = DiagnosticCollection()
        diagnostics.add_info("test.info", "Test info")

        output_path = self.repo_root / "report.json"
        self.writer.write_json(diagnostics, scope="tooling", output_path=output_path)

        assert output_path.exists()
        with output_path.open() as f:
            data = json.load(f)
        assert data["summary"]["info"] == 1

    def test_write_json_with_version_sources(self):
        diagnostics = DiagnosticCollection()
        version_sources = [
            VersionSource(
                name="core_runtime/__version__.py",
                path=self.repo_root / "core_runtime/__version__.py",
                version="10.5.0",
                pattern="test",
                is_canonical=True,
            ),
            VersionSource(
                name="pyproject.toml",
                path=self.repo_root / "pyproject.toml",
                version="10.5.0",
                pattern="test",
                is_canonical=False,
            ),
        ]

        report = self.writer.write_json(
            diagnostics, scope="tooling", version_sources=version_sources
        )

        assert "version_inventory" in report
        assert len(report["version_inventory"]) == 2
        assert report["version_inventory"][0]["is_canonical"] is True

    def test_write_json_with_file_inventory(self):
        diagnostics = DiagnosticCollection()
        file_inventory = {"README.md": True, "missing.txt": False}

        report = self.writer.write_json(
            diagnostics, scope="tooling", file_inventory=file_inventory
        )

        assert "file_inventory" in report
        assert report["file_inventory"]["README.md"] is True
        assert report["file_inventory"]["missing.txt"] is False

    def test_write_markdown_basic(self):
        diagnostics = DiagnosticCollection()
        diagnostics.add_error("test.error", "Test error message", "test.py")
        diagnostics.add_warning("test.warning", "Test warning message")

        markdown = self.writer.write_markdown(diagnostics, scope="tooling")

        assert "# CORE Tooling Lint Report" in markdown
        assert "## Summary" in markdown
        assert "core-runtime lint" in markdown
        assert "tooling" in markdown
        assert "ERROR" in markdown
        assert "WARNING" in markdown
        assert "test.error" in markdown
        assert "test.warning" in markdown
        assert "Test error message" in markdown

    def test_write_markdown_with_version_sources(self):
        diagnostics = DiagnosticCollection()
        version_sources = [
            VersionSource(
                name="core_runtime/__version__.py",
                path=self.repo_root / "core_runtime/__version__.py",
                version="10.5.0",
                pattern="test",
                is_canonical=True,
            ),
        ]

        markdown = self.writer.write_markdown(
            diagnostics, scope="tooling", version_sources=version_sources
        )

        assert "## Version Inventory" in markdown
        assert "10.5.0" in markdown
        assert "Yes" in markdown  # Canonical

    def test_write_markdown_with_file_inventory(self):
        diagnostics = DiagnosticCollection()
        file_inventory = {"README.md": True, "missing.txt": False}

        markdown = self.writer.write_markdown(
            diagnostics, scope="tooling", file_inventory=file_inventory
        )

        assert "## File Inventory" in markdown
        assert "README.md" in markdown
        assert "missing.txt" in markdown
        assert "✓" in markdown
        assert "✗" in markdown

    def test_write_markdown_status_pass(self):
        diagnostics = DiagnosticCollection()  # No diagnostics = OK
        markdown = self.writer.write_markdown(diagnostics, scope="tooling")
        assert "✅ **PASS**" in markdown

    def test_write_markdown_status_error(self):
        diagnostics = DiagnosticCollection()
        diagnostics.add_error("test.error", "Error")
        markdown = self.writer.write_markdown(diagnostics, scope="tooling")
        assert "❌ **ERROR**" in markdown

    def test_write_markdown_status_blocked(self):
        diagnostics = DiagnosticCollection()
        diagnostics.add_blocked("test.blocked", "Blocked")
        markdown = self.writer.write_markdown(diagnostics, scope="tooling")
        assert "🚫 **BLOCKED**" in markdown

    def test_write_markdown_with_output_file(self):
        diagnostics = DiagnosticCollection()
        diagnostics.add_info("test.info", "Sample message")

        output_path = self.repo_root / "report.md"
        self.writer.write_markdown(diagnostics, scope="tooling", output_path=output_path)

        assert output_path.exists()
        content = output_path.read_text(encoding="utf-8")
        assert "test.info" in content
        assert "Sample message" in content


class TestDiagnosticSerialization:
    def test_diagnostic_to_dict_complete(self):
        d = Diagnostic(
            code="test.code",
            severity=Severity.ERROR,
            message="Test message",
            mutation_allowed=False,
            path="test/path.py",
            expected="1.0.0",
            actual="2.0.0",
            details="Additional details",
        )
        data = d.to_dict()
        assert data["code"] == "test.code"
        assert data["severity"] == "error"
        assert data["message"] == "Test message"
        assert data["mutation_allowed"] is False
        assert data["path"] == "test/path.py"
        assert data["expected"] == "1.0.0"
        assert data["actual"] == "2.0.0"
        assert data["details"] == "Additional details"

    def test_diagnostic_to_dict_minimal(self):
        d = Diagnostic(
            code="test.code",
            severity=Severity.INFO,
            message="Test message",
            mutation_allowed=False,
        )
        data = d.to_dict()
        assert "path" not in data
        assert "expected" not in data
        assert "actual" not in data
        assert "details" not in data
