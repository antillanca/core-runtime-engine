#!/usr/bin/env python3
"""Compile CoreRuleAnchor with pinned settings and verify frozen artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_PATH = PROJECT_ROOT / "contracts" / "CoreRuleAnchor.sol"
ABI_PATH = PROJECT_ROOT / "contracts" / "CoreRuleAnchor.abi.json"
CREATION_PATH = PROJECT_ROOT / "contracts" / "CoreRuleAnchor.bin"
RUNTIME_PATH = PROJECT_ROOT / "contracts" / "CoreRuleAnchor.runtime.bin"
BUILD_PATH = PROJECT_ROOT / "contracts" / "CoreRuleAnchor.build.json"
COMPILER_PACKAGE = "solc@0.8.30"
FUNCTION_SELECTOR = "0x6919e458"

SETTINGS: dict[str, Any] = {
    "optimizer": {"enabled": True, "runs": 200},
    "evmVersion": "shanghai",
    "metadata": {"appendCBOR": True, "bytecodeHash": "ipfs"},
    "outputSelection": {
        "*": {
            "*": [
                "abi",
                "evm.bytecode.object",
                "evm.deployedBytecode.object",
            ]
        }
    },
}


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _compiler_input() -> dict[str, Any]:
    return {
        "language": "Solidity",
        "sources": {
            "contracts/CoreRuleAnchor.sol": {
                "content": SOURCE_PATH.read_text(encoding="utf-8")
            }
        },
        "settings": SETTINGS,
    }


def build_manifest(
    abi: list[dict[str, Any]],
    creation_bytecode: str,
    runtime_bytecode: str,
) -> dict[str, Any]:
    """Return the canonical build declaration implied by compiler output."""

    return {
        "abi_canonical_sha256": _sha256_bytes(_canonical_json_bytes(abi)),
        "compiler": COMPILER_PACKAGE,
        "contract": "CoreRuleAnchor",
        "creation_bytecode_sha256": _sha256_bytes(bytes.fromhex(creation_bytecode)),
        "evm_version": SETTINGS["evmVersion"],
        "function_selector": FUNCTION_SELECTOR,
        "metadata": {
            "append_cbor": SETTINGS["metadata"]["appendCBOR"],
            "bytecode_hash": SETTINGS["metadata"]["bytecodeHash"],
        },
        "optimizer": SETTINGS["optimizer"],
        "runtime_bytecode_sha256": _sha256_bytes(bytes.fromhex(runtime_bytecode)),
        "schema_version": "core.solidity_build.v1",
        "source": "contracts/CoreRuleAnchor.sol",
        "source_sha256": _sha256_bytes(SOURCE_PATH.read_bytes()),
    }


def compile_contract() -> tuple[dict[str, Any], str, str]:
    result = subprocess.run(
        [
            "npx",
            "--yes",
            COMPILER_PACKAGE,
            "--standard-json",
            "--base-path",
            str(PROJECT_ROOT),
        ],
        input=json.dumps(_compiler_input(), separators=(",", ":")),
        capture_output=True,
        text=True,
        check=False,
        cwd=PROJECT_ROOT,
    )
    output_text = result.stdout
    json_start = output_text.find("{")
    if json_start < 0:
        raise RuntimeError("Solidity compiler did not return JSON output")
    output = json.loads(output_text[json_start:])
    fatal_errors = [
        item
        for item in output.get("errors", [])
        if item.get("severity") == "error"
    ]
    if result.returncode != 0 or fatal_errors:
        raise RuntimeError("Solidity compiler rejected CoreRuleAnchor")
    contract = output["contracts"]["contracts/CoreRuleAnchor.sol"]["CoreRuleAnchor"]
    return (
        contract["abi"],
        contract["evm"]["bytecode"]["object"],
        contract["evm"]["deployedBytecode"]["object"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compile and check CoreRuleAnchor with solc 0.8.30 / Shanghai."
    )
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    try:
        abi, creation_bytecode, runtime_bytecode = compile_contract()
    except (OSError, KeyError, json.JSONDecodeError, RuntimeError) as exc:
        print(
            json.dumps(
                {
                    "schema": "core.solidity_build_verification.v1",
                    "status": "failed",
                    "errors": [
                        {"code": "solidity_compilation_failed", "message": str(exc)}
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    errors: list[dict[str, str]] = []
    generated_build = build_manifest(abi, creation_bytecode, runtime_bytecode)
    expected_files = (ABI_PATH, CREATION_PATH, RUNTIME_PATH, BUILD_PATH)
    for path in expected_files:
        if not path.is_file():
            errors.append(
                {
                    "code": "frozen_artifact_missing",
                    "message": f"Frozen artifact is missing: {path.name}",
                }
            )

    if not errors:
        try:
            expected_abi = json.loads(ABI_PATH.read_text(encoding="utf-8"))
            expected_creation = CREATION_PATH.read_text(encoding="utf-8").strip()
            expected_runtime = RUNTIME_PATH.read_text(encoding="utf-8").strip()
            expected_build = json.loads(BUILD_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(
                {
                    "code": "frozen_artifact_unreadable",
                    "message": exc.__class__.__name__,
                }
            )
        else:
            if _canonical_json_bytes(expected_abi) != _canonical_json_bytes(abi):
                errors.append(
                    {"code": "abi_mismatch", "message": "Frozen ABI differs."}
                )
            if expected_creation != creation_bytecode:
                errors.append(
                    {
                        "code": "creation_bytecode_mismatch",
                        "message": "Frozen creation bytecode differs.",
                    }
                )
            if expected_runtime != runtime_bytecode:
                errors.append(
                    {
                        "code": "runtime_bytecode_mismatch",
                        "message": "Frozen runtime bytecode differs.",
                    }
                )
            if _canonical_json_bytes(expected_build) != _canonical_json_bytes(
                generated_build
            ):
                errors.append(
                    {
                        "code": "build_manifest_mismatch",
                        "message": "Frozen CoreRuleAnchor.build.json differs.",
                    }
                )

    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "CoreRuleAnchor.abi.json").write_text(
            json.dumps(abi, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (args.output_dir / "CoreRuleAnchor.bin").write_text(
            creation_bytecode + "\n", encoding="utf-8"
        )
        (args.output_dir / "CoreRuleAnchor.runtime.bin").write_text(
            runtime_bytecode + "\n", encoding="utf-8"
        )
        (args.output_dir / "CoreRuleAnchor.build.json").write_text(
            json.dumps(generated_build, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    print(
        json.dumps(
            {
                "schema": "core.solidity_build_verification.v1",
                "status": "passed" if not errors else "failed",
                "errors": errors,
                "compiler": COMPILER_PACKAGE,
                "evm_version": SETTINGS["evmVersion"],
                "optimizer": SETTINGS["optimizer"],
                "source_sha256": generated_build["source_sha256"],
                "abi_canonical_sha256": generated_build["abi_canonical_sha256"],
                "creation_bytecode_sha256": generated_build[
                    "creation_bytecode_sha256"
                ],
                "runtime_bytecode_sha256": generated_build[
                    "runtime_bytecode_sha256"
                ],
                "build_manifest_canonical_sha256": _sha256_bytes(
                    _canonical_json_bytes(generated_build)
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
