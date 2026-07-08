from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from pathlib import Path

BUSINESS_ADAPTER = Path("examples/adapters/business_operations")
PRIVACY_ADAPTER = Path("examples/adapters/privacy_safe_customer_flow")

BUSINESS_FIXTURES = [
    (
        Path("examples/adapters/business_operations/fixtures/sales_drop_v1"),
        "daily_sales",
        "event:business_operations:sales_drop:v1",
    ),
    (
        Path("examples/adapters/business_operations/fixtures/low_stock_v1"),
        "stock_units",
        "event:business_operations:low_stock:v1",
    ),
]

PRIVACY_FIXTURE = Path(
    "examples/adapters/privacy_safe_customer_flow/fixtures/privacy_safe_customer_flow_v1"
)

VALIDATOR = Path("scripts/validate_sensor_manifest.py")
CERTIFIER = Path("scripts/certify_sensor_fixture.py")
COMPLIANCE = Path("scripts/check_adapter_compliance.py")

PII_PATTERNS = [
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"connection_string", re.IGNORECASE),
]


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def _json_payload(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert result.stdout.strip(), result.stderr
    return json.loads(result.stdout)


def _assert_fixture_valid_certified(fixture_dir: Path) -> None:
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


def _assert_adapter_compliant(adapter_dir: Path) -> None:
    compliance = _run([sys.executable, str(COMPLIANCE), str(adapter_dir)])
    compliance_payload = _json_payload(compliance)

    assert compliance.returncode == 0, compliance.stderr
    assert compliance_payload["status"] == "compliant"
    assert compliance_payload["compliant"] is True


def test_business_operations_generates_all_scenarios() -> None:
    result = _run(
        [
            sys.executable,
            str(BUSINESS_ADAPTER / "generate_fixture.py"),
            "--scenario",
            "all",
        ]
    )
    assert result.returncode == 0, result.stderr

    for fixture_dir, value_key, event_id in BUSINESS_FIXTURES:
        manifest_path = fixture_dir / "manifest.json"
        samples_path = fixture_dir / "samples.csv"

        assert manifest_path.exists()
        assert samples_path.exists()

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["value_key"] == value_key
        assert manifest["observation_event_id"] == event_id

        _assert_fixture_valid_certified(fixture_dir)

    _assert_adapter_compliant(BUSINESS_ADAPTER)


def test_privacy_safe_customer_flow_generates_valid_certified_fixture() -> None:
    result = _run([sys.executable, str(PRIVACY_ADAPTER / "generate_fixture.py")])
    assert result.returncode == 0, result.stderr

    manifest_path = PRIVACY_FIXTURE / "manifest.json"
    samples_path = PRIVACY_FIXTURE / "samples.csv"

    assert manifest_path.exists()
    assert samples_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["value_key"] == "flow_count"
    assert manifest["observation_event_id"] == "event:privacy_safe_customer_flow:flow_spike:v1"

    _assert_fixture_valid_certified(PRIVACY_FIXTURE)
    _assert_adapter_compliant(PRIVACY_ADAPTER)


def test_domain_privacy_examples_are_byte_stable() -> None:
    first_business = _run(
        [
            sys.executable,
            str(BUSINESS_ADAPTER / "generate_fixture.py"),
            "--scenario",
            "all",
        ]
    )
    assert first_business.returncode == 0, first_business.stderr

    first_business_files = {
        fixture_dir: {
            "manifest": (fixture_dir / "manifest.json").read_text(encoding="utf-8"),
            "samples": (fixture_dir / "samples.csv").read_text(encoding="utf-8"),
        }
        for fixture_dir, _value_key, _event_id in BUSINESS_FIXTURES
    }

    first_privacy = _run([sys.executable, str(PRIVACY_ADAPTER / "generate_fixture.py")])
    assert first_privacy.returncode == 0, first_privacy.stderr

    first_privacy_manifest = (PRIVACY_FIXTURE / "manifest.json").read_text(encoding="utf-8")
    first_privacy_samples = (PRIVACY_FIXTURE / "samples.csv").read_text(encoding="utf-8")

    second_business = _run(
        [
            sys.executable,
            str(BUSINESS_ADAPTER / "generate_fixture.py"),
            "--scenario",
            "all",
        ]
    )
    assert second_business.returncode == 0, second_business.stderr

    for fixture_dir, _value_key, _event_id in BUSINESS_FIXTURES:
        assert first_business_files[fixture_dir]["manifest"] == (
            fixture_dir / "manifest.json"
        ).read_text(encoding="utf-8")
        assert first_business_files[fixture_dir]["samples"] == (
            fixture_dir / "samples.csv"
        ).read_text(encoding="utf-8")

    second_privacy = _run([sys.executable, str(PRIVACY_ADAPTER / "generate_fixture.py")])
    assert second_privacy.returncode == 0, second_privacy.stderr

    assert first_privacy_manifest == (PRIVACY_FIXTURE / "manifest.json").read_text(
        encoding="utf-8"
    )
    assert first_privacy_samples == (PRIVACY_FIXTURE / "samples.csv").read_text(
        encoding="utf-8"
    )


def test_validation_certification_and_compliance_outputs_are_deterministic() -> None:
    for fixture_dir, _value_key, _event_id in BUSINESS_FIXTURES:
        first_validation = _run([sys.executable, str(VALIDATOR), str(fixture_dir)])
        second_validation = _run([sys.executable, str(VALIDATOR), str(fixture_dir)])
        assert first_validation.stdout == second_validation.stdout

        first_certification = _run([sys.executable, str(CERTIFIER), str(fixture_dir)])
        second_certification = _run([sys.executable, str(CERTIFIER), str(fixture_dir)])
        assert first_certification.stdout == second_certification.stdout

    first_business_compliance = _run([sys.executable, str(COMPLIANCE), str(BUSINESS_ADAPTER)])
    second_business_compliance = _run([sys.executable, str(COMPLIANCE), str(BUSINESS_ADAPTER)])
    assert first_business_compliance.stdout == second_business_compliance.stdout

    first_privacy_validation = _run([sys.executable, str(VALIDATOR), str(PRIVACY_FIXTURE)])
    second_privacy_validation = _run([sys.executable, str(VALIDATOR), str(PRIVACY_FIXTURE)])
    assert first_privacy_validation.stdout == second_privacy_validation.stdout

    first_privacy_certification = _run([sys.executable, str(CERTIFIER), str(PRIVACY_FIXTURE)])
    second_privacy_certification = _run([sys.executable, str(CERTIFIER), str(PRIVACY_FIXTURE)])
    assert first_privacy_certification.stdout == second_privacy_certification.stdout

    first_privacy_compliance = _run([sys.executable, str(COMPLIANCE), str(PRIVACY_ADAPTER)])
    second_privacy_compliance = _run([sys.executable, str(COMPLIANCE), str(PRIVACY_ADAPTER)])
    assert first_privacy_compliance.stdout == second_privacy_compliance.stdout


def test_privacy_fixture_contains_no_obvious_pii() -> None:
    result = _run([sys.executable, str(PRIVACY_ADAPTER / "generate_fixture.py")])
    assert result.returncode == 0, result.stderr

    for path in [PRIVACY_FIXTURE / "manifest.json", PRIVACY_FIXTURE / "samples.csv"]:
        text = path.read_text(encoding="utf-8")
        for pattern in PII_PATTERNS:
            assert not pattern.search(text), f"PII-like pattern found in {path}: {pattern.pattern}"

    with (PRIVACY_FIXTURE / "samples.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows
    assert "anonymous_customer_hash" in rows[0]

    for row in rows:
        assert re.fullmatch(r"\d{16}", row["anonymous_customer_hash"])
