from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from core_runtime.core.rule_anchor import artifact_fingerprint
from scripts.validate_frozen_release_manifest import (
    CRITICAL_SUBSYSTEMS,
    INVENTORY_PROFILE,
    RELEASE_VERSION,
    SELF_REFERENCE_POLICY,
    build_v11_1_manifest,
    required_v11_1_artifacts,
    validate_frozen_release_manifest,
)


ROOT = Path(__file__).resolve().parent.parent
ACCEPTED = (
    ROOT
    / "examples"
    / "frozen_release_manifest"
    / "accepted_v11_1_0.json"
)


def _load_accepted() -> dict:
    return json.loads(ACCEPTED.read_text(encoding="utf-8"))


def _write(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _rebind(payload: dict) -> None:
    payload["fingerprint"] = artifact_fingerprint(payload)


def _codes(report: dict) -> set[str]:
    return {item["code"] for item in report["errors"]}


def test_accepted_v11_1_manifest_is_a_self_consistent_historical_baseline() -> None:
    """v11.1 is a closed historical baseline, not the current release line.

    Its recorded bytes are deliberately not re-verified against the live
    tree. 19 of its 138 tracked artifacts have legitimately changed across
    the v11.2/v11.2.1 lines (runtime modules, docs, version files, shared
    release tooling), and that number only grows with every future release.
    `scripts/verify_release.py` already encodes exactly this policy: it
    reports this manifest as `historical_baseline_preserved` for any target
    >= v11.2 instead of re-hashing it against a newer working tree.

    What must hold forever is the manifest's own internal consistency and
    its declared inventory, which is what this test asserts. Live-byte
    verification belongs to the *current* release line's manifest and is
    covered by tests/test_frozen_release_manifest_v11_2*.py; forgery
    detection is covered by test_altered_manifest_cases_fail_closed below.
    """
    payload = _load_accepted()
    expected = required_v11_1_artifacts()

    assert payload["release_version"] == RELEASE_VERSION
    assert payload["inventory_profile"] == INVENTORY_PROFILE
    assert payload["critical_subsystems"] == list(CRITICAL_SUBSYSTEMS)
    assert payload["self_reference_policy"] == SELF_REFERENCE_POLICY
    assert payload["status"] == "frozen"

    recorded = {item["path"]: item["role"] for item in payload["artifacts"]}
    assert recorded == expected
    assert payload["artifact_count"] == len(expected)

    paths = [item["path"] for item in payload["artifacts"]]
    assert paths == sorted(paths)
    assert len(paths) == len(set(paths))
    assert len([path for path in expected if path.startswith("schemas/core/")]) == 26

    # The manifest's canonical fingerprint must still cover its own content.
    assert payload["fingerprint"] == artifact_fingerprint(payload)

    # Bytes may have moved on, but nothing v11.1 froze may have vanished:
    # a deleted artifact is a different failure and must still be caught.
    assert sorted(path for path in expected if not (ROOT / path).is_file()) == []


def test_v11_1_builder_is_deterministic_and_preserves_the_frozen_inventory() -> None:
    """The builder must stay deterministic and keep reproducing v11.1's exact
    inventory. Only the per-file hashes and the resulting fingerprint may
    differ from the checked-in baseline, because the builder re-reads the
    live tree — see the historical-baseline note above."""
    payload = _load_accepted()
    frozen_at = payload["frozen_at"]

    first = build_v11_1_manifest(frozen_at)
    assert build_v11_1_manifest(frozen_at) == first

    volatile = {"artifacts", "fingerprint"}
    assert {key: value for key, value in first.items() if key not in volatile} == {
        key: value for key, value in payload.items() if key not in volatile
    }
    assert [(item["path"], item["role"]) for item in first["artifacts"]] == [
        (item["path"], item["role"]) for item in payload["artifacts"]
    ]
    assert first["fingerprint"] == artifact_fingerprint(first)


@pytest.mark.parametrize(
    ("case", "expected_code"),
    (
        ("artifact_hash_tampered", "artifact_hash_mismatch"),
        ("critical_artifact_omitted", "artifact_inventory_mismatch"),
        ("unexpected_artifact_added", "artifact_inventory_mismatch"),
        ("artifact_role_tampered", "artifact_role_mismatch"),
        ("manifest_fingerprint_tampered", "fingerprint_mismatch"),
    ),
)
def test_altered_manifest_cases_fail_closed(
    tmp_path: Path,
    case: str,
    expected_code: str,
) -> None:
    payload = copy.deepcopy(_load_accepted())

    if case == "artifact_hash_tampered":
        payload["artifacts"][0]["file_sha256"] = "sha256:" + "0" * 64
        _rebind(payload)
    elif case == "critical_artifact_omitted":
        payload["artifacts"].pop(0)
        payload["artifact_count"] = len(payload["artifacts"])
        _rebind(payload)
    elif case == "unexpected_artifact_added":
        relative = "examples/frozen_release_manifest/accepted_v11_1_0.json"
        payload["artifacts"].append(
            {
                "path": relative,
                "role": "example",
                "file_sha256": "sha256:"
                + hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(),
            }
        )
        payload["artifacts"].sort(key=lambda item: item["path"])
        payload["artifact_count"] = len(payload["artifacts"])
        _rebind(payload)
    elif case == "artifact_role_tampered":
        payload["artifacts"][0]["role"] = "documentation"
        _rebind(payload)
    else:
        replacement = "0" if payload["fingerprint"][-1] != "0" else "1"
        payload["fingerprint"] = payload["fingerprint"][:-1] + replacement

    report = validate_frozen_release_manifest(_write(tmp_path, payload))
    assert report["status"] == "failed"
    assert expected_code in _codes(report)
