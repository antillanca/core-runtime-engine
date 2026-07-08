# Synthetic Indexed Document

This is a synthetic document for CORE bounded reference index testing.

<!-- core:index id="chapter_a" -->
# Chapter A

This is chapter A content. It contains synthetic text for testing
bounded reference reads. The agent should stop reading when it
encounters the next marker or reaches max_bytes.

Key points:
- Bounded reads limit token consumption
- Fingerprints ensure cache validity
- Markers define exact boundaries
<!-- core:index id="chapter_b" -->
# Chapter B

This is chapter B content. It demonstrates the next_marker end policy
where reading chapter A stops at this marker.

Additional points:
- Each chapter has a stable ref_id
- Paths are always relative
- max_bytes prevents unbounded reads
<!-- core:index id="chapter_c" -->
# Chapter C

This is the final chapter. It ends at EOF since there is no next marker.

End of synthetic document.
