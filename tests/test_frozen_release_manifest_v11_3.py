from __future__ import annotations

import copy
import json
from pathlib import Path

import scripts.verify_release as verify_release
from core_runtime.core.rule_anchor import artifact_fingerprint
from scripts.validate_frozen_release_manifest_v11_3 import (
    CRITICAL_SUBSYSTEMS,
    INVENTORY_PROFILE,
    RELEASE_VERSION,
    build_v11_3_candidate_manifest,
    required_v11_3_candidate_artifacts,
    validate_v11_3_release_manifest,
)


ROOT = Path(__file__).resolve().parent.parent
ACCEPTED = ROOT / "examples/frozen_release_manifest/accepted_v11_3_0_candidate.json"


def test_verify_release_registers_v11_3_manifest_gates() -> None:
    assert (
        verify_release.FROZEN_RELEASE_MANIFEST_CHECKS["frozen_release_manifest_v11_3_candidate_accepted"][-1]
        == "examples/frozen_release_manifest/accepted_v11_3_0_candidate.json"
    )
    assert (
        verify_release.FROZEN_RELEASE_MANIFEST_CHECKS["frozen_release_manifest_v11_3_frozen_accepted"][-1]
        == "examples/frozen_release_manifest/accepted_v11_3_0.json"
    )


def test_candidate_manifest_remains_valid_historical_evidence() -> None:
    """v11.3 is a closed historical baseline, not the current release line.

    Its recorded bytes are deliberately not re-verified against the live
    tree. Shared files (runtime modules, docs, version files, release
    tooling) legitimately move on across v11.4+, and that number only
    grows with every future release. verify_release.py already encodes
    exactly this policy: it reports this manifest as
    historical_baseline_preserved for any target >= v11.4.

    What must hold forever is the manifest's own internal consistency and
    its declared inventory, which is what this test asserts. Live-byte
    verification belongs to the *current* release line's manifest and is
    covered by tests/test_frozen_release_manifest_v11_4.py.
    """
    payload = json.loads(ACCEPTED.read_text(encoding="utf-8"))
    report = validate_v11_3_release_manifest(ACCEPTED)

    assert report["status"] == "passed", report["errors"]
    assert payload["release_version"] == RELEASE_VERSION
    assert payload["inventory_profile"] == INVENTORY_PROFILE
    assert payload["critical_subsystems"] == list(CRITICAL_SUBSYSTEMS)
    assert payload["status"] == "candidate"
    assert payload["artifact_count"] == len(required_v11_3_candidate_artifacts())
    assert report["live_artifacts_verified"] is False

    recorded = {item["path"]: item["role"] for item in payload["artifacts"]}
    assert recorded == required_v11_3_candidate_artifacts()

    paths = [item["path"] for item in payload["artifacts"]]
    assert paths == sorted(paths)
    assert len(paths) == len(set(paths))

    assert payload["fingerprint"] == artifact_fingerprint(payload)

    assert sorted(path for path in required_v11_3_candidate_artifacts() if not (ROOT / path).is_file()) == []


def test_candidate_builder_is_deterministic_and_preserves_the_frozen_inventory() -> None:
    """The builder must stay deterministic and keep reproducing v11.3's exact
    inventory. Only the per-file hashes and the resulting fingerprint may
    differ from the checked-in baseline, because the builder re-reads the
    live tree — see the historical-baseline note above."""
    payload = json.loads(ACCEPTED.read_text(encoding="utf-8"))
    first = build_v11_3_candidate_manifest(payload["created_at"])

    assert build_v11_3_candidate_manifest(payload["created_at"]) == first
    volatile = {"artifacts", "fingerprint"}
    assert {key: value for key, value in first.items() if key not in volatile} == {
        key: value for key, value in payload.items() if key not in volatile
    }
    assert [(item["path"], item["role"]) for item in first["artifacts"]] == [
        (item["path"], item["role"]) for item in payload["artifacts"]
    ]
    assert first["fingerprint"] == artifact_fingerprint(first)


def test_candidate_manifest_fails_when_hash_is_tampered(tmp_path: Path) -> None:
    payload = copy.deepcopy(json.loads(ACCEPTED.read_text(encoding="utf-8")))
    payload["artifacts"][0]["file_sha256"] = "sha256:" + "0" * 64
    payload["fingerprint"] = artifact_fingerprint(payload)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_v11_3_release_manifest(path, verify_live_artifacts=True)
    assert report["status"] == "failed"
    assert any(item["code"] == "artifact_hash_mismatch" for item in report["errors"])
