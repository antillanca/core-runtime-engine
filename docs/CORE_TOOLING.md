# CORE Tooling Reference

This document covers the available CORE runtime tooling commands, their arguments, output formats, and exit codes.

Roadmap note: future repository operations should follow
[`CORE_DETERMINISTIC_TOOLING_SURFACE.md`](CORE_DETERMINISTIC_TOOLING_SURFACE.md).
That document keeps read-only diagnostics separate from guarded mutation,
defines the intended report envelope for new commands, and records the next
tooling slices.

## Commands

### lint

Run tooling lint checks against the repository.

```bash
python -m core_runtime.cli lint [--scope tooling] [--format json|markdown] [--output <path>]
```

| Argument | Default | Description |
|----------|---------|-------------|
| `--scope` | `tooling` | Scope of lint checks |
| `--format` | `json` | Output format |
| `--output` | stdout | Write output to file |

**Exit codes:** 0 = pass, 1 = errors, 2 = blocked, 3 = internal error

**Checks performed:**

1. Version inventory and consistency (`core_runtime/__version__.py`, `pyproject.toml`, `README.md`, `docs/VERSIONING_POLICY.md`, `docs/CORE_RELEASE_README.md`, `CHANGELOG.md`)
2. Required file inventory (scripts, docs, schemas, examples, tests, requirements)
3. Script compilation checks
4. JSON parse checks (schemas, examples, requirements.lock)
5. Stale documentation checks (warnings only)
6. Safety checks (private path leakage, proposal execution safety, explicit TODO/template placeholders)

The CI replay-certification workflow runs the same lint command early as a
read-only gate:

```bash
python -m core_runtime.cli lint --scope tooling --format json --output artifacts/tooling/CORE-tooling-lint-ci.json
python -m core_runtime.cli lint --scope tooling --format markdown --output artifacts/tooling/CORE-tooling-lint-ci.md
```

Warnings remain non-fatal in CI. Only `error`, `blocked`, and `internal_error`
states should fail the job.

---

### release-check

Run the release-check wrapper around `scripts/verify_release.py`.

```bash
python -m core_runtime.cli release-check [--target <version>] [--format json|markdown] [--output <path>] [--skip-tooling-lint] [--timeout <seconds>] [--preflight-only] [--group <name>] [--profile <name>] [--list-checks] [--plan] [--timing-json <path>] [--debug]
```

| Argument | Default | Description |
|----------|---------|-------------|
| `--target` | canonical repository version | Release target |
| `--format` | `json` | Output format |
| `--output` | stdout | Write output to file |
| `--skip-tooling-lint` | `false` | Skip the tooling lint precheck |
| `--timeout` | `120` | Maximum seconds for the release gate subprocess |
| `--preflight-only` | `false` | Run bounded preflight checks without the full gate |
| `--group` | none | Run a named release-gate slice such as `tooling`, `release-metadata`, `docs`, `replay`, `tests`, or `tests-full` |
| `--profile` | none | Run a named release-check profile preset such as `fast`, `local`, `full`, or `release-candidate` |
| `--list-checks` | `false` | List available checks without executing them |
| `--plan` | `false` | Emit the planned release-gate execution order without running checks |
| `--timing-json` | none | Write deterministic timing data for the selected gate mode |
| `--debug` | `false` | Include command, cwd, target mapping, and output previews |

Target normalization:

- `10.5.1` is accepted and normalized to `10.5.1` internally.
- `v10.5.1` is accepted and normalized to `10.5.1` internally.
- If `--target` is omitted, the canonical version is read from `core_runtime/__version__.py`.
- The wrapped `scripts/verify_release.py` is invoked with `--target v10.5.1`.

Execution order:

1. tooling lint precheck
2. release gate script preflight, including `scripts/verify_release.py --help` in preflight-only mode
3. authoritative `scripts/verify_release.py` with bounded timeout

Gate decomposition modes:

