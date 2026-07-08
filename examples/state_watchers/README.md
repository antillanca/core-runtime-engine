# State Watchers Example

This directory contains synthetic fixtures for CORE v7.1 state watchers
and business event derivation.

All data is synthetic. No real business data. No private domain references.

## Structure

- `registrations/` -- watcher registration fixtures
- `observations/` -- frozen scalar observation fixtures
- `derived_events/` -- deterministic derived events from watcher evaluation

## Usage

Validate a watcher registration:

```bash
python scripts/validate_state_watcher.py examples/state_watchers/registrations/valid_threshold_watcher.json
```

Derive business events from observations:

```bash
python scripts/derive_business_event.py   examples/state_watchers/registrations/valid_threshold_watcher.json   examples/state_watchers/observations/scalar_observations_v1
```

## Scope

- synthetic data only
- offline-only
- no hardware, network or GPU dependency
- no runtime mutation
- no private domain data

## References

- `docs/RFC_STATE_WATCHERS_AND_BUSINESS_EVENTS.md`
- `docs/CORE_ROADMAP.md` (v7.1 section)
- `schemas/state_watcher.schema.json`
- `schemas/business_event.schema.json`
