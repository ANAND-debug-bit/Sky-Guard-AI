"""
Layer 4 — Forecasting (Chronos-2 corridor) (v2)
================================================
SkyGuard AI — microservices/app/layers_v2/forecasting.py

Design follows idea-pitch/01-architecture-and-layers.md (L4):
  amazon/chronos-2 (zero-shot, multivariate: T/P/RH fed jointly)
  forecasts the next reading as a p5/p50/p95 corridor; a breach is
  flagged when the actual value strays too far from the corridor.

Threshold logic reused from the reference predictor
  (microservices/app/layers/forecasting/predictor.py):
  - IQR-based severity threshold (Tukey fence, 1977)
  - MAD-based deviation threshold (Leys et al., 2013)

Input/output contract (see AGENTS.md):
  input : pipeline + plain list of reading dicts (last n_context+1 rows
          of ONE station, chronological)
  output: single unified payload dict
  The DataFrame is built inside and never crosses the boundary.
"""

import numpy as np
import pandas as pd

SENSOR_COLS = ["temp_c", "humidity_pct", "pressure_hpa"]


# ── Dynamic threshold helpers (logic from predictor.py) ──────────────

def _iqr_severity_threshold(context_values: np.ndarray, k: float = 1.5) -> float:
    """
    Tukey-fence threshold on the per-step severity scores of the context
    window. Returns max(0.5, Q3 + k·IQR) so the floor never drops below a
    sensible minimum even for extremely stable windows.
    Source: Tukey 1977 — "Exploratory Data Analysis".
    """
    q1, q3 = np.percentile(context_values, [25, 75])
    iqr = q3 - q1
    return max(0.5, q3 + k * iqr)


def _mad_deviation_threshold(context_values: np.ndarray, k: float = 3.0) -> float:
    """
    MAD-based threshold: median + k × MAD (k=3 ≈ 3σ, robust to outliers).
    Source: Leys et al. 2013, J. Exp. Soc. Psych. 49(4):764-766.
    Returns 0.0 for a perfectly constant window (caller falls back).
    """
    median = np.median(context_values)
    mad = np.median(np.abs(context_values - median))
    if mad == 0:
        return 0.0
    return median + k * 1.4826 * mad


# ── Layer 4 entrypoint ───────────────────────────────────────────────

def forecast_reading(pipeline, readings, n_context: int = 20) -> dict:
    """
    Forecast the next reading after the last reading and compare it to
    the actual last reading (which the window includes).

    readings : plain list of reading dicts (AGENTS.md contract), at least
               n_context+1 entries, chronological, for ONE station.
               The DataFrame is built inside and never crosses the boundary.
    Returns the L4 payload dict (unified layer contract).
    """
    df = pd.DataFrame(readings)
    df = df.sort_values("timestamp").reset_index(drop=True)

    if len(df) < n_context + 1:
        last_row = df.iloc[-1]
        return {
            "layer": "L4",
            "station_id": last_row["station_id"],
            "timestamp": last_row["timestamp"],
            "predicted_anomaly": False,
            "checks": {
                "forecast": {
                    "error": f"insufficient data ({len(df)} rows < {n_context + 1} required)"
                }
            },
            "affected_sensors": [],
            "reason": f"insufficient context ({len(df)} rows, need {n_context + 1})",
        }

    # NaN handling: forward-fill then back-fill the sensor columns before
    # feeding Chronos (idea-pitch/02-thresholds.md: "forward-fill + back-fill
    # the window before predict").
    df[SENSOR_COLS] = df[SENSOR_COLS].ffill().bfill()

    # Input shape: (batch=1, series=3, context=n_context) — T/P/RH jointly.
    context = [df[col].values[-n_context - 1 : -1] for col in SENSOR_COLS]
    inputs = np.array([[c for c in context]])

    quantiles, _ = pipeline.predict_quantiles(
        inputs, prediction_length=1, quantile_levels=[0.05, 0.5, 0.95]
    )
    forecast = quantiles[0]  # (3 series, 1 step, 3 quantiles)

    actual = [df[col].values[-1] for col in SENSOR_COLS]
    last_row = df.iloc[-1]

    payload = {
        "layer": "L4",
        "station_id": last_row["station_id"],
        "timestamp": last_row["timestamp"],
        "predicted_anomaly": False,
        "checks": {"forecast": {}},
        "affected_sensors": [],
        "reason": None,
    }

    reasons = []
    for i, sensor in enumerate(SENSOR_COLS):
        # quantiles come back as torch tensors -> detach + float.
        p5, p50, p95 = [float(v) for v in forecast[i][0]]
        corridor_width = p95 - p5
        value = float(actual[i])

        # Breach beyond the corridor + severity (predictor logic).
        upper_breach = max(0.0, value - p95)
        lower_breach = max(0.0, p5 - value)
        total_breach = upper_breach + lower_breach
        severity = round(total_breach / corridor_width, 4) if corridor_width > 0 else 0.0

        # Dynamic threshold 1: IQR on historical residuals (Tukey fence).
        ctx = context[i].astype(float)
        ctx_median = np.median(ctx)
        ctx_residuals = np.abs(ctx - ctx_median)
        sev_threshold = _iqr_severity_threshold(
            ctx_residuals / (corridor_width if corridor_width > 0 else 1.0)
        )

        # Dynamic threshold 2: MAD on residuals (Leys et al.).
        dev_threshold = _mad_deviation_threshold(ctx)
        if dev_threshold == 0.0:
            dev_threshold = corridor_width

        deviation = abs(value - p50)
        flagged = severity > sev_threshold or deviation > dev_threshold

        payload["checks"]["forecast"][sensor] = {
            "p5": round(p5, 3),
            "p50": round(p50, 3),
            "p95": round(p95, 3),
            "actual": round(value, 3),
            "severity": severity,
            "deviation": round(deviation, 4),
            "outside_corridor": bool(value < p5 or value > p95),
        }

        if flagged:
            payload["predicted_anomaly"] = True
            payload["affected_sensors"].append(sensor)
            reasons.append(
                f"{sensor} outside forecast corridor (severity {severity}, "
                f"p50 {p50:.2f}, actual {value:.2f})"
            )

    payload["affected_sensors"] = sorted(set(payload["affected_sensors"]))
    if reasons:
        payload["reason"] = "; ".join(reasons)
    return payload