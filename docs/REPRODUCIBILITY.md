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
- Frozen rule validation, SHA-256 commitments, Merkle construction, proof
  verification, and unsigned calldata construction are offline and
  deterministic.
- External EIP-191 signature recovery and RPC-backed chain/balance checks use
  the optional `anchoring` extra (`web3` and its cryptographic backend).
- `create_private_rule_commitment.py` intentionally uses operating-system
  randomness. The resulting commitment is deterministic after it is frozen;
  generating a second opening must produce a different commitment.
- RPC fee, nonce, balance, confirmation, and block observations are explicitly
  non-deterministic evidence. They are fingerprinted after observation and are
  never part of rule evaluation replay.
- No command signs or broadcasts. Reproducibility therefore never depends on
  access to a wallet secret.

See [FROZEN_RULE_ANCHORING.md](FROZEN_RULE_ANCHORING.md) for the exact hash
domains and trust boundary.
