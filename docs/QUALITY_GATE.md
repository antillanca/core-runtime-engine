# Quality Gate

## Status

Minimum quality gate for the CORE v11.x line.

## Required before release certification

- `python -m core_runtime.cli lint --scope tooling --format json` — must
  report `"status": "pass"` with zero errors/warnings.
- `pytest -q` — full suite green, no network, under 60 seconds.
- `python -m core_runtime.cli doctor` — repository health check.

## Scope

v11 intentionally has no `ruff`/type-checker requirement in this gate: the
codebase is small enough that `pytest` plus the tooling lint catch the
practical risks (missing files, version drift, schema/example errors).
Add static analysis back here if the surface grows enough to justify it.
