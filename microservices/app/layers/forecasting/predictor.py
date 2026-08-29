import pandas as pd
import numpy as np


# ── Dynamic threshold helpers ────────────────────────────────────────
#
# Instead of hard-coding severity > 0.8, we derive thresholds from the
# context window's own distribution each time.  Two complementary tests:
#
# 1) SEVERITY THRESHOLD  –  IQR-based, inspired by the Tukey fence
#    (Tukey, J.W. 1977, "Exploratory Data Analysis", Addison-Wesley).
#    Any value beyond Q3 + k·IQR is flagged.  k = 1.5 is the classic
#    "outlier" fence; we apply this to the *severity scores* themselves
#    so the threshold adapts to how variable the prediction errors are.
#    Ref: https://en.wikipedia.org/wiki/Interquartile_range#Outliers
#
# 2) DEVIATION THRESHOLD  –  MAD-scaled, following Leys et al. (2013),
#    "Detecting outliers: Do not use standard deviation around the mean,
#    use absolute deviation around the median", Journal of Experimental
#    Social Psychology 49(4):764-766.   DOI: 10.1016/j.jesp.2013.03.013
#    Threshold = median + k · MAD,  with k = 3 (very conservative) as
#    the default.  MAD is more robust to outliers than σ.
#
# Both methods auto-calibrate from the sliding window so they work
# across sensors with wildly different scales and volatility.
# ─────────────────────────────────────────────────────────────────────

def _iqr_severity_threshold(context_values: np.ndarray, k: float = 1.5) -> float:
    """
    Tukey-fence threshold on the per-step severity scores of the context
    window.  Returns max(0.5, Q3 + k·IQR) so the floor never drops
    below a sensible minimum even for extremely stable windows.

    Source: Tukey 1977 — "Exploratory Data Analysis"
    https://en.wikipedia.org/wiki/Interquartile_range#Outliers
    """
    q1, q3 = np.percentile(context_values, [25, 75])
    iqr = q3 - q1
    # Floor of 0.5 prevents over-sensitivity on perfectly flat windows
    return max(0.5, q3 + k * iqr)


def _mad_deviation_threshold(context_values: np.ndarray, k: float = 3.0) -> float:
    """
    MAD-based threshold: median + k × MAD.
    Returns the absolute-deviation cutoff above which a residual is
    anomalous.  k = 3 ≈ 3σ for Gaussian data, but is robust to
    non-Gaussian tails.

    Source: Leys et al. 2013, J. Exp. Soc. Psych. 49(4):764-766
    DOI: 10.1016/j.jesp.2013.03.013
    """
    median = np.median(context_values)
    mad = np.median(np.abs(context_values - median))
    # 1.4826 converts MAD → σ-equivalent for Gaussian data
    # (consistency constant, see Leys et al. §2.1)
    if mad == 0:
        # Perfectly constant window — fall back to corridor_width × 1.0
        return 0.0
    return median + k * 1.4826 * mad


def predict(pipeline, df, N=20):
    sensor_names = ["temperature", "humidity", "pressure"]
    col_names = ["temp_c", "humidity_pct", "pressure_hpa"]

    context = [
        df[col].values[-N - 1 : -1] for col in col_names
    ]

    inputs = np.array([[c for c in context]])

    quantiles, mean = pipeline.predict_quantiles(
        inputs, prediction_length=1, quantile_levels=[0.05, 0.5, 0.95]
    )

    actual = [df[col].values[-1] for col in col_names]

    forecast = quantiles[0].tolist()

    payload = {"is_anomaly": False, "sensors": []}

    for i, reading in enumerate(forecast):

        p5, p50, p95 = reading[0]
        corridor_width = p95 - p5

        # ── Breach & severity (same as before) ──────────────────────
        upper_breach = np.maximum(0.0, actual[i] - p95)
        lower_breach = np.maximum(0.0, p5 - actual[i])
        total_breach = upper_breach + lower_breach

        if corridor_width > 0:
            severity = total_breach / corridor_width
        else:
            severity = 0.0
        severity = np.round(severity, 4)

        # ── Dynamic threshold 1: IQR on historical residuals ────────
        # Compute severity scores for each step in the context window
        # so the threshold reflects this sensor's recent error profile.
        ctx = context[i]                          # shape (N,)
        ctx_median = np.median(ctx)
        ctx_residuals = np.abs(ctx - ctx_median)  # per-step deviations
        sev_threshold = _iqr_severity_threshold(ctx_residuals / (corridor_width if corridor_width > 0 else 1.0))

        # ── Dynamic threshold 2: MAD on residuals ───────────────────
        dev_threshold = _mad_deviation_threshold(ctx)
        # If MAD returned 0 (constant window), fall back to corridor
        if dev_threshold == 0.0:
            dev_threshold = corridor_width

        deviation = abs(actual[i] - p50)

        predicted_anomaly = severity > sev_threshold or deviation > dev_threshold

        if predicted_anomaly:
            payload["is_anomaly"] = True
            payload["sensors"].append(sensor_names[i])

    return payload
