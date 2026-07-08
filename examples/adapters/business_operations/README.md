# business_operations

Synthetic business operations adapter example for CORE.

This adapter demonstrates how generic operational data can produce multiple
offline Sensor Evidence fixtures without touching the runtime.

It intentionally does not use real business data or any product-specific name.

## Scenarios

- `sales_drop_v1`: daily sales drop event.
- `low_stock_v1`: inventory low-stock event.

## Generate

Generate all fixtures:

```bash
python examples/adapters/business_operations/generate_fixture.py --scenario all
```

Generate only sales drop:

```bash
python examples/adapters/business_operations/generate_fixture.py --scenario sales_drop
```

Generate only low stock:

```bash
python examples/adapters/business_operations/generate_fixture.py --scenario low_stock
```

## Validate

```bash
python scripts/validate_sensor_manifest.py examples/adapters/business_operations/fixtures/sales_drop_v1
python scripts/validate_sensor_manifest.py examples/adapters/business_operations/fixtures/low_stock_v1
```

## Certify

```bash
python scripts/certify_sensor_fixture.py examples/adapters/business_operations/fixtures/sales_drop_v1
python scripts/certify_sensor_fixture.py examples/adapters/business_operations/fixtures/low_stock_v1
```

## Compliance

```bash
python scripts/check_adapter_compliance.py examples/adapters/business_operations
```

## Scope

* Offline fixture only.
* Synthetic data only.
* No real business data.
* No live database.
* No secrets.
* No PII.
* No GPU.
* No runtime mutation.
