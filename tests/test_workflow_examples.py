from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

WORKFLOWS = [
    Path("examples/workflows/skeleton_roundtrip_demo/run_demo.py"),
]


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def _payload(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert result.stdout.strip(), result.stderr
    return json.loads(result.stdout)


def test_workflow_examples_pass() -> None:
    for workflow in WORKFLOWS:
        result = _run([sys.executable, str(workflow)])
        payload = _payload(result)

        assert result.returncode == 0, result.stderr
        assert payload["status"] == "passed"


def test_workflow_examples_are_byte_stable() -> None:
    for workflow in WORKFLOWS:
        first = _run([sys.executable, str(workflow)])
        second = _run([sys.executable, str(workflow)])

        assert first.returncode == 0
        assert second.returncode == 0
        assert first.stdout == second.stdout
