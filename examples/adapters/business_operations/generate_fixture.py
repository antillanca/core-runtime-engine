from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core_runtime.core.sensor_evidence import (  # noqa: E402
    SensorSource,
    derive_threshold_observation_event,
    load_sensor_trace_csv,
)

ROOT = PROJECT_ROOT / "examples" / "adapters" / "business_operations"
SCENARIOS = {"sales_drop", "low_stock", "all"}


def _canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _write_sales_drop_samples(samples_csv: Path) -> None:
    samples_csv.parent.mkdir(parents=True, exist_ok=True)

    with samples_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["index", "logical_time", "daily_sales", "baseline_sales"],
        )
        writer.writeheader()

        for index in range(100):
            baseline_sales = 1000.0 + ((index % 7) * 10.0)
            if 70 <= index <= 85:
                daily_sales = 520.0 + ((index % 4) * 5.0)
            else:
                daily_sales = 940.0 + ((index % 9) * 12.0)

            writer.writerow(
                {
                    "index": index,
                    "logical_time": f"d{index:03d}",
                    "daily_sales": f"{daily_sales:.2f}",
                    "baseline_sales": f"{baseline_sales:.2f}",
                }
            )


def _write_low_stock_samples(samples_csv: Path) -> None:
    samples_csv.parent.mkdir(parents=True, exist_ok=True)

    with samples_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["index", "logical_time", "stock_units", "reorder_level"],
        )
        writer.writeheader()

        for index in range(100):
            stock_units = max(5.0, 80.0 - (index * 0.9))
            reorder_level = 20.0

            writer.writerow(
                {
                    "index": index,
                    "logical_time": f"d{index:03d}",
                    "stock_units": f"{stock_units:.2f}",
                    "reorder_level": f"{reorder_level:.2f}",
                }
            )


def _build_manifest(
    *,
    fixture_id: str,
    samples_csv: Path,
    value_keys: list[str],
    value_key: str,
    threshold: float,
    sensor_id: str,
    trace_id: str,
    event_id: str,
    event_type: str,
    sensor_type: str,
    calibration_id: str,
    notes: list[str],
) -> dict[str, object]:
    samples_csv_rel = samples_csv.relative_to(PROJECT_ROOT)

    source = SensorSource(
        sensor_id=sensor_id,
        sensor_type=sensor_type,
        capture_mode="offline_fixture",
        calibration_id=calibration_id,
        environment_id="environment:business_operations_example",
    )

    trace = load_sensor_trace_csv(
        samples_csv_rel,
        trace_id=trace_id,
        source=source,
    )

    event = derive_threshold_observation_event(
        trace,
        event_id=event_id,
        event_type=event_type,
        value_key=value_key,
        threshold=threshold,
    )

    return {
        "fixture_id": fixture_id,
        "schema_version": "core.sensor_evidence.v1",
        "trace_id": trace_id,
        "sensor_id": sensor_id,
        "expected_trace_id": trace_id,
        "expected_sensor_id": sensor_id,
        "sensor_type": sensor_type,
        "capture_mode": "offline_fixture",
        "calibration_id": calibration_id,
        "environment_id": "environment:business_operations_example",
        "sample_count": 100,
        "value_keys": value_keys,
        "value_key": value_key,
        "threshold": threshold,
        "expected_event_type": event_type,
        "observation_event_id": event_id,
        "trace_fingerprint": trace.fingerprint(),
        "observation_event_fingerprints": {
            event.event_id: event.fingerprint(),
        },
        "notes": notes,
    }


def generate_sales_drop() -> Path:
    fixture_dir = ROOT / "fixtures" / "sales_drop_v1"
    samples_csv = fixture_dir / "samples.csv"
    manifest_json = fixture_dir / "manifest.json"

    _write_sales_drop_samples(samples_csv)

    manifest = _build_manifest(
        fixture_id="sales_drop_v1",
        samples_csv=samples_csv,
        value_keys=["baseline_sales", "daily_sales"],
        value_key="daily_sales",
        threshold=600.0,
        sensor_id="sensor:business_operations:sales:v1",
        trace_id="trace:business_operations:sales_drop:v1",
        event_id="event:business_operations:sales_drop:v1",
        event_type="sensor.business_operations.sales_drop",
        sensor_type="business_operations_sales",
        calibration_id="calibration:business_operations:sales:v1",
        notes=[
            "Synthetic business operations sales-drop example.",
            "Offline-only.",
            "No real business data.",
            "No runtime authority is granted to adapter data.",
        ],
    )

    manifest_json.write_text(_canonical_json(manifest), encoding="utf-8")
    return fixture_dir


def generate_low_stock() -> Path:
    fixture_dir = ROOT / "fixtures" / "low_stock_v1"
    samples_csv = fixture_dir / "samples.csv"
    manifest_json = fixture_dir / "manifest.json"

    _write_low_stock_samples(samples_csv)

    manifest = _build_manifest(
        fixture_id="low_stock_v1",
        samples_csv=samples_csv,
        value_keys=["reorder_level", "stock_units"],
        value_key="stock_units",
        threshold=20.0,
        sensor_id="sensor:business_operations:inventory:v1",
        trace_id="trace:business_operations:low_stock:v1",
        event_id="event:business_operations:low_stock:v1",
        event_type="sensor.business_operations.low_stock",
        sensor_type="business_operations_inventory",
        calibration_id="calibration:business_operations:inventory:v1",
        notes=[
            "Synthetic business operations low-stock example.",
            "Offline-only.",
            "No real inventory data.",
            "No runtime authority is granted to adapter data.",
        ],
    )

    manifest_json.write_text(_canonical_json(manifest), encoding="utf-8")
    return fixture_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate deterministic business operations fixtures."
    )
    parser.add_argument(
        "--scenario",
        choices=sorted(SCENARIOS),
        default="all",
        help="Scenario to generate.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    generated: list[Path] = []
    if args.scenario in {"sales_drop", "all"}:
        generated.append(generate_sales_drop())
    if args.scenario in {"low_stock", "all"}:
        generated.append(generate_low_stock())

    for fixture_dir in generated:
        rel = fixture_dir.relative_to(PROJECT_ROOT)
        print(f"Wrote fixture: {rel}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
