"""Static contract checks for CORE tooling CI gate."""

from __future__ import annotations

from pathlib import Path


WORKFLOW_PATH = Path(".github/workflows/replay-certification.yml")


def test_replay_certification_includes_core_tooling_lint_gate() -> None:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "CORE tooling lint" in text
    assert "python -m core_runtime.cli lint --scope tooling --format json" in text
    assert "python -m core_runtime.cli lint --scope tooling --format markdown" in text
    assert "actions/upload-artifact@v4" in text
    assert "--apply" not in text
    assert "git tag" not in text
    assert "gh release" not in text
    assert "twine upload" not in text

