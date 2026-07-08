from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TEMP_ROOT = Path("/tmp/core_skeleton_roundtrip_demo")
ADAPTER_NAME = "workflow_roundtrip_adapter"
ADAPTER_DIR = TEMP_ROOT / ADAPTER_NAME
FIXTURE_DIR = ADAPTER_DIR / "fixtures" / f"{ADAPTER_NAME}_v1"
CREATE_SKELETON = PROJECT_ROOT / "scripts" / "create_adapter_skeleton.py"
VALIDATOR = PROJECT_ROOT / "scripts" / "validate_sensor_manifest.py"
CERTIFIER = PROJECT_ROOT / "scripts" / "certify_sensor_fixture.py"
COMPLIANCE = PROJECT_ROOT / "scripts" / "check_adapter_compliance.py"


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def _run_json(cmd: list[str]) -> dict[str, Any]:
    result = _run(cmd)
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(cmd)}\nstdout={result.stdout}\nstderr={result.stderr}"
        )
    assert result.stdout.strip(), result.stderr
    return json.loads(result.stdout)


def main() -> int:
    shutil.rmtree(TEMP_ROOT, ignore_errors=True)
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)

    create_result = _run(
        [
            sys.executable,
            str(CREATE_SKELETON),
            ADAPTER_NAME,
            "--value-key",
            "signal",
            "--threshold",
            "1.0",
            "--output-dir",
            str(TEMP_ROOT),
            "--force",
        ]
    )
    if create_result.returncode != 0:
        raise SystemExit(create_result.returncode)

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    generate_result = _run([sys.executable, str(ADAPTER_DIR / "generate_fixture.py")])
    if generate_result.returncode != 0:
        raise SystemExit(generate_result.returncode)

    validation = _run_json([sys.executable, str(VALIDATOR), str(FIXTURE_DIR)])
    certification = _run_json([sys.executable, str(CERTIFIER), str(FIXTURE_DIR)])
    compliance = _run_json([sys.executable, str(COMPLIANCE), str(ADAPTER_DIR)])

    payload = {
        "adapter_name": ADAPTER_NAME,
        "fixture_id": f"{ADAPTER_NAME}_v1",
        "status": "passed",
        "steps": {
            "create_adapter_skeleton": "passed",
            "generate_fixture": "passed",
            "validate": validation["status"],
            "certify": certification["status"],
            "compliance": compliance["status"],
        },
    }

    sys.stdout.write(_canonical_json(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
