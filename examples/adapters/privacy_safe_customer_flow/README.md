# privacy_safe_customer_flow

Privacy-safe operational flow adapter example for CORE.

This example demonstrates how to create Sensor Evidence from synthetic,
privacy-safe customer-flow data without exposing raw PII.

## Privacy rules

This example does not include:

- real emails
- real phone numbers
- real names
- real addresses
- raw personal identifiers
- secrets
- connection strings

Synthetic customer IDs are hashed with SHA-256 and reduced to stable numeric
codes before they appear in the fixture.

## Generate

```bash
python examples/adapters/privacy_safe_customer_flow/generate_fixture.py
```

## Validate

```bash
python scripts/validate_sensor_manifest.py examples/adapters/privacy_safe_customer_flow/fixtures/privacy_safe_customer_flow_v1
```

## Certify

```bash
python scripts/certify_sensor_fixture.py examples/adapters/privacy_safe_customer_flow/fixtures/privacy_safe_customer_flow_v1
```

## Compliance

```bash
python scripts/check_adapter_compliance.py examples/adapters/privacy_safe_customer_flow
```

## Scope

* Offline fixture only.
* Synthetic data only.
* No real PII.
* No live database.
* No secrets.
* No GPU.
* No runtime mutation.
