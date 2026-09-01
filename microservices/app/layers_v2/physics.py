"""
Layer 1 — Physics Sanity Checks (v2, fresh start)
=================================================
SkyGuard AI — microservices/app/layers_v2/physics.py

Works on ONE reading at a time (streaming contract):

    input : reading + previous_reading + station
    output: per-check flags, affected sensors, reason

Checks implemented (see idea-pitch/02-thresholds.md for sources):
    1. range            - per-sensor hard physical bounds
    2. dew_point        - T_dew <= T_air + 0.5 (Magnus / Alduchov-Eskridge)
    3. pressure_altitude- |P_actual - P_expected(elevation)| > 30 hPa
    4. rate_of_change   - per-sensor delta vs previous reading;
                          fault threshold vs alert-candidate threshold

Semantics of `checks`:
    range.{sensor}        : True = value outside hard bounds
    dew_point             : True = violated (humidity sensor lying)
    pressure_altitude     : True = barometer miscalibrated
    rate_of_change.{sensor}.fault  : True = exceeds fault limit (SENSOR_FAULT)
    rate_of_change.{sensor}.alert  : True = exceeds alert limit only
                                     (real weather candidate -> L6 decides)

Keep this layer deterministic, O(1), and free of ML/neighbours.
"""

import math
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Thresholds — sourced from idea-pitch/02-thresholds.md; treat as tunable.
# ---------------------------------------------------------------------------

# Range bounds (India-restricted, WMO record extremes).
TEMP_MIN_C = -40.0      # WMO/BoM, India subset
TEMP_MAX_C = 55.0
PRESSURE_MIN_HPA = 300.0
PRESSURE_MAX_HPA = 1084.0
HUMIDITY_MIN_PCT = 0.0
HUMIDITY_MAX_PCT = 100.0

# Dew point (Magnus / Alduchov-Eskridge).
MAGNUS_A = 17.625
MAGNUS_B = 243.04
DEW_POINT_TOLERANCE_C = 0.5   # T_dew <= T_air + 0.5
MAGNUS_VALID_T_MIN = -40.0    # Magnus formula valid range (v1 kept this)
MAGNUS_VALID_T_MAX = 50.0

# Pressure-altitude consistency.
PRESSURE_ALTITUDE_TOLERANCE_HPA = 30.0

# Rate of change per sensor — fault limit and alert-candidate limit.
# Sources: NOAA MADIS validity limits (fault), cyclone-class (alert).
RATE_FAULT = {
    "temp_c": 19.4,        # deg C / hr
    "pressure_hpa": 15.0,  # hPa / hr
    "humidity_pct": 50.0,  # % / hr
}
RATE_ALERT = {
    "temp_c": 8.0,         # deg C / hr (tightened watch level)
    "pressure_hpa": 3.0,   # hPa / hr (cyclone-class)
    "humidity_pct": 20.0,  # % / hr
}

SENSOR_KEYS = ["temp_c", "pressure_hpa", "humidity_pct"]


# ---------------------------------------------------------------------------
# Core math helpers (shared constants kept here so L5 can import P_MSL too)
# ---------------------------------------------------------------------------

def msl_pressure(p_station_hpa: float, t_celsius: float, h_m: float) -> float:
    """
    Reduce station pressure to Mean Sea Level (MSL) so stations at
    different elevations are comparable. Formula:
        P_MSL = P * (1 - 0.0065*h / (T + 0.0065*h + 273.15)) ^ -5.257
    At h=0 returns P_station exactly.
    """
    lapse_term = (0.0065 * h_m) / (t_celsius + 0.0065 * h_m + 273.15)
    return p_station_hpa * (1 - lapse_term) ** (-5.257)


def expected_pressure(elevation_m: float) -> float:
    """
    Pressure a station at this elevation *should* read (standard
    barometric formula with sea-level reference T0 = 288.15 K):
        P(h) = 1013.25 * (1 - 0.0065*h / 288.15) ^ 5.25588
    Reference: ~772 hPa at 2200 m (Shimla), not 1013 hPa.
    Used by the pressure-altitude consistency check.
    """
    return 1013.25 * (1 - 0.0065 * elevation_m / 288.15) ** 5.25588


