"""
SkyGuard AI — core entry point (v2, fresh start)
================================================
Static replay: read datasets from ../data/, run Layer 1 physics (per row),
Layer 2 ML (per batch) and Layer 4 forecasting (sliding window) from
../layers_v2/.

Layers exchange plain Python dicts per the AGENTS.md payload contract;
core is the only place DataFrames/parquet exist.

A test layer (config.RUN_TEST) runs L1+L2(+L4) on the injected evaluation
dataset and compares flags against the is_anomaly ground-truth labels.

Run from microservices/app/core:
    python main.py

Which dataset and how many rows are controlled by variables in config.py.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Make imports work when run from anywhere under microservices/app/core.
APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

import config  # noqa: E402
from layers_v2.ml import FEATURES, isolation_forest_shap, train_ml_model  # noqa: E402
from layers_v2.physics import evaluate_physics  # noqa: E402

# Columns that describe the station, not the sensor reading.
STATION_COLS = ["lat", "lon", "elevation_m"]

# Context window size for the L4 forecast (predictor used N=20).
FORECAST_CONTEXT = 20


def reading_from_row(row: pd.Series) -> dict:
    """Build the L1 `reading` payload from a dataframe row."""
    return {
        "timestamp": str(row["timestamp"]),
        "station_id": row["station_id"],
        "temp_c": row["temp_c"],
        "pressure_hpa": row["pressure_hpa"],
        "humidity_pct": row["humidity_pct"],
    }


def station_from_row(row: pd.Series) -> dict:
    """Build the L1 `station` payload from a dataframe row."""
    return {col: row[col] for col in STATION_COLS}


def run_static(parquet_path: Path, label: str) -> None:
    print(f"[core] loading {label}: {parquet_path}")
    df = pd.read_parquet(parquet_path)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df = df.head(config.ROW_LIMIT)
    readings = [reading_from_row(row) for _, row in df.iterrows()]
    print(f"[core] {len(readings)} readings to evaluate (limit={config.ROW_LIMIT})")

    # --- Layer 2: train once on the clean baseline -------------------------
    clean_df = pd.read_parquet(config.CLEAN_PARQUET)
    clean_readings = [reading_from_row(row) for _, row in clean_df.iterrows()]
    print("[core] training L2 IsolationForest on clean baseline …")
    model, explainer = train_ml_model(clean_readings)
    print("[core] L2 model ready")

    # Layer 2 runs on the whole batch.
    l2_payloads = isolation_forest_shap(readings, model, explainer, FEATURES)

    # --- Layer 1: per-row physics -----------------------------------------
    l1_flags = []
    for i, (row, reading) in enumerate(zip(df.iterrows(), readings)):
        r = evaluate_physics(reading, station=station_from_row(row[1]))
        l1_flags.append(r["predicted_anomaly"])
        l2_anom = l2_payloads[i]["predicted_anomaly"]
        if r["predicted_anomaly"] or l2_anom:
            print(
                f"  [{i}] {reading['station_id']} {reading['timestamp']} "
                f"L1={r['predicted_anomaly']} L2={l2_anom} "
                f"L1_sensors={r['affected_sensors']} "
                f"L2_sensor={l2_payloads[i]['checks']['shap']['blamed_feature']}"
            )

    l1_count = sum(l1_flags)
    l2_count = sum(1 for p in l2_payloads if p["predicted_anomaly"])
    combined = sum(1 for a, p in zip(l1_flags, l2_payloads) if a or p["predicted_anomaly"])
    print(
        f"[core] done — L1 flagged {l1_count}/{len(readings)} rows, "
        f"L2 flagged {l2_count}/{len(readings)} rows, combined {combined}"
    )


def run_l3_frozen_payloads(df: pd.DataFrame) -> list:
    """
    Run L3 over the eval window: slide a window per station and check
    the last reading for frozen sensors. Returns the L3 payload dicts
    for each scored window (timestamp = window's last reading).
    Deterministic + cheap, so no limit is needed.
    """
    from layers_v2.frozen import MIN_WINDOW_LEN, evaluate_frozen

    df = df.sort_values(["station_id", "timestamp"]).reset_index(drop=True)
    payloads = []
    for station in df["station_id"].unique():
        sdf = df[df["station_id"] == station].reset_index(drop=True)
        for i in range(len(sdf) - MIN_WINDOW_LEN):
            window_readings = [
                reading_from_row(row)
                for _, row in sdf.iloc[i : i + MIN_WINDOW_LEN + 1].iterrows()
            ]
            payloads.append(evaluate_frozen(window_readings))
    return payloads


def run_l4_forecast_payloads(pipeline, df: pd.DataFrame) -> list:
    """
    Run L4 over the eval window: slide a context window per station and
    forecast the next reading. Returns the L4 payload dicts for each
    scored window (capped by config.FORECAST_LIMIT).
    """
    from layers_v2.forecasting import forecast_reading

    df = df.sort_values(["station_id", "timestamp"]).reset_index(drop=True)
    payloads = []
    for station in df["station_id"].unique():
        sdf = df[df["station_id"] == station].reset_index(drop=True)
        for i in range(len(sdf) - FORECAST_CONTEXT - 1):
            window_readings = [
                reading_from_row(row)
                for _, row in sdf.iloc[i : i + FORECAST_CONTEXT + 1].iterrows()
            ]
            payloads.append(
                forecast_reading(pipeline, window_readings, n_context=FORECAST_CONTEXT)
            )
            if len(payloads) >= config.FORECAST_LIMIT:
                return payloads
    return payloads


def test_layer(parquet_path: Path) -> None:
    """
    Test layer: run the full pipeline (L1-L6) on the injected evaluation
    dataset and measure it against ALL three ground-truth axes:
      1. Detection      — is_anomaly (does any layer / fusion flag it?)
      2. Sensor type    — affected_sensor (do we blame the right sensor?)
      3. Fault type     — anomaly_type (do we classify the fault right?)
    Reporting is F2/precision-at-recall friendly (idea-pitch/02-thresholds.md):
    the dataset is ~98% normal, so raw accuracy would be misleading.
    """
    print(f"[test] loading evaluation dataset: {parquet_path}")

    clean_df = pd.read_parquet(config.CLEAN_PARQUET)
    clean_readings = [reading_from_row(row) for _, row in clean_df.iterrows()]
    print("[test] training L2 IsolationForest on clean baseline …")
    model, explainer = train_ml_model(clean_readings)
    print("[test] L2 model ready")

    df = pd.read_parquet(parquet_path)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df = df.head(config.TEST_ROW_LIMIT)
    readings = [reading_from_row(row) for _, row in df.iterrows()]
    print(f"[test] {len(readings)} readings (limit={config.TEST_ROW_LIMIT})")

    gt = df["is_anomaly"].astype(int).to_numpy()

    # --- Run every layer ----------------------------------------------------
    # L2 ML (batch).
    l2_payloads = isolation_forest_shap(readings, model, explainer, FEATURES)
    l2_preds = np.array([1 if p["predicted_anomaly"] else 0 for p in l2_payloads])

    # L2 gap (dropout) — deterministic, cheap.
    from layers_v2.gap import detect_gaps

    gap_payloads = detect_gaps(readings)
    gap_preds = np.array([1 if p["predicted_anomaly"] else 0 for p in gap_payloads])

    # L1 (per row).
    l1_payloads = []
    for reading, (_, row) in zip(readings, df.iterrows()):
        r = evaluate_physics(reading, station=station_from_row(row))
        l1_payloads.append(r)
    l1_preds = np.array([1 if p["predicted_anomaly"] else 0 for p in l1_payloads])

    # L3 (frozen) — deterministic, runs over every window.
    print("[test] running L3 frozen checks …")
    l3_payloads = run_l3_frozen_payloads(df)
    l3_map = {(p["station_id"], p["timestamp"]): p for p in l3_payloads}
    l3_preds = np.array(
        [
            1 if l3_map.get((row["station_id"], str(row["timestamp"])), {}).get("predicted_anomaly") else 0
            for _, row in df.iterrows()
        ]
    )

    # L4 (forecasting) — optional, needs Chronos-2.
    l4_payloads = None
    if config.RUN_FORECAST:
        from chronos import Chronos2Pipeline

        print("[test] loading Chronos-2 pipeline (first run downloads the model) …")
        pipeline = Chronos2Pipeline.from_pretrained("amazon/chronos-2")
        print("[test] pipeline ready — running L4 forecasts …")
        l4_payloads = run_l4_forecast_payloads(pipeline, df)
        print(f"[test] L4 scored {len(l4_payloads)} windows (limit={config.FORECAST_LIMIT})")
    l4_map = (
        {(p["station_id"], p["timestamp"]): p for p in l4_payloads}
        if l4_payloads else {}
    )
    l4_preds = np.array(
        [
            1 if l4_map.get((row["station_id"], str(row["timestamp"])), {}).get("predicted_anomaly") else 0
            for _, row in df.iterrows()
        ]
    )

    # L5 (spatial context) — never flags; shows neighbour agreement.
    from layers_v2.spatial import evaluate_spatial

    stations_meta = {}
    for _, row in df.iterrows():
        stations_meta[row["station_id"]] = {
            "lat": row["lat"], "lon": row["lon"], "elevation_m": row["elevation_m"],
        }
    l5_payloads = []
    for ts, group in df.groupby("timestamp"):
        snap_readings = [reading_from_row(row) for _, row in group.iterrows()]
        l5_payloads.extend(evaluate_spatial(snap_readings, stations_meta))
    l5_disagree = sum(
        1 for p in l5_payloads
        if p["checks"]["spatial"].get("temp_agree") is False
        or p["checks"]["spatial"].get("pressure_agree") is False
    )
    print(f"[test] L5 spatial: {l5_disagree} rows where neighbours disagree (context for L6)")

    # L6 fusion.
    from layers_v2.fusion import fuse

    fused_payloads = fuse(
        l1=l1_payloads,
        l2=l2_payloads,
        l2_gap=gap_payloads,
        l3=l3_payloads,
        l4=l4_payloads,
        l5=l5_payloads,
    )
    fused_map = {(p["station_id"], p["timestamp"]): p for p in fused_payloads}
    fused_preds = np.array(
        [
            1 if fused_map.get((row["station_id"], str(row["timestamp"])), {}).get("predicted_anomaly") else 0
            for _, row in df.iterrows()
        ]
    )

    # --- 1) Detection report (per layer + fusion) ---------------------------
    print("\n┌─────────── 1) Detection vs is_anomaly ───────────┐")
    rows = [("L1 Physics", l1_preds), ("L2 Gap", gap_preds), ("L2 ML", l2_preds),
            ("L3 Frozen", l3_preds)]
    if l4_payloads:
        rows.append(("L4 Forecast", l4_preds))
    rows.append(("L6 Fusion", fused_preds))
    for name, preds in rows:
        tp = int(((preds == 1) & (gt == 1)).sum())
        fp = int(((preds == 1) & (gt == 0)).sum())
        fn = int(((preds == 0) & (gt == 1)).sum())
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f2 = (5 * precision * recall) / (4 * precision + recall) if (4 * precision + recall) else 0.0
        print(f"│ {name:<10} TP={tp:<4} FP={fp:<4} FN={fn:<4} "
              f"prec={precision:.3f} rec={recall:.3f} F2={f2:.3f}")
    print(f"└{'─' * 44}┘")

    # --- 2) Sensor-type attribution (only on true anomalies) ----------------
    # Ground truth affected_sensor may be a single sensor, a pair
    # (temp_humidity), or all_sensors; compare the fused affected set.
    print("\n┌─── 2) Sensor attribution vs affected_sensor (anomalies) ───┐")
    _report_sensor_attribution(df, fused_map, gt)
    print(f"└{'─' * 50}┘")

    # --- 3) Fault-type classification (fused verdict vs anomaly_type) ------
    print("\n┌──────── 3) Fault classification vs anomaly_type ────────┐")
    _report_fault_classification(df, fused_map, gt)
    print(f"└{'─' * 50}┘")

    print(f"\n[test] done — {len(df)} rows, {int(gt.sum())} true anomalies in window")


def _gt_sensor_set(affected_sensor: str) -> set:
    """Ground-truth affected_sensor string -> set of sensor keys."""
    mapping = {
        "none": set(),
        "temp_c": {"temp_c"},
        "humidity_pct": {"humidity_pct"},
        "pressure_hpa": {"pressure_hpa"},
        "temp_humidity": {"temp_c", "humidity_pct"},
        "all_sensors": {"temp_c", "pressure_hpa", "humidity_pct"},
    }
    return mapping.get(affected_sensor, set())


def _report_sensor_attribution(df, fused_map, gt) -> None:
    """Compare fused affected_sensors vs ground truth on true-anomaly rows."""
    total = exact = overlap = 0
    per_sensor = {}  # gt_sensor -> {total, exact}
    for _, row in df[gt == 1].iterrows():
        fused = fused_map.get((row["station_id"], str(row["timestamp"])))
        if fused is None:
            continue
        gt_set = _gt_sensor_set(row["affected_sensor"])
        if not gt_set:
            continue
        pred_set = set(fused.get("affected_sensors", []))
        total += 1
        hit = bool(gt_set & pred_set)
        overlap += int(hit)
        exact += int(gt_set == pred_set)
        for s in gt_set:
            d = per_sensor.setdefault(s, {"total": 0, "exact": 0})
            d["total"] += 1
            d["exact"] += int(s in pred_set)
    if total == 0:
        print("│  no scored anomaly rows with a sensor label")
        return
    print(f"│  scored anomaly rows : {total}")
    print(f"│  sensor overlap hit  : {overlap} ({overlap/total:.3f})")
    print(f"│  exact set match     : {exact} ({exact/total:.3f})")
    for s, d in sorted(per_sensor.items()):
        print(f"│  {s:<16} caught {d['exact']}/{d['total']} "
              f"({d['exact']/d['total']:.3f})")


# Expected fused fault_type per injected anomaly_type (idea-pitch/06).
_EXPECTED_FAULT = {
    "spike": {"ml_anomaly", "physics", "forecast_deviation"},
    "gradual_drift": {"ml_anomaly", "forecast_deviation"},
    "noise_burst": {"ml_anomaly"},
    "barometric_altitude_inconsistency": {"physics"},
    "frozen_sensor": {"frozen_sensor"},
    "cross_sensor_decoupling": {"ml_anomaly"},
    "dropout_power_cut": {"gap"},
    "linear_dampened": {"frozen_sensor"},
}


def _report_fault_classification(df, fused_map, gt) -> None:
    """Compare fused fault_type vs expected set per anomaly_type."""
    total = correct = 0
    per_type = {}
    for _, row in df[gt == 1].iterrows():
        fused = fused_map.get((row["station_id"], str(row["timestamp"])))
        if fused is None:
            continue
        atype = row["anomaly_type"]
        expected = _EXPECTED_FAULT.get(atype, set())
        if not expected:
            continue
        fault_type = fused["checks"]["fusion"].get("fault_type")
        d = per_type.setdefault(atype, {"total": 0, "correct": 0})
        d["total"] += 1
        d["correct"] += int(fault_type in expected)
        total += 1
        correct += int(fault_type in expected)
    if total == 0:
        print("│  no scored anomaly rows with a classifiable type")
        return
    print(f"│  classified rows : {total} | correct fault_type: {correct} ({correct/total:.3f})")
    for atype, d in sorted(per_type.items()):
        print(f"│  {atype:<38} {d['correct']}/{d['total']} "
              f"({d['correct']/d['total']:.3f})")


def main() -> None:
    # Test layer first if enabled (it needs the eval labels).
    if config.RUN_TEST:
        test_layer(config.EVAL_PARQUET)
        return

    if config.DATASET == "eval":
        run_static(config.EVAL_PARQUET, "injected evaluation dataset")
    else:
        run_static(config.CLEAN_PARQUET, "clean baseline")


if __name__ == "__main__":
    main()