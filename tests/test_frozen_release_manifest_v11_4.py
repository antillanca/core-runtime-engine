from __future__ import annotations

import copy
import json
from pathlib import Path

import scripts.verify_release as verify_release
from core_runtime.core.rule_anchor import artifact_fingerprint
from scripts.validate_frozen_release_manifest_v11_4 import (
    CRITICAL_SUBSYSTEMS,
    INVENTORY_PROFILE,
    RELEASE_VERSION,
    build_v11_4_candidate_manifest,
    required_v11_4_candidate_artifacts,
    validate_v11_4_release_manifest,
)


ROOT = Path(__file__).resolve().parent.parent
ACCEPTED = ROOT / "examples/frozen_release_manifest/accepted_v11_4_0_candidate.json"


def test_verify_release_registers_v11_4_manifest_gates() -> None:
    assert (
        verify_release.FROZEN_RELEASE_MANIFEST_CHECKS["frozen_release_manifest_v11_4_candidate_accepted"][-1]
        == "examples/frozen_release_manifest/accepted_v11_4_0_candidate.json"
    )


def test_candidate_manifest_remains_valid_historical_evidence() -> None:
    payload = json.loads(ACCEPTED.read_text(encoding="utf-8"))
    report = validate_v11_4_release_manifest(ACCEPTED)

    assert report["status"] == "passed", report["errors"]
    assert payload["release_version"] == RELEASE_VERSION
    assert payload["inventory_profile"] == INVENTORY_PROFILE
    assert payload["critical_subsystems"] == list(CRITICAL_SUBSYSTEMS)
    assert payload["status"] == "candidate"
    assert payload["artifact_count"] == len(required_v11_4_candidate_artifacts())
    assert report["live_artifacts_verified"] is False


def test_candidate_builder_is_deterministic_and_live_verification_is_explicit(tmp_path: Path) -> None:
    payload = json.loads(ACCEPTED.read_text(encoding="utf-8"))
    first = build_v11_4_candidate_manifest(payload["created_at"])

    assert build_v11_4_candidate_manifest(payload["created_at"]) == first
    volatile = {"artifacts", "fingerprint"}
    assert {key: value for key, value in first.items() if key not in volatile} == {
        key: value for key, value in payload.items() if key not in volatile
    }
    assert [(item["path"], item["role"]) for item in first["artifacts"]] == [
        (item["path"], item["role"]) for item in payload["artifacts"]
    ]

    current = tmp_path / "current-candidate.json"
    current.write_text(json.dumps(first), encoding="utf-8")
    assert validate_v11_4_release_manifest(current, verify_live_artifacts=True)["status"] == "passed"
    assert validate_v11_4_release_manifest(ACCEPTED, verify_live_artifacts=True)["status"] == "passed"


def test_candidate_manifest_fails_when_hash_is_tampered(tmp_path: Path) -> None:
    payload = copy.deepcopy(json.loads(ACCEPTED.read_text(encoding="utf-8")))
    payload["artifacts"][0]["file_sha256"] = "sha256:" + "0" * 64
    payload["fingerprint"] = artifact_fingerprint(payload)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_v11_4_release_manifest(path, verify_live_artifacts=True)
    assert report["status"] == "failed"
    assert any(item["code"] == "artifact_hash_mismatch" for item in report["errors"])
