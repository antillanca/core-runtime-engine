# Minimal Sensor Adapter

This is a minimal downstream-style adapter example for CORE v4.5.

It demonstrates how to produce an offline Sensor Evidence fixture without
touching `core_runtime/`.

## Generate fixture

```bash
python examples/adapters/minimal_sensor_adapter/generate_fixture.py
```

## Validate

```bash
python scripts/validate_sensor_manifest.py examples/adapters/minimal_sensor_adapter/fixtures/minimal_temperature_v1
```

## Certify

```bash
python scripts/certify_sensor_fixture.py examples/adapters/minimal_sensor_adapter/fixtures/minimal_temperature_v1
```

## Scope

This adapter:

- uses simulated temperature data
- requires no hardware
- requires no network
- requires no GPU
- does not modify runtime
- does not modify KnowledgeBase
- does not modify scheduler or replay semantics

## Purpose

This example is a template for forks and downstream adapters.
