from __future__ import annotations

import copy
import json
from pathlib import Path

from core_runtime.core.rule_anchor import artifact_fingerprint
from scripts.validate_frozen_release_manifest_v11_2 import (
    CRITICAL_SUBSYSTEMS,
    INVENTORY_PROFILE,
    RELEASE_VERSION,
    build_v11_2_candidate_manifest,
    required_v11_2_candidate_artifacts,
    validate_v11_2_release_manifest,
)


ROOT = Path(__file__).resolve().parent.parent
ACCEPTED = ROOT / "examples/frozen_release_manifest/accepted_v11_2_1_candidate.json"


def test_candidate_manifest_matches_exact_repository_bytes() -> None:
    payload = json.loads(ACCEPTED.read_text(encoding="utf-8"))
    report = validate_v11_2_release_manifest(ACCEPTED)

    assert report["status"] == "passed", report["errors"]
    assert payload["release_version"] == RELEASE_VERSION
    assert payload["inventory_profile"] == INVENTORY_PROFILE
    assert payload["critical_subsystems"] == list(CRITICAL_SUBSYSTEMS)
    assert payload["status"] == "candidate"
    assert payload["artifact_count"] == len(required_v11_2_candidate_artifacts())


def test_candidate_builder_replays_checked_in_candidate() -> None:
    payload = json.loads(ACCEPTED.read_text(encoding="utf-8"))
    assert build_v11_2_candidate_manifest(payload["created_at"]) == payload


def test_candidate_manifest_fails_when_hash_is_tampered(tmp_path: Path) -> None:
    payload = copy.deepcopy(json.loads(ACCEPTED.read_text(encoding="utf-8")))
    payload["artifacts"][0]["file_sha256"] = "sha256:" + "0" * 64
    payload["fingerprint"] = artifact_fingerprint(payload)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_v11_2_release_manifest(path)
    assert report["status"] == "failed"
    assert any(item["code"] == "artifact_hash_mismatch" for item in report["errors"])
