import sys
import time
import traceback
import requests
import json
import config
import numpy as np
import pandas as pd
from collections import deque
import shap
from sklearn.ensemble import IsolationForest

# run from core
sys.path.insert(0, "../layers/forecasting")
from predictor import predict
from chronos import Chronos2Pipeline


# ── ML layer (inlined from ml_code.py — original file untouched) ─────
def isolation_forest_shap(batch_df, model, explainer, features):
    result_df = pd.DataFrame()
    result_df["time"] = batch_df["timestamp"]
    result_df["station_id"] = batch_df["station_id"]
    result_df["predicted_anomaly"] = 0
    result_df["sensor_type"] = None
    result_df["anomaly_value"] = np.nan
    result_df["anomaly_reason"] = None
    result_df["expected_cause"] = "Multivariate deviation from historical baseline"
    result_df["recommended_action"] = (
        "Check blamed sensor for calibration drift or transient faults"
    )
    result_df["layer_used"] = "Layer 2: ML (Isolation Forest + SHAP)"

    batch_features = batch_df[features]
    predictions = model.predict(batch_features)

    anom_idx = batch_df.index[predictions == -1]

    if not anom_idx.empty:
        result_df.loc[anom_idx, "predicted_anomaly"] = 1
        shap_values = explainer.shap_values(batch_df.loc[anom_idx, features])

        for i, idx in enumerate(anom_idx):
            row_shap_values = shap_values[i]
            top_feature_idx = np.argmax(np.abs(row_shap_values))
            blamed_feature = features[top_feature_idx]

            result_df.loc[idx, "sensor_type"] = blamed_feature
            result_df.loc[idx, "anomaly_value"] = batch_df.loc[idx, blamed_feature]
            result_df.loc[idx, "anomaly_reason"] = (
                f"SHAP flagged '{blamed_feature}' as primary driver of the multivariate anomaly."
            )

    return result_df


# ── Model ────────────────────────────────────────────────────────────
print("[core] loading Chronos-2 pipeline …")
pipeline = Chronos2Pipeline.from_pretrained("amazon/chronos-2")
print("[core] pipeline ready")

# ── Sliding-window buffer ────────────────────────────────────────────
# predict() needs N context rows + 1 actual row  →  21 total
CONTEXT_LEN = 20
BUFFER_SIZE = CONTEXT_LEN + 1
buffer = deque(maxlen=BUFFER_SIZE)

# ── Latency / throughput metrics ─────────────────────────────────────
STATS_EVERY = 10  # print a summary every N predictions


class Metrics:
    def __init__(self):
        self.last_arrival = None  # wall-clock time of previous reading
        self.inference_times = []  # seconds per predict() call
        self.arrival_gaps = []  # seconds between consecutive readings
        self.drift_times = (
            []
        )  # arrival_gap − inference_time (negative = falling behind)
        self.total_readings = 0
        self.total_predictions = 0
        self.dropped = 0  # readings that arrived while we were inferring

    def record_arrival(self):
        now = time.perf_counter()
        if self.last_arrival is not None:
            self.arrival_gaps.append(now - self.last_arrival)
        self.last_arrival = now
        self.total_readings += 1

    def record_inference(self, elapsed: float):
        self.inference_times.append(elapsed)
        self.total_predictions += 1
        # drift = how much longer inference took vs the arrival gap
        if self.arrival_gaps:
            gap = self.arrival_gaps[-1]
            self.drift_times.append(elapsed - gap)

    def should_report(self) -> bool:
        return self.total_predictions > 0 and self.total_predictions % STATS_EVERY == 0

    def report(self) -> str:
        n = len(self.inference_times)
        if n == 0:
            return ""

        inf = self.inference_times
        avg_inf = sum(inf) / n
        min_inf = min(inf)
        max_inf = max(inf)

        lines = [
            f"┌──────────── scalability report  (after {self.total_predictions} predictions) ────────────┐",
            f"│  readings received   : {self.total_readings}",
            f"│  predictions made    : {self.total_predictions}",
            f"│  inference  avg/min/max : {avg_inf*1000:7.1f} / {min_inf*1000:7.1f} / {max_inf*1000:7.1f}  ms",
        ]

        if self.arrival_gaps:
            gaps = self.arrival_gaps
            avg_gap = sum(gaps) / len(gaps)
            lines.append(
                f"│  arrival gap avg     : {avg_gap*1000:7.1f} ms   (stream interval)"
            )
            throughput = 1.0 / avg_inf if avg_inf > 0 else float("inf")
            stream_rate = 1.0 / avg_gap if avg_gap > 0 else float("inf")
            lines.append(
                f"│  throughput          : {throughput:7.1f} pred/s   vs  stream {stream_rate:.1f} msg/s"
            )

            if self.drift_times:
                avg_drift = sum(self.drift_times) / len(self.drift_times)
                if avg_drift > 0:
                    lines.append(
                        f"│  ⚠ avg drift        : +{avg_drift*1000:.1f} ms   (inference SLOWER than stream)"
                    )
                else:
                    lines.append(
                        f"│  ✓ avg drift        : {avg_drift*1000:.1f} ms   (inference faster than stream)"
                    )

        lines.append("└" + "─" * 72 + "┘")
        return "\n".join(lines)

    def reset_window(self):
        """Reset rolling stats but keep totals."""
        self.inference_times.clear()
        self.arrival_gaps.clear()
        self.drift_times.clear()


