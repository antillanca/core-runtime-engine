# CORE v11.0.1 — deterministic contract, schema and validation engine

CORE validates artifacts against public contracts: JSON schemas, fingerprints,
manifests and bounded evidence windows. It never executes domain business
logic, never holds private data or naming, and never decides legal, fiscal
or economic truth — it only certifies that a declared artifact has the
structure, traceability and evidence its contract requires.

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

## What's here

- `schemas/` — 36 public JSON schemas plus the `core.*` v1 contract family
  (`TaskCloseout`, `EffectResult`, `MemoryArtifact`, `ContextGate`, etc.).
- `scripts/validate_*.py` — one script per schema, invoked as a subprocess.
  No shared server, no daemon: each call is a pure function over an input
  file and the schema it validates against.
- `scripts/read_bounded_reference.py` — bounded, marker-based file reader
  used by bounded indexing tooling.
- `scripts/core_anchor.py`, `submit_anchoring.py` — optional blockchain
  anchoring (requires the `anchoring` extra); every other script works
  without it.
- Sensor adapter contract: `check_adapter_compliance.py`,
  `certify_sensor_fixture.py`, `create_adapter_skeleton.py`, and the
  adapter examples under `examples/adapters/`.
- `core_runtime/cli/` — repository tooling: `validate`, `lint`, `doctor`,
  `inventory`, `contract_preflight`, `release_check`, `bump_version`,
  `create_domain`, `sync_template`, `repair_artifact_paths`.

## Integration model

- Downstream applications call validator scripts by subprocess or through
  their own adapters. CORE validates structure, fingerprints, manifests and
  evidence windows; the downstream domain owns business semantics.
- External indexing or workflow tooling may call `read_bounded_reference.py` for
  bounded, deterministic file reads.

## Quality gate

```bash
pytest -q                                                    # full suite, <60s, no network
python -m core_runtime.cli lint --scope tooling --format json  # release hygiene
python -m core_runtime.cli doctor                            # repo health check
```

## History

This is a v11.0 clean rebuild by whitelist. The prior repository — a
physics-informed surrogate simulator (CPT) plus a self-referential
protocol-model certification apparatus — is preserved at the
`legacy-final` git tag. See [docs/CORE_REBUILD_FROM_ZERO.md](docs/CORE_REBUILD_FROM_ZERO.md)
for the full rationale and the exact whitelist/blacklist, and
[docs/releases/v11.0.1.md](docs/releases/v11.0.1.md) for what changed.

## Boundary

CORE is public and domain-agnostic. It must never receive private names,
paths, customer data or business semantics from the domains that consume
it.
It does not operate a POS, does not decide legal or fiscal truth, and a
passing validation is not a legal, financial or fraud-free certification —
only a statement that the artifact matches its declared contract.
