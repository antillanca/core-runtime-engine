# CORE Versioning Policy

## Semantic Versioning

CORE follows strict semantic versioning (MAJOR.MINOR.PATCH).

- **Current**: v11.6.0
- **MAJOR**: breaking changes to public schemas, validator CLI contracts,
  or frozen fingerprint/canonicalization semantics.
- **MINOR**: new schemas, new validator scripts, new CLI subcommands
  (additive, non-breaking).
- **PATCH**: bug fixes, performance improvements, documentation.

### v11.6.0 stabilization boundary

v11.6.0 is the additive stabilization line before CORE-Interop. It may repair
determinism, fail-closed validation, package metadata, release tooling, replay
gates and documentation without changing the meaning of an existing frozen
fingerprint or public schema. The public contract name is **Domain Scale
Kernel v3**, and its technical compatibility identifier remains
`core.dsk.v3`.

### Planned v12.0.0 boundary

v12.0.0 is reserved for a separately approved breaking migration. Its design
record must cover, at minimum:

- an interoperable canonicalization profile (preferably RFC 8785/JCS or an
  explicitly versioned equivalent) and a migration for existing fingerprints;
- strict I-JSON/non-finite-number rejection and removal of implicit
  `default=str` coercion from public hashing paths;
- closed, versioned result envelopes and schema references across all public
  validators and runtimes;
- a compatibility matrix for the CLI, package resources, Engine/Runtime and
  CORE-Interop consumers; and
- dual-read/replay evidence proving that v11 artifacts remain verifiable
  without silently treating them as v12 artifacts.

No v12 behavior is enabled by the v11.6.0 release. A v12 implementation must
introduce new fingerprints and manifests rather than rewriting v11 history.

## Frozen-manifest lifecycle

A frozen release manifest binds exact repository bytes, so it is only
byte-verifiable against the working tree while its line is *current*. Once
a newer line is cut, shared files (release tooling, `CHANGELOG.md`,
`__version__.py`, runtime modules) legitimately move on and the older
manifest can never match the live tree again. That is expected, not
corruption: the manifest stays as the historical record and is never
rewritten.

When cutting a new release line, do all three:

1. Point `scripts/verify_release.py`'s frozen-manifest checks and the CI
   release gate at the **new** line. Leaving CI pinned to the previous
   line makes it fail permanently on a green tree.
2. Give the superseded line the `historical_baseline_preserved` treatment
   in `verify_release.py` rather than re-hashing it.
3. Rescope that line's byte-equality tests into historical-baseline
   integrity tests — inventory, roles, ordering, uniqueness,
   `artifact_count`, self-consistent fingerprint and continued existence
   of every artifact, without live-byte comparison. See
   `tests/test_frozen_release_manifest.py` for the v11.1 example.

Never assert a fixed count of files in a live directory in these tests
(`len(glob("schemas/core/*.json")) == 26`); the tree grows, and such an
assertion fails the moment it does.

## v11.0.0 — clean rebuild

v11 is a whitelist rebuild of the engine: only public schemas, validators,
tooling CLI surfaces and generic downstream-adapter entrypoints were carried
forward. The full historical repository
(CPT simulator, protocol-model candidate certification, expert router,
GAIA pipeline, and the v8.x-pinned governance freeze) is preserved at the
`legacy-final` tag and in `_archive/core-runtime-engine-legacy/` in the
workspace. See
[CORE_REBUILD_FROM_ZERO.md](CORE_REBUILD_FROM_ZERO.md) for the full
rationale and whitelist/blacklist.

Versioning resets to v11.0.0 rather than continuing the v10.x line because
the surface changed too much for a patch/minor bump to be meaningful.

## v11.0.1 — public-surface hygiene release

v11.0.1 supersedes the withdrawn v11.0.0 release. It keeps the v11 public
surface and rebuild rationale, while tightening public/private boundary
hygiene and release verification.

## v11.1.0 — frozen-rule anchoring

v11.1.0 adds generic frozen rule sets, blinded personal commitments,
externally signed approvals, deterministic SHA-256 Merkle batching, unsigned
EVM transaction preparation, gas-reserve checks, read-only chain evidence, and
the minimal non-custodial `CoreRuleAnchor` contract. It does not change CORE
into a runtime, wallet, financial authority, or source of domain truth.
