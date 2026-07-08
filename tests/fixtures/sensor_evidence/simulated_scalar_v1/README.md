# Simulated Scalar Sensor Fixture v1

This fixture contains 100 deterministic scalar samples for the v4.4 Sensor
Evidence Schema bootstrap.

It is not a live sensor capture.

The matching `manifest.json` records the offline-only contract, trace identity,
and expected value keys.

Purpose:

- validate SensorTrace serialization
- validate deterministic trace fingerprinting
- derive one ObservationEvent through a simple threshold rule
- allow StaticExplainer to explain a sensor-derived event structurally

Rules:

- do not mutate during tests
- do not treat as real-world evidence
- do not connect to runtime scheduling
