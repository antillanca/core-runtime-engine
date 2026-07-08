# multi_channel_environment

Multi-channel Sensor Evidence adapter example for CORE.

This example demonstrates a trace with multiple value keys:

- `temperature`
- `humidity`
- `pressure`

The `ObservationEvent` is derived only from `temperature`.

## Generate

```bash
python examples/adapters/multi_channel_environment/generate_fixture.py
```

## Validate

```bash
python scripts/validate_sensor_manifest.py examples/adapters/multi_channel_environment/fixtures/multi_channel_environment_v1
```

## Certify

```bash
python scripts/certify_sensor_fixture.py examples/adapters/multi_channel_environment/fixtures/multi_channel_environment_v1
```

## Compliance

```bash
python scripts/check_adapter_compliance.py examples/adapters/multi_channel_environment
```

## Scope

- Offline fixture only.
- No live sensors.
- No hardware.
- No GPU.
- No runtime mutation.