metrics = Metrics()


def process_data(data: dict) -> dict | None:
    """
    Append one sensor reading to the sliding window.
    Once the window is full (21 readings), build a DataFrame from the
    last 21 readings and run the Chronos-2 forecast + anomaly check.

    Returns the prediction payload when a forecast is made, else None.
    """
    metrics.record_arrival()
    buffer.append(data["reading"])

    if len(buffer) < BUFFER_SIZE:
        print(f"[core] buffering … {len(buffer)}/{BUFFER_SIZE}")
        return None

    df = pd.DataFrame(list(buffer))

    # Stream sends "id" — rename to match ml_code expectations
    if "id" in df.columns and "station_id" not in df.columns:
        df.rename(columns={"id": "station_id"}, inplace=True)

    # Derive "hour" feature from timestamp (ML model was trained with it)
    df["hour"] = pd.to_datetime(df["timestamp"]).dt.hour

    t0 = time.perf_counter()

    try:
        ml_layer = isolation_forest_shap(
            batch_df=df,
            model=data["ml"]["isolation_forest"],
            explainer=data["ml"]["explainer"],
            features=data["ml"]["features"],
        )
        forecasting_layer = predict(pipeline=pipeline, df=df)
    except Exception as e:
        traceback.print_exc()
        print(f"[core] prediction error: {e}")
        return None
    elapsed = time.perf_counter() - t0

    metrics.record_inference(elapsed)

    # Summarize ML layer results
    ml_anomalies = ml_layer["predicted_anomaly"].sum()
    ml_sensors = (
        ml_layer.loc[ml_layer["predicted_anomaly"] == 1, "sensor_type"]
        .unique()
        .tolist()
    )
    fc_status = forecasting_layer["is_anomaly"]
    fc_sensors = forecasting_layer["sensors"]

    is_anomaly = ml_anomalies > 0 or fc_status
    all_sensors = list(set(ml_sensors + fc_sensors))
    status = "🔴 ANOMALY" if is_anomaly else "🟢 normal"
    sensor_str = ", ".join(all_sensors) if all_sensors else "—"
    print(
        f"[core] {status}  sensors={sensor_str}  ml_hits={ml_anomalies} fc_layer={str(fc_sensors)}  inference={elapsed*1000:.1f}ms"
    )

    # Print scalability report periodically
    if metrics.should_report():
        print(metrics.report())
        metrics.reset_window()


# ── Shared: train ML model on clean baseline ─────────────────────────
CLEAN_PARQUET = "../seeds/data/raw/aws_clean_baseline.parquet"
EVAL_PARQUET = "../seeds/aws_evaluation_dataset.parquet"
ML_FEATURES = ["temp_c", "pressure_hpa", "humidity_pct", "hour"]


