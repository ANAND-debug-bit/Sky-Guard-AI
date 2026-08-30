"""
Layer 3 — Frozen Sensor Detection
==================================
SkyGuard AI — Sky-Guard-AI/microservices/app/layers/frozen

Detects sensors that are physically stuck/frozen by checking whether
readings stay (near-)constant over a sliding window.  A live physical
quantity (temperature, pressure, humidity) will always exhibit some
natural micro-variation; if the second derivative is effectively zero
across the board, the sensor is almost certainly jammed.

Theory (from README):
    d²x/dt² ≈ 0   for all sensor channels
    ⇒ flagged as a **stuck/frozen sensor alert**

Detection strategy:
    1. Compute the first-order differences  (Δx = x[t] − x[t−1]).
    2. Compute the second-order differences (Δ²x = Δx[t] − Δx[t−1]).
    3. If the *range* (max − min) of the raw readings AND the absolute
       values of both first and second derivatives are all below
       sensor-specific tolerances for the entire window → frozen.

    We also track simple variance of raw readings as a complementary
    check: a perfectly constant series has variance = 0.

Why per-sensor tolerances?
    ADC resolution and natural variability differ by sensor type:
      - Temperature sensors (thermistors/RTDs): ±0.1°C resolution is
        common; natural micro-variation in still air is ~0.05–0.2°C/step.
      - Pressure transducers: ±0.1 hPa resolution; barometric pressure
        can be remarkably stable over short windows (hours), so we use
        a tighter tolerance but require a longer stuck window.
      - Humidity sensors (capacitive): ±1% RH resolution; natural
        fluctuation is broader, so the tolerance is wider.
"""

import numpy as np
import pandas as pd


# ── Per-sensor tolerances ────────────────────────────────────────────
# These define the maximum variation (range of raw values, max |Δx|,
# max |Δ²x|) below which a sensor is considered "stuck".  Tuned to
# be well above ADC noise but below any plausible real-world change
# over a multi-hour window.
#
# Format: {column_name: (range_tol, d1_tol, d2_tol)}
#   range_tol : max allowable spread (max − min) in the window
#   d1_tol    : max allowable |first derivative| across the window
#   d2_tol    : max allowable |second derivative| across the window

SENSOR_TOLERANCES = {
    "temp_c":        (0.05, 0.05, 0.05),   # °C
    "pressure_hpa":  (0.1,  0.1,  0.1),    # hPa
    "humidity_pct":  (0.5,  0.5,  0.5),     # %RH
}

# Minimum window length required to make a meaningful frozen call.
# With hourly data, 6 rows = 6 hours of constant readings — very
# suspicious for any live sensor.  With 10-min data, 6 rows = 1 hour.
MIN_WINDOW_LEN = 6


# ── Core detection ───────────────────────────────────────────────────

def _is_frozen(values: np.ndarray, range_tol: float,
               d1_tol: float, d2_tol: float) -> bool:
    """
    Return True if `values` (a 1-D array of sensor readings) show
    effectively zero variation — indicating a stuck/frozen sensor.

    Checks:
      1. Range of raw values ≤ range_tol
      2. Max |first difference|  ≤ d1_tol
      3. Max |second difference| ≤ d2_tol
    All three must hold simultaneously.
    """
    if len(values) < MIN_WINDOW_LEN:
        return False

    # Drop NaNs — if too many are missing, we can't judge
    clean = values[~np.isnan(values)]
    if len(clean) < MIN_WINDOW_LEN:
        return False

    # 1. Raw range
    val_range = np.ptp(clean)  # max − min
    if val_range > range_tol:
        return False

    # 2. First differences  (Δx)
    d1 = np.diff(clean)
    if np.max(np.abs(d1)) > d1_tol:
        return False

    # 3. Second differences (Δ²x  ≈  d²x/dt²)
    d2 = np.diff(d1)
    if len(d2) == 0:
        return False
    if np.max(np.abs(d2)) > d2_tol:
        return False

    return True


# ── Batch layer function ─────────────────────────────────────────────
# Follows the same contract as layer1_physics(batch_df) → result_df.

