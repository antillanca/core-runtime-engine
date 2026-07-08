from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path("scripts/run_all_examples.py")

EXPECTED_ADAPTERS = {
    "audio_envelope_wav",
    "image_brightness_motion",
    "minimal_sensor_adapter",
    "threshold_scalar_basic",
    "multi_channel_environment",
    "logic_debounce",
    "business_operations",
    "privacy_safe_customer_flow",
    "wifi_csi_synthetic_bridge",
}

EXPECTED_WORKFLOWS = {
    "skeleton_roundtrip_demo",
}


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def test_run_all_examples_passes() -> None:
    result = _run([sys.executable, str(SCRIPT)])
    assert result.returncode == 0, result.stderr

    payload = json.loads(result.stdout)

    assert payload["status"] == "passed"
    assert EXPECTED_ADAPTERS.issubset(set(payload["adapters"]))
    assert EXPECTED_WORKFLOWS.issubset(set(payload["workflows"]))
    assert "hysteresis_v1" in payload["adapters"]["threshold_scalar_basic"]["fixtures"]


def test_run_all_examples_is_byte_stable() -> None:
    first = _run([sys.executable, str(SCRIPT)])
    second = _run([sys.executable, str(SCRIPT)])

    assert first.returncode == 0
    assert second.returncode == 0
    assert first.stdout == second.stdout
