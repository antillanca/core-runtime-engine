from __future__ import annotations

from pathlib import Path

from scripts.certify_router_replay import certify_all, certify_fixture
from scripts.expert_router_common import evaluate_fixture, validate_fixture
from scripts.report_expert_router import build_report


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "expert_router" / "routing_fixtures" / "minimal_routing.json"
FIXTURE_ROOT = FIXTURE.parent


def test_router_fixture_validates_and_evaluates_offline() -> None:
    validation = validate_fixture(FIXTURE)
    evaluation = evaluate_fixture(FIXTURE)

    assert validation["status"] == "passed"
    assert evaluation["status"] == "passed"
    assert evaluation["evaluation_summary"] == {"selected_count": 1, "rejected_count": 1, "total_proposals": 2}
    assert evaluation["execution_authorized"] is False


def test_router_replay_and_batch_report_are_stable() -> None:
    first = certify_fixture(FIXTURE)
    second = certify_fixture(FIXTURE)
    batch = certify_all(FIXTURE_ROOT)
    report = build_report(FIXTURE_ROOT)

    assert first == second
    assert first["status"] == "certified"
    assert batch["status"] == "certified"
    assert report["status"] == "passed"
