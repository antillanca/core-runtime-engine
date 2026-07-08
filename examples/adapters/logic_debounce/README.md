# logic_debounce

Digital debounce adapter example for CORE.

This example demonstrates how to represent a noisy digital input and a stable
derived signal as Sensor Evidence.

The event is derived from `debounced_signal`, not `raw_signal`.

## Generate

```bash
python examples/adapters/logic_debounce/generate_fixture.py
```

## Validate

```bash
python scripts/validate_sensor_manifest.py examples/adapters/logic_debounce/fixtures/logic_debounce_v1
```

## Certify

```bash
python scripts/certify_sensor_fixture.py examples/adapters/logic_debounce/fixtures/logic_debounce_v1
```

## Compliance

```bash
python scripts/check_adapter_compliance.py examples/adapters/logic_debounce
```

## Scope

- Offline fixture only.
- No live hardware.
- No GPIO access.
- No GPU.
- No runtime mutation.
