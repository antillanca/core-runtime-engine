# audio_envelope_wav

Synthetic audio envelope adapter example for CORE.

This adapter demonstrates how a deterministic synthetic WAV file can be
converted into Sensor Evidence.

The flow is:

```text
synthetic WAV -> RMS envelope windows -> samples.csv -> ObservationEvent
```

## Fixture

- `audio_envelope_wav_v1`

## Signal

The generated WAV is:

- mono
- 16-bit PCM
- 8000 Hz
- 1 second
- generated with Python stdlib
- deterministic byte for byte

The amplitude is low at the beginning and end, and higher in the middle. The
RMS envelope crosses the configured threshold during the high-amplitude region.

## Generate

```bash
python examples/adapters/audio_envelope_wav/generate_fixture.py
```

## Validate

```bash
python scripts/validate_sensor_manifest.py examples/adapters/audio_envelope_wav/fixtures/audio_envelope_wav_v1
```

## Certify

```bash
python scripts/certify_sensor_fixture.py examples/adapters/audio_envelope_wav/fixtures/audio_envelope_wav_v1
```

## Compliance

```bash
python scripts/check_adapter_compliance.py examples/adapters/audio_envelope_wav
```

## Scope

- Offline fixture only.
- Synthetic audio only.
- No microphone.
- No live audio.
- No speech recognition.
- No ML model.
- No external dataset.
- No GPU/Kaggle dependency.
- No runtime mutation.
