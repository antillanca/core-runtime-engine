"""CLI argument parser and command dispatch."""

from __future__ import annotations

import argparse
from pathlib import Path

from core_runtime.cli.bump_version import cmd_bump_version
from core_runtime.cli.create_domain import cmd_create_domain
from core_runtime.cli.contract_preflight import cmd_contract_preflight
from core_runtime.cli.doctor import cmd_doctor
from core_runtime.cli.inventory import cmd_info, cmd_list
from core_runtime.cli.release_check import cmd_release_check
from core_runtime.cli.repair_artifact_paths import cmd_repair_artifact_paths
from core_runtime.cli.sync_template import cmd_sync_template
from core_runtime.cli.validate import cmd_validate
from core_runtime.tooling.diagnostics import DiagnosticCollection
from core_runtime.tooling.file_inventory import FileInventory
from core_runtime.tooling.json_checks import JSONChecks
from core_runtime.tooling.report_writer import ReportWriter
from core_runtime.tooling.release_check import RELEASE_CHECK_PROFILES
from core_runtime.tooling.safety_checks import SafetyChecks
from core_runtime.tooling.version_inventory import VersionInventory


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="core-runtime",
        description="CORE Runtime tooling commands",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    # lint subcommand
    lint_parser = subparsers.add_parser("lint", help="Run tooling lint checks")
    lint_parser.add_argument(
        "--scope",
        choices=["tooling"],
        default="tooling",
        help="Scope of lint checks (default: tooling)",
    )
    lint_parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="Output format (default: json)",
    )
    lint_parser.add_argument(
        "--output",
        type=Path,
        help="Write output to file instead of stdout",
    )
    lint_parser.set_defaults(func=cmd_lint)

    # release-check subcommand
    release_check_parser = subparsers.add_parser(
        "release-check",
        help="Run lint precheck and the authoritative release gate",
    )
    release_check_parser.add_argument(
        "--target",
        type=str,
        default=None,
        help="Release target (default: canonical version from core_runtime/__version__.py)",
    )
    release_check_parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="Output format (default: json)",
    )
    release_check_parser.add_argument(
        "--output",
        type=Path,
        help="Write output to file instead of stdout",
    )
    release_check_parser.add_argument(
        "--skip-tooling-lint",
        action="store_true",
        default=False,
        help="Skip the tooling lint precheck",
    )
    release_check_parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Maximum seconds for the release gate subprocess (default: 120)",
    )
    release_check_parser.add_argument(
        "--preflight-only",
        action="store_true",
        default=False,
        help="Run bounded preflight checks without the full release gate",
    )
    release_check_parser.add_argument(
        "--group",
        default=None,
        help="Run a named release-gate group instead of the full gate",
    )
    release_check_parser.add_argument(
        "--profile",
        choices=sorted(RELEASE_CHECK_PROFILES),
        default=None,
        help="Run a named release-check profile preset",
    )
    release_check_parser.add_argument(
        "--list-checks",
        action="store_true",
        default=False,
        help="List available release-gate checks without executing them",
    )
    release_check_parser.add_argument(
        "--plan",
        action="store_true",
        default=False,
        help="Emit the release-gate execution plan without running checks",
    )
    release_check_parser.add_argument(
        "--timing-json",
        default=None,
        help="Write deterministic release-gate timing output to a JSON file",
    )
    release_check_parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Include debug details in the report",
    )
    release_check_parser.set_defaults(func=cmd_release_check)

    # bump-version subcommand
    bump_parser = subparsers.add_parser(
        "bump-version",
        help="Plan or apply a version bump",
    )
    bump_parser.add_argument(
        "target_version",
        help="Target version (e.g. 10.5.1)",
    )
    bump_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Dry-run mode (compute planned changes without mutation)",
    )
    bump_parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Apply mode (perform the actual version mutation)",
    )
    bump_parser.add_argument(
        "--confirm-current",
        type=str,
        default=None,
        help="Confirm the current version before apply (required with --apply)",
    )
    bump_parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="Output format (default: json)",
    )
    bump_parser.add_argument(
        "--output",
        type=Path,
        help="Write output to file instead of stdout",
    )
    bump_parser.set_defaults(func=cmd_bump_version)

    # list subcommand
    list_parser = subparsers.add_parser("list", help="List read-only repository inventory items")
    list_parser.add_argument(
        "kind",
        nargs="?",
        default="schemas",
        help="Inventory kind to list (schemas|contracts|adapters|domains; default: schemas)",
    )
    list_parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="Output format (default: json)",
    )
    list_parser.add_argument(
        "--output",
        type=Path,
        help="Write output to file instead of stdout",
    )
    list_parser.set_defaults(func=cmd_list)

    # info subcommand
    info_parser = subparsers.add_parser("info", help="Show repository inventory summary or item details")
    info_parser.add_argument(
        "kind",
        nargs="?",
        default=None,
        help="Optional inventory kind to inspect (schema|schemas|contract|contracts|adapter|adapters|domain|domains)",
    )
    info_parser.add_argument(
        "name",
        nargs="?",
        default=None,
        help="Optional item name to inspect inside the selected kind",
    )
    info_parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="Output format (default: json)",
    )
    info_parser.add_argument(
        "--output",
        type=Path,
        help="Write output to file instead of stdout",
    )
    info_parser.set_defaults(func=cmd_info)

    # validate subcommand
    validate_parser = subparsers.add_parser("validate", help="Run read-only structural validation")
    validate_parser.add_argument(
        "kind",
        nargs="?",
        default="schemas",
        help="Validation kind (schemas|examples|manifests|contracts|domain; default: schemas)",
    )
    validate_parser.add_argument(
        "name",
        nargs="?",
        default=None,
        help="Optional name for domain validation",
    )
    validate_parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="Output format (default: json)",
    )
    validate_parser.add_argument(
        "--output",
        type=Path,
        help="Write output to file instead of stdout",
    )
    validate_parser.set_defaults(func=cmd_validate)

    # doctor subcommand
    doctor_parser = subparsers.add_parser("doctor", help="Run read-only environment diagnostics")
    doctor_parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="Output format (default: json)",
    )
    doctor_parser.add_argument(
        "--output",
        type=Path,
        help="Write output to file instead of stdout",
    )
    doctor_parser.set_defaults(func=cmd_doctor)

    # contract-preflight subcommand
    contract_preflight_parser = subparsers.add_parser(
        "contract-preflight",
        help="Run advisory-only contract candidate review",
    )
    mode_group = contract_preflight_parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--candidate",
        type=str,
        default=None,
        help="Review a known contract candidate by name",
    )
    mode_group.add_argument(
        "--compare",
        nargs=2,
        metavar=("LEFT", "RIGHT"),
        default=None,
        help="Compare two known contract candidates",
    )
    contract_preflight_parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="Output format (default: json)",
    )
    contract_preflight_parser.add_argument(
        "--output",
        type=Path,
        help="Write output to file instead of stdout",
    )
    contract_preflight_parser.set_defaults(func=cmd_contract_preflight)

    # create-domain subcommand
    create_domain_parser = subparsers.add_parser(
        "create-domain",
        help="Plan a new domain scaffold (dry-run only in this slice)",
    )
    create_domain_parser.add_argument(
        "name",
        help="Domain name to scaffold",
    )
    create_domain_parser.add_argument(
        "--template",
        default="generic",
        help="Template name to use for the plan (default: generic)",
    )
    create_domain_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Required for this slice; emit plan without mutating files",
    )
    create_domain_parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="Output format (default: json)",
    )
    create_domain_parser.add_argument(
        "--output",
        type=Path,
        help="Write output to file instead of stdout",
    )
    create_domain_parser.set_defaults(func=cmd_create_domain)

    # sync-template subcommand
    sync_template_parser = subparsers.add_parser(
        "sync-template",
        help="Compare domains against the canonical scaffold template",
    )
    sync_mode_group = sync_template_parser.add_mutually_exclusive_group(required=True)
    sync_mode_group.add_argument(
        "--domain",
        type=str,
        default=None,
        help="Sync a single domain against the template",
    )
    sync_mode_group.add_argument(
        "--all",
        action="store_true",
        default=False,
        help="Sync all discovered domains against the template",
    )
    sync_template_parser.add_argument(
        "--template",
        default="generic",
        help="Template name to compare against (default: generic)",
    )
    sync_template_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Required for this slice; emit plan without mutating files",
    )
    sync_template_parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="Output format (default: json)",
    )
    sync_template_parser.add_argument(
        "--output",
        type=Path,
        help="Write output to file instead of stdout",
    )
    sync_template_parser.set_defaults(func=cmd_sync_template)

    # repair-artifact-paths subcommand
    repair_parser = subparsers.add_parser(
        "repair-artifact-paths",
        help="Plan repairs for migrated artifact path references",
    )
    repair_parser.add_argument(
        "--from",
        dest="source_path",
        default=None,
        help="Source path or prefix to replace",
    )
    repair_parser.add_argument(
        "--to",
        dest="destination_path",
        default=None,
        help="Destination path or prefix to use",
    )
    repair_parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional migration manifest to drive repair rules",
    )
    repair_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Required in this slice; emit a repair plan without mutating files",
    )
    repair_parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Reserved for a later guarded mutation slice",
    )
    repair_parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="Output format (default: json)",
    )
    repair_parser.add_argument(
        "--output",
        type=Path,
        help="Write output to file instead of stdout",
    )
    repair_parser.set_defaults(func=cmd_repair_artifact_paths)

    return parser


