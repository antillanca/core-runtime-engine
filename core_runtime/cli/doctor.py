"""CLI command for `core-runtime doctor`."""

from __future__ import annotations

import json
from pathlib import Path

from core_runtime.tooling.diagnostics import ExitCode
from core_runtime.tooling.doctor import RepositoryDoctor


def cmd_doctor(args: object) -> int:
    """Execute the doctor preflight command."""
    fmt: str = getattr(args, "format", "json")
    output = getattr(args, "output", None)
    repo_root = Path(__file__).resolve().parents[2]
    doctor = RepositoryDoctor(repo_root)
    report = doctor.build_report()
    output_path = Path(output) if output else None

    if fmt == "json":
        payload = report.to_dict()
        text = json.dumps(payload, indent=2, ensure_ascii=False)
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(text + "\n", encoding="utf-8")
        else:
            print(text)
    else:
        markdown = report.to_markdown()
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(markdown, encoding="utf-8")
        else:
            print(markdown)

    status_to_exit = {
        "pass": ExitCode.OK.value,
        "warning": ExitCode.OK.value,
        "error": ExitCode.ERROR.value,
        "blocked": ExitCode.BLOCKED.value,
        "internal_error": ExitCode.INTERNAL_ERROR.value,
    }
    return status_to_exit.get(report.status, ExitCode.INTERNAL_ERROR.value)