- `--group tooling` covers the fast tooling precheck slice.
- `--group release-metadata` and `--group docs` cover the long prefix before replay.
- `--group replay` covers replay certification and router replay certification.
- `--group tests-tooling` covers the tooling pytest subset.
- `--group tests-replay` covers replay-adjacent pytest and currently reaches the configured timeout in this workspace.
- `--group tests-integration`, `--group tests-contracts`, and `--group tests-core` split the remaining test surface into bounded slices.
- `--group tests-full` runs the full subgroup sequence.
- `--group tests` is the umbrella plan/alias for the test subgroups.
- `--profile fast` runs tooling, metadata and tooling-test baseline slices.
- `--profile local` adds bounded development test slices to `fast`.
- `--profile full` runs the current full deterministic release surface.
- `--profile release-candidate` matches `full` and reserves future tag/package expectation checks.
- `--list-checks` and `--plan` are read-only introspection modes and do not execute checks.
- `--timing-json` writes deterministic JSON timing data for the selected mode without changing gate behavior.

Tooling lint failures stop the release-check wrapper before the release gate is invoked.
When the full gate exceeds the configured timeout, the wrapper returns a blocked diagnostic instead of hanging indefinitely.
`tests-replay`, `tests-integration`, `tests-contracts`, and `tests-core` are all
bounded now. In this workspace the full release-check passes within a 300 second
budget, and release-check profiles are now available as stable presets.

---

### list / info

Read-only repository inventory navigation.

```bash
python -m core_runtime.cli list [schemas|contracts|adapters|domains] [--format json|markdown] [--output <path>]
python -m core_runtime.cli info [schema|schemas|contract|contracts|adapter|adapters|domain|domains] [name] [--format json|markdown] [--output <path>]
```

| Command | Purpose |
|---------|---------|
| `list schemas` | List schema inventory items |
| `list contracts` | List contract inventory items |
| `list adapters` | List adapter inventory items |
| `list domains` | List domain inventory items |
| `info` | Show repository-level summary |
| `info schema TaskCloseout.v1` | Show a specific item inside a kind |

`list` and `info` use the shared read-only inventory envelope. Missing or
unknown kinds are reported as `blocked`; item lookup failures are reported as
`error`. Warnings remain non-fatal.

---

### validate

Read-only structural validation separate from linting.

```bash
python -m core_runtime.cli validate [schemas|examples|manifests|contracts|domain] [name] [--format json|markdown] [--output <path>]
```

| Command | Purpose |
|---------|---------|
| `validate schemas` | Validate schema metadata and JSON shape |
| `validate examples` | Validate example manifests |
| `validate manifests` | Validate manifest path references |
| `validate contracts` | Validate Solidity and contract-doc surfaces |
| `validate domain accounting` | Validate a specific domain package |

`validate` keeps `lint` fast and broad while running deeper surface-specific
checks. Missing kinds are reported as `blocked`; malformed surfaces are
reported as `error`; warnings remain non-fatal unless a consumer chooses to
elevate them.

---

### doctor

Read-only environment diagnostics for local development readiness.

```bash
python -m core_runtime.cli doctor [--format json|markdown] [--output <path>]
```

Checks performed:

1. Python version baseline.
2. Development tool availability (`pytest`, `ruff`, `mypy`).
3. Git availability and branch detection.
4. `scripts/verify_release.py --help` execution.
5. Release notes directory permissions.
6. Dirty version-bearing file detection.

The command is advisory and read-only. Warning-level findings should remain
non-fatal for local development; blocked and error states should only be used
when the environment cannot be meaningfully inspected.

---

### contract-preflight

Advisory-only contract candidate review against known public CORE schemas.

```bash
python -m core_runtime.cli contract-preflight --candidate <name> [--format json|markdown] [--output <path>]
python -m core_runtime.cli contract-preflight --compare <left> <right> [--format json|markdown] [--output <path>]
```

| Mode | Purpose |
|------|---------|
| `--candidate <name>` | Review a single known contract candidate by name |
| `--compare <left> <right>` | Compare two known contract candidates |

The command resolves contracts from `schemas/core/` using schema title and
`schema_version` metadata. Unknown candidates are reported as `blocked`.
Comparisons are read-only and advisory-only; they emit required-field overlap,
field deltas and schema-version parity without any promotion action.

---

### create-domain

Dry-run-first domain scaffolding plan.

```bash
python -m core_runtime.cli create-domain <name> --dry-run [--template <name>] [--format json|markdown] [--output <path>]
```

| Argument | Default | Description |
|----------|---------|-------------|
| `name` | required | Domain name to scaffold |
| `--template` | `generic` | Scaffold template name |
| `--dry-run` | `false` | Required in this slice; emits plan without mutating files |

