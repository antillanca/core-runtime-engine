from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from core_runtime.core.rule_anchor import (
    artifact_fingerprint,
    load_verified_rule_anchor_build,
    validate_unsigned_rule_anchor_deployment_payload,
)
from scripts.validate_unsigned_rule_anchor_deployment import validate_unsigned_deployment


ROOT = Path(__file__).resolve().parent.parent
PREPARE = ROOT / "scripts" / "prepare_core_rule_anchor_deployment.py"
DEPLOYER = "0x3333333333333333333333333333333333333333"


def _prepare(tmp_path: Path, *extra: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    output = tmp_path / "unsigned-deployment.json"
    command = [
        sys.executable,
        str(PREPARE),
        "--chain-id",
        "31337",
        "--deployer",
        DEPLOYER,
        "--output",
        str(output),
        *extra,
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    return result, output


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_frozen_build_and_manual_deployment_request_are_reproducible(tmp_path: Path) -> None:
    build, creation_hex = load_verified_rule_anchor_build()
    result, output = _prepare(
        tmp_path,
        "--gas-limit",
        "500000",
        "--gas-price-wei",
        "1000000000",
        "--post-deployment-reserve-wei",
        "1000000000000000",
    )
    assert result.returncode == 0, result.stderr
    request = _load(output)
    assert request["transaction"]["data"] == "0x" + creation_hex
    assert request["expected_runtime_bytecode_sha256"] == build["runtime_bytecode_sha256"]
    assert request["gas_reserve"]["deployment_max_cost_wei"] == 500_000_000_000_000
    assert request["gas_reserve"]["required_balance_wei"] == 1_500_000_000_000_000
    assert request["readiness"] == "balance_unobserved"
    assert request["signing_mode"] == "external_wallet_only"
    assert request["broadcast"] is False
    assert validate_unsigned_rule_anchor_deployment_payload(request) == []
    report = validate_unsigned_deployment(output)
    assert report["status"] == "passed"
    assert report["execution_authorized"] is False
    assert report["broadcast_authorized"] is False


def test_deployment_validator_rejects_bytecode_and_reserve_tampering(tmp_path: Path) -> None:
    result, output = _prepare(
        tmp_path,
        "--gas-limit",
        "500000",
        "--gas-price-wei",
        "1000000000",
    )
    assert result.returncode == 0, result.stderr
    request = _load(output)
    replacement = "0" if request["transaction"]["data"][-1] != "0" else "1"
    request["transaction"]["data"] = request["transaction"]["data"][:-1] + replacement
    request["gas_reserve"]["required_balance_wei"] += 1
    request["readiness"] = "ready"
    request["fingerprint"] = artifact_fingerprint(request)

    codes = {
        item["code"] for item in validate_unsigned_rule_anchor_deployment_payload(request)
    }
    assert "deployment_bytecode_mismatch" in codes
    assert "gas_reserve_mismatch" in codes
    assert "readiness_mismatch" in codes
    assert "fingerprint_mismatch" not in codes


def test_deployment_validator_rejects_secret_fields_even_before_signing(tmp_path: Path) -> None:
    result, output = _prepare(tmp_path)
    assert result.returncode == 0, result.stderr
    request = _load(output)
    request["private_key"] = "forbidden"
    request["fingerprint"] = artifact_fingerprint(request)
    codes = {
        item["code"] for item in validate_unsigned_rule_anchor_deployment_payload(request)
    }
    assert "wallet_secret_forbidden" in codes
    assert "schema_validation_error" in codes


def test_prepare_cli_rejects_incoherent_priority_fee(tmp_path: Path) -> None:
    result, output = _prepare(
        tmp_path,
        "--gas-limit",
        "500000",
        "--gas-price-wei",
        "1000000000",
        "--max-priority-fee-per-gas-wei",
        "1",
    )
    assert result.returncode == 2
    assert not output.exists()
    assert "requires max-fee-per-gas-wei" in result.stderr


def test_deployment_tools_have_no_signing_or_broadcast_path() -> None:
    source = "\n".join(
        (ROOT / "scripts" / name).read_text(encoding="utf-8")
        for name in (
            "prepare_core_rule_anchor_deployment.py",
            "validate_unsigned_rule_anchor_deployment.py",
        )
    )
    forbidden = (
        "--private-key",
        "ANCHOR_KEY",
        "from_key(",
        "sign_transaction(",
        "send_raw_transaction(",
        "send_transaction(",
        "--broadcast",
    )
    assert not any(marker in source for marker in forbidden)
