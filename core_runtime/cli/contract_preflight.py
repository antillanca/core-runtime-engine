"""CLI command for `core-runtime contract-preflight`."""

from __future__ import annotations

import json
from pathlib import Path

from core_runtime.tooling.contract_preflight import ContractPreflightReport, RepositoryContractPreflight
from core_runtime.tooling.diagnostics import ExitCode


def cmd_contract_preflight(args: object) -> int:
    """Execute the advisory-only contract preflight command."""
    fmt: str = getattr(args, "format", "json")
    output = getattr(args, "output", None)
    candidate = getattr(args, "candidate", None)
    compare = getattr(args, "compare", None)
    repo_root = Path(__file__).resolve().parents[2]
    preflight = RepositoryContractPreflight(repo_root)

    if compare:
        report = preflight.build_compare_report(compare[0], compare[1])
    elif candidate:
        report = preflight.build_candidate_report(candidate)
    else:
        from core_runtime.tooling.diagnostics import DiagnosticCollection

        diagnostics = DiagnosticCollection()
        diagnostics.add_blocked(
            code="core.contract_preflight.mode_required",
            message="contract-preflight requires --candidate or --compare",
            path="contract-preflight",
            expected="--candidate <name> or --compare <a> <b>",
            actual="missing mode",
        )
        report = ContractPreflightReport(
            tool="core-runtime contract-preflight",
            command="contract-preflight",
            status="blocked",
            summary={"mode": "missing", "item_count": 0},
            selection={"mode": "missing"},
            diagnostics=diagnostics,
        )

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
