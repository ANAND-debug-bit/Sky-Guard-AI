"""
Sensor Aging / Health Layer (v2)
=================================
SkyGuard AI — microservices/app/layers_v2/aging.py

Tracks gradual sensor degradation (ageing, corrosion, slow decalibration)
that the live L1-L4 detectors miss — each individual reading looks fine,
only the *trend* reveals drift. Runs independently of live detection
(idea-pitch/07-sensor-health.md).

Method (from the reference ml_code.py `sensor_health` + plan thresholds):
  1. Decompose the sensor series: y = trend + seasonal + residual.
     Daily mean - 30-day rolling mean (seasonal baseline) -> daily error.
  2. Mann-Kendall test on the daily errors (pymannkendall, original_test).
     p < 0.05 => significant monotonic trend (drift), not random noise.
  3. Theil-Sen slope (from MK result) = drift rate per day.
  4. Current drift = |days_active * slope + intercept|; compare against the
     max allowable drift per sensor (WMO/industrial standards).
  5. Health % = max(0, 100 * (1 - current_drift / max_allowable_drift));
     days-until-maintenance = remaining allowance / |slope|.

Thresholds (sources):
  - Max allowable drift: temp 0.5 C, pressure 0.5 hPa, RH 5%
    (WMO/industrial, reference ml_code.py).
  - Mann-Kendall window: >= 30 daily points (idea-pitch/02-thresholds.md).

Input/output contract (see AGENTS.md):
  input : plain list of reading dicts (chronological, ONE station, hourly) —
          the DataFrame is built inside and never crosses the boundary
  output: single payload dict in the unified layer contract, where checks
          holds the per-sensor health report
"""

import numpy as np
import pandas as pd
import pymannkendall as mk

SENSOR_KEYS = ["temp_c", "pressure_hpa", "humidity_pct"]

# Max allowable long-term drift (WMO/industrial, from reference ml_code.py).
MAX_ALLOWABLE_DRIFT = {
    "temp_c": 0.5,        # deg C
    "pressure_hpa": 0.5,  # hPa
    "humidity_pct": 5.0,  # %RH
}

# Minimum daily points for a meaningful Mann-Kendall test (thresholds doc).
MIN_DAILY_POINTS = 30

# Health zones (plan 07-sensor-health.md tiers, adapted to % scale).
HEALTHY_PCT = 85.0     # >= 85 -> healthy
WATCH_PCT = 60.0       # 60-85 -> watch
DEGRADED_PCT = 40.0    # 40-60 -> degraded; below -> critical


def _extract_daily_errors(df: pd.DataFrame, sensor: str) -> np.ndarray:
    """
    Daily mean - 30-day rolling mean (seasonal baseline) = daily error.
    The 30-day baseline removes weather/seasonal influence so the MK test
    sees only sensor drift (reference ml_code.py `extract_daily_error`).
    """
    ts = pd.to_datetime(df["timestamp"])
    daily = df.groupby(ts.dt.date)[sensor].mean().to_frame(name="value")
    raw_daily = daily["value"]
    seasonal_baseline = raw_daily.rolling(window=30, min_periods=1).mean()
    return (raw_daily - seasonal_baseline).dropna().to_numpy()


def _sensor_health(daily_errors: np.ndarray, sensor: str) -> dict:
    """
    Mann-Kendall + Theil-Sen on daily errors -> health report for one sensor.
    """
    max_drift = MAX_ALLOWABLE_DRIFT.get(sensor, 2.0)
    mk_result = mk.original_test(daily_errors)

    slope = float(mk_result.slope)
    intercept = float(mk_result.intercept)
    trend = mk_result.trend
    p_value = float(mk_result.p)

    days_active = len(daily_errors)
    # Net drift = |slope| * time. The MK intercept is the estimated value at
    # index 0 (the starting error level), NOT a drift offset — including it
    # would inflate the drift by the initial seasonal-error magnitude.
    current_drift = abs(slope * days_active)
    health_pct = round(max(0.0, 100.0 * (1.0 - current_drift / max_drift)), 2)

    if health_pct >= HEALTHY_PCT:
        zone = "Healthy"
    elif health_pct >= WATCH_PCT:
        zone = "Watch"
    elif health_pct >= DEGRADED_PCT:
        zone = "Degraded"
    else:
        zone = "Critical"

    # Predict days until maintenance from the drift rate (Theil-Sen slope).
    has_trend = p_value < 0.05 and slope != 0.0
    if has_trend:
        remaining = max_drift - current_drift
        days_until_maintenance = max(0, int(remaining / abs(slope)))
    else:
        days_until_maintenance = "stable — no maintenance required"

    return {
        "trend": trend,
        "p_value": round(p_value, 4),
        "drift_per_day": round(abs(slope), 5),
        "current_drift": round(current_drift, 3),
        "max_allowable_drift": max_drift,
        "health_percent": health_pct,
        "zone": zone,
        "days_until_maintenance": days_until_maintenance,
    }


def evaluate_aging(readings, min_daily_points: int = MIN_DAILY_POINTS) -> dict:
    """
    Run the aging/health check on a station's history.

    readings : plain list of reading dicts (AGENTS.md contract), hourly,
               chronological, for ONE station.
    Returns a payload dict (unified layer contract) whose checks.aging
    holds one health report per sensor. predicted_anomaly = any sensor
    degraded or critical.
    """
    df = pd.DataFrame(readings)
    df = df.sort_values("timestamp").reset_index(drop=True)

    last = df.iloc[-1]
    payload = {
        "layer": "L2",  # aging is the L2 trend/drift sub-module
        "station_id": last["station_id"],
        "timestamp": last["timestamp"],
        "predicted_anomaly": False,
        "checks": {"aging": {}},
        "affected_sensors": [],
        "reason": None,
    }

    for sensor in SENSOR_KEYS:
        if df[sensor].isna().mean() > 0.5:
            # Too many missing values to trust a drift estimate.
            payload["checks"]["aging"][sensor] = {"error": "insufficient data"}
            continue

        daily_errors = _extract_daily_errors(df, sensor)
        if len(daily_errors) < min_daily_points:
            payload["checks"]["aging"][sensor] = {
                "error": f"insufficient history ({len(daily_errors)} daily "
                         f"points < {min_daily_points})"
            }
            continue

        report = _sensor_health(daily_errors, sensor)
        payload["checks"]["aging"][sensor] = report

        if report["zone"] in ("Degraded", "Critical"):
            payload["predicted_anomaly"] = True
            payload["affected_sensors"].append(sensor)

    payload["affected_sensors"] = sorted(set(payload["affected_sensors"]))
    if payload["predicted_anomaly"]:
        payload["reason"] = (
            "Sensor(s) showing significant drift: "
            + ", ".join(payload["affected_sensors"])
        )
    return payload