# threshold_scalar_basic

Basic scalar threshold adapter example for CORE.

This example demonstrates the minimal Sensor Evidence pattern:

```text
scalar signal -> threshold crossing -> ObservationEvent -> validate -> certify -> compliance
```

It also includes a hysteresis variant to show how a stable state can be
derived from a signal that oscillates around the threshold.

## Fixtures

- `threshold_scalar_basic_v1`
- `hysteresis_v1`

## Generate

```bash
python examples/adapters/threshold_scalar_basic/generate_fixture.py --scenario all
```

## Validate

```bash
python scripts/validate_sensor_manifest.py examples/adapters/threshold_scalar_basic/fixtures/threshold_scalar_basic_v1
python scripts/validate_sensor_manifest.py examples/adapters/threshold_scalar_basic/fixtures/hysteresis_v1
```

## Certify

```bash
python scripts/certify_sensor_fixture.py examples/adapters/threshold_scalar_basic/fixtures/threshold_scalar_basic_v1
python scripts/certify_sensor_fixture.py examples/adapters/threshold_scalar_basic/fixtures/hysteresis_v1
```

## Compliance

```bash
python scripts/check_adapter_compliance.py examples/adapters/threshold_scalar_basic
```

## Scope

- Offline fixture only.
- No live sensors.
- No hardware.
- No GPU.
- No runtime mutation.