def _train_ml_model():
    """Train IsolationForest on the clean baseline and return (model, explainer, features)."""
    df = pd.read_parquet(CLEAN_PARQUET)
    df["hour"] = pd.to_datetime(df["timestamp"]).dt.hour

    model = IsolationForest(n_estimators=100, contamination=0.01, random_state=42)
    print("[model] training IsolationForest on clean baseline …")
    model.fit(df[ML_FEATURES])
    print("[model] training complete")

    explainer = shap.TreeExplainer(model)
    print("[model] SHAP explainer ready")
    return model, explainer, ML_FEATURES


# ── Accuracy check ───────────────────────────────────────────────────
def _confusion(y_true, y_pred):
    """Return (TP, FP, TN, FN) from boolean/int arrays."""
    tp = int(((y_true == 1) & (y_pred == 1)).sum())
    fp = int(((y_true == 0) & (y_pred == 1)).sum())
    tn = int(((y_true == 0) & (y_pred == 0)).sum())
    fn = int(((y_true == 1) & (y_pred == 0)).sum())
    return tp, fp, tn, fn


def _print_metrics(name, tp, fp, tn, fn):
    total = tp + fp + tn + fn
    accuracy = (tp + tn) / total if total else 0
    precision = tp / (tp + fp) if (tp + fp) else 0
    recall = tp / (tp + fn) if (tp + fn) else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0

    print(f"\n┌─────────────── {name} ───────────────┐")
    print(f"│  Total samples : {total}")
    print(f"│  TP / FP       : {tp:>5} / {fp:<5}")
    print(f"│  TN / FN       : {tn:>5} / {fn:<5}")
    print(f"│  Accuracy      : {accuracy:.4f}")
    print(f"│  Precision     : {precision:.4f}")
    print(f"│  Recall        : {recall:.4f}")
    print(f"│  F1 Score      : {f1:.4f}")
    print(f"└{'─' * 42}┘")


def run_accuracy_check():
    """
    Slide a window of BUFFER_SIZE over the evaluation dataset.
    At each step, run both layers and compare predictions to ground truth.
    """
    model, explainer, features = _train_ml_model()

    print("\n[eval] loading evaluation dataset …")
    df_eval = pd.read_parquet(EVAL_PARQUET)
    df_eval = df_eval.sort_values("timestamp").reset_index(drop=True)

    # Rename "id" → "station_id" if needed
    if "id" in df_eval.columns and "station_id" not in df_eval.columns:
        df_eval.rename(columns={"id": "station_id"}, inplace=True)

    df_eval["hour"] = pd.to_datetime(df_eval["timestamp"]).dt.hour

    # Pick one station to evaluate sequentially (same as live ingestion)
    stations = df_eval["station_id"].unique()
    print(f"[eval] stations available: {list(stations)}")
    station_id = stations[0]
    df_station = df_eval[df_eval["station_id"] == station_id].reset_index(drop=True)
    print(f"[eval] evaluating station '{station_id}' — {len(df_station)} rows")

    # Drop rows with NaN in sensor columns (dropout anomalies)
    sensor_cols = ["temp_c", "pressure_hpa", "humidity_pct"]
    valid_mask = df_station[sensor_cols].notna().all(axis=1)
    df_station = df_station[valid_mask].reset_index(drop=True)
    print(f"[eval] after dropping NaN rows: {len(df_station)} rows")

    n_windows = len(df_station) - BUFFER_SIZE
    if n_windows <= 0:
        print("[eval] not enough data for even one window")
        return

    # Storage for per-row predictions
    gt_labels = []          # ground truth: 1 = anomaly, 0 = normal
    ml_preds = []           # ML layer prediction for the last row
    fc_preds = []           # forecasting layer prediction for the last row
    combined_preds = []     # either layer flagged it

    print(f"[eval] sliding {n_windows} windows (buffer={BUFFER_SIZE}) …\n")

    t_start = time.perf_counter()
    for i in range(n_windows):
        window = df_station.iloc[i : i + BUFFER_SIZE].copy()
        window = window.reset_index(drop=True)

        # Ground truth for the last (newest) row
        last_row = window.iloc[-1]
        gt = int(last_row.get("is_anomaly", 0))
        gt_labels.append(gt)

        # ── ML layer ─────────────────────────────────────────────────
        try:
            ml_result = isolation_forest_shap(
                batch_df=window, model=model, explainer=explainer, features=features
            )
            # Check if the last row was flagged
            ml_flag = int(ml_result.iloc[-1]["predicted_anomaly"])
        except Exception:
            ml_flag = 0
        ml_preds.append(ml_flag)

        # ── Forecasting layer ────────────────────────────────────────
        try:
            fc_result = predict(pipeline=pipeline, df=window)
            fc_flag = 1 if fc_result["is_anomaly"] else 0
        except Exception:
            fc_flag = 0
        fc_preds.append(fc_flag)

        # ── Combined ─────────────────────────────────────────────────
        combined_preds.append(1 if (ml_flag or fc_flag) else 0)

        # Progress
        if (i + 1) % 50 == 0 or i == n_windows - 1:
            elapsed = time.perf_counter() - t_start
            rate = (i + 1) / elapsed
            print(f"  [{i+1}/{n_windows}]  {rate:.1f} windows/s  "
                  f"gt_anom={sum(gt_labels)}  ml_det={sum(ml_preds)}  fc_det={sum(fc_preds)}")

    # ── Results ──────────────────────────────────────────────────────
    gt = np.array(gt_labels)
    ml = np.array(ml_preds)
    fc = np.array(fc_preds)
    cb = np.array(combined_preds)

    _print_metrics("ML Layer (IsolationForest + SHAP)", *_confusion(gt, ml))
    _print_metrics("Forecasting Layer (Chronos-2)", *_confusion(gt, fc))
    _print_metrics("Combined (ML ∪ Forecasting)", *_confusion(gt, cb))

    total_time = time.perf_counter() - t_start
    print(f"\n[eval] done — {n_windows} windows in {total_time:.1f}s "
          f"({n_windows/total_time:.1f} windows/s)")


