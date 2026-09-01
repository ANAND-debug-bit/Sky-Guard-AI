"""
Layer 3 — Frozen Sensor Detection (v2)
=======================================
SkyGuard AI — microservices/app/layers_v2/frozen.py

Detects sensors physically stuck/jammed: a live physical quantity always
shows micro-variation, so a (near-)constant window means the sensor is
almost certainly frozen.

Design follows idea-pitch/02-thresholds.md (L3):
  - std(window) < 0.01  -> frozen (conservative; stable weather still
                           varies ~0.3-0.5 std)
  - max(|2nd derivative|) < 0.01 as alt/confirm (functionally equivalent)
  - min window: 10 non-null readings (avoid false freeze on short windows)
  - all 3 sensors frozen -> logger/station failure, not a single sensor

Input/output contract (see AGENTS.md):
  input : plain list of reading dicts (chronological, ONE station) —
          the DataFrame is built inside and never crosses the boundary
  output: single unified payload dict
          {layer, station_id, timestamp, predicted_anomaly, checks,
           affected_sensors, reason}
"""

import numpy as np
import pandas as pd

# SENSOR_KEYS: the three core sensors (same order everywhere).
SENSOR_KEYS = ["temp_c", "pressure_hpa", "humidity_pct"]

# Frozen threshold: window std below this = frozen (thresholds doc).
STD_FROZEN = 0.01
# Min readings required before calling anything frozen. The thresholds doc
# says 10 (production, 10-min cadence); the reference layer used 6, and the
# injected demo runs are only 4-12 hrs of hourly data, so 6 is the tuned
# default here — mark as a tunable.
MIN_WINDOW_LEN = 6

# Per-sensor tolerances from the v1 reference layer
# (layers/frozen/frozen.py): (range_tol, d1_tol, d2_tol). The v1 detection
# treats a sensor as frozen when raw range, max |1st derivative| and max
# |2nd derivative| all stay below these — a complementary check to the
# plan's std<0.01 test, kept because natural variability differs per sensor.
SENSOR_TOLERANCES = {
    "temp_c": (0.05, 0.05, 0.05),   # °C
    "pressure_hpa": (0.1, 0.1, 0.1),  # hPa
    "humidity_pct": (0.5, 0.5, 0.5),  # %RH
}


def _is_frozen_v1(values: np.ndarray, sensor: str) -> bool:
    """
    v1 frozen check: range, max|d1| and max|d2| all within the sensor's
    tolerance. Returns False if there aren't enough valid values.
    """
    if len(values) < MIN_WINDOW_LEN:
        return False
    range_tol, d1_tol, d2_tol = SENSOR_TOLERANCES.get(sensor, (0.05, 0.05, 0.05))

    if float(np.ptp(values)) > range_tol:
        return False
    d1 = np.diff(values)
    if len(d1) and float(np.max(np.abs(d1))) > d1_tol:
        return False
    d2 = np.diff(d1)
    if len(d2) and float(np.max(np.abs(d2))) > d2_tol:
        return False
    return True


def evaluate_frozen(readings, min_window: int = MIN_WINDOW_LEN) -> dict:
    """
    Run the L3 frozen check on a window of readings for ONE station.
    Only the LAST min_window readings decide the verdict — a short frozen
    run at the end of the window is still caught even if the window
    includes earlier, non-frozen history.

    readings : plain list of reading dicts (AGENTS.md contract).
    Returns the L3 payload dict (unified layer contract).
    """
    df = pd.DataFrame(readings)
    df = df.sort_values("timestamp").reset_index(drop=True)

    last = df.iloc[-1]
    payload = {
        "layer": "L3",
        "station_id": last["station_id"],
        "timestamp": last["timestamp"],
        "predicted_anomaly": False,
        "checks": {"frozen": {}},
        "affected_sensors": [],
        "reason": None,
    }

    frozen = []
    for sensor in SENSOR_KEYS:
        values = df[sensor].dropna().astype(float).to_numpy()
        # Only the trailing min_window readings are the evidence.
        tail = values[-min_window:]
        # Need enough valid readings to judge.
        if len(tail) < min_window:
            payload["checks"]["frozen"][sensor] = False
            continue

        # Primary (plan): window std below threshold.
        std_flag = float(np.std(tail, ddof=1)) < STD_FROZEN
        # Confirm (plan): 2nd derivative ~ 0.
        if std_flag and len(tail) >= 3:
            d1 = np.diff(tail)
            d2 = np.diff(d1)
            std_flag = float(np.max(np.abs(d2))) < STD_FROZEN

        # Complementary (v1): per-sensor range/d1/d2 tolerance test.
        v1_flag = _is_frozen_v1(tail, sensor)

        payload["checks"]["frozen"][sensor] = bool(std_flag or v1_flag)
        if std_flag or v1_flag:
            frozen.append(sensor)

    if frozen:
        payload["predicted_anomaly"] = True
        payload["affected_sensors"] = frozen
        if len(frozen) == len(SENSOR_KEYS):
            # All three frozen -> station/logger failure, not single sensor.
            payload["reason"] = (
                f"All sensors frozen (std < {STD_FROZEN} over last "
                f"{min_window} readings) — station/data-logger failure"
            )
        else:
            payload["reason"] = (
                f"Frozen sensor(s): {', '.join(frozen)} (std < {STD_FROZEN} "
                f"over last {min_window} readings)"
            )

    return payload