The command emits planned domain files, tests, examples, docs, collisions and
design risks. It is advisory-only and read-only in this slice; apply mode is
not enabled yet.

---

### repair-artifact-paths

Dry-run-first artifact path repair planning for derived artifacts.

```bash
python -m core_runtime.cli repair-artifact-paths --dry-run [--from <path>] [--to <path>] [--manifest <path>] [--format json|markdown] [--output <path>]
```

| Argument | Default | Description |
|----------|---------|-------------|
| `--dry-run` | `false` | Required in this slice; emits a repair plan without mutating files |
| `--from` / `--to` | none | Optional targeted source-to-destination replacement rule |
| `--manifest` | `core_runtime/data/artifact_migration_manifest.json` | Optional migration manifest that drives default repair rules |

The command scans derived text artifacts for migrated path references, reports
planned repairs for mutable files, and marks immutable evidence as blocked if
it still contains an old path. Apply mode is reserved for a later guarded
mutation slice.

---

### bump-version

Plan or apply a version bump. Supports both dry-run (preview changes) and controlled apply (transactional mutation) modes.

#### Dry-run mode

Computes and reports all files that would change if the version were bumped, without modifying any files.

```bash
python -m core_runtime.cli bump-version <target_version> --dry-run [--format json|markdown] [--output <path>]
```

#### Apply mode

Performs the actual version mutation with safety checks. Requires `--confirm-current` to protect against stale assumptions.

```bash
python -m core_runtime.cli bump-version <target_version> --apply --confirm-current <current_version> [--format json|markdown] [--output <path>]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `target_version` | Yes | Target SemVer version (e.g. `10.5.1`) |
| `--dry-run` | No | Dry-run mode (default if neither `--dry-run` nor `--apply` specified) |
| `--apply` | No | Apply mode — perform the actual version mutation |
| `--confirm-current` | With `--apply` | Confirm the current version before applying (safety gate) |
| `--format` | No | Output format: `json` (default) or `markdown` |
| `--output` | No | Write output to file instead of stdout |

**Mutual exclusion:** `--dry-run` and `--apply` cannot both be set. If neither is specified, `--dry-run` is the default.

**Exit codes:** 0 = pass, 1 = errors, 2 = blocked, 3 = internal error

**Pre-apply validation (apply mode only):**

1. Target version format validation (MAJOR.MINOR.PATCH, no leading `v`, no prerelease).
2. Current canonical version discovery from `core_runtime/__version__.py`.
3. `--confirm-current` must match the discovered canonical version.
4. Version consistency check across all version-bearing files.
5. Version movement rule: target must be strictly greater than current (same or lower is blocked).
6. Git safety check: approved mutation files must have no uncommitted changes.
7. File allowlist check: only approved version-bearing files may be mutated.

**Transactional mutation (apply mode):**

All file contents are computed in memory first. No file is written until all validation passes. If any write fails mid-transaction, the error is reported with the list of touched files (partial mutation).

**Post-apply validation (apply mode):**

After all files are written, a fresh version inventory consistency check is re-run. Any inconsistencies are reported as error diagnostics.

**Changelog handling (apply mode):**

Only the first `## v` heading in `CHANGELOG.md` is replaced (the latest release heading). Historical entries are preserved.

**Release notes (apply mode):**

If `docs/releases/v<target>.md` does not exist, a minimal release note template is created.

**Version movement rules:**

| Current | Target | Result |
|---------|--------|--------|
| 10.5.0 | 10.5.1 | Accepted (patch bump) |
| 10.5.0 | 10.6.0 | Accepted (minor bump) |
| 10.5.0 | 11.0.0 | Accepted (major bump) |
| 10.5.0 | 10.5.0 | Blocked (same version) |
| 10.5.1 | 10.5.0 | Blocked (lower version) |

**Files mutated (apply mode) / inspected (dry-run):**

- `core_runtime/__version__.py`
- `pyproject.toml`
- `core_runtime/__init__.py` (Version: comment)
- `README.md`
- `docs/VERSIONING_POLICY.md`
- `docs/CORE_RELEASE_README.md`
- `CHANGELOG.md`
- `docs/releases/README.md`

**Files created (apply mode):**

- `docs/releases/v<target>.md` (if not already present)

**Version validation rules:**

