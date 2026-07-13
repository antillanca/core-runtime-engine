# Frozen rule anchoring

CORE v11.1 introduces a non-custodial path for freezing, approving, batching,
and timestamping general rules and personal rule commitments. Blockchain is
an external persistence and ordering witness. It does not make a rule true,
beneficial, valid, or executable.

The trust chain is:

`canonical rule -> SHA-256 fingerprint -> external approval signature ->`
`Merkle batch -> externally signed transaction -> confirmed event -> replay`

Every link is independently checkable. A broken link fails closed.

## What “frozen” means

A `FrozenRuleSet.v1` has immutable content, a version, canonical JSON
serialization, a SHA-256 fingerprint, declared validation steps, typed step
results, deterministic evaluation, required evidence, and replay. An amendment
creates a new frozen version; it never edits the prior artifact.

This is the useful part of the Bitcoin analogy. Participants do not trust a
central statement that “the rules ran.” They can run the same validators,
recompute the same hashes, inspect the signed approval, and compare the same
anchored root. CORE remains a conformance standard, not a sovereign authority.

SHA-256 identifies content. EVM signatures establish approval by a public
address. They solve different problems. MD5 is not accepted.

## Public general rules and private personal rules

A general rule publishes its complete frozen rule content. A personal rule
publishes only:

- a randomized blinded commitment;
- a non-identifying rule-set envelope;
- the rule count;
- its authorized public signer policy.

The private content and its 32-byte random opening remain off-chain. The exact
commitment is:

```text
SHA256(
  "CORE_PRIVATE_RULE_COMMITMENT_V1\\0" ||
  SHA256(canonical_private_content) ||
  random_32_byte_nonce
)
```

Publishing the unblinded private-content hash would permit guesses against
low-entropy personal rules. Publishing the nonce would destroy the privacy
property. Back up the opening separately, encrypted, and never commit it to
Git. `create_private_rule_commitment.py` refuses to place the opening inside
the public CORE repository and writes it with mode `0600`.

The public address can still create a correlation. A person who needs stronger
unlinkability should use a purpose-specific address and obtain appropriate
privacy and legal review before using a public chain.

## Approval without wallet custody

CORE never asks for, receives, stores, logs, or transmits a private key, seed
phrase, wallet password, hardware-wallet PIN, or recovery phrase. There is no
secret environment variable or command-line argument.

The approval message uses EIP-191 and binds all three values:

- the exact frozen rule-set fingerprint;
- the EIP-155 chain ID;
- the deployed `CoreRuleAnchor` address.

This prevents a signature for one rule, chain, or contract from being silently
reused for another. CORE recovers the public signer and rejects malformed,
unauthorized, duplicate, and high-s malleable signatures.

Example workflow:

```bash
python scripts/validate_frozen_rule_set.py frozen_rule_set.json

python scripts/create_rule_approval_request.py \
  --rule-set frozen_rule_set.json \
  --chain-id 11155111 \
  --contract 0xPUBLIC_CONTRACT_ADDRESS \
  --signer 0xPUBLIC_SIGNER_ADDRESS \
  --output approval_request.json

# Review and sign approval_request.message in the external wallet.
# Put only the resulting public 0x signature in signature.txt.

python scripts/finalize_rule_approval.py \
  --request approval_request.json \
  --signature-file signature.txt \
  --output approval.json

python scripts/validate_rule_approval.py approval.json
```

The example address placeholders above are public values. Never substitute a
wallet secret into a shell argument or file intended for CORE.

## Merkle batching and minimum value per rule

One on-chain transaction can cover many rule sets. Leaves are sorted by frozen
rule fingerprint. Approval fingerprints are sorted within each leaf. The
domain-separated hashes are:

```text
leaf   = SHA256(0x00 || "CORE_RULE_ANCHOR_LEAF_V1\\0" || canonical_leaf_json)
parent = SHA256(0x01 || "CORE_RULE_ANCHOR_NODE_V1\\0" || left || right)
```

An odd final node is paired with itself. Every batch contains a proof for each
leaf, the root, and a fingerprint of the complete manifest.

```bash
python scripts/build_rule_anchor_batch.py \
  --rule-set general.json \
  --rule-set personal_commitment.json \
  --approval general_approval.json \
  --approval personal_approval.json \
  --output batch.json

python scripts/validate_rule_anchor_batch.py batch.json
```

CORE does not invent a token or a fee “per datum.” The smallest actual unit is
the selected network's native `wei`. The maximum batch cost divided by the
number of rule sets is reported as `max_cost_per_rule_wei`. It is an upper
bound for reserve planning, not a price charged by CORE.