def cmd_lint(args: argparse.Namespace) -> int:
    """Execute the lint command."""
    repo_root = Path(__file__).resolve().parents[2]  # core_runtime/cli/ -> core_runtime/ -> repo_root

    # Initialize checkers
    version_inv = VersionInventory(repo_root)
    file_inv = FileInventory(repo_root)
    json_checks = JSONChecks(repo_root)
    safety_checks = SafetyChecks(repo_root)
    report_writer = ReportWriter(repo_root)

    from core_runtime.tooling.diagnostics import DiagnosticCollection

    diagnostics = DiagnosticCollection()

    # 1. Version inventory and consistency
    version_sources = version_inv.check_consistency(diagnostics)
    version_inv.check_changelog_latest(diagnostics)
    version_inv.check_release_note(diagnostics)

    # 2. Required file inventory
    file_results = file_inv.check_all(diagnostics)

    # 3. Script compilation checks
    check_script_compilation(repo_root, diagnostics)

    # 4. JSON parse checks
    schema_checked, schema_errors = json_checks.check_schemas(diagnostics)
    example_checked, example_errors = json_checks.check_examples(diagnostics)
    lock_ok = json_checks.check_requirements_lock(diagnostics)

    json_results = {
        "schemas_checked": schema_checked,
        "schemas_errors": schema_errors,
        "examples_checked": example_checked,
        "examples_errors": example_errors,
        "requirements_lock_readable": lock_ok,
    }

    # 5. Stale documentation checks (warnings)
    check_stale_docs(repo_root, diagnostics)

    # 6. Safety checks
    safety_checks.check_private_path_leakage(diagnostics)
    safety_checks.check_proposal_execution_safety(diagnostics)
    safety_checks.check_todo_templates(diagnostics)

    safety_results = {
        "private_path_scan": "completed",
        "proposal_safety_scan": "completed",
        "template_scan": "completed",
    }

    # Write output
    if args.format == "json":
        report = report_writer.write_json(
            diagnostics=diagnostics,
            scope=args.scope,
            output_path=args.output,
            version_sources=version_sources,
            file_inventory=file_results,
            json_checks=json_results,
            safety_checks=safety_results,
        )
        if not args.output:
            import json
            print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        markdown = report_writer.write_markdown(
            diagnostics=diagnostics,
            scope=args.scope,
            output_path=args.output,
            version_sources=version_sources,
            file_inventory=file_results,
            json_checks=json_results,
            safety_checks=safety_results,
        )
        if not args.output:
            print(markdown)

    # Return exit code
    return diagnostics.compute_exit_code().value


