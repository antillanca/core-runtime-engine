# image_brightness_motion

Synthetic image brightness/motion adapter example for CORE.

This adapter demonstrates how deterministic synthetic image frames can be
converted into Sensor Evidence.

The flow is:

```text
synthetic PGM frames -> brightness/delta metrics -> samples.csv -> ObservationEvent
```

## Fixture

- `image_brightness_motion_v1`

## Frames

The generated frames are:

- PGM P5 binary grayscale
- 32x32 pixels
- 10 frames
- generated with Python stdlib
- deterministic byte for byte

Frames 4-6 contain a bright central block, creating a deterministic frame delta
spike.

## Generate

```bash
python examples/adapters/image_brightness_motion/generate_fixture.py
```

## Validate

```bash
python scripts/validate_sensor_manifest.py examples/adapters/image_brightness_motion/fixtures/image_brightness_motion_v1
```

## Certify

```bash
python scripts/certify_sensor_fixture.py examples/adapters/image_brightness_motion/fixtures/image_brightness_motion_v1
```

## Compliance

```bash
python scripts/check_adapter_compliance.py examples/adapters/image_brightness_motion
```

## Scope

- Offline fixture only.
- Synthetic frames only.
- No camera.
- No real images.
- No object detection.
- No OpenCV.
- No PIL/Pillow.
- No numpy.
- No ML model.
- No external dataset.
- No GPU/Kaggle dependency.
- No runtime mutation.
