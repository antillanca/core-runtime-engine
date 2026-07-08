"""Tests for scripts/validate_state_watcher.py — deterministic schema validation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VALIDATOR_SCRIPT = PROJECT_ROOT / "scripts" / "validate_state_watcher.py"
REGISTRATIONS_DIR = PROJECT_ROOT / "examples" / "state_watchers" / "registrations"


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )


def test_valid_threshold_watcher_passes() -> None:
    result = _run(
        [sys.executable, str(VALIDATOR_SCRIPT),
         str(REGISTRATIONS_DIR / "valid_threshold_watcher.json")]
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    assert payload["watcher_id"] == "synthetic.threshold_exceeded"
    assert payload["errors"] == []


def test_valid_range_watcher_passes() -> None:
    result = _run(
        [sys.executable, str(VALIDATOR_SCRIPT),
         str(REGISTRATIONS_DIR / "valid_range_watcher.json")]
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    assert payload["watcher_id"] == "synthetic.within_range"


def test_valid_disabled_watcher_passes() -> None:
    result = _run(
        [sys.executable, str(VALIDATOR_SCRIPT),
         str(REGISTRATIONS_DIR / "valid_disabled_watcher.json")]
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    assert payload["watcher_id"] == "synthetic.disabled_monitor"


def test_invalid_missing_watcher_id_fails() -> None:
    result = _run(
        [sys.executable, str(VALIDATOR_SCRIPT),
         str(REGISTRATIONS_DIR / "invalid_missing_watcher_id.json")]
    )
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert any(e["code"] == "schema_validation_failed" for e in payload["errors"])


def test_invalid_unknown_operator_fails() -> None:
    result = _run(
        [sys.executable, str(VALIDATOR_SCRIPT),
         str(REGISTRATIONS_DIR / "invalid_unknown_operator.json")]
    )
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert any(e["code"] == "schema_validation_failed" for e in payload["errors"])


def test_invalid_empty_event_type_fails() -> None:
    result = _run(
        [sys.executable, str(VALIDATOR_SCRIPT),
         str(REGISTRATIONS_DIR / "invalid_empty_event_type.json")]
    )
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert any(e["code"] == "schema_validation_failed" for e in payload["errors"])


def test_directory_validation_reports_correct_counts() -> None:
    result = _run(
        [sys.executable, str(VALIDATOR_SCRIPT), str(REGISTRATIONS_DIR)]
    )
    assert result.returncode != 0  # some are invalid
    payload = json.loads(result.stdout)
    assert payload["total_count"] == 6
    assert payload["passed_count"] == 3
    assert payload["failed_count"] == 3


def test_directory_validation_is_deterministic() -> None:
    first = _run([sys.executable, str(VALIDATOR_SCRIPT), str(REGISTRATIONS_DIR)])
    second = _run([sys.executable, str(VALIDATOR_SCRIPT), str(REGISTRATIONS_DIR)])
    assert first.stdout == second.stdout
