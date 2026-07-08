# Reproducibility

CORE v11 has a small dependency surface. Deterministic installs use the
generated lockfile.

## Install From Lock

```bash
pip install -e . -r requirements.lock
```

The lock is regenerated with:

```bash
python scripts/generate_requirements_lock.py > requirements.lock
```

## Determinism guarantees

- Schema validation and fingerprinting use canonical JSON (sorted keys,
  stable float quantization) — same input always produces the same hash.
- Validator scripts are pure functions over their input file plus the
  repository's schemas: no network access, no wall-clock dependence, no
  random seeds.
- The optional `anchoring` extra (`web3`) is only used by
  `scripts/submit_anchoring.py` and `scripts/core_anchor.py`; without it,
  those scripts fall back to dry-run mode and every other script in the
  repository runs without it installed.