| Input | Result |
|-------|--------|
| `10.5.1` | Accepted |
| `0.0.0` | Accepted |
| `v10.5.1` | Rejected (no leading `v`) |
| `10.5` | Rejected (missing patch) |
| `10.5.1-rc1` | Rejected (no prerelease) |
| `abc` | Rejected (not SemVer) |

**Diagnostic codes:**

| Code | Severity | Description |
|------|----------|-------------|
| `core.bump_version.invalid_target` | blocked | Invalid target version format |
| `core.bump_version.canonical_missing` | blocked | Cannot discover current version |
| `core.bump_version.version_inconsistent` | blocked | Version consistency check failed |
| `core.bump_version.confirm_current_mismatch` | blocked | `--confirm-current` does not match canonical version |
| `core.bump_version.target_not_greater` | blocked | Target version is not greater than current |
| `core.bump_version.dirty_version_file` | blocked | Version file has uncommitted git changes |
| `core.bump_version.file_not_in_allowlist` | blocked | File not in approved mutation set |
| `core.bump_version.mutual_exclusion` | blocked | `--dry-run` and `--apply` both specified |
| `core.bump_version.confirm_current_required` | blocked | `--apply` without `--confirm-current` |
| `core.bump_version.internal_error` | blocked | Internal error during mutation |
| `core.bump_version.real_mutation_not_enabled` | blocked | (Removed in Slice 3 — apply is now supported) |

---

## Output Formats

### JSON (both commands)

```json
{
  "tool": "core-runtime lint|bump-version",
  "scope": "tooling",
  "status": "pass",
  "diagnostics": [],
  "checks": { ... }
}
```

### Markdown (both commands)

```markdown
# CORE <command> report

## Summary
...
```

For `bump-version`, the JSON output includes additional fields:

```json
{
  "tool": "core-runtime bump-version",
  "mode": "dry-run",
  "mutation_performed": false,
  "current_version": "10.5.0",
  "target_version": "10.5.1",
  "summary": {
    "files_checked": 6,
    "files_that_would_change": 4,
    "replacement_count": 8,
    "info": 0,
    "warning": 0,
    "error": 0,
    "blocked": 0
  },
  "changes": [
    {
      "path": "core_runtime/__version__.py",
      "would_change": true,
      "replacement_count": 2
    }
  ],
  "diagnostics": []
}
```

---

## Diagnostic Model

All commands use a shared diagnostic model:

| Severity | Exit code impact |
|----------|-----------------|
| `info` | No impact |
| `warning` | No impact (informational) |
| `error` | Exit code 1 |
| `blocked` | Exit code 2 |

Each diagnostic includes:

| Field | Description |
|-------|-------------|
| `code` | Machine-readable code (e.g. `core.bump_version.invalid_target`) |
| `severity` | `info`, `warning`, `error`, or `blocked` |
| `message` | Human-readable message |
| `path` | File path (if applicable) |
| `details` | Additional context |

---

## Module Layout

```text
core_runtime/
  cli/
    main.py            # Argument parser and dispatch
    lint.py             # Lint command implementation
    doctor.py           # Doctor preflight command implementation
    contract_preflight.py # Contract preflight command implementation
    create_domain.py   # Domain scaffolding preflight command implementation
    sync_template.py   # Domain template drift preflight command implementation
    repair_artifact_paths.py # Artifact path repair preflight command implementation
    inventory.py        # List/info command implementation
    validate.py         # Validate command implementation
    bump_version.py     # Bump-version command implementation
  tooling/
    diagnostics.py      # Diagnostic model (shared)
    version_inventory.py # Version discovery and consistency
    file_inventory.py   # Required file checks
    json_checks.py      # JSON parse checks
    safety_checks.py    # Safety checks
    report_writer.py    # JSON/Markdown report writer
    repository_inventory.py # Read-only inventory navigation
    validation.py       # Read-only structural validation
    doctor.py           # Read-only environment diagnostics
    contract_preflight.py # Advisory-only contract review helpers
    create_domain.py    # Dry-run-first domain scaffold planner
    sync_template.py    # Dry-run-first template drift planner
    repair_artifact_paths.py # Dry-run-first artifact path repair planner
    bump_version.py     # Bump-version planner and controlled mutation engine
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Pass — no errors or blockers |
| 1 | Error — at least one error diagnostic |
| 2 | Blocked — at least one blocked diagnostic |
| 3 | Internal error — tooling itself failed |
