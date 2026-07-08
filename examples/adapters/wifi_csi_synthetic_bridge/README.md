# wifi_csi_synthetic_bridge

Synthetic CSI-like bridge example for CORE.

This adapter demonstrates how WiFi-CSI-like aggregate features can be
represented as deterministic Sensor Evidence without using real WiFi hardware.

The flow is:

```text
synthetic CSI-like features -> samples.csv -> ObservationEvent
```

## Fixture

* `wifi_csi_synthetic_v1`

## What it generates

The fixture contains 100 synthetic frames with aggregate features:

* `subcarrier_mean_amplitude`
* `subcarrier_amplitude_variance`
* `phase_delta`
* `motion_score`

A deterministic synthetic disturbance is introduced in the middle of the
sequence. The `motion_score` crosses the configured threshold during that
disturbance window.

## Generate

```bash
python examples/adapters/wifi_csi_synthetic_bridge/generate_fixture.py
```

## Validate

```bash
python scripts/validate_sensor_manifest.py \
  examples/adapters/wifi_csi_synthetic_bridge/fixtures/wifi_csi_synthetic_v1
```

## Certify

```bash
python scripts/certify_sensor_fixture.py \
  examples/adapters/wifi_csi_synthetic_bridge/fixtures/wifi_csi_synthetic_v1
```

## Compliance

```bash
python scripts/check_adapter_compliance.py examples/adapters/wifi_csi_synthetic_bridge
```

## Explicit boundaries

This example is:

* synthetic only;
* offline only;
* deterministic;
* an aggregate feature fixture;
* not RuView integration;
* not real WiFi sensing.

This example does not:

* use WiFi hardware;
* capture packets;
* read network interfaces;
* use external CSI datasets;
* detect humans;
* infer presence;
* localize movement;
* classify gestures;
* make real sensing claims;
* use ML models;
* use GPU/Kaggle;
* mutate runtime.