## Unsigned contract deployment

CORE prepares deployment data but never signs or broadcasts it. The frozen
source, ABI, creation bytecode, runtime bytecode, compiler settings, and their
digests are bound by `CoreRuleAnchor.build.json`. The preparer verifies those
artifacts before emitting a request.

An offline request can be priced with manually observed public fee values:

```bash
python scripts/prepare_core_rule_anchor_deployment.py \
  --chain-id 11155111 \
  --deployer 0xPUBLIC_DEPLOYER_ADDRESS \
  --gas-limit 500000 \
  --max-fee-per-gas-wei 1000000000 \
  --max-priority-fee-per-gas-wei 100000000 \
  --post-deployment-reserve-wei 1000000000000000 \
  --output unsigned_deployment.json

python scripts/validate_unsigned_rule_anchor_deployment.py \
  unsigned_deployment.json
```

Alternatively, `--rpc-url-file` obtains the chain ID, nonce, estimated gas,
fees, and public balance from a node. It cannot be combined with manual gas
values. The RPC URL stays in its private input file and is never copied into
the artifact.

The validator independently recomputes the build fingerprint, creation
bytecode, expected runtime hash, maximum deployment cost, reserve, shortfall,
readiness, and artifact fingerprint. A passing report still contains
`execution_authorized: false` and `broadcast_authorized: false`. The operator
must review and sign in an external wallet. After confirmation, the deployed
runtime bytecode must equal `expected_runtime_bytecode_sha256` before the new
address is used in approval or anchoring requests.

## Contract and gas reserve

`CoreRuleAnchor.sol` has no owner, upgrade, pause, token, custom fee, payable
entrypoint, withdrawal, or custody. It stores one mapping slot from Merkle root
to manifest hash and emits the anchorer, root, manifest, count, visibility
mask, and timestamp. Duplicate and zero roots fail closed.

The transaction preparer never signs or broadcasts. When given an RPC URL via
a private file, it verifies chain ID and deployed code, estimates gas, obtains
fees and balance, and calculates a reserve for several future batches. Provider
URLs are read from a file because they often embed credentials and are never
copied into output.

```bash
python scripts/prepare_rule_anchor_transaction.py \
  --batch batch.json \
  --submitter 0xPUBLIC_SIGNER_ADDRESS \
  --rpc-url-file /private/path/rpc-url.txt \
  --reserve-batches 4 \
  --output unsigned_transaction.json
```

If the balance is below the reserve, readiness is
`insufficient_balance` and the command exits blocked. CORE never transfers or
auto-refills funds. The operator reviews `to`, `chain_id`, `value_wei = 0`,
calldata, gas, and fees in an external wallet before signing and broadcasting.

After broadcast, verify the transaction, exact calldata, event, contract
state, and confirmations:

```bash
python scripts/verify_rule_anchor_onchain.py \
  --batch batch.json \
  --tx-hash 0xPUBLIC_TRANSACTION_HASH \
  --rpc-url-file /private/path/rpc-url.txt \
  --confirmations 3 \
  --output chain_evidence.json
```

## Worked public example

`examples/frozen_rules/general_cooperative_supply.json` demonstrates a generic
cooperative quote rule. It requires a privacy-safe aggregate quantity result,
an exact quote comparison, evidence provenance, responsible review on an
ambiguous comparison, and deterministic replay. It is synthetic and does not
certify any supplier, cooperative, price, or real-world arrangement.

The mixed batch also includes
`examples/frozen_rules/personal_commitment.json`. No personal plaintext or
opening is present in the repository or Merkle manifest.

## Projection and responsible agency

Evidence may come from a human, nonhuman biological source, software,
human-directed software, or a mixed ensemble. Authorization remains a separate
accountable signer boundary. See
[`PROJECTION_AND_RESPONSIBLE_AGENCY.md`](PROJECTION_AND_RESPONSIBLE_AGENCY.md)
for the 2D-projection/3D-reconstruction analogy and compatibility guidance for
historical `human_*` schema fields.

## Security limits

- An anchor proves existence no later than a block; it does not prove truth.
- A valid signature proves control of a key, not wisdom or fair governance.
- A commitment hides content only while the random opening remains secret.
- Public addresses, timing, and repeated batches can create metadata links.
- Chain reorganization risk is handled by a configurable confirmation count.
- Contract bytecode and source must be compiled reproducibly and verified
  before a production address is accepted.
- Catastrophic or irreversible policy remains subject to stricter responsible
  approval and veto rules; blockchain persistence never bypasses them.
