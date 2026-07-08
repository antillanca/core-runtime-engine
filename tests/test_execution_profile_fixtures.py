from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


PROFILE_DIR = Path("examples/execution_profiles")
EXPECTED_SCHEMA = "core.execution_profile.v1"

EXPECTED_PROFILES = {
    "audit_profile.json": "audit",
    "certified_profile.json": "certified",
    "explainable_profile.json": "explainable",
    "minimal_profile.json": "minimal",
    "standard_profile.json": "standard",
}

REQUIRED_FIELDS = {
    "profile_schema",
    "profile_id",
    "profile_name",
    "description",
    "requirements",
    "safety",
    "expected_use",
    "notes",
}

REQUIRED_REQUIREMENTS = {
    "audit_level",
    "requires_batch_report",
    "requires_certified_evidence",
    "requires_deterministic_evaluation",
    "requires_explainability",
    "requires_replay_certification",
    "requires_structural_validation",
}

REQUIRED_SAFETY = {
    "allows_runtime_mutation",
    "allows_tool_execution",
}

ABSOLUTE_PATH_PATTERNS = [
    re.compile(r"(?<![A-Za-z0-9_])/[^\s\"']+"),
    re.compile(r"[A-Za-z]:\\\\"),
]

CLAIM_PATTERNS = [
    re.compile(r"[0-9]+%"),
    re.compile(r"\$[0-9]"),
    re.compile(r"ROI", re.IGNORECASE),
    re.compile(r"accuracy", re.IGNORECASE),
    re.compile(r"compliance guaranteed", re.IGNORECASE),
]


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _flatten(value: Any) -> str:
    if isinstance(value, dict):
        return "\n".join(
            f"{key}: {_flatten(inner)}"
            for key, inner in sorted(value.items())
        )
    if isinstance(value, list):
        return "\n".join(_flatten(item) for item in value)
    return str(value)


def test_expected_execution_profile_fixtures_exist():
    for filename in EXPECTED_PROFILES:
        assert (PROFILE_DIR / filename).exists()


def test_execution_profile_fixtures_match_minimal_contract():
    for filename, profile_name in EXPECTED_PROFILES.items():
        payload = _load(PROFILE_DIR / filename)

        assert REQUIRED_FIELDS.issubset(payload)
        assert payload["profile_schema"] == EXPECTED_SCHEMA
        assert payload["profile_name"] == profile_name
        assert payload["profile_id"] == f"execution_profile:{profile_name}:v1"

        assert isinstance(payload["description"], str)
        assert isinstance(payload["expected_use"], str)
        assert isinstance(payload["notes"], list)
        assert payload["notes"]

        assert isinstance(payload["requirements"], dict)
        assert REQUIRED_REQUIREMENTS.issubset(payload["requirements"])

        assert isinstance(payload["safety"], dict)
        assert REQUIRED_SAFETY.issubset(payload["safety"])


def test_all_execution_profile_fixtures_are_non_executable():
    for filename in EXPECTED_PROFILES:
        payload = _load(PROFILE_DIR / filename)

        assert payload["safety"]["allows_tool_execution"] is False
        assert payload["safety"]["allows_runtime_mutation"] is False


def test_execution_profiles_have_expected_requirement_progression():
    minimal = _load(PROFILE_DIR / "minimal_profile.json")
    standard = _load(PROFILE_DIR / "standard_profile.json")
    certified = _load(PROFILE_DIR / "certified_profile.json")
    explainable = _load(PROFILE_DIR / "explainable_profile.json")
    audit = _load(PROFILE_DIR / "audit_profile.json")

    assert minimal["requirements"]["requires_structural_validation"] is True
    assert minimal["requirements"]["requires_deterministic_evaluation"] is False

    assert standard["requirements"]["requires_deterministic_evaluation"] is True
    assert standard["requirements"]["requires_batch_report"] is True

    assert certified["requirements"]["requires_certified_evidence"] is True
    assert explainable["requirements"]["requires_explainability"] is True

    assert audit["requirements"]["requires_certified_evidence"] is True
    assert audit["requirements"]["requires_explainability"] is True
    assert audit["requirements"]["requires_replay_certification"] is True


def test_execution_profile_fixtures_do_not_contain_absolute_paths():
    for filename in EXPECTED_PROFILES:
        flattened = _flatten(_load(PROFILE_DIR / filename))
        for pattern in ABSOLUTE_PATH_PATTERNS:
            assert not pattern.search(flattened), filename


def test_execution_profile_fixtures_do_not_contain_unverified_claims():
    for filename in EXPECTED_PROFILES:
        flattened = _flatten(_load(PROFILE_DIR / filename))
        for pattern in CLAIM_PATTERNS:
            assert not pattern.search(flattened), filename


def test_execution_profile_fixture_files_are_pretty_json_with_trailing_newline():
    for filename in EXPECTED_PROFILES:
        path = PROFILE_DIR / filename
        text = path.read_text(encoding="utf-8")

        assert text.endswith("\n")
        assert json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n" == text