def check_script_compilation(repo_root: Path, diagnostics: DiagnosticCollection) -> dict:
    """Check that key scripts compile without errors."""
    import py_compile

    scripts = [
        "scripts/verify_release.py",
        "scripts/check_version_consistency.py",
        "scripts/bump_version.py",
        "scripts/generate_requirements_lock.py",
    ]

    results = {}
    for script in scripts:
        script_path = repo_root / script
        if not script_path.exists():
            diagnostics.add_error(
                code="core.script.missing",
                message="Required script not found: {0}".format(script),
                path=script,
                expected="exists",
                actual="missing",
            )
            results[script] = False
            continue

        try:
            py_compile.compile(str(script_path), doraise=True)
            results[script] = True
        except py_compile.PyCompileError as e:
            # e.args = (message, (filename, lineno, offset, text))
            lineno = e.args[1][1] if len(e.args) > 1 and len(e.args[1]) > 1 else "unknown"
            diagnostics.add_error(
                code="core.script.compile_error",
                message="Script compilation failed: {0}".format(e.msg),
                path=script,
                details="line {0}: {1}".format(lineno, e.msg),
            )
            results[script] = False
        except Exception as e:
            diagnostics.add_error(
                code="core.script.compile_error",
                message="Script compilation error: {0}".format(e),
                path=script,
            )
            results[script] = False

    return results


def check_stale_docs(repo_root: Path, diagnostics: DiagnosticCollection) -> None:
    """Check for known stale documentation references."""
    def _is_historical_reference(text: str) -> bool:
        return "historical" in text.lower()

    # VERSIONING_POLICY.md - v4.x compatibility matrix
    vpolicy = repo_root / "docs" / "VERSIONING_POLICY.md"
    if vpolicy.exists():
        text = vpolicy.read_text(encoding="utf-8")
        if "v4." in text and "compatibility" in text.lower() and not _is_historical_reference(text):
            diagnostics.add_warning(
                code="core.docs.stale_compatibility_matrix",
                message="VERSIONING_POLICY.md contains v4.x-era compatibility matrix",
                path="docs/VERSIONING_POLICY.md",
                details="Should be updated for current versioning",
            )

    # QUALITY_GATE.md - v4.4.0-rc1 reference
    qgate = repo_root / "docs" / "QUALITY_GATE.md"
    if qgate.exists():
        text = qgate.read_text(encoding="utf-8")
        if ("v4.4.0-rc1" in text or "4.4.0-rc1" in text) and not _is_historical_reference(text):
            diagnostics.add_warning(
                code="core.docs.stale_quality_gate",
                message="QUALITY_GATE.md references v4.4.0-rc1",
                path="docs/QUALITY_GATE.md",
                details="Should reference current version",
            )