# ── Static ingestion (quick test on clean data) ──────────────────────
def static_ingestion():
    model, explainer, features = _train_ml_model()
    df = pd.read_parquet(CLEAN_PARQUET)
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Pick first station
    station_id = df["station_id"].unique()[0]
    df_station = df[df["station_id"] == station_id].reset_index(drop=True)

    n_rows = min(1000, len(df_station))
    print(f"[static] running {n_rows} rows from station '{station_id}' …")

    buffer.clear()
    for i in range(n_rows):
        row = df_station.iloc[i].to_dict()
        data = {
            "reading": row,
            "ml": {
                "isolation_forest": model,
                "explainer": explainer,
                "features": features,
            },
        }
        process_data(data)


# ── Stream ingestion ─────────────────────────────────────────────────
def start_ingestion():
    model, explainer, features = _train_ml_model()

    stream_url = f"{config.SENSOR_URL}/v1/sensor/injected/HYD001"
    print(f"[core] connecting to {stream_url}")

    try:
        with requests.get(stream_url, stream=True) as response:
            response.raise_for_status()
            print("[core] stream connected ✓")

            for line in response.iter_lines():
                if not line:
                    continue

                decoded_line = line.decode("utf-8").strip()
                if not decoded_line:
                    continue

                try:
                    reading = json.loads(decoded_line)
                    data = {
                        "reading": reading,
                        "ml": {
                            "isolation_forest": model,
                            "explainer": explainer,
                            "features": features,
                        },
                    }
                    process_data(data)
                except json.JSONDecodeError:
                    print(f"[core] skipped malformed JSON: {decoded_line[:80]}")

    except requests.exceptions.RequestException as e:
        print(f"[core] stream connection failed: {e}")


# ── CLI ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Sky-Guard-AI Core Engine")
    parser.add_argument(
        "mode",
        nargs="?",
        default="stream",
        choices=["stream", "static", "accuracy"],
        help="stream = live sensor stream (default), "
             "static = offline test on clean data, "
             "accuracy = evaluate both layers on clean + eval parquets",
    )
    args = parser.parse_args()

    if args.mode == "accuracy":
        run_accuracy_check()
    elif args.mode == "static":
        static_ingestion()
    else:
        start_ingestion()