def layer3_frozen_sensor(batch_df: pd.DataFrame,
                         sensor_columns: list[str] | None = None,
                         ) -> pd.DataFrame:
    """
    Layer 3: Frozen / Stuck Sensor Detection.

    Scans each sensor column across the entire batch window.
    If a sensor's readings are effectively constant (second derivative
    ≈ 0, range ≈ 0), every row in the batch is flagged for that sensor.

    Parameters
    ----------
    batch_df : pd.DataFrame
        Must contain a time/timestamp column, 'station_id', and the
        sensor columns listed in `sensor_columns`.
    sensor_columns : list of str, optional
        Sensor columns to check.  Defaults to the three core sensors
        ['temp_c', 'pressure_hpa', 'humidity_pct'].

    Returns
    -------
    pd.DataFrame
        One row per input row, in the shared contract shape:
        time, station_id, predicted_anomaly, sensor_type,
        anomaly_value, anomaly_reason, expected_cause,
        recommended_action, layer_used.
    """
    if sensor_columns is None:
        sensor_columns = list(SENSOR_TOLERANCES.keys())

    # Resolve time column name (some parts of the codebase use 'time',
    # others use 'timestamp')
    time_col = "time" if "time" in batch_df.columns else "timestamp"

    result_df = pd.DataFrame()
    result_df["time"] = batch_df[time_col]
    result_df["station_id"] = batch_df["station_id"]
    result_df["predicted_anomaly"] = 0
    result_df["sensor_type"] = None
    result_df["anomaly_value"] = np.nan
    result_df["anomaly_reason"] = None
    result_df["expected_cause"] = None
    result_df["recommended_action"] = None
    result_df["layer_used"] = "Layer 3: Frozen Sensor Detection"

    frozen_sensors: list[str] = []

    for col in sensor_columns:
        if col not in batch_df.columns:
            continue

        tols = SENSOR_TOLERANCES.get(col, (0.05, 0.05, 0.05))
        values = batch_df[col].values.astype(float)

        if _is_frozen(values, *tols):
            frozen_sensors.append(col)

    if frozen_sensors:
        # Flag every row in the batch — the entire window is suspect
        result_df["predicted_anomaly"] = 1
        result_df["sensor_type"] = ", ".join(frozen_sensors)
        result_df["anomaly_reason"] = (
            f"Sensor readings constant (d²x/dt² ≈ 0) across "
            f"{len(batch_df)} consecutive readings: {', '.join(frozen_sensors)}"
        )
        result_df["expected_cause"] = (
            "Sensor jam, ice/dust blocking, or hardware freeze"
        )
        result_df["recommended_action"] = (
            "Physical inspection; clean/replace affected sensor(s)"
        )

        # Store the constant value as anomaly_value for each frozen sensor
        # (use the first sensor's value for the column; if multiple sensors
        # are frozen, the individual values are in the reason string)
        for col in frozen_sensors:
            vals = batch_df[col].dropna()
            if not vals.empty:
                result_df["anomaly_value"] = vals.iloc[0]
                break

    return result_df


# ── Tests ────────────────────────────────────────────────────────────

