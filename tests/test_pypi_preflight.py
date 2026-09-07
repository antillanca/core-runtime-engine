from __future__ import annotations

from scripts.pypi_preflight import classify_project_metadata


def test_missing_version_is_available() -> None:
    result = classify_project_metadata({"releases": {"11.5.1": [{}]}}, "11.6.0")
    assert result == {"status": "passed", "state": "version_available", "errors": []}


def test_existing_version_is_collision() -> None:
    result = classify_project_metadata({"releases": {"11.6.0": []}}, "11.6.0")
    assert result["status"] == "blocked"
    assert result["state"] == "collision"
    assert result["errors"][0]["code"] == "version_already_exists"


def test_malformed_response_blocks() -> None:
    result = classify_project_metadata({}, "11.6.0")
    assert result["status"] == "blocked"
    assert result["state"] == "malformed_registry_response"