def dew_point(t_celsius: float, rh_percent: float) -> float:
    """
    Dew point from air temperature and RH (Magnus formula).
    Reference: T=25C, RH=50% -> ~13.86C. At RH=100% returns T exactly.
    Returns -inf for RH <= 0 (physically meaningless).
    """
    if rh_percent <= 0:
        return float('-inf')
    gamma = math.log(rh_percent / 100.0) + (MAGNUS_A * t_celsius) / (MAGNUS_B + t_celsius)
    return (MAGNUS_B * gamma) / (MAGNUS_A - gamma)


def magnus_confidence(t_celsius: float) -> float:
    """
    Confidence (0-100) that the Magnus formula is valid at this temperature
    (ported from v1). Full confidence inside [-40, 50] C; ramps linearly to
    0 toward the hard temperature extremes.
    """
    if t_celsius is None or math.isnan(t_celsius):
        return 0.0
    if MAGNUS_VALID_T_MIN <= t_celsius <= MAGNUS_VALID_T_MAX:
        return 100.0
    if t_celsius > MAGNUS_VALID_T_MAX:
        span = TEMP_MAX_C - MAGNUS_VALID_T_MAX
        frac = (t_celsius - MAGNUS_VALID_T_MAX) / span
        return max(0.0, 100.0 * (1 - frac))
    span = MAGNUS_VALID_T_MIN - TEMP_MIN_C
    frac = (MAGNUS_VALID_T_MIN - t_celsius) / span
    return max(0.0, 100.0 * (1 - frac))


def depression(t_air: float, t_dew: float) -> float:
    """
    Dew-point depression = T_air - T_dew (soft/informational, v1 helper).
    Small positive = near-saturation (fog); negative = physically impossible.
    """
    return t_air - t_dew


# ---------------------------------------------------------------------------
# Layer 1 — single-reading entrypoint
# ---------------------------------------------------------------------------