def _run_frozen_tests():
    """Comprehensive tests for the frozen sensor detection layer."""

    # --- Test 1: perfectly constant temperature → frozen ---
    n = 10
    batch_frozen = pd.DataFrame({
        "time": pd.date_range("2026-08-29 10:00", periods=n, freq="h"),
        "station_id": ["DEL01"] * n,
        "temp_c": [25.0] * n,                # perfectly stuck
        "pressure_hpa": np.linspace(1010, 1015, n),  # normal variation
        "humidity_pct": np.linspace(50, 65, n),       # normal variation
    })
    result = layer3_frozen_sensor(batch_frozen)
    assert len(result) == n
    assert (result["predicted_anomaly"] == 1).all(), \
        "constant temp_c must be flagged as frozen"
    assert "temp_c" in result.iloc[0]["sensor_type"]
    assert "pressure_hpa" not in result.iloc[0]["sensor_type"], \
        "pressure_hpa is varying, should NOT be flagged"
    print("  ✓ Test 1: constant temperature detected as frozen")

    # --- Test 2: all sensors healthy (natural variation) → NOT frozen ---
    np.random.seed(42)
    batch_healthy = pd.DataFrame({
        "time": pd.date_range("2026-08-29 10:00", periods=n, freq="h"),
        "station_id": ["DEL01"] * n,
        "temp_c": 25.0 + np.random.normal(0, 0.5, n),
        "pressure_hpa": 1010.0 + np.random.normal(0, 1.0, n),
        "humidity_pct": 60.0 + np.random.normal(0, 3.0, n),
    })
    result = layer3_frozen_sensor(batch_healthy)
    assert (result["predicted_anomaly"] == 0).all(), \
        "healthy sensors with variation must NOT be flagged"
    print("  ✓ Test 2: healthy sensors correctly pass")

    # --- Test 3: too-short window → no flag (insufficient evidence) ---
    batch_short = pd.DataFrame({
        "time": pd.date_range("2026-08-29 10:00", periods=3, freq="h"),
        "station_id": ["DEL01"] * 3,
        "temp_c": [25.0] * 3,
        "pressure_hpa": [1010.0] * 3,
        "humidity_pct": [60.0] * 3,
    })
    result = layer3_frozen_sensor(batch_short)
    assert (result["predicted_anomaly"] == 0).all(), \
        "window too short to call frozen — must not flag"
    print("  ✓ Test 3: short window correctly skipped")

    # --- Test 4: multiple sensors frozen simultaneously ---
    batch_multi = pd.DataFrame({
        "time": pd.date_range("2026-08-29 10:00", periods=n, freq="h"),
        "station_id": ["DEL01"] * n,
        "temp_c": [25.0] * n,
        "pressure_hpa": [1010.0] * n,
        "humidity_pct": np.linspace(50, 65, n),  # only this one is alive
    })
    result = layer3_frozen_sensor(batch_multi)
    assert (result["predicted_anomaly"] == 1).all()
    sensor_types = result.iloc[0]["sensor_type"]
    assert "temp_c" in sensor_types and "pressure_hpa" in sensor_types, \
        "both temp_c and pressure_hpa must be flagged"
    assert "humidity_pct" not in sensor_types, \
        "humidity_pct is varying, should NOT be flagged"
    print("  ✓ Test 4: multiple frozen sensors detected together")

    # --- Test 5: near-constant but within ADC noise → frozen ---
    # Tiny jitter within tolerance (simulates ADC quantization noise).
    # Pattern chosen so range, max|d1|, and max|d2| all stay well below
    # the 0.05 tolerance (max|d2| here ≈ 0.02).
    jitter = np.array([0.0, 0.01, 0.0, 0.01, 0.0,
                        0.01, 0.0, 0.01, 0.0, 0.01])
    batch_adc = pd.DataFrame({
        "time": pd.date_range("2026-08-29 10:00", periods=n, freq="h"),
        "station_id": ["DEL01"] * n,
        "temp_c": 25.0 + jitter,  # range = 0.04, within 0.05 tolerance
        "pressure_hpa": np.linspace(1010, 1015, n),
        "humidity_pct": np.linspace(50, 65, n),
    })
    result = layer3_frozen_sensor(batch_adc)
    assert (result["predicted_anomaly"] == 1).all(), \
        "ADC-noise-level jitter should still be flagged as frozen"
    assert "temp_c" in result.iloc[0]["sensor_type"]
    print("  ✓ Test 5: ADC-noise-level jitter correctly flagged")

    # --- Test 6: 'timestamp' column (alternative naming) ---
    batch_ts = batch_frozen.rename(columns={"time": "timestamp"})
    result = layer3_frozen_sensor(batch_ts)
    assert (result["predicted_anomaly"] == 1).all(), \
        "must work with 'timestamp' column too"
    print("  ✓ Test 6: 'timestamp' column name handled correctly")

    # --- Test 7: NaN-heavy window → not enough data → no flag ---
    batch_nan = pd.DataFrame({
        "time": pd.date_range("2026-08-29 10:00", periods=n, freq="h"),
        "station_id": ["DEL01"] * n,
        "temp_c": [25.0, np.nan, np.nan, np.nan, np.nan,
                   np.nan, np.nan, np.nan, np.nan, 25.0],
        "pressure_hpa": np.linspace(1010, 1015, n),
        "humidity_pct": np.linspace(50, 65, n),
    })
    result = layer3_frozen_sensor(batch_nan)
    # Only 2 valid temp readings — not enough to call frozen
    assert result.iloc[0]["sensor_type"] is None or \
        "temp_c" not in str(result.iloc[0]["sensor_type"]), \
        "NaN-heavy column should not be flagged as frozen"
    print("  ✓ Test 7: NaN-heavy window correctly handled")

    print("\nAll Layer 3 (Frozen Sensor) tests passed. ✓")


if __name__ == "__main__":
    _run_frozen_tests()
