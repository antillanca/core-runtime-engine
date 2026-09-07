from __future__ import annotations

import json
from pathlib import Path

from scripts.replay_certification import certify_reference_dir


ROOT = Path(__file__).resolve().parents[1]


def test_reference_replay_certification_is_deterministic() -> None:
    first = certify_reference_dir(ROOT / "tests" / "reference_data")
    second = certify_reference_dir(ROOT / "tests" / "reference_data")

    assert first["status"] == "certified"
    assert first == second


def test_reference_replay_rejects_tampered_sidecar(tmp_path: Path) -> None:
    source = ROOT / "tests" / "reference_data" / "v4.1.0"
    target = tmp_path / "v4.1.0"
    target.mkdir()
    for item in source.iterdir():
        target.joinpath(item.name).write_bytes(item.read_bytes())
    target.joinpath("projection_hash.txt").write_text("tampered\n", encoding="utf-8")

    report = certify_reference_dir(target)

    assert report["status"] == "failed"
    assert any(item["code"] == "fingerprint_sidecar_mismatch" for item in report["datasets"][0]["errors"])
