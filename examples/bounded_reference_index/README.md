# Bounded Reference Index Fixtures

Synthetic examples for the CORE bounded reference index contract.

## Files

| File | Purpose | Expected Validation |
|------|---------|---------------------|
| `sample_document.md` | Document with synthetic `<!-- core:index -->` markers | Source document for reads |
| `accepted_index.json` | Valid bounded reference index (3 entries) | passed |
| `accepted_read_window.json` | Valid bounded read window (chapter_a) | passed |
| `accepted_processed_cache.json` | Valid processed reference cache (fresh) | passed |
| `rejected_missing_marker.json` | Index referencing nonexistent marker | failed: missing_start_marker |
| `rejected_absolute_path.json` | Index with absolute path | failed: absolute_path_rejected |
| `rejected_path_escape.json` | Index with `../` path escape | failed: path_escape_rejected |
| `rejected_stale_cache.json` | Processed cache with mismatched fingerprint | failed: stale_processed_cache |

## Canonical Commands

Validate all fixtures:

```bash
python scripts/validate_bounded_reference_index.py examples/bounded_reference_index/accepted_index.json
python scripts/validate_bounded_reference_index.py examples/bounded_reference_index/
```

Read a bounded reference:

```bash
python scripts/read_bounded_reference.py examples/bounded_reference_index/accepted_index.json chapter_a
```
