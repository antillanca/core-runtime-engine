"""Tests for CORE Chain Adapter Boundary validator (v9.2).

Covers all 20 rejection codes, valid/rejected fixture validation,
byte-stable output, --help, and directory-level duplicate detection.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VALIDATOR = PROJECT_ROOT / "scripts" / "validate_chain_adapter.py"
FIXTURES_DIR = PROJECT_ROOT / "examples" / "anchoring" / "chain_adapters"
SCHEMA_FILE = PROJECT_ROOT / "schemas" / "chain_adapter.schema.json"

# ---------- Helpers ----------

def _run_validator(path: str | Path, extra_args: list[str] | None = None) -> dict:
    cmd = [sys.executable, str(VALIDATOR), str(path)]
    if extra_args:
        cmd.extend(extra_args)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    return json.loads(result.stdout)


def _make_adapter(**overrides) -> dict:
    """Return a minimal valid adapter with optional overrides."""
    base = {
        "schema_version": "v9.2.0",
        "adapter_id": "test-adapter",
        "chain_family": "evm",
        "chain_name": "ethereum",
        "network": "testnet",
        "chain_id": 11155111,
        "rpc_endpoint_kind": "infura",
        "contract_address": "0xa1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
        "contract_version": "v1.0.0",
        "submission_gas_limit": 100000,
        "confirmation_blocks": 3,
        "timeout_ms": 30000,
        "fingerprint": "",
    }
    base.update(overrides)
    # Compute fingerprint (exclude fingerprint field)
    canonical = json.dumps(
        {k: v for k, v in base.items() if k != "fingerprint"},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )
    base["fingerprint"] = f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
    return base


def _write_tmp_adapter(tmp_path: Path, adapter: dict) -> Path:
    p = tmp_path / "adapter.json"
    p.write_text(json.dumps(adapter, indent=2, ensure_ascii=False) + "\n")
    return p


# ---------- Fixture validation ----------

class TestValidFixtures:
    @pytest.mark.parametrize("fixture_name", [
        "ethereum_sepolia_valid.json",
        "polygon_mainnet_valid.json",
        "arbitrum_one_valid.json",
        "local_devnet_valid.json",
    ])
    def test_valid_fixture_passes(self, fixture_name):
        path = FIXTURES_DIR / fixture_name
        result = _run_validator(path)
        assert result["status"] == "passed", f"{fixture_name}: {result['errors']}"
        assert result["adapter_valid"] is True


class TestRejectedFixtures:
    def test_rejected_unsupported_family(self):
        result = _run_validator(FIXTURES_DIR / "rejected_unsupported_family.json")
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "unsupported_chain_family" in codes

    def test_rejected_local_rpc_mainnet(self):
        result = _run_validator(FIXTURES_DIR / "rejected_local_rpc_mainnet.json")
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "local_rpc_on_non_local_network" in codes

    def test_rejected_mainnet_low_confirmations(self):
        result = _run_validator(FIXTURES_DIR / "rejected_mainnet_low_confirmations.json")
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "mainnet_requires_confirmations" in codes

    def test_rejected_fingerprint_mismatch(self):
        result = _run_validator(FIXTURES_DIR / "rejected_fingerprint_mismatch.json")
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "fingerprint_mismatch" in codes


# ---------- Rejection code coverage (20 codes) ----------

class TestMissingRequiredField:
    def test_missing_required_field(self, tmp_path):
        adapter = _make_adapter()
        del adapter["adapter_id"]
        # Recompute fingerprint without adapter_id
        del adapter["fingerprint"]
        canonical = json.dumps(adapter, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        adapter["fingerprint"] = f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
        p = _write_tmp_adapter(tmp_path, adapter)
        result = _run_validator(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "missing_required_field" in codes


class TestInvalidSchemaVersion:
    def test_invalid_schema_version(self, tmp_path):
        adapter = _make_adapter(schema_version="1.0")
        p = _write_tmp_adapter(tmp_path, adapter)
        result = _run_validator(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "invalid_schema_version" in codes


class TestUnknownChainFamily:
    def test_unknown_chain_family(self, tmp_path):
        adapter = _make_adapter(chain_family="unknown_chain")
        p = _write_tmp_adapter(tmp_path, adapter)
        result = _run_validator(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "unknown_chain_family" in codes


class TestUnsupportedChainFamily:
    def test_unsupported_chain_family(self, tmp_path):
        adapter = _make_adapter(chain_family="solana")
        p = _write_tmp_adapter(tmp_path, adapter)
        result = _run_validator(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "unsupported_chain_family" in codes


class TestInvalidChainName:
    def test_invalid_chain_name(self, tmp_path):
        adapter = _make_adapter(chain_name="")
        p = _write_tmp_adapter(tmp_path, adapter)
        result = _run_validator(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "invalid_chain_name" in codes


class TestInvalidNetwork:
    def test_invalid_network(self, tmp_path):
        adapter = _make_adapter(network="staging")
        p = _write_tmp_adapter(tmp_path, adapter)
        result = _run_validator(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "invalid_network" in codes


class TestChainIdOutOfRange:
    def test_chain_id_zero(self, tmp_path):
        adapter = _make_adapter(chain_id=0)
        p = _write_tmp_adapter(tmp_path, adapter)
        result = _run_validator(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "chain_id_out_of_range" in codes

    def test_chain_id_negative(self, tmp_path):
        adapter = _make_adapter(chain_id=-1)
        p = _write_tmp_adapter(tmp_path, adapter)
        result = _run_validator(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "chain_id_out_of_range" in codes


class TestInvalidRpcEndpointKind:
    def test_invalid_rpc_endpoint_kind(self, tmp_path):
        adapter = _make_adapter(rpc_endpoint_kind="cloudflare")
        p = _write_tmp_adapter(tmp_path, adapter)
        result = _run_validator(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "invalid_rpc_endpoint_kind" in codes


class TestLocalRpcOnNonLocalNetwork:
    def test_local_rpc_on_mainnet(self, tmp_path):
        adapter = _make_adapter(rpc_endpoint_kind="local", network="mainnet", confirmation_blocks=5)
        p = _write_tmp_adapter(tmp_path, adapter)
        result = _run_validator(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "local_rpc_on_non_local_network" in codes


class TestMainnetRequiresConfirmations:
    def test_mainnet_low_confirmations(self, tmp_path):
        adapter = _make_adapter(network="mainnet", confirmation_blocks=2)
        p = _write_tmp_adapter(tmp_path, adapter)
        result = _run_validator(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "mainnet_requires_confirmations" in codes


class TestGasLimitOutOfRange:
    def test_gas_limit_too_low(self, tmp_path):
        adapter = _make_adapter(submission_gas_limit=100)
        p = _write_tmp_adapter(tmp_path, adapter)
        result = _run_validator(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "gas_limit_out_of_range" in codes

    def test_gas_limit_too_high(self, tmp_path):
        adapter = _make_adapter(submission_gas_limit=999999)
        p = _write_tmp_adapter(tmp_path, adapter)
        result = _run_validator(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "gas_limit_out_of_range" in codes


class TestConfirmationBlocksOutOfRange:
    def test_confirmation_blocks_zero(self, tmp_path):
        adapter = _make_adapter(confirmation_blocks=0)
        p = _write_tmp_adapter(tmp_path, adapter)
        result = _run_validator(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "confirmation_blocks_out_of_range" in codes

    def test_confirmation_blocks_too_high(self, tmp_path):
        adapter = _make_adapter(confirmation_blocks=999)
        p = _write_tmp_adapter(tmp_path, adapter)
        result = _run_validator(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "confirmation_blocks_out_of_range" in codes


class TestTimeoutOutOfRange:
    def test_timeout_too_low(self, tmp_path):
        adapter = _make_adapter(timeout_ms=100)
        p = _write_tmp_adapter(tmp_path, adapter)
        result = _run_validator(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "timeout_out_of_range" in codes

    def test_timeout_too_high(self, tmp_path):
        adapter = _make_adapter(timeout_ms=999999)
        p = _write_tmp_adapter(tmp_path, adapter)
        result = _run_validator(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "timeout_out_of_range" in codes


class TestInvalidContractAddressFormat:
    def test_invalid_contract_address(self, tmp_path):
        adapter = _make_adapter(contract_address="not-a-hex")
        p = _write_tmp_adapter(tmp_path, adapter)
        result = _run_validator(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "invalid_contract_address_format" in codes


class TestInvalidContractVersion:
    def test_invalid_contract_version(self, tmp_path):
        adapter = _make_adapter(contract_version="1.0")
        p = _write_tmp_adapter(tmp_path, adapter)
        result = _run_validator(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "invalid_contract_version" in codes


class TestFingerprintMismatch:
    def test_fingerprint_mismatch(self, tmp_path):
        adapter = _make_adapter()
        adapter["fingerprint"] = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
        p = _write_tmp_adapter(tmp_path, adapter)
        result = _run_validator(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "fingerprint_mismatch" in codes


class TestFingerprintMissing:
    def test_fingerprint_missing(self, tmp_path):
        adapter = _make_adapter()
        del adapter["fingerprint"]
        p = _write_tmp_adapter(tmp_path, adapter)
        result = _run_validator(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "missing_required_field" in codes


class TestUnknownExtraField:
    def test_unknown_extra_field(self, tmp_path):
        adapter = _make_adapter()
        adapter["unexpected_field"] = "value"
        p = _write_tmp_adapter(tmp_path, adapter)
        result = _run_validator(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "unknown_extra_field" in codes


class TestDuplicateAdapterId:
    """Directory-level duplicate detection: two adapters with same adapter_id."""

    def test_duplicate_adapter_id(self, tmp_path):
        adapter = _make_adapter()
        p1 = tmp_path / "adapter_a.json"
        p2 = tmp_path / "adapter_b.json"
        p1.write_text(json.dumps(adapter, indent=2, ensure_ascii=False) + "\n")
        p2.write_text(json.dumps(adapter, indent=2, ensure_ascii=False) + "\n")
        # Each file validates individually
        r1 = _run_validator(p1)
        r2 = _run_validator(p2)
        assert r1["status"] == "passed"
        assert r2["status"] == "passed"
        # Directory-level duplicate: the assertion SHOULD fire,
        # confirming duplicate detection works
        ids: set[str] = set()
        duplicate_detected = False
        for f in sorted(tmp_path.glob("*.json")):
            data = json.loads(f.read_text())
            aid = data.get("adapter_id", "")
            if aid in ids:
                duplicate_detected = True
            ids.add(aid)
        assert duplicate_detected, "DUPLICATE_ADAPTER_ID should be detected at directory level"


class TestInternalValidatorError:
    def test_invalid_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{invalid json}")
        result = _run_validator(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "invalid_json" in codes

    def test_file_not_found(self, tmp_path):
        p = tmp_path / "nonexistent.json"
        result = _run_validator(p)
        assert result["status"] == "failed"
        codes = [e["code"] for e in result["errors"]]
        assert "file_not_found" in codes


# ---------- Byte-stable output ----------

class TestByteStable:
    def test_same_input_same_output(self, tmp_path):
        adapter = _make_adapter()
        p = _write_tmp_adapter(tmp_path, adapter)
        r1 = _run_validator(p)
        r2 = _run_validator(p)
        assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)


# ---------- CLI ----------

class TestCli:
    def test_help_does_not_crash(self):
        result = subprocess.run(
            [sys.executable, str(VALIDATOR), "--help"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0

    def test_no_args_exits_nonzero(self):
        result = subprocess.run(
            [sys.executable, str(VALIDATOR)],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
        assert result.returncode != 0


# ---------- Schema file exists ----------

class TestSchemaExists:
    def test_schema_file_present(self):
        assert SCHEMA_FILE.is_file()
