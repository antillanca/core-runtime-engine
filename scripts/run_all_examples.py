#!/usr/bin/env python3
"""Run and verify all CORE example adapters and workflows."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_EXAMPLES_DIR = PROJECT_ROOT / "examples" / "adapters"
DEFAULT_WORKFLOWS_DIR = PROJECT_ROOT / "examples" / "workflows"
VALIDATOR = PROJECT_ROOT / "scripts" / "validate_sensor_manifest.py"
CERTIFIER = PROJECT_ROOT / "scripts" / "certify_sensor_fixture.py"
COMPLIANCE = PROJECT_ROOT / "scripts" / "check_adapter_compliance.py"


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _display(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return path.as_posix()


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def _load_json(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    assert result.stdout.strip(), result.stderr
    return json.loads(result.stdout)


def _check_fixture(fixture_dir: Path) -> dict[str, str]:
    fixture_arg = _display(fixture_dir)
    validation = _run([sys.executable, str(VALIDATOR), fixture_arg])
    certification = _run([sys.executable, str(CERTIFIER), fixture_arg])
    if validation.returncode != 0 or certification.returncode != 0:
        raise RuntimeError(
            f"fixture failed: {_display(fixture_dir)}\n"
            f"validation={validation.returncode}\n"
            f"certification={certification.returncode}\n"
            f"validation_stdout={validation.stdout}\nvalidation_stderr={validation.stderr}\n"
            f"certification_stdout={certification.stdout}\ncertification_stderr={certification.stderr}"
        )

    validation_payload = _load_json(validation)
    certification_payload = _load_json(certification)

    return {
        "validation": validation_payload["status"],
        "certification": certification_payload["status"],
    }


def _check_adapter(adapter_dir: Path) -> dict[str, Any]:
    adapter_arg = _display(adapter_dir)
    readme_exists = (adapter_dir / "README.md").exists()
    generator_path = adapter_dir / "generate_fixture.py"
    generator_exists = generator_path.exists()
    fixtures_dir = adapter_dir / "fixtures"
    fixtures_dir_exists = fixtures_dir.exists()

    if not (readme_exists and generator_exists and fixtures_dir_exists):
        return {
            "status": "failed",
            "readme_exists": readme_exists,
            "generator_exists": generator_exists,
            "fixtures_dir_exists": fixtures_dir_exists,
            "fixtures": {},
            "compliance": "failed",
        }

    generator_cmd = [sys.executable, str(generator_path)]
    if adapter_dir.name == "business_operations":
        generator_cmd.extend(["--scenario", "all"])

    generator_result = _run(generator_cmd)
    if generator_result.returncode != 0:
        raise RuntimeError(
            f"generator failed for {_display(adapter_dir)}\n"
            f"stdout={generator_result.stdout}\nstderr={generator_result.stderr}"
        )

    fixtures_summary: dict[str, dict[str, str]] = {}
    fixture_dirs = sorted(
        fixture for fixture in fixtures_dir.iterdir() if fixture.is_dir()
    )
    for fixture_dir in fixture_dirs:
        fixtures_summary[fixture_dir.name] = _check_fixture(fixture_dir)

    compliance_result = _run([sys.executable, str(COMPLIANCE), adapter_arg])
    if compliance_result.returncode != 0:
        raise RuntimeError(
            f"compliance failed for {_display(adapter_dir)}\n"
            f"stdout={compliance_result.stdout}\nstderr={compliance_result.stderr}"
        )

    compliance_payload = _load_json(compliance_result)
    return {
        "status": "passed" if compliance_payload.get("compliant") else "failed",
        "readme_exists": readme_exists,
        "generator_exists": generator_exists,
        "fixtures_dir_exists": fixtures_dir_exists,
        "fixtures": fixtures_summary,
        "compliance": compliance_payload["status"],
    }


def _check_workflow(workflow_dir: Path) -> dict[str, Any]:
    readme_exists = (workflow_dir / "README.md").exists()
    run_demo_path = workflow_dir / "run_demo.py"
    run_demo_exists = run_demo_path.exists()
    if not (readme_exists and run_demo_exists):
        return {
            "status": "failed",
            "readme_exists": readme_exists,
            "run_demo_exists": run_demo_exists,
        }

    result = _run([sys.executable, str(run_demo_path)])
    if result.returncode != 0:
        raise RuntimeError(
            f"workflow failed for {_display(workflow_dir)}\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
    payload = _load_json(result)
    return {
        "status": payload["status"],
        "readme_exists": readme_exists,
        "run_demo_exists": run_demo_exists,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run all CORE examples.")
    parser.add_argument(
        "--examples-dir",
        type=Path,
        default=DEFAULT_EXAMPLES_DIR,
        help="Directory containing adapter examples.",
    )
    parser.add_argument(
        "--workflows-dir",
        type=Path,
        default=DEFAULT_WORKFLOWS_DIR,
        help="Directory containing workflow examples.",
    )
    parser.add_argument(
        "--include-workflows",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Also verify workflow examples.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write the JSON report.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    examples_dir = args.examples_dir
    if not examples_dir.exists():
        return 2

    adapters: dict[str, Any] = {}
    adapters_checked = 0
    fixtures_checked = 0
    for adapter_dir in sorted(p for p in examples_dir.iterdir() if p.is_dir()):
        if not (adapter_dir / "generate_fixture.py").exists():
            continue
        adapters_checked += 1
        adapter_summary = _check_adapter(adapter_dir)
        adapters[adapter_dir.name] = adapter_summary
        fixtures_checked += len(adapter_summary.get("fixtures", {}))

    workflows: dict[str, Any] = {}
    workflows_checked = 0
    if args.include_workflows:
        workflows_dir = args.workflows_dir
        if workflows_dir.exists():
            for workflow_dir in sorted(p for p in workflows_dir.iterdir() if p.is_dir()):
                if not (workflow_dir / "run_demo.py").exists():
                    continue
                workflows_checked += 1
                workflows[workflow_dir.name] = _check_workflow(workflow_dir)

    passed = all(
        adapter.get("status") == "passed" and adapter.get("compliance") == "compliant"
        for adapter in adapters.values()
    ) and all(workflow.get("status") == "passed" for workflow in workflows.values())

    payload = {
        "status": "passed" if passed else "failed",
        "adapters_checked": adapters_checked,
        "fixtures_checked": fixtures_checked,
        "workflows_checked": workflows_checked,
        "adapters": adapters,
        "workflows": workflows,
    }

    report = _canonical_json(payload)
    sys.stdout.write(report)
    if args.output is not None:
        args.output.write_text(report, encoding="utf-8")

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
