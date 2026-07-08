# Anchoring Event Fixtures

| File | Purpose | Expected Result |
|------|---------|-----------------|
| accepted_freeze_anchor.json | Valid event for freeze artifact anchoring | passed |
| accepted_profile_anchor.json | Valid event for business_profile anchoring (downstream fork example) | passed |
| rejected_fingerprint_mismatch.json | event_fingerprint doesn't match canonical computation | failed |
| rejected_hash_fp_mismatch.json | anchor_hash doesn't match artifact_fingerprint bytes32 | failed |
| rejected_unknown_chain.json | chain_id not in allowed set | failed |
