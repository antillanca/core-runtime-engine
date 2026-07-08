# Parametric Template Fixtures

Synthetic examples for the CORE parametric template cache contract.

## Files

| File | Purpose | Expected Validation |
|------|---------|---------------------|
| `valid_read_template.json` | Valid read-method template with enum+string slots | passed |
| `valid_write_template.json` | Valid write-method template with all forbidden categories | passed |
| `valid_binding_read.json` | Valid variable binding resolving the read template | passed |
| `invalid_command_validation_false.json` | Structural invalid: requires_command_validation=false | failed |
| `invalid_fingerprint_format.json` | Structural invalid: malformed template_fingerprint | failed |
| `invalid_enum_empty_values.json` | Structural invalid: enum slot with empty enum_values + empty forbidden_categories | failed |

## Design Rules

- All domain names, intent names and slot names are **synthetic**.
- No private business names, paths, SQL or endpoints.
- Fingerprint values use the `sha256:` prefix format.
- Templates that produce `command_candidate` MUST have `requires_command_validation: true`.
- `forbidden_categories` must always include `live_results` at minimum.
- Enum slots must have non-empty `enum_values`.

## Safety Rules

- No live results, state events, permissions, financial state, or stock state may be cached.
- The parametric cache stores ONLY the structural command skeleton (route, shape, resolved slots).
- Exact cache remains the authority for identical inputs -- parametric cache only reuses structure.

## Validation

```bash
python scripts/validate_parametric_template.py examples/parametric_templates/
```

Individual files:

```bash
python scripts/validate_parametric_template.py examples/parametric_templates/valid_read_template.json
```
