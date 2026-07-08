from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SCRIPT = Path("scripts/validate_execution_profile.py")
PROFILE_DIR = Path("examples/execution_profiles")

VALID_PROFILES = [
    "audit_profile.json",
    "certified_profile.json",
    "explainable_profile.json",
    "minimal_profile.json",
    "standard_profile.json",
]


def _run(path: Path):
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path)],
        check=False,
        capture_output=True,
        text=True,
    )


def _payload(result) -> dict[str, Any]:
    assert result.stdout.strip(), result.stderr
    return json.loads(result.stdout)


def _valid_profile() -> dict[str, Any]:
    return json.loads(
        (PROFILE_DIR / "standard_profile.json").read_text(encoding="utf-8")
    )


def _write_profile(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "profile.json"
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def test_all_execution_profile_fixtures_pass_structural_validation():
    for filename in VALID_PROFILES:
        result = _run(PROFILE_DIR / filename)
        payload = _payload(result)

        assert result.returncode == 0, result.stderr
        assert payload["schema"] == "core.execution_profile_validation.v1"
        assert payload["status"] == "passed"
        assert payload["errors"] == []
        assert payload["warnings"] == []


def test_validate_execution_profile_output_is_byte_stable():
    first = _run(PROFILE_DIR / "audit_profile.json")
    second = _run(PROFILE_DIR / "audit_profile.json")

    assert first.returncode == 0
    assert second.returncode == 0
    assert first.stdout == second.stdout


def test_invalid_profile_schema_fails(tmp_path):
    profile = _valid_profile()
    profile["profile_schema"] = "core.execution_profile.v999"

    result = _run(_write_profile(tmp_path, profile))
    payload = _payload(result)

    assert result.returncode == 1
    assert any(error["code"] == "invalid_profile_schema" for error in payload["errors"])


def test_missing_required_field_fails(tmp_path):
    profile = _valid_profile()
    del profile["profile_id"]

    result = _run(_write_profile(tmp_path, profile))
    payload = _payload(result)

    assert result.returncode == 1
    assert any(error["code"] == "missing_required_field" for error in payload["errors"])


def test_unknown_root_field_fails(tmp_path):
    profile = _valid_profile()
    profile["unexpected"] = "not allowed"

    result = _run(_write_profile(tmp_path, profile))
    payload = _payload(result)

    assert result.returncode == 1
    assert any(error["code"] == "unknown_field" for error in payload["errors"])


def test_invalid_profile_id_format_fails(tmp_path):
    profile = _valid_profile()
    profile["profile_id"] = "profile:standard"

    result = _run(_write_profile(tmp_path, profile))
    payload = _payload(result)

    assert result.returncode == 1
    assert any(error["code"] == "invalid_profile_id_format" for error in payload["errors"])


def test_profile_id_name_mismatch_fails(tmp_path):
    profile = _valid_profile()
    profile["profile_id"] = "execution_profile:minimal:v1"
    profile["profile_name"] = "standard"

    result = _run(_write_profile(tmp_path, profile))
    payload = _payload(result)

    assert result.returncode == 1
    assert any(error["code"] == "profile_id_name_mismatch" for error in payload["errors"])


def test_missing_requirement_field_fails(tmp_path):
    profile = _valid_profile()
    del profile["requirements"]["requires_batch_report"]

    result = _run(_write_profile(tmp_path, profile))
    payload = _payload(result)

    assert result.returncode == 1
    assert any(error["code"] == "missing_requirement_field" for error in payload["errors"])


def test_unknown_requirement_field_fails(tmp_path):
    profile = _valid_profile()
    profile["requirements"]["unknown_requirement"] = True

    result = _run(_write_profile(tmp_path, profile))
    payload = _payload(result)

    assert result.returncode == 1
    assert any(error["code"] == "unknown_requirement_field" for error in payload["errors"])


def test_invalid_requirement_type_fails(tmp_path):
    profile = _valid_profile()
    profile["requirements"]["requires_batch_report"] = "yes"

    result = _run(_write_profile(tmp_path, profile))
    payload = _payload(result)

    assert result.returncode == 1
    assert any(error["code"] == "invalid_requirement_type" for error in payload["errors"])


def test_missing_safety_field_fails(tmp_path):
    profile = _valid_profile()
    del profile["safety"]["allows_tool_execution"]

    result = _run(_write_profile(tmp_path, profile))
    payload = _payload(result)

    assert result.returncode == 1
    assert any(error["code"] == "missing_safety_field" for error in payload["errors"])


def test_unknown_safety_field_fails(tmp_path):
    profile = _valid_profile()
    profile["safety"]["allows_network"] = False

    result = _run(_write_profile(tmp_path, profile))
    payload = _payload(result)

    assert result.returncode == 1
    assert any(error["code"] == "unknown_safety_field" for error in payload["errors"])


def test_allows_tool_execution_true_fails(tmp_path):
    profile = _valid_profile()
    profile["safety"]["allows_tool_execution"] = True

    result = _run(_write_profile(tmp_path, profile))
    payload = _payload(result)

    assert result.returncode == 1
    assert any(error["code"] == "unsafe_tool_execution_allowed" for error in payload["errors"])


def test_allows_runtime_mutation_true_fails(tmp_path):
    profile = _valid_profile()
    profile["safety"]["allows_runtime_mutation"] = True

    result = _run(_write_profile(tmp_path, profile))
    payload = _payload(result)

    assert result.returncode == 1
    assert any(error["code"] == "unsafe_runtime_mutation_allowed" for error in payload["errors"])


def test_absolute_path_fails(tmp_path):
    profile = _valid_profile()
    profile["notes"].append("/home/example/private")

    result = _run(_write_profile(tmp_path, profile))
    payload = _payload(result)

    assert result.returncode == 1
    assert any(error["code"] == "absolute_path_detected" for error in payload["errors"])


def test_secret_like_content_fails(tmp_path):
    profile = _valid_profile()
    profile["notes"].append("api_key=not-real")

    result = _run(_write_profile(tmp_path, profile))
    payload = _payload(result)

    assert result.returncode == 1
    assert any(error["code"] == "secret_like_content_detected" for error in payload["errors"])


def test_unverified_claim_fails(tmp_path):
    profile = _valid_profile()
    profile["description"] = "Improves accuracy by 99%."

    result = _run(_write_profile(tmp_path, profile))
    payload = _payload(result)

    assert result.returncode == 1
    assert any(error["code"] == "unverified_claim_detected" for error in payload["errors"])


def test_invalid_json_fails_without_traceback(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text("{not valid json", encoding="utf-8")

    result = _run(path)
    payload = _payload(result)

    assert result.returncode == 1
    assert payload["status"] == "failed"
    assert any(error["code"] == "invalid_json" for error in payload["errors"])
    assert "Traceback" not in result.stderr
    assert "Traceback" not in result.stdout


def test_missing_file_returns_usage_error():
    result = _run(Path("examples/execution_profiles/does_not_exist.json"))
    payload = _payload(result)

    assert result.returncode == 2
    assert payload["status"] == "failed"
    assert any(error["code"] == "file_not_found" for error in payload["errors"])
