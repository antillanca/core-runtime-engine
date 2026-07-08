"""Tests for the CORE release-check wrapper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from core_runtime.cli.release_check import cmd_release_check
from core_runtime.tooling.release_check import (
    RELEASE_CHECK_PROFILES,
    ReleaseCheckRunner,
    SubprocessCapture,
    normalize_release_target,
)
import scripts.verify_release as verify_release


def _make_repo(tmp_path: Path, version: str = "10.5.1", with_release_script: bool = True) -> Path:
    core_runtime = tmp_path / "core_runtime"
    core_runtime.mkdir()
    (core_runtime / "__version__.py").write_text(
        '__version__ = "{0}"\nCORE_VERSION = "{0}"\n'.format(version),
        encoding="utf-8",
    )
    if with_release_script:
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "verify_release.py").write_text("#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")
    return tmp_path


def _completed(cmd: list[str], returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=cmd, returncode=returncode, stdout=stdout, stderr=stderr)


def _lint_pass(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    payload = {
        "tool": "core-runtime lint",
        "scope": "tooling",
        "status": "pass",
        "mutation_performed": False,
        "summary": {"info": 0, "warning": 0, "error": 0, "blocked": 0},
        "diagnostics": [],
    }
    return _completed(cmd, 0, json.dumps(payload))


def _lint_error(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    payload = {
        "tool": "core-runtime lint",
        "scope": "tooling",
        "status": "error",
        "mutation_performed": False,
        "summary": {"info": 0, "warning": 0, "error": 1, "blocked": 0},
        "diagnostics": [],
    }
    return _completed(cmd, 1, json.dumps(payload))


def _gate_pass(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    payload = {
        "schema": "core.release_verification.v1",
        "target": "v10.5.1",
        "status": "passed",
        "checks": {},
        "details": {},
    }
    return _completed(cmd, 0, json.dumps(payload))


def _gate_fail(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    payload = {
        "schema": "core.release_verification.v1",
        "target": "v10.5.1",
        "status": "failed",
        "checks": {"pytest": "failed"},
        "details": {"pytest": "failed"},
    }
    return _completed(cmd, 1, json.dumps(payload))


def _help_pass(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return _completed(cmd, 0, "usage: verify_release.py [--target TARGET]\n")


def _help_missing_target(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return _completed(cmd, 0, "usage: verify_release.py [--output OUTPUT]\n")


def _gate_timeout(cmd: list[str], timeout: int = 120) -> None:
    raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout, output="gate stdout " + ("x" * 5000), stderr="gate stderr " + ("y" * 5000))


def test_normalize_release_target_accepts_v_prefix() -> None:
    assert normalize_release_target("v10.5.1") == "10.5.1"
    assert normalize_release_target("10.5.1") == "10.5.1"


def test_release_check_default_target_discovered_from_canonical_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[1:4] == ["-m", "core_runtime.cli", "lint"]:
            return _lint_pass(cmd)
        return _gate_pass(cmd)

    monkeypatch.setattr("core_runtime.tooling.release_check.subprocess.run", fake_run)

    report = ReleaseCheckRunner(repo).run(target=None)

    assert report.target == "10.5.1"
    assert report.target_argument == "v10.5.1"
    assert report.status == "pass"
    assert calls


def test_release_check_accepts_raw_target_and_normalizes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)

    def fake_run(cmd, **kwargs):
        if cmd[1:4] == ["-m", "core_runtime.cli", "lint"]:
            return _lint_pass(cmd)
        assert cmd[1].endswith("verify_release.py")
        assert cmd[-1] == "v10.5.1"
        return _gate_pass(cmd)

    monkeypatch.setattr("core_runtime.tooling.release_check.subprocess.run", fake_run)

    report = ReleaseCheckRunner(repo).run(target="10.5.1")

    assert report.target == "10.5.1"
    assert report.release_gate is not None
    assert report.release_gate.command[-1] == "v10.5.1"
    assert report.status == "pass"


def test_release_check_accepts_v_prefixed_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)

    def fake_run(cmd, **kwargs):
        if cmd[1:4] == ["-m", "core_runtime.cli", "lint"]:
            return _lint_pass(cmd)
        assert cmd[-1] == "v10.5.1"
        return _gate_pass(cmd)

    monkeypatch.setattr("core_runtime.tooling.release_check.subprocess.run", fake_run)

    report = ReleaseCheckRunner(repo).run(target="v10.5.1")

    assert report.target == "10.5.1"
    assert report.release_gate is not None
    assert report.release_gate.status == "pass"


def test_release_check_invalid_target_is_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)

    def fake_run(cmd, **kwargs):
        raise AssertionError("subprocess should not be called for invalid target")

    monkeypatch.setattr("core_runtime.tooling.release_check.subprocess.run", fake_run)

    report = ReleaseCheckRunner(repo).run(target="invalid")

    assert report.status == "blocked"
    assert any(d.code == "core.release_check.invalid_target" for d in report.diagnostics.diagnostics)


def test_release_check_tooling_lint_failure_blocks_release_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[1:4] == ["-m", "core_runtime.cli", "lint"]:
            return _lint_error(cmd)
        raise AssertionError("release gate should not run after lint failure")

    monkeypatch.setattr("core_runtime.tooling.release_check.subprocess.run", fake_run)

    report = ReleaseCheckRunner(repo).run(target="10.5.1")

    assert report.status == "error"
    assert report.release_gate is None
    assert any(d.code == "core.release_check.tooling_lint_failed" for d in report.diagnostics.diagnostics)
    assert len(calls) == 1


def test_release_check_skip_tooling_lint_bypasses_precheck_only_when_requested(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        assert cmd[1].endswith("verify_release.py")
        return _gate_pass(cmd)

    monkeypatch.setattr("core_runtime.tooling.release_check.subprocess.run", fake_run)

    report = ReleaseCheckRunner(repo).run(target="10.5.1", skip_tooling_lint=True)

    assert report.status == "pass"
    assert report.tooling_lint is None
    assert len(calls) == 1


@pytest.mark.parametrize(
    "kwargs, expected_flag",
    [
        ({"list_checks": True}, "--list-checks"),
        ({"plan": True}, "--plan"),
        ({"group": "tooling"}, "--group"),
    ],
)
def test_release_check_passes_group_and_plan_flags_through_safely(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kwargs: dict[str, object],
    expected_flag: str,
) -> None:
    repo = _make_repo(tmp_path)
    calls: list[list[str]] = []

    def fake_run(cmd, **inner_kwargs):
        calls.append(cmd)
        if cmd[1:4] == ["-m", "core_runtime.cli", "lint"]:
            return _lint_pass(cmd)
        payload = {
            "schema": "core.release_verification.v1",
            "mode": "plan" if kwargs.get("plan") else ("list-checks" if kwargs.get("list_checks") else "group:tooling"),
            "status": "passed",
            "checks": {},
            "details": {},
        }
        return _completed(cmd, 0, json.dumps(payload))

    monkeypatch.setattr("core_runtime.tooling.release_check.subprocess.run", fake_run)

    report = ReleaseCheckRunner(repo).run(target="10.5.1", **kwargs)

    release_cmd = next(cmd for cmd in calls if cmd[1].endswith("verify_release.py"))
    assert expected_flag in release_cmd
    assert report.status == "pass"
    assert report.release_gate is not None
    assert "--apply" not in " ".join(release_cmd)


def test_release_check_profile_fast_runs_expected_group_sequence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)
    calls: list[list[str]] = []
    expected_groups = list(RELEASE_CHECK_PROFILES["fast"]["groups"])

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[1:4] == ["-m", "core_runtime.cli", "lint"]:
            return _lint_pass(cmd)
        assert cmd[1].endswith("verify_release.py")
        assert "--group" in cmd
        assert cmd[cmd.index("--group") + 1] in expected_groups
        return _gate_pass(cmd)

    monkeypatch.setattr("core_runtime.tooling.release_check.subprocess.run", fake_run)

    report = ReleaseCheckRunner(repo).run(target="10.5.1", profile="fast")

    assert report.status == "pass"
    assert report.profile == "fast"
    assert report.profile_definition is not None
    assert report.profile_definition["groups"] == tuple(expected_groups)
    assert len(report.profile_runs) == len(expected_groups)
    observed_groups = [cmd[cmd.index("--group") + 1] for cmd in calls if cmd[1].endswith("verify_release.py")]
    assert observed_groups == expected_groups


def test_release_check_profile_rejects_group_combination(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    report = ReleaseCheckRunner(repo).run(target="10.5.1", profile="fast", group="tooling")

    assert report.status == "blocked"
    assert any(d.code == "core.release_check.invalid_mode" for d in report.diagnostics.diagnostics)


def test_release_check_group_timeout_reports_group_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[1:4] == ["-m", "core_runtime.cli", "lint"]:
            return _lint_pass(cmd)
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 120), output="", stderr="")

    monkeypatch.setattr("core_runtime.tooling.release_check.subprocess.run", fake_run)

    report = ReleaseCheckRunner(repo).run(target="10.5.1", group="replay")

    assert report.mode == "group:replay"
    assert report.status == "blocked"
    assert report.release_gate is not None
    assert report.release_gate.timed_out is True
    assert any("--group" in cmd and "replay" in cmd for cmd in calls)


def test_release_check_preflight_only_runs_lint_and_help_but_not_full_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[1:4] == ["-m", "core_runtime.cli", "lint"]:
            return _lint_pass(cmd)
        if cmd[-1] == "--help":
            return _help_pass(cmd)
        raise AssertionError("full release gate should not run in preflight-only mode")

    monkeypatch.setattr("core_runtime.tooling.release_check.subprocess.run", fake_run)

    report = ReleaseCheckRunner(repo).run(target="10.5.1", preflight_only=True)

    assert report.mode == "preflight-only"
    assert report.status == "pass"
    assert report.release_gate is None
    assert report.release_gate_help is not None
    assert report.preflight_checks["help_status"] == "pass"
    assert report.preflight_checks["help_contains_target"] is True
    assert any(cmd[-1] == "--help" for cmd in calls)
    assert all("--target" not in cmd for cmd in calls if cmd[1].endswith("verify_release.py"))


def test_release_gate_subprocess_pass_maps_to_wrapper_status_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)

    def fake_run(cmd, **kwargs):
        if cmd[1:4] == ["-m", "core_runtime.cli", "lint"]:
            return _lint_pass(cmd)
        return _gate_pass(cmd)

    monkeypatch.setattr("core_runtime.tooling.release_check.subprocess.run", fake_run)

    report = ReleaseCheckRunner(repo).run(target="10.5.1")

    assert report.status == "pass"
    assert report.release_gate is not None
    assert report.release_gate.json_detected is True


def test_release_gate_subprocess_fail_maps_to_wrapper_status_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)

    def fake_run(cmd, **kwargs):
        if cmd[1:4] == ["-m", "core_runtime.cli", "lint"]:
            return _lint_pass(cmd)
        return _gate_fail(cmd)

    monkeypatch.setattr("core_runtime.tooling.release_check.subprocess.run", fake_run)

    report = ReleaseCheckRunner(repo).run(target="10.5.1")

    assert report.status == "error"
    assert report.release_gate is not None
    assert any(d.code == "core.release_check.release_gate_failed" for d in report.diagnostics.diagnostics)


def test_release_gate_timeout_maps_to_blocked_and_exit_code_two(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _make_repo(tmp_path)
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[1:4] == ["-m", "core_runtime.cli", "lint"]:
            return _lint_pass(cmd)
        timeout = int(kwargs.get("timeout", 120))
        _gate_timeout(cmd, timeout=timeout)

    monkeypatch.setattr("core_runtime.tooling.release_check.subprocess.run", fake_run)

    exit_code = cmd_release_check(
        type(
            "Args",
            (),
            {
                "target": "10.5.1",
                "format": "json",
                "output": None,
                "skip_tooling_lint": False,
                "timeout": 120,
                "preflight_only": False,
                "debug": False,
            },
        )()
    )
    captured = capsys.readouterr()

    payload = json.loads(captured.out)
    assert exit_code == 2
    assert payload["status"] == "blocked"
    assert payload["release_gate"]["timed_out"] is True
    assert any(d["code"] == "core.release_check.timeout" for d in payload["diagnostics"])
    assert len(calls) == 2


def test_release_gate_missing_script_maps_to_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path, with_release_script=False)

    def fake_run(cmd, **kwargs):
        if cmd[1:4] == ["-m", "core_runtime.cli", "lint"]:
            return _lint_pass(cmd)
        raise AssertionError("release gate subprocess should not run when script is missing")

    monkeypatch.setattr("core_runtime.tooling.release_check.subprocess.run", fake_run)

    report = ReleaseCheckRunner(repo).run(target="10.5.1")

    assert report.status == "blocked"
    assert report.release_gate is None
    assert any(d.code == "core.release_check.release_script_missing" for d in report.diagnostics.diagnostics)


def test_release_check_preflight_only_blocks_when_help_missing_target_mapping(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[1:4] == ["-m", "core_runtime.cli", "lint"]:
            return _lint_pass(cmd)
        if cmd[-1] == "--help":
            return _help_missing_target(cmd)
        raise AssertionError("release gate should not run when target mapping is unverified")

    monkeypatch.setattr("core_runtime.tooling.release_check.subprocess.run", fake_run)

    report = ReleaseCheckRunner(repo).run(target="10.5.1", preflight_only=True)

    assert report.status == "blocked"
    assert any(d.code == "core.release_check.target_mapping_unverified" for d in report.diagnostics.diagnostics)
    assert any(cmd[-1] == "--help" for cmd in calls)
    assert all("--target" not in cmd for cmd in calls if cmd[1].endswith("verify_release.py"))


def test_release_check_json_output_parses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)

    def fake_run(cmd, **kwargs):
        if cmd[1:4] == ["-m", "core_runtime.cli", "lint"]:
            return _lint_pass(cmd)
        return _gate_pass(cmd)

    monkeypatch.setattr("core_runtime.tooling.release_check.subprocess.run", fake_run)

    report = ReleaseCheckRunner(repo).run(target="10.5.1")
    payload = report.to_dict()
    assert json.loads(json.dumps(payload))["release_gate"]["json_detected"] is True


def test_release_check_markdown_renders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)

    def fake_run(cmd, **kwargs):
        if cmd[1:4] == ["-m", "core_runtime.cli", "lint"]:
            return _lint_pass(cmd)
        return _gate_pass(cmd)

    monkeypatch.setattr("core_runtime.tooling.release_check.subprocess.run", fake_run)

    report = ReleaseCheckRunner(repo).run(target="10.5.1")
    markdown = report.to_markdown()

    assert "# CORE release-check report" in markdown
    assert "## Final Status" in markdown
    assert "PASS" in markdown


def test_release_check_mutation_performed_is_always_false(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)

    def fake_run(cmd, **kwargs):
        if cmd[1:4] == ["-m", "core_runtime.cli", "lint"]:
            return _lint_pass(cmd)
        return _gate_pass(cmd)

    monkeypatch.setattr("core_runtime.tooling.release_check.subprocess.run", fake_run)

    report = ReleaseCheckRunner(repo).run(target="10.5.1")

    assert report.mutation_performed is False
    assert report.to_dict()["mutation_performed"] is False


def test_release_check_invokes_no_mutation_or_publish_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[1:4] == ["-m", "core_runtime.cli", "lint"]:
            return _lint_pass(cmd)
        return _gate_pass(cmd)

    monkeypatch.setattr("core_runtime.tooling.release_check.subprocess.run", fake_run)

    ReleaseCheckRunner(repo).run(target="10.5.1")

    flattened = " \n".join(" ".join(cmd) for cmd in calls)
    for token in ["--apply", "git tag", "gh release", "twine upload", "git push"]:
        assert token not in flattened


def test_release_check_subprocess_commands_use_sys_executable_and_explicit_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)
    recorded: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(cmd, **kwargs):
        recorded.append((cmd, kwargs))
        if cmd[1:4] == ["-m", "core_runtime.cli", "lint"]:
            return _lint_pass(cmd)
        return _gate_pass(cmd)

    monkeypatch.setattr("core_runtime.tooling.release_check.subprocess.run", fake_run)

    ReleaseCheckRunner(repo).run(target="10.5.1")

    assert recorded
    for cmd, kwargs in recorded:
        assert cmd[0] == sys.executable
        assert kwargs["cwd"] == repo
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["check"] is False
        assert kwargs["input"] == ""


def test_release_check_stdout_and_stderr_previews_are_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)

    def fake_run(cmd, **kwargs):
        if cmd[1:4] == ["-m", "core_runtime.cli", "lint"]:
            return _lint_pass(cmd)
        long_stdout = json.dumps(
            {
                "schema": "core.release_verification.v1",
                "target": "v10.5.1",
                "status": "passed",
                "details": "x" * 5000,
            }
        )
        return _completed(cmd, 0, long_stdout, "y" * 5000)

    monkeypatch.setattr("core_runtime.tooling.release_check.subprocess.run", fake_run)

    report = ReleaseCheckRunner(repo).run(target="10.5.1")

    assert report.release_gate is not None
    assert report.release_gate.stdout_truncated is True
    assert report.release_gate.stderr_truncated is True
    assert len(report.release_gate.stdout_preview) <= 2060
    assert len(report.release_gate.stderr_preview) <= 2060
    assert report.release_gate.stdout_preview.endswith("…[truncated]")


def test_verify_release_list_checks_does_not_execute_checks(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(verify_release.sys, "argv", ["verify_release.py", "--target", "v10.5.1", "--list-checks"])
    monkeypatch.setattr(verify_release, "_run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("checks should not run")))

    exit_code = verify_release.main()
    captured = capsys.readouterr()

    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["mode"] == "list-checks"
    assert payload["status"] == "passed"


def test_verify_release_plan_does_not_execute_checks(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(verify_release.sys, "argv", ["verify_release.py", "--target", "v10.5.1", "--plan"])
    monkeypatch.setattr(verify_release, "_run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("checks should not run")))

    exit_code = verify_release.main()
    captured = capsys.readouterr()

    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["mode"] == "plan"
    assert payload["status"] == "passed"


def test_verify_release_unknown_group_is_structured_blocked(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(verify_release.sys, "argv", ["verify_release.py", "--target", "v10.5.1", "--group", "nope"])
    monkeypatch.setattr(verify_release, "_run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("checks should not run")))

    exit_code = verify_release.main()
    captured = capsys.readouterr()

    payload = json.loads(captured.out)
    assert exit_code == 2
    assert payload["status"] == "blocked"
    assert payload["diagnostics"][0]["code"] == "core.release_gate.group_unknown"


def test_verify_release_timing_json_is_emitted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    timing_json = tmp_path / "timing.json"

    def fake_run(cmd, **kwargs):
        return _lint_pass(cmd)

    monkeypatch.setattr(verify_release, "_run", fake_run)

    exit_code, payload = verify_release.verify(
        skip_full_pytest=True,
        target="v10.5.1",
        stop_after_tooling=True,
        timing_json=str(timing_json),
    )

    assert exit_code == 0
    assert payload["mode"] == "tooling"
    assert timing_json.exists()
    timing_payload = json.loads(timing_json.read_text())
    assert timing_payload["mode"] == "tooling"
    assert timing_payload["timings"]


def _pytest_capture(command: list[str], returncode: int = 0, stdout: str = "", stderr: str = "", timed_out: bool = False) -> SubprocessCapture:
    return SubprocessCapture(
        command=command,
        cwd=str(Path.cwd()),
        expect_json=False,
        returncode=None if timed_out else returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        timeout_seconds=120,
        elapsed_seconds=0.5,
        json_detected=False,
        json_payload=None,
        report_path=None,
        target_argument=None,
        stdout_preview=stdout[:64],
        stderr_preview=stderr[:64],
        stdout_truncated=len(stdout) > 64,
        stderr_truncated=len(stderr) > 64,
    )


def test_verify_release_tests_plan_does_not_execute_pytest(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(verify_release.sys, "argv", ["verify_release.py", "--target", "v10.5.1", "--group", "tests", "--plan"])
    monkeypatch.setattr(verify_release, "_run_command", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("pytest should not run")))

    exit_code = verify_release.main()
    captured = capsys.readouterr()

    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["mode"] == "plan"
    assert payload["group"] == "tests"
    assert payload["test_subgroups"]
    assert payload["test_subgroups"][0]["name"] == "tests-tooling"


def test_verify_release_tests_tooling_uses_tooling_targets(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    calls: list[list[str]] = []

    def fake_run_command(command, **kwargs):
        calls.append(command)
        if command[1:3] == ["-m", "pytest"]:
            assert "tests/test_tooling_release_check.py" in command or "tests/test_tooling_ci_contract.py" in command
            return _pytest_capture(command)
        raise AssertionError("unexpected command")

    monkeypatch.setattr(verify_release.sys, "argv", ["verify_release.py", "--target", "v10.5.1", "--group", "tests-tooling"])
    monkeypatch.setattr(verify_release, "_run_command", fake_run_command)

    exit_code = verify_release.main()
    captured = capsys.readouterr()

    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["group"] == "tests-tooling"
    assert payload["status"] == "passed"
    assert calls
    assert any("tests/test_tooling_release_check.py" in " ".join(cmd) or "tests/test_tooling_ci_contract.py" in " ".join(cmd) for cmd in calls)


def test_verify_release_tests_full_keeps_full_suite_targets(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    calls: list[list[str]] = []

    def fake_run_command(command, **kwargs):
        calls.append(command)
        if command[1:3] == ["-m", "pytest"]:
            return _pytest_capture(command)
        raise AssertionError("unexpected command")

    monkeypatch.setattr(verify_release.sys, "argv", ["verify_release.py", "--target", "v10.5.1", "--group", "tests-full"])
    monkeypatch.setattr(verify_release, "_run_command", fake_run_command)

    exit_code = verify_release.main()
    captured = capsys.readouterr()

    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["group"] == "tests-full"
    assert payload["test_subgroups"]
    assert any(cmd[0] == verify_release.sys.executable and cmd[2] == "pytest" for cmd in calls if len(cmd) > 2)
    assert any("core_runtime/tests" in " ".join(cmd) or "tests/test_v" in " ".join(cmd) for cmd in calls)


def test_verify_release_tests_timeout_emits_structured_diagnostic(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def fake_run_command(command, **kwargs):
        if command[1:3] == ["-m", "pytest"]:
            return _pytest_capture(command, timed_out=True)
        raise AssertionError("unexpected command")

    monkeypatch.setattr(verify_release.sys, "argv", ["verify_release.py", "--target", "v10.5.1", "--group", "tests-core"])
    monkeypatch.setattr(verify_release, "_run_command", fake_run_command)

    exit_code = verify_release.main()
    captured = capsys.readouterr()

    payload = json.loads(captured.out)
    assert exit_code == 2
    assert payload["status"] == "blocked"
    assert payload["diagnostics"][0]["code"] == "core.release_gate.tests_subgroup_timeout"
    assert payload["diagnostics"][0]["details"]["subgroup"] == "tests-core"
    assert payload["timings"][0]["subgroup"] == "tests-core"
    assert payload["timings"][0]["status"] == "blocked"


def test_release_check_wrapper_passes_tests_group_flags_safely(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[1:4] == ["-m", "core_runtime.cli", "lint"]:
            return _lint_pass(cmd)
        if cmd[1].endswith("verify_release.py"):
            assert "--group" in cmd
            assert "tests-tooling" in cmd or "tests-core" in cmd or "tests-full" in cmd
            return _completed(cmd, 0, json.dumps({"schema": "core.release_verification.v1", "mode": "tests-tooling", "status": "passed", "checks": {}, "details": {}, "test_subgroups": []}))
        raise AssertionError("unexpected command")

    monkeypatch.setattr("core_runtime.tooling.release_check.subprocess.run", fake_run)

    report = ReleaseCheckRunner(repo).run(target="10.5.1", group="tests-tooling")

    assert report.status == "pass"
    assert report.release_gate is not None
    assert any("--group" in cmd and "tests-tooling" in cmd for cmd in calls)


def test_cmd_release_check_passes_profile_flag_through(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _make_repo(tmp_path)
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[1:4] == ["-m", "core_runtime.cli", "lint"]:
            return _lint_pass(cmd)
        return _gate_pass(cmd)

    monkeypatch.setattr("core_runtime.tooling.release_check.subprocess.run", fake_run)

    exit_code = cmd_release_check(
        type(
            "Args",
            (),
            {
                "target": "10.5.1",
                "format": "json",
                "output": None,
                "skip_tooling_lint": False,
                "timeout": 120,
                "preflight_only": False,
                "debug": False,
                "group": None,
                "profile": "fast",
                "list_checks": False,
                "plan": False,
                "timing_json": None,
            },
        )()
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["profile"] == "fast"
    assert payload["status"] == "pass"
    assert any("--group" in cmd for cmd in calls if cmd[1].endswith("verify_release.py"))


def test_release_check_profile_plan_remains_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[1:4] == ["-m", "core_runtime.cli", "lint"]:
            return _lint_pass(cmd)
        return _completed(cmd, 0, json.dumps({"schema": "core.release_verification.v1", "mode": "plan", "status": "passed", "plan": []}))

    monkeypatch.setattr("core_runtime.tooling.release_check.subprocess.run", fake_run)

    report = ReleaseCheckRunner(repo).run(target="10.5.1", profile="fast", plan=True)

    assert report.status == "pass"
    assert report.mode == "plan"
    assert report.profile == "fast"
    assert report.profile_definition is not None
    assert report.profile_runs == []
    assert any(cmd[-1] == "--plan" for cmd in calls if cmd[1].endswith("verify_release.py"))
