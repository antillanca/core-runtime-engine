from __future__ import annotations

import copy
import json
from pathlib import Path

from core_runtime.core.rule_anchor import artifact_fingerprint
from scripts.validate_frozen_release_manifest_v11_3_frozen import (
    INVENTORY_PROFILE,
    RELEASE_VERSION,
    build_v11_3_frozen_manifest,
    required_v11_3_frozen_artifacts,
    validate_v11_3_frozen_release_manifest,
)


ROOT = Path(__file__).resolve().parent.parent
ACCEPTED = ROOT / "examples/frozen_release_manifest/accepted_v11_3_0.json"


def test_frozen_manifest_remains_valid_historical_evidence() -> None:
    payload = json.loads(ACCEPTED.read_text(encoding="utf-8"))
    report = validate_v11_3_frozen_release_manifest(ACCEPTED)

    assert report["status"] == "passed", report["errors"]
    assert payload["release_version"] == RELEASE_VERSION
    assert payload["inventory_profile"] == INVENTORY_PROFILE
    assert payload["status"] == "frozen"
    assert payload["artifact_count"] == len(required_v11_3_frozen_artifacts())
    assert report["live_artifacts_verified"] is False


def test_frozen_builder_is_deterministic_and_live_verification_is_explicit(tmp_path: Path) -> None:
    payload = json.loads(ACCEPTED.read_text(encoding="utf-8"))
    first = build_v11_3_frozen_manifest(payload["frozen_at"])

    assert build_v11_3_frozen_manifest(payload["frozen_at"]) == first
    volatile = {"artifacts", "fingerprint"}
    assert {key: value for key, value in first.items() if key not in volatile} == {
        key: value for key, value in payload.items() if key not in volatile
    }
    assert [(item["path"], item["role"]) for item in first["artifacts"]] == [
        (item["path"], item["role"]) for item in payload["artifacts"]
    ]

    current = tmp_path / "current-frozen.json"
    current.write_text(json.dumps(first), encoding="utf-8")
    assert validate_v11_3_frozen_release_manifest(current, verify_live_artifacts=True)["status"] == "passed"
    assert validate_v11_3_frozen_release_manifest(ACCEPTED, verify_live_artifacts=True)["status"] == "passed"


def test_frozen_manifest_fails_when_status_is_candidate(tmp_path: Path) -> None:
    payload = copy.deepcopy(json.loads(ACCEPTED.read_text(encoding="utf-8")))
    payload["status"] = "candidate"
    payload["fingerprint"] = artifact_fingerprint(payload)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_v11_3_frozen_release_manifest(path)
    assert report["status"] == "failed"
    assert any(item["code"] == "schema_validation_error" for item in report["errors"])
