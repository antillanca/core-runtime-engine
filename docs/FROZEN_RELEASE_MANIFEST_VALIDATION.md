# Frozen release manifest validation

Frozen release manifests contain historical evidence. Their recorded
`file_sha256` values and canonical `fingerprint` describe the tree that was
sealed at release time; they must remain verifiable after the repository
evolves.

The v11.2 validators therefore have two explicit modes:

- The default mode validates the manifest itself: schema, canonical
  fingerprint, inventory, roles, safe paths and artifact presence.
- `--verify-live-artifacts` additionally compares every recorded file hash with
  the current checkout. This mode is for validating a newly built candidate or
  frozen manifest before sealing it; it is not a historical replay gate.

The manifest file remains excluded from its own artifact inventory. Its
canonical fingerprint covers the manifest content, while the artifact hashes
cover the declared release surface.
