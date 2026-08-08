# CORE v11.4.0 — deterministic contract, schema and validation engine

CORE validates artifacts against public contracts: JSON schemas, fingerprints,
manifests and bounded evidence windows. It never executes domain business
logic, never holds private data or naming, and never decides legal, fiscal
or economic truth — it reports whether a declared artifact has the structure,
executable invariants, traceability and evidence its contract requires.

CORE is a local checker for structured evidence packages. Give it a JSON
artifact plus public rules, and it returns reproducible pass/fail results.
It does not run your business logic, call a server, or decide legal,
fiscal, or economic truth.

## Try it

```bash
cd core-runtime-engine
python scripts/validate_agent_session.py examples/agent_sessions/accepted_agent_task.json
```

Expected shape:

```json
{
  "schema": "core.agent_session_validation.v1",
  "status": "passed",
  "passed_count": 1,
  "failed_count": 0
}
```

Schema compatibility alone is not an operational decision. Run the strict
semantic evaluator or the repository-wide executability audit when a contract
must prove more than field presence:

```bash
python scripts/evaluate_core_contract.py artifact.json
python scripts/audit_contract_executability.py
```

## What's here

- `schemas/` — public JSON schemas plus the `core.*` v1 contract family
  (`TaskCloseout`, `EffectResult`, `MemoryArtifact`, `ContextGate`, etc.).
- `scripts/validate_*.py` — one script per schema, invoked as a subprocess.
  No shared server, no daemon: each call is a pure function over an input
  file and the schema it validates against.
- `scripts/read_bounded_reference.py` — bounded, marker-based file reader
  used by bounded indexing tooling.
- Executable contract evaluation for the complete generic `core.*` family,
  with schema-valid negative probes and deterministic decision fingerprints.
- `PhysicalSafetyAssuranceCase.v1`: bounded evidence, preserved extremes,
  fail-closed out-of-distribution handling, independent physical barriers,
  epistemic dignity and no deployment authority. See
  [executable contracts and physical safety](docs/EXECUTABLE_CONTRACTS_AND_PHYSICAL_SAFETY.md).
- `FrozenRuleSet.v1`, external-wallet approvals, SHA-256 Merkle batching,
  `CoreRuleAnchor.sol`, independently validated unsigned deployment and
  transaction preparation, native-gas reserve checks, and read-only on-chain
  verification. See
  [frozen rule anchoring](docs/FROZEN_RULE_ANCHORING.md).
- Sensor adapter contract: `check_adapter_compliance.py`,
  `certify_sensor_fixture.py`, `create_adapter_skeleton.py`, and the
  adapter examples under `examples/adapters/`.
- `core_runtime/cli/` — repository tooling: `validate`, `lint`, `doctor`,
  `inventory`, `contract_preflight`, `release_check`, `bump_version`,
  `create_domain`, `sync_template`, `repair_artifact_paths`.

## Integration model

- Downstream applications call validator scripts by subprocess or through
  their own adapters. CORE validates structure, semantic invariants,
  fingerprints, manifests and evidence windows; the downstream domain owns
  business semantics.
- External indexing or workflow tooling may call `read_bounded_reference.py` for
  bounded, deterministic file reads.

## Quality gate

```bash
pytest -q                                                    # full suite, <60s, no network
python -m core_runtime.cli lint --scope tooling --format json  # release hygiene
python -m core_runtime.cli doctor                            # repo health check
```

The full rule-validation and Merkle path is offline. Signature recovery and
RPC verification use the optional `anchoring` extra. CORE never accepts wallet
keys, seed phrases, passwords, or signing PINs.

## History

This is a v11.0 clean rebuild by whitelist. The prior repository — a
physics-informed surrogate simulator (CPT) plus a self-referential
protocol-model certification apparatus — is preserved at the
`legacy-final` git tag. See [docs/CORE_REBUILD_FROM_ZERO.md](docs/CORE_REBUILD_FROM_ZERO.md)
for the full rationale and the exact whitelist/blacklist, and
[docs/releases/v11.0.1.md](docs/releases/v11.0.1.md) for the clean-rebuild
baseline and `docs/releases/v11.1.0.md` for the frozen-rule extension.

## Boundary

CORE is public and domain-agnostic. It must never receive private names,
paths, customer data or business semantics from the domains that consume
it.
It does not operate a POS, does not decide legal or fiscal truth, and a
passing validation is not a legal, financial or fraud-free certification —
only a reproducible statement that the artifact matches its declared contract
and executable evaluator. Observed, inferred and demonstrated-within-model
claims remain bounded by their evidence and assumptions.
