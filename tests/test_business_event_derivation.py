"""Tests for scripts/derive_business_event.py — deterministic event derivation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DERIVE_SCRIPT = PROJECT_ROOT / "scripts" / "derive_business_event.py"
REGISTRATIONS_DIR = PROJECT_ROOT / "examples" / "state_watchers" / "registrations"
OBSERVATIONS_DIR = PROJECT_ROOT / "examples" / "state_watchers" / "observations" / "scalar_observations_v1"
DERIVED_DIR = PROJECT_ROOT / "examples" / "state_watchers" / "derived_events"


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )


def test_threshold_watcher_derives_events() -> None:
    result = _run(
        [sys.executable, str(DERIVE_SCRIPT),
         str(REGISTRATIONS_DIR / "valid_threshold_watcher.json"),
         str(OBSERVATIONS_DIR)]
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "derived"
    assert payload["watcher_id"] == "synthetic.threshold_exceeded"
    assert payload["derived_event_count"] == 2
    assert payload["observation_count"] == 5

    events = payload["events"]
    assert events[0]["event_type"] == "threshold_exceeded"
    assert events[0]["payload"]["observation_id"] == "obs_002"
    assert events[0]["payload"]["operand_value"] == 120.0
    assert events[1]["payload"]["observation_id"] == "obs_004"
    assert events[1]["payload"]["operand_value"] == 150.0


def test_disabled_watcher_derives_no_events() -> None:
    result = _run(
        [sys.executable, str(DERIVE_SCRIPT),
         str(REGISTRATIONS_DIR / "valid_disabled_watcher.json"),
         str(OBSERVATIONS_DIR)]
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["derived_event_count"] == 0


def test_derived_event_fingerprints_match_fixtures() -> None:
    result = _run(
        [sys.executable, str(DERIVE_SCRIPT),
         str(REGISTRATIONS_DIR / "valid_threshold_watcher.json"),
         str(OBSERVATIONS_DIR)]
    )
    payload = json.loads(result.stdout)
    events = payload["events"]

    fixture_1 = json.loads((DERIVED_DIR / "threshold_exceeded_event.json").read_text())
    fixture_2 = json.loads((DERIVED_DIR / "threshold_exceeded_event_obs004.json").read_text())

    assert events[0]["fingerprint"] == fixture_1["fingerprint"]
    assert events[1]["fingerprint"] == fixture_2["fingerprint"]


def test_derivation_is_deterministic() -> None:
    first = _run(
        [sys.executable, str(DERIVE_SCRIPT),
         str(REGISTRATIONS_DIR / "valid_threshold_watcher.json"),
         str(OBSERVATIONS_DIR)]
    )
    second = _run(
        [sys.executable, str(DERIVE_SCRIPT),
         str(REGISTRATIONS_DIR / "valid_threshold_watcher.json"),
         str(OBSERVATIONS_DIR)]
    )
    assert first.returncode == 0
    assert second.returncode == 0
    assert first.stdout == second.stdout


def test_derivation_fails_on_missing_watcher() -> None:
    result = _run(
        [sys.executable, str(DERIVE_SCRIPT),
         str(REGISTRATIONS_DIR / "nonexistent.json"),
         str(OBSERVATIONS_DIR)]
    )
    assert result.returncode != 0


def test_derivation_fails_on_missing_observations_dir() -> None:
    result = _run(
        [sys.executable, str(DERIVE_SCRIPT),
         str(REGISTRATIONS_DIR / "valid_threshold_watcher.json"),
         "/nonexistent/observations"]
    )
    assert result.returncode != 0
