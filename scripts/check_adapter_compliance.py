#!/usr/bin/env python3
"""Check whether an adapter directory is well formed as a CORE extension."""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


ALLOWED_IMPORT_ROOTS = {
    "__future__",
}
ALLOWED_CORE_IMPORTS = {
    "core_runtime.core.sensor_evidence",
}


def _canonical_dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _display_path(path: Path, *, anchor: Path | None = None) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        if anchor is not None:
            resolved_anchor = anchor.resolve()
            try:
                relative = resolved.relative_to(resolved_anchor)
            except ValueError:
                pass
            else:
                relative_str = relative.as_posix()
                if relative_str == ".":
                    return anchor.name
                return f"{anchor.name}/{relative_str}"

        return path.name


def _check(status: str, **metadata: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": status}
    for key, value in sorted(metadata.items()):
        if value is not None:
            payload[key] = value
    return payload


def _error(code: str, message: str, **metadata: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    for key, value in sorted(metadata.items()):
        if value is not None:
            payload[key] = value
    return payload


def _run_json_command(command: list[str]) -> tuple[int, dict[str, Any], str]:
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()

    if not stdout:
        return result.returncode, {}, stderr

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return result.returncode, {}, stdout + ("\n" + stderr if stderr else "")

    return result.returncode, payload, stderr


def _extract_imports(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return ["<syntax-error>"]

    imports: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                imports.append("<relative-import>")
            else:
                imports.append(node.module)

    return sorted(imports)


def _is_allowed_import(module: str) -> bool:
    if module in {"<syntax-error>", "<relative-import>"}:
        return False
    if module in ALLOWED_CORE_IMPORTS:
        return True
    root = module.split(".", 1)[0]
    return root in ALLOWED_IMPORT_ROOTS or root in sys.stdlib_module_names


def _find_absolute_path_strings(path: Path, *, anchor: Path | None = None) -> list[str]:
    findings: list[str] = []

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return findings

    for line_number, line in enumerate(text.splitlines(), start=1):
        if "/home/" in line or "/tmp/" in line or "\\Users\\" in line:
            findings.append(f"{_display_path(path, anchor=anchor)}:{line_number}")

    return findings


def _discover_fixtures(adapter_dir: Path) -> list[Path]:
    fixtures_dir = adapter_dir / "fixtures"
    if not fixtures_dir.exists():
        return []
    return sorted(fixture for fixture in fixtures_dir.iterdir() if fixture.is_dir())


def _invalid_adapter_dir_payload(adapter_dir: Path) -> dict[str, Any]:
    return {
        "adapter_dir": _display_path(adapter_dir),
        "status": "failed",
        "compliant": False,
        "errors": [
            _error(
                "adapter_dir_missing",
                "Adapter directory does not exist.",
            )
        ],
        "warnings": [],
        "checks": {},
        "fixtures": {},
    }


def check_adapter_compliance(adapter_dir: Path) -> tuple[int, dict[str, Any]]:
    adapter_dir = Path(adapter_dir)
    adapter_dir_display = _display_path(adapter_dir)

    if not adapter_dir.exists():
        return 2, _invalid_adapter_dir_payload(adapter_dir)

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    checks: dict[str, dict[str, Any]] = {}
    fixtures_payload: dict[str, dict[str, Any]] = {}

    readme_path = adapter_dir / "README.md"
    generator_path = adapter_dir / "generate_fixture.py"
    fixtures_dir = adapter_dir / "fixtures"

    readme_exists = readme_path.exists()
    generator_exists = generator_path.exists()
    fixtures_dir_exists = fixtures_dir.exists()

    checks["readme_exists"] = _check("passed" if readme_exists else "failed")
    checks["generator_exists"] = _check("passed" if generator_exists else "failed")
    checks["fixtures_dir_exists"] = _check("passed" if fixtures_dir_exists else "failed")

    if not readme_exists:
        errors.append(_error("readme_missing", "Adapter README.md is missing."))
    if not generator_exists:
        errors.append(_error("generator_missing", "Adapter generate_fixture.py is missing."))
    if not fixtures_dir_exists:
        errors.append(_error("fixtures_dir_missing", "Adapter fixtures/ directory is missing."))

    fixtures = _discover_fixtures(adapter_dir)
    checks["fixtures_discovered"] = _check(
        "passed" if fixtures else "failed",
        count=len(fixtures),
    )

    if not fixtures:
        errors.append(_error("fixtures_missing", "No fixture directories were found."))

    if generator_exists:
        imports = _extract_imports(generator_path)
        disallowed_imports = [module for module in imports if not _is_allowed_import(module)]
        checks["generator_imports_allowed"] = _check(
            "passed" if not disallowed_imports else "failed",
            imports=imports,
            disallowed_imports=disallowed_imports,
        )
        if disallowed_imports:
            errors.append(
                _error(
                    "disallowed_imports",
                    "Adapter generator imports modules outside the allowed set.",
                    disallowed_imports=disallowed_imports,
                )
            )
    else:
        checks["generator_imports_allowed"] = _check("failed")

    absolute_path_findings: list[str] = []
    for candidate in [readme_path, generator_path]:
        if candidate.exists():
            absolute_path_findings.extend(
                _find_absolute_path_strings(candidate, anchor=adapter_dir)
            )

    for fixture in fixtures:
        for candidate in [fixture / "manifest.json", fixture / "samples.csv"]:
            if candidate.exists():
                absolute_path_findings.extend(
                    _find_absolute_path_strings(candidate, anchor=adapter_dir)
                )

    checks["no_absolute_paths"] = _check(
        "passed" if not absolute_path_findings else "failed",
        findings=absolute_path_findings,
    )
    if absolute_path_findings:
        errors.append(
            _error(
                "absolute_paths_found",
                "Adapter files contain local absolute path strings.",
                findings=absolute_path_findings,
            )
        )

    fixture_files_ok = True
    validation_ok = True
    certification_ok = True
    validator_deterministic = True
    certifier_deterministic = True

    for fixture in fixtures:
        manifest_path = fixture / "manifest.json"
        samples_path = fixture / "samples.csv"
        fixture_name = fixture.name
        fixture_rel = _display_path(fixture, anchor=adapter_dir)

        fixture_payload: dict[str, Any] = {
            "fixture_dir": fixture_rel,
        }

        if not manifest_path.exists():
            fixture_files_ok = False
            errors.append(
                _error(
                    "fixture_manifest_missing",
                    "Fixture manifest.json is missing.",
                    fixture_dir=fixture_rel,
                )
            )
            fixture_payload["validation_status"] = "missing"
            fixture_payload["certification_status"] = "missing"
            fixtures_payload[fixture_name] = fixture_payload
            continue

        if not samples_path.exists():
            fixture_files_ok = False
            errors.append(
                _error(
                    "fixture_samples_missing",
                    "Fixture samples.csv is missing.",
                    fixture_dir=fixture_rel,
                )
            )
            fixture_payload["validation_status"] = "missing"
            fixture_payload["certification_status"] = "missing"
            fixtures_payload[fixture_name] = fixture_payload
            continue

        validation_command = [
            sys.executable,
            "scripts/validate_sensor_manifest.py",
            str(fixture),
        ]
        first_validation_code, first_validation, _first_validation_err = _run_json_command(
            validation_command
        )
        second_validation_code, second_validation, _second_validation_err = _run_json_command(
            validation_command
        )

        if first_validation_code != 0:
            validation_ok = False
        if first_validation != second_validation:
            validator_deterministic = False

        certification_command = [
            sys.executable,
            "scripts/certify_sensor_fixture.py",
            str(fixture),
        ]
        first_certification_code, first_certification, _first_certification_err = _run_json_command(
            certification_command
        )
        second_certification_code, second_certification, _second_certification_err = _run_json_command(
            certification_command
        )

        if first_certification_code != 0:
            certification_ok = False
        if first_certification != second_certification:
            certifier_deterministic = False

        fixture_payload.update(
            {
                "validation_status": first_validation.get("status", "failed"),
                "certification_status": first_certification.get("status", "failed"),
            }
        )
        fixtures_payload[fixture_name] = fixture_payload

    checks["fixture_files_exist"] = _check("passed" if fixture_files_ok else "failed")
    checks["fixture_validation"] = _check("passed" if validation_ok else "failed")
    checks["fixture_certification"] = _check("passed" if certification_ok else "failed")
    checks["validator_deterministic"] = _check("passed" if validator_deterministic else "failed")
    checks["certifier_deterministic"] = _check("passed" if certifier_deterministic else "failed")

    if not validation_ok:
        errors.append(_error("fixture_validation_failed", "At least one fixture failed validation."))
    if not certification_ok:
        errors.append(_error("fixture_certification_failed", "At least one fixture failed certification."))
    if not validator_deterministic:
        errors.append(_error("validator_not_deterministic", "Validator output differed across repeated runs."))
    if not certifier_deterministic:
        errors.append(_error("certifier_not_deterministic", "Certifier output differed across repeated runs."))

    compliant = not errors and all(check["status"] == "passed" for check in checks.values())

    payload = {
        "adapter_dir": adapter_dir_display,
        "status": "compliant" if compliant else "failed",
        "compliant": compliant,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
        "fixtures": fixtures_payload,
    }

    return (0 if compliant else 1), payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check CORE adapter compliance.")
    parser.add_argument(
        "adapter_dir",
        help="Path to adapter directory, for example examples/adapters/minimal_sensor_adapter.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    exit_code, payload = check_adapter_compliance(Path(args.adapter_dir))
    print(_canonical_dump(payload))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