def evaluate_physics(
    reading: dict,
    previous_reading: Optional[dict] = None,
    station: Optional[dict] = None,
) -> dict:
    """
    Run all L1 checks on one reading.

    Payload contract:
        reading:  {"timestamp", "station_id", "temp_c", "pressure_hpa", "humidity_pct"}
        station:  {"lat", "lon", "elevation_m"}          (optional for alt check)
        previous: same shape as reading                   (optional for rate check)

    Returns the L1 result dict (see module docstring for `checks` shape).
    """
    result = {
        "layer": "L1",
        "station_id": reading.get("station_id"),
        "timestamp": reading.get("timestamp"),
        "predicted_anomaly": False,
        "checks": {
            "range": {},
            "dew_point": False,
            "pressure_altitude": False,
            "rate_of_change": {},
            # Informational derived values (v1 exported P_MSL/T_dew/depression
            # as extra columns; kept here so L5 can reuse without recomputing).
            "p_msl": None,
            "t_dew": None,
            "depression_c": None,
        },
        "affected_sensors": [],
        "reason": None,
    }

    reasons = []

    # --- Informational derived values (computed once, used below) ---------
    t = reading.get("temp_c")
    rh = reading.get("humidity_pct")
    p = reading.get("pressure_hpa")
    t_dew = None
    if t is not None and rh is not None and 0 < rh <= 100:
        t_dew = dew_point(t, rh)
    result["checks"]["t_dew"] = round(t_dew, 3) if t_dew is not None else None
    result["checks"]["depression_c"] = (
        round(depression(t, t_dew), 3) if t is not None and t_dew is not None else None
    )

    # --- Range + missing-value handling per sensor ------------------------
    bounds = {
        "temp_c": (TEMP_MIN_C, TEMP_MAX_C),
        "pressure_hpa": (PRESSURE_MIN_HPA, PRESSURE_MAX_HPA),
        "humidity_pct": (HUMIDITY_MIN_PCT, HUMIDITY_MAX_PCT),
    }
    for sensor in SENSOR_KEYS:
        value = reading.get(sensor)
        if value is None or (isinstance(value, float) and math.isnan(value)):
            result["checks"]["range"][sensor] = True
            result["affected_sensors"].append(sensor)
            reasons.append(f"{sensor} missing/NaN (dropout)")
            continue
        lo, hi = bounds[sensor]
        if not (lo <= value <= hi):
            result["checks"]["range"][sensor] = True
            result["affected_sensors"].append(sensor)
            reasons.append(f"{sensor}={value} outside [{lo}, {hi}]")

    # --- Dew point (only if temp + RH valid) -------------------------------
    if t is not None and rh is not None and 0 < rh <= 100:
        if t_dew is not None and t_dew > t + DEW_POINT_TOLERANCE_C:
            result["checks"]["dew_point"] = True
            result["affected_sensors"].append("humidity_pct")
            reasons.append("dew point exceeds air temperature (RH > 100%)")

    # --- Pressure-altitude consistency -------------------------------------
    # Compare raw station pressure vs the barometric-formula expected
    # pressure at this elevation. This catches misconfigured altitude or a
    # barometer stuck at sea-level readings at a high-altitude station.
    # MSL normalization is still computed (for L5 spatial reuse) but the
    # consistency check uses raw-vs-expected so real weather (low/high
    # pressure systems) doesn't trigger false positives.
    if station and p is not None and t is not None:
        elev = station.get("elevation_m")
        if elev is not None:
            p_msl = msl_pressure(p, t, elev)
            result["checks"]["p_msl"] = round(p_msl, 2)
            p_exp = expected_pressure(elev)
            if abs(p - p_exp) > PRESSURE_ALTITUDE_TOLERANCE_HPA:
                result["checks"]["pressure_altitude"] = True
                result["affected_sensors"].append("pressure_hpa")
                reasons.append(
                    f"Station pressure {p:.0f} hPa inconsistent with "
                    f"elevation {elev} m (expected ~{p_exp:.0f} hPa)"
                )

    # --- Rate of change (needs previous reading) ----------------------------
    if previous_reading:
        dt_hours = _hours_between(reading.get("timestamp"), previous_reading.get("timestamp"))
        for sensor in SENSOR_KEYS:
            curr = reading.get(sensor)
            prev = previous_reading.get(sensor)
            if curr is None or prev is None or dt_hours is None or dt_hours <= 0:
                continue
            delta = abs(curr - prev) / dt_hours
            fault_limit = RATE_FAULT[sensor]
            alert_limit = RATE_ALERT[sensor]
            if delta > fault_limit:
                result["checks"]["rate_of_change"][sensor] = {"fault": True, "alert": False}
                result["affected_sensors"].append(sensor)
                reasons.append(f"{sensor} changed {delta:.1f}/hr (fault limit {fault_limit}/hr)")
            elif delta > alert_limit:
                # Alert-candidate only (e.g. cyclone-class pressure drop):
                # record in checks so L6 fusion can see it, but do NOT add
                # to affected_sensors / predicted_anomaly — L6 decides
                # whether this is a fault or real weather via spatial context.
                result["checks"]["rate_of_change"][sensor] = {"fault": False, "alert": True}

    # --- Collapse ------------------------------------------------------------
    result["affected_sensors"] = sorted(set(result["affected_sensors"]))
    result["predicted_anomaly"] = bool(result["affected_sensors"])
    if reasons:
        result["reason"] = "; ".join(reasons)
    return result


def _hours_between(t1, t2):
    """Return |t1 - t2| in hours, or None if either timestamp is unusable."""
    try:
        ts1 = pd.to_datetime(t1)
        ts2 = pd.to_datetime(t2)
        return abs((ts1 - ts2).total_seconds()) / 3600.0
    except Exception:
        return None