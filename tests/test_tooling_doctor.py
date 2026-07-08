"""Tests for read-only environment diagnostics."""

from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess

from core_runtime.cli.main import build_parser
from core_runtime.tooling.doctor import RepositoryDoctor


def _make_repo(tmp_path: Path) -> Path:
    core_runtime = tmp_path / "core_runtime"
    core_runtime.mkdir()
    (core_runtime / "__version__.py").write_text('__version__ = "10.5.0"\n', encoding="utf-8")
    (core_runtime / "__init__.py").write_text("from core_runtime.__version__ import __version__\n", encoding="utf-8")

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "VERSIONING_POLICY.md").write_text("Current: v10.5.0\n", encoding="utf-8")
    (docs / "CORE_RELEASE_README.md").write_text("CORE: v10.5.0\n", encoding="utf-8")
    releases = docs / "releases"
    releases.mkdir()
    (releases / "README.md").write_text("# Releases\n", encoding="utf-8")
    (releases / "v10.5.0.md").write_text("# v10.5.0\n", encoding="utf-8")

    (tmp_path / "README.md").write_text("CORE v10.5.0\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('version = "10.5.0"\n', encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("## v10.5.0\n", encoding="utf-8")

    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "verify_release.py").write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "if '--help' in sys.argv:\n"
        "    print('help')\n"
        "    raise SystemExit(0)\n",
        encoding="utf-8",
    )

    return tmp_path


def _fake_run(*args, **kwargs):  # noqa: ANN001, D401
    cmd = args[0]
    if cmd[0] == "git" and "status" in cmd and "--porcelain" in cmd:
        return CompletedProcess(cmd, 0, stdout="", stderr="")
    return CompletedProcess(cmd, 0, stdout="", stderr="")


def _fake_run_dirty(*args, **kwargs):  # noqa: ANN001, D401
    cmd = args[0]
    if cmd[0] == "git" and "status" in cmd and "--porcelain" in cmd:
        return CompletedProcess(cmd, 0, stdout=" M core_runtime/__version__.py\n", stderr="")
    return CompletedProcess(cmd, 0, stdout="", stderr="")


def test_build_parser_includes_doctor_command() -> None:
    parser = build_parser()

    args = parser.parse_args(["doctor"])
    assert args.command == "doctor"


def test_doctor_report_is_pass_for_clean_repo(tmp_path: Path, monkeypatch) -> None:
    repo = _make_repo(tmp_path)
    doctor = RepositoryDoctor(repo)
    monkeypatch.setattr(RepositoryDoctor, "_tool_version", lambda self, tool: f"{tool} 1.0")
    monkeypatch.setattr(RepositoryDoctor, "_git_branch", lambda self: "main")
    monkeypatch.setattr("core_runtime.tooling.doctor.subprocess.run", _fake_run)

    report = doctor.build_report()

    assert report.status == "pass"
    assert report.summary["item_count"] == 8
    assert any(item.name == "python" for item in report.items)
    assert any(item.name == "verify_release.py" for item in report.items)
    assert report.to_dict()["tool"] == "core-runtime doctor"


def test_doctor_warns_on_dirty_version_files(tmp_path: Path, monkeypatch) -> None:
    repo = _make_repo(tmp_path)
    doctor = RepositoryDoctor(repo)
    monkeypatch.setattr(RepositoryDoctor, "_tool_version", lambda self, tool: f"{tool} 1.0")
    monkeypatch.setattr(RepositoryDoctor, "_git_branch", lambda self: "main")
    monkeypatch.setattr("core_runtime.tooling.doctor.subprocess.run", _fake_run_dirty)

    report = doctor.build_report()

    assert report.status == "warning"
    assert any(d.code == "core.doctor.version_dirty" for d in report.diagnostics.diagnostics)
    assert any(item.name == "version-bearing-files" and item.status == "warning" for item in report.items)
