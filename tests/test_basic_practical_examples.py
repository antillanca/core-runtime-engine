from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


EXAMPLES = [
    (
        Path("examples/adapters/threshold_scalar_basic"),
        [
            (
                Path("examples/adapters/threshold_scalar_basic/fixtures/threshold_scalar_basic_v1"),
                "signal",
                "event:threshold_scalar_basic:threshold:v1",
            ),
            (
                Path("examples/adapters/threshold_scalar_basic/fixtures/hysteresis_v1"),
                "hysteresis_state",
                "event:threshold_scalar_basic:hysteresis_active:v1",
            ),
        ],
    ),
    (
        Path("examples/adapters/multi_channel_environment"),
        [
            (
                Path("examples/adapters/multi_channel_environment/fixtures/multi_channel_environment_v1"),
                "temperature",
                "event:multi_channel_environment:temperature_threshold:v1",
            ),
        ],
    ),
    (
        Path("examples/adapters/logic_debounce"),
        [
            (
                Path("examples/adapters/logic_debounce/fixtures/logic_debounce_v1"),
                "debounced_signal",
                "event:logic_debounce:stable_high:v1",
            ),
        ],
    ),
]

VALIDATOR = Path("scripts/validate_sensor_manifest.py")
CERTIFIER = Path("scripts/certify_sensor_fixture.py")
COMPLIANCE = Path("scripts/check_adapter_compliance.py")


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
    )


def _json_payload(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert result.stdout.strip(), result.stderr
    return json.loads(result.stdout)


def test_basic_examples_generate_validate_certify_and_comply() -> None:
    for adapter_dir, fixtures in EXAMPLES:
        generated = _run(
            [sys.executable, str(adapter_dir / "generate_fixture.py"), "--scenario", "all"]
            if adapter_dir.name == "threshold_scalar_basic"
            else [sys.executable, str(adapter_dir / "generate_fixture.py")]
        )
        assert generated.returncode == 0, generated.stderr

        for fixture_dir, value_key, event_id in fixtures:
            assert (fixture_dir / "manifest.json").exists()
            assert (fixture_dir / "samples.csv").exists()

            manifest = json.loads((fixture_dir / "manifest.json").read_text(encoding="utf-8"))
            assert manifest["value_key"] == value_key
            assert manifest["observation_event_id"] == event_id

            validation = _run([sys.executable, str(VALIDATOR), str(fixture_dir)])
            validation_payload = _json_payload(validation)
            assert validation.returncode == 0, validation.stderr
            assert validation_payload["status"] == "passed"

            certification = _run([sys.executable, str(CERTIFIER), str(fixture_dir)])
            certification_payload = _json_payload(certification)
            assert certification.returncode == 0, certification.stderr
            assert certification_payload["status"] == "certified"
            assert certification_payload["valid"] is True
            assert certification_payload["certified"] is True

        compliance = _run([sys.executable, str(COMPLIANCE), str(adapter_dir)])
        compliance_payload = _json_payload(compliance)
        assert compliance.returncode == 0, compliance.stderr
        assert compliance_payload["status"] == "compliant"
        assert compliance_payload["compliant"] is True


def test_basic_examples_outputs_are_byte_stable() -> None:
    for adapter_dir, fixtures in EXAMPLES:
        first_generate = _run(
            [sys.executable, str(adapter_dir / "generate_fixture.py"), "--scenario", "all"]
            if adapter_dir.name == "threshold_scalar_basic"
            else [sys.executable, str(adapter_dir / "generate_fixture.py")]
        )
        assert first_generate.returncode == 0, first_generate.stderr

        first_outputs = {
            fixture_dir: {
                "manifest": (fixture_dir / "manifest.json").read_text(encoding="utf-8"),
                "samples": (fixture_dir / "samples.csv").read_text(encoding="utf-8"),
            }
            for fixture_dir, _value_key, _event_id in fixtures
        }

        second_generate = _run(
            [sys.executable, str(adapter_dir / "generate_fixture.py"), "--scenario", "all"]
            if adapter_dir.name == "threshold_scalar_basic"
            else [sys.executable, str(adapter_dir / "generate_fixture.py")]
        )
        assert second_generate.returncode == 0, second_generate.stderr

        for fixture_dir, _value_key, _event_id in fixtures:
            assert first_outputs[fixture_dir]["manifest"] == (
                fixture_dir / "manifest.json"
            ).read_text(encoding="utf-8")
            assert first_outputs[fixture_dir]["samples"] == (
                fixture_dir / "samples.csv"
            ).read_text(encoding="utf-8")


def test_basic_examples_validation_certification_and_compliance_are_deterministic() -> None:
    for adapter_dir, fixtures in EXAMPLES:
        for fixture_dir, _value_key, _event_id in fixtures:
            first_validation = _run([sys.executable, str(VALIDATOR), str(fixture_dir)])
            second_validation = _run([sys.executable, str(VALIDATOR), str(fixture_dir)])
            assert first_validation.returncode == 0
            assert second_validation.returncode == 0
            assert first_validation.stdout == second_validation.stdout

            first_certification = _run([sys.executable, str(CERTIFIER), str(fixture_dir)])
            second_certification = _run([sys.executable, str(CERTIFIER), str(fixture_dir)])
            assert first_certification.returncode == 0
            assert second_certification.returncode == 0
            assert first_certification.stdout == second_certification.stdout

        first_compliance = _run([sys.executable, str(COMPLIANCE), str(adapter_dir)])
        second_compliance = _run([sys.executable, str(COMPLIANCE), str(adapter_dir)])
        assert first_compliance.returncode == 0
        assert second_compliance.returncode == 0
        assert first_compliance.stdout == second_compliance.stdout


def test_logic_debounce_uses_debounced_signal_not_raw_signal() -> None:
    fixture_dir = Path("examples/adapters/logic_debounce/fixtures/logic_debounce_v1")
    manifest = json.loads((fixture_dir / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["value_key"] == "debounced_signal"
    assert "raw_signal" in manifest["value_keys"]
    assert "debounced_signal" in manifest["value_keys"]


def test_multi_channel_environment_has_multiple_value_keys() -> None:
    fixture_dir = Path("examples/adapters/multi_channel_environment/fixtures/multi_channel_environment_v1")
    manifest = json.loads((fixture_dir / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["value_key"] == "temperature"
    assert manifest["value_keys"] == ["temperature", "humidity", "pressure"]


def test_hysteresis_fixture_uses_hysteresis_state() -> None:
    fixture_dir = Path("examples/adapters/threshold_scalar_basic/fixtures/hysteresis_v1")
    manifest = json.loads((fixture_dir / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["value_key"] == "hysteresis_state"
    assert manifest["observation_event_id"] == "event:threshold_scalar_basic:hysteresis_active:v1"
    assert manifest["threshold"] == 0.5
