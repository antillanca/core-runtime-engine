# Private Domain Integration Examples

## Purpose

These fixtures demonstrate the generic pattern by which a private downstream
fork integrates with CORE without leaking private data into the public
repository.

## Structure

```
private_domain_integration/
  vocabularies/
    synthetic_sales_v1.json    # Generic synthetic vocabulary (not any real business)
  command_candidates/
    accepted.json              # Candidate that passes all CORE validation
    rejected_private_data.json # Candidate containing private-data placeholders
    rejected_unknown_command.json # Candidate referencing an unknown command
```

## Design Rules

1. All data is synthetic and domain-neutral.
2. No private project names, paths or aliases.
3. Vocabulary IDs use the `external:` prefix to signal they are provided by
   a downstream fork, not by CORE's public vocabulary bundle.
4. Command candidates that embed private business data (costs, margins,
   customer records) are rejected deterministically.
5. Command candidates that reference commands not in any known vocabulary
   are rejected fail-closed.

## Vocabulary Reference Pattern

A private downstream fork provides its own vocabulary files. CORE's public
validator only needs the `vocabulary_id` string to check that the candidate
targets a known domain. The actual vocabulary content lives in the private
repository.

The `external:` prefix tells CORE validators: "This vocabulary is maintained
outside CORE's public bundle. CORE validates structure; the downstream fork
validates semantics."

Example:

```json
{
  "vocabulary_id": "external:sales_reports.commands.v1",
  "domain_id": "sales_reports",
  "command": "sales_summary"
}
```

CORE validates that the structure is correct and the `vocabulary_id` follows
the `external:` naming convention. It does NOT resolve or load the external
vocabulary file itself.
