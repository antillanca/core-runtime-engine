from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "scripts" / "validate_parametric_template.py"
FIXTURES_DIR = PROJECT_ROOT / "examples" / "parametric_templates"

VALID_FP = "sha256:" + "a" * 64


def _run_single(fixture: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(FIXTURES_DIR / fixture)],
        check=False,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )


def _run_directory() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(FIXTURES_DIR)],
        check=False,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )


def _run_payload(payload: dict) -> subprocess.CompletedProcess[str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, dir="/tmp") as f:
        json.dump(payload, f)
        f.flush()
        return subprocess.run(
            [sys.executable, str(SCRIPT), f.name],
            check=False,
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )


# === Valid fixtures ===


def test_valid_read_template_passes() -> None:
    result = _run_single("valid_read_template.json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    assert payload["results"][0]["artifact_type"] == "parametric_template"
    assert payload["results"][0]["template_id"] == "synthetic_reports.daily_summary.v1"
    assert payload["results"][0]["method"] == "read"


def test_valid_write_template_passes() -> None:
    result = _run_single("valid_write_template.json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    assert payload["results"][0]["method"] == "write"


def test_valid_binding_passes() -> None:
    result = _run_single("valid_binding_read.json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    assert payload["results"][0]["artifact_type"] == "variable_binding"
    assert payload["results"][0]["slot_count"] == 2


# === Invalid fixtures ===


def test_invalid_command_validation_false() -> None:
    result = _run_single("invalid_command_validation_false.json")
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "command_validation_not_required" in codes


def test_invalid_fingerprint_format() -> None:
    result = _run_single("invalid_fingerprint_format.json")
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "invalid_template_fingerprint" in codes


def test_invalid_enum_empty_values() -> None:
    result = _run_single("invalid_enum_empty_values.json")
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "enum_slot_empty_values" in codes
    assert "forbidden_categories_empty" in codes


# === Directory validation ===


def test_directory_validation_counts() -> None:
    result = _run_directory()
    assert result.returncode != 0  # 3 invalids
    payload = json.loads(result.stdout)
    assert payload["schema"] == "core.parametric_template_validation.v1"
    assert payload["total_artifacts"] == 6
    assert payload["passed_count"] == 3
    assert payload["failed_count"] == 3


# === Byte stability ===


def test_directory_validation_is_byte_stable() -> None:
    first = _run_directory()
    second = _run_directory()
    assert first.stdout == second.stdout


# === Structural edge cases: Template ===


def test_missing_schema_version() -> None:
    template = {
        "type": "parametric_template",
        "template_id": "synth.v1",
        "template_fingerprint": VALID_FP,
        "domain": "synth",
        "intent": "test",
        "slots": [{"name": "k", "type": "string", "required": True}],
        "route": {"action": "do_thing", "method": "read"},
        "safety": {"requires_command_validation": True, "forbidden_categories": ["live_results"]},
    }
    result = _run_payload(template)
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "missing_schema_version" in codes


def test_invalid_type() -> None:
    template = {
        "schema_version": "core.parametric_template.v1",
        "type": "wrong_type",
        "template_id": "synth.v1",
        "template_fingerprint": VALID_FP,
        "domain": "synth",
        "intent": "test",
        "slots": [{"name": "k", "type": "string", "required": True}],
        "route": {"action": "do_thing", "method": "read"},
        "safety": {"requires_command_validation": True, "forbidden_categories": ["live_results"]},
    }
    result = _run_payload(template)
    payload = json.loads(result.stdout)
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "invalid_type" in codes


def test_slots_empty() -> None:
    template = {
        "schema_version": "core.parametric_template.v1",
        "type": "parametric_template",
        "template_id": "synth.v1",
        "template_fingerprint": VALID_FP,
        "domain": "synth",
        "intent": "test",
        "slots": [],
        "route": {"action": "do_thing", "method": "read"},
        "safety": {"requires_command_validation": True, "forbidden_categories": ["live_results"]},
    }
    result = _run_payload(template)
    payload = json.loads(result.stdout)
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "slots_empty" in codes


def test_non_enum_slot_with_enum_values() -> None:
    template = {
        "schema_version": "core.parametric_template.v1",
        "type": "parametric_template",
        "template_id": "synth.v1",
        "template_fingerprint": VALID_FP,
        "domain": "synth",
        "intent": "test",
        "slots": [{"name": "k", "type": "string", "required": True, "enum_values": ["a", "b"]}],
        "route": {"action": "do_thing", "method": "read"},
        "safety": {"requires_command_validation": True, "forbidden_categories": ["live_results"]},
    }
    result = _run_payload(template)
    payload = json.loads(result.stdout)
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "non_enum_slot_has_enum_values" in codes


def test_route_invalid_method() -> None:
    template = {
        "schema_version": "core.parametric_template.v1",
        "type": "parametric_template",
        "template_id": "synth.v1",
        "template_fingerprint": VALID_FP,
        "domain": "synth",
        "intent": "test",
        "slots": [{"name": "k", "type": "string", "required": True}],
        "route": {"action": "do_thing", "method": "patch"},
        "safety": {"requires_command_validation": True, "forbidden_categories": ["live_results"]},
    }
    result = _run_payload(template)
    payload = json.loads(result.stdout)
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "route_invalid_method" in codes


def test_forbidden_categories_missing_live_results() -> None:
    template = {
        "schema_version": "core.parametric_template.v1",
        "type": "parametric_template",
        "template_id": "synth.v1",
        "template_fingerprint": VALID_FP,
        "domain": "synth",
        "intent": "test",
        "slots": [{"name": "k", "type": "string", "required": True}],
        "route": {"action": "do_thing", "method": "read"},
        "safety": {"requires_command_validation": True, "forbidden_categories": ["state_events"]},
    }
    result = _run_payload(template)
    payload = json.loads(result.stdout)
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "forbidden_categories_missing_live_results" in codes


# === Structural edge cases: Variable Binding ===


def test_binding_missing_value() -> None:
    binding = {
        "schema_version": "core.variable_binding.v1",
        "type": "variable_binding",
        "template_id": "synth.v1",
        "template_fingerprint": VALID_FP,
        "bindings": {"k": {"source": "explicit"}},
    }
    result = _run_payload(binding)
    payload = json.loads(result.stdout)
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "binding_missing_value" in codes


def test_binding_invalid_source() -> None:
    binding = {
        "schema_version": "core.variable_binding.v1",
        "type": "variable_binding",
        "template_id": "synth.v1",
        "template_fingerprint": VALID_FP,
        "bindings": {"k": {"value": "v", "source": "guessed"}},
    }
    result = _run_payload(binding)
    payload = json.loads(result.stdout)
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "binding_invalid_source" in codes


def test_bindings_not_object() -> None:
    binding = {
        "schema_version": "core.variable_binding.v1",
        "type": "variable_binding",
        "template_id": "synth.v1",
        "template_fingerprint": VALID_FP,
        "bindings": "not_an_object",
    }
    result = _run_payload(binding)
    payload = json.loads(result.stdout)
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "bindings_not_object" in codes


# === Structural edge cases: Cache Entry ===


def test_cache_entry_valid() -> None:
    entry = {
        "schema_version": "core.parametric_cache_entry.v1",
        "type": "parametric_cache_entry",
        "template_id": "synth.v1",
        "template_fingerprint": VALID_FP,
        "binding_fingerprint": VALID_FP,
        "compiled_shape": {
            "action": "generate_report",
            "method": "read",
            "resolved_slots": {"date_preset": "today"},
        },
        "cache_policy": {
            "ttl_seconds": 0,
            "max_entries_per_template": 100,
            "eviction_policy": "lru",
        },
        "safety": {
            "forbidden_categories_cached": ["live_results", "financial_state"],
            "live_data_excluded": True,
        },
    }
    result = _run_payload(entry)
    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    assert payload["results"][0]["artifact_type"] == "parametric_cache_entry"


def test_cache_entry_live_data_not_excluded() -> None:
    entry = {
        "schema_version": "core.parametric_cache_entry.v1",
        "type": "parametric_cache_entry",
        "template_id": "synth.v1",
        "template_fingerprint": VALID_FP,
        "binding_fingerprint": VALID_FP,
        "compiled_shape": {
            "action": "generate_report",
            "method": "read",
            "resolved_slots": {"date_preset": "today"},
        },
        "cache_policy": {
            "ttl_seconds": 0,
            "max_entries_per_template": 100,
            "eviction_policy": "lru",
        },
        "safety": {
            "forbidden_categories_cached": ["live_results"],
            "live_data_excluded": False,
        },
    }
    result = _run_payload(entry)
    payload = json.loads(result.stdout)
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "live_data_not_excluded" in codes


def test_cache_entry_invalid_binding_fingerprint() -> None:
    entry = {
        "schema_version": "core.parametric_cache_entry.v1",
        "type": "parametric_cache_entry",
        "template_id": "synth.v1",
        "template_fingerprint": VALID_FP,
        "binding_fingerprint": "bad_format",
        "compiled_shape": {
            "action": "generate_report",
            "method": "read",
            "resolved_slots": {"date_preset": "today"},
        },
        "cache_policy": {
            "ttl_seconds": 0,
            "max_entries_per_template": 100,
            "eviction_policy": "lru",
        },
        "safety": {
            "forbidden_categories_cached": ["live_results"],
            "live_data_excluded": True,
        },
    }
    result = _run_payload(entry)
    payload = json.loads(result.stdout)
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "missing_binding_fingerprint" in codes


def test_cache_entry_invalid_eviction_policy() -> None:
    entry = {
        "schema_version": "core.parametric_cache_entry.v1",
        "type": "parametric_cache_entry",
        "template_id": "synth.v1",
        "template_fingerprint": VALID_FP,
        "binding_fingerprint": VALID_FP,
        "compiled_shape": {
            "action": "generate_report",
            "method": "read",
            "resolved_slots": {"date_preset": "today"},
        },
        "cache_policy": {
            "ttl_seconds": 0,
            "max_entries_per_template": 100,
            "eviction_policy": "random",
        },
        "safety": {
            "forbidden_categories_cached": ["live_results"],
            "live_data_excluded": True,
        },
    }
    result = _run_payload(entry)
    payload = json.loads(result.stdout)
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "cache_policy_invalid_eviction" in codes


# === Unknown schema dispatch ===


def test_unknown_schema_version() -> None:
    artifact = {
        "schema_version": "core.unknown.v1",
        "type": "something",
    }
    result = _run_payload(artifact)
    payload = json.loads(result.stdout)
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "unknown_schema_version" in codes


def test_invalid_json_file() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, dir="/tmp") as f:
        f.write("not json at all")
        f.flush()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), f.name],
            check=False, capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    codes = [e["code"] for e in payload["results"][0]["errors"]]
    assert "invalid_json" in codes
