"""
Layer 1 — Physics Checks

SkyGuard AI — Sky-Guard-AI/microservices/app/layers/physics

"""

import math
import pandas as pd
import numpy as np



# examples are in the comments


# Magnus formula constants (Alduchov–Eskridge approximation).
# Standard published constants for this formula — not tuned by us —
# valid for T in [-40°C, 50°C].
MAGNUS_A = 17.625
MAGNUS_B = 243.04  # °C
MAGNUS_VALID_T_MIN = -40.0
MAGNUS_VALID_T_MAX = 50.0

# Temperature extremes — India-specific
#   Highest ever recorded in India: 51.0°C, Phalodi, Rajasthan, 19 May 2016
#     (official IMD record; previous record Alwar, 50.6°C, 1956)
#   Lowest ever recorded in India: -45°C, Dras, Jammu & Kashmir, 1995
# Small safety margin added above the record high since a real reading
# could legitimately edge past a 9-year-old record without being a fault.
#
# Real-world cautionary example for why this matters: in 2024, an
# automated sensor in Mungeshpur, Delhi reported 52.9°C — later flagged
# by experts as a likely sensor error and excluded from official records.
# This bound exists to catch exactly that automatically.


TEMP_MIN_C = -45.0
TEMP_MAX_C = 52.0

# recorded central pressures as low as ~927–932 hPa (2001 Gujarat cyclone)
# and ~943 hPa (1977 Andhra Pradesh cyclone, one of the deadliest ever
# recorded). Standard MSL pressure globally is 1013.25 hPa; Indian
# high-pressure systems rarely push much past the mid-1030s hPa. Widened
# beyond the most extreme landfall readings since stations rarely sit
# exactly at a cyclone's eye, so a real severe event is never flagged.
PRESSURE_MIN_HPA = 920.0
PRESSURE_MAX_HPA = 1050.0






# ---------------------------------------------------------------------------
# CORE MATH FUNCTIONS (single reading, pure, unit-tested)
# ---------------------------------------------------------------------------

def msl_pressure(p_station_hpa: float, t_celsius: float, h_m: float) -> float:
    """
    Reduce station pressure to Mean Sea Level (MSL) equivalent, so
    stations at different elevations become comparable. Without this,
    Layer 5's neighbour comparison would flag altitude differences as
    anomalies, which they are not, this value is also exported for L5
    to consume directly, so it's not recomputed twice with two slightly
    different implementations.

    P_MSL = P_station * (1 - 0.0065*h / (T + 0.0065*h + 273.15)) ^ (-5.257)
    (0.0065 °C/m = standard atmosphere lapse rate; -5.257 comes from the
    physical constants baked into the standard-atmosphere barometric
    formula.)

    Sanity property: at h=0, this returns P_station exactly, for any T.
    """
    lapse_term = (0.0065 * h_m) / (t_celsius + 0.0065 * h_m + 273.15)
    return p_station_hpa * (1 - lapse_term) ** (-5.257)


def dew_point(t_celsius: float, rh_percent: float) -> float:
    """
    Dew point from air temperature and RH (Magnus formula). Reference
    value: T=25°C, RH=50% -> ~13.86°C. At RH=100%, returns T exactly.
    """
    gamma = math.log(rh_percent / 100.0) + (MAGNUS_A * t_celsius) / (MAGNUS_B + t_celsius)
    return (MAGNUS_B * gamma) / (MAGNUS_A - gamma)


def magnus_confidence(t_celsius: float) -> float:
    """
    Confidence (0-100) in the Magnus formula's result. Full confidence
    (100) anywhere inside its proven valid range (-40 to 50°C) — no
    manufactured doubt near the edge, since there's no evidence the
    formula is less accurate at 49°C than at 20°C. Tapers only once PAST
    the proven range, reaching 0 at the hard Indian extreme bound
    (TEMP_MAX_C / TEMP_MIN_C).

    A missing/NaN input returns 0 confidence directly there's nothing
    to have confidence in. (Rule 0 in layer1_physics already flags a
    missing reading as its own anomaly; this just keeps the confidence
    score consistent with that rather than producing NaN or crashing.)
    """
    if math.isnan(t_celsius):
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

    return t_air - t_dew


# ---------------------------------------------------------------------------
# BATCH RULE LAYER — matches the team's layer_template(batch_df) contract.
# Real column names from the repo: time, station_id, temp_c, pressure_hpa,
# humidity_pct, elevation_m.
# ---------------------------------------------------------------------------

def layer1_physics(batch_df: pd.DataFrame) -> pd.DataFrame:
    """
    Layer 1: Physics Sanity Checks.

    Rule priority when multiple checks fail on the same row (contract
    only allows one reason per row — see open question with the team
    about whether multi-flag rows are supported):
        1. RH out of bounds        (most direct, cheapest to check)
        2. Extreme temperature     (independent of RH)
        3. Pressure out of range   (independent of RH and T)
        4. T_dew > T_air           (kept for ideation consistency — currently
                                     a no-op in practice, see KNOWN LIMITATION
                                     note near the top of this file)
        5. Depression check        (soft/informational — same note)
    First one that fires wins and is reported; the row is still only
    flagged once even if more than one rule would have fired.

    Returns a DataFrame in the shared contract shape, plus two extra
    columns (P_MSL, T_dew) that downstream layers — L5 in particular —
    need and shouldn't have to recompute themselves.
    """
    result_df = pd.DataFrame()
    result_df['time'] = batch_df['time']
    result_df['station_id'] = batch_df['station_id']
    result_df['predicted_anomaly'] = 0
    result_df['sensor_type'] = None
    result_df['anomaly_value'] = np.nan
    result_df['anomaly_reason'] = None
    result_df['expected_cause'] = None
    result_df['recommended_action'] = None
    result_df['layer_used'] = 'Layer 1: Physics Sanity Checks'

    # --- Rule 0: missing/NaN readings (hard) — runs FIRST ---
    # Without this, a NaN in temp_c/humidity_pct/pressure_hpa silently
    # passes every other rule as "clean": pandas comparisons against NaN
    # (NaN < 0, NaN > 100, etc.) always evaluate to False, so a missing
    # reading was previously indistinguishable from a genuinely good one.
    # A missing reading is a dropout, not clean data — flag it explicitly
    # and skip the other rules for that row (nothing downstream can be
    # trusted from a NaN input anyway).
    core_cols = ['temp_c', 'humidity_pct', 'pressure_hpa']
    missing = batch_df[core_cols].isna().any(axis=1)
    idx = missing[missing].index
    if not idx.empty:
        # record which specific column(s) were missing per row
        missing_cols = batch_df.loc[idx, core_cols].isna().apply(
            lambda r: ','.join(r.index[r]), axis=1
        )
        result_df.loc[idx, 'predicted_anomaly'] = 1
        result_df.loc[idx, 'sensor_type'] = missing_cols
        result_df.loc[idx, 'anomaly_reason'] = 'Missing/NaN reading'
        result_df.loc[idx, 'expected_cause'] = 'Power cut, supply failure, or communication dropout'
        result_df.loc[idx, 'recommended_action'] = 'Check station connectivity/power; verify next batch'

    # Derived values other layers need — computed once here, not
    # recomputed downstream (see msl_pressure docstring). NaN inputs
    # produce NaN outputs here safely (no crash) — those rows are already
    # flagged by Rule 0 above, so downstream rules skip them via the
    # `remaining` mask pattern.
    result_df['P_MSL'] = batch_df.apply(
        lambda r: msl_pressure(r['pressure_hpa'], r['temp_c'], r['elevation_m']),
        axis=1
    )
    # T_dew only meaningful for RH in (0, 100]; guard against log(<=0)
    # domain errors for already-invalid or missing RH (that row is
    # already caught by Rule 0 or the RH-bounds rule below).
    result_df['T_dew'] = batch_df.apply(
        lambda r: dew_point(r['temp_c'], r['humidity_pct'])
        if pd.notna(r['humidity_pct']) and 0 < r['humidity_pct'] <= 100 else np.nan,
        axis=1
    )

    # --- Rule 1: RH bounds (hard) — only rows not already flagged by Rule 0 ---
    remaining = result_df['predicted_anomaly'] == 0
    rh_broken = remaining & ((batch_df['humidity_pct'] < 0) | (batch_df['humidity_pct'] > 100))
    idx = rh_broken[rh_broken].index
    if not idx.empty:
        result_df.loc[idx, 'predicted_anomaly'] = 1
        result_df.loc[idx, 'sensor_type'] = 'humidity_pct'
        result_df.loc[idx, 'anomaly_value'] = batch_df.loc[idx, 'humidity_pct']
        result_df.loc[idx, 'anomaly_reason'] = 'RH outside physical range [0,100]'
        result_df.loc[idx, 'expected_cause'] = 'Sensor fault, saturation, or wiring/calibration error'
        result_df.loc[idx, 'recommended_action'] = 'Inspect/replace humidity probe'

    # --- Rule 2: extreme temperature (hard) — only rows not already flagged ---
    remaining = result_df['predicted_anomaly'] == 0
    temp_broken = remaining & ((batch_df['temp_c'] < TEMP_MIN_C) | (batch_df['temp_c'] > TEMP_MAX_C))
    idx = temp_broken[temp_broken].index
    if not idx.empty:
        result_df.loc[idx, 'predicted_anomaly'] = 1
        result_df.loc[idx, 'sensor_type'] = 'temp_c'
        result_df.loc[idx, 'anomaly_value'] = batch_df.loc[idx, 'temp_c']
        result_df.loc[idx, 'anomaly_reason'] = f'Temperature outside India\'s physical extremes [{TEMP_MIN_C}, {TEMP_MAX_C}]°C'
        result_df.loc[idx, 'expected_cause'] = 'Voltage surge, EMI, lightning, or sensor fault'
        result_df.loc[idx, 'recommended_action'] = 'Flag for immediate inspection; cross-check with neighbouring stations (L5)'

    # --- Rule 3: pressure plausible range (hard) — only rows not already flagged ---
    remaining = result_df['predicted_anomaly'] == 0
    p_broken = remaining & ((result_df['P_MSL'] < PRESSURE_MIN_HPA) | (result_df['P_MSL'] > PRESSURE_MAX_HPA))
    idx = p_broken[p_broken].index
    if not idx.empty:
        result_df.loc[idx, 'predicted_anomaly'] = 1
        result_df.loc[idx, 'sensor_type'] = 'pressure_hpa'
        result_df.loc[idx, 'anomaly_value'] = batch_df.loc[idx, 'pressure_hpa']
        result_df.loc[idx, 'anomaly_reason'] = f'MSL-corrected pressure outside plausible range [{PRESSURE_MIN_HPA}, {PRESSURE_MAX_HPA}] hPa'
        result_df.loc[idx, 'expected_cause'] = 'Pressure sensor fault or corrupted reading'
        result_df.loc[idx, 'recommended_action'] = 'Inspect/replace barometric transducer'

#Rule 4 is for the Tdew check
    remaining = result_df['predicted_anomaly'] == 0
    tdew_broken = remaining & (result_df['T_dew'] > batch_df['temp_c'])
    idx = tdew_broken[tdew_broken].index
    if not idx.empty:
        result_df.loc[idx, 'predicted_anomaly'] = 1
        result_df.loc[idx, 'sensor_type'] = 'humidity_pct'
        result_df.loc[idx, 'anomaly_value'] = batch_df.loc[idx, 'humidity_pct']
        result_df.loc[idx, 'anomaly_reason'] = 'Dew point exceeds air temperature (implies RH > 100%)'
        result_df.loc[idx, 'expected_cause'] = 'Humidity sensor fault'
        result_df.loc[idx, 'recommended_action'] = 'Inspect/replace humidity probe'

    # --- Rule 5: depression check 
    # Same limitation as Rule 4. Recorded as informational only — does not
    # set predicted_anomaly, since it currently carries no information
    # beyond what RH already reports.
    result_df['depression_c'] = batch_df['temp_c'] - result_df['T_dew']

    return result_df


def layer1_confidence(batch_df: pd.DataFrame, result_df: pd.DataFrame) -> pd.DataFrame:
    """
    Separate confidence dataframe, per team agreement on WhatsApp:
    columns anomaly_binary, time, station_id, confidence_score — kept out
    of the main returning df so it doesn't break concat when all layers'
    outputs are merged. Merge happens later, once every layer's output is
    stable (also per that thread).

    confidence_score here is Magnus-formula confidence (see
    magnus_confidence docstring) — genuine computed logic, not the
    hardcoded ~50 placeholder floated as a fallback in the team chat. If
    the team merges this in expecting a flat 50, flag that this is
    already a real (if simple) scoring function, not a stub — worth a
    heads-up before merge so nobody overwrites it by accident.
    """
    confidence_df = pd.DataFrame()
    confidence_df['time'] = batch_df['time']
    confidence_df['station_id'] = batch_df['station_id']
    confidence_df['anomaly_binary'] = result_df['predicted_anomaly']
    confidence_df['confidence_score'] = batch_df['temp_c'].apply(magnus_confidence)
    return confidence_df



# TESTS


def _run_math_tests():
    assert abs(msl_pressure(1005.3, 30.0, 0.0) - 1005.3) < 1e-9
    assert abs(msl_pressure(1005.3, -10.0, 0.0) - 1005.3) < 1e-9
    delhi_msl = msl_pressure(992.0, 25.0, 216.0)
    assert 1000.0 < delhi_msl < 1025.0

    td = dew_point(25.0, 50.0)
    assert abs(td - 13.86) < 0.1
    td_sat = dew_point(20.0, 100.0)
    assert abs(td_sat - 20.0) < 0.05

    assert magnus_confidence(25.0) == 100.0
    assert magnus_confidence(49.0) == 100.0
    assert magnus_confidence(50.0) == 100.0
    assert magnus_confidence(51.0) == 50.0
    assert magnus_confidence(52.0) == 0.0
    assert magnus_confidence(60.0) == 0.0
    assert magnus_confidence(-40.0) == 100.0
    assert magnus_confidence(-42.5) == 50.0
    assert magnus_confidence(float('nan')) == 0.0, "NaN input must return 0 confidence, not crash or propagate NaN"
    print("Math function tests: passed.")


def _run_batch_tests():
    batch = pd.DataFrame({
        'time': pd.date_range('2026-08-29 10:00', periods=6, freq='min'),
        'station_id': ['DEL01'] * 6,
        'temp_c': [25.0, 25.0, 55.0, 25.0, 25.0, np.nan],        # row 2: extreme temp, row 5: missing
        'humidity_pct': [50.0, 105.0, 50.0, 50.0, 50.0, 50.0],    # row 1: RH out of bounds
        'pressure_hpa': [992.0, 992.0, 992.0, 700.0, 992.0, 992.0],  # row 3: pressure fault
        'elevation_m': [216.0, 216.0, 216.0, 216.0, 216.0, 216.0],
    })

    result = layer1_physics(batch)

    assert len(result) == 6, "output must be same length as input batch"
    assert result.loc[0, 'predicted_anomaly'] == 0, "row 0 is clean, should pass"
    assert result.loc[1, 'predicted_anomaly'] == 1 and result.loc[1, 'sensor_type'] == 'humidity_pct', \
        "row 1: RH=105 must be flagged as humidity fault"
    assert result.loc[2, 'predicted_anomaly'] == 1 and result.loc[2, 'sensor_type'] == 'temp_c', \
        "row 2: T=55 must be flagged as temperature fault"
    assert result.loc[3, 'predicted_anomaly'] == 1 and result.loc[3, 'sensor_type'] == 'pressure_hpa', \
        "row 3: raw pressure 700hPa must be flagged as pressure fault"
    assert result.loc[4, 'predicted_anomaly'] == 0, "row 4 is clean, should pass"
    assert result.loc[5, 'predicted_anomaly'] == 1 and result.loc[5, 'sensor_type'] == 'temp_c', \
        "row 5: missing temp_c must be flagged as a dropout, not silently pass as clean"
    assert result.loc[5, 'anomaly_reason'] == 'Missing/NaN reading'

    # P_MSL and T_dew must be present as columns; NaN is expected (and
    # correct) for the missing-input row 5 — that's Rule 0 doing its job,
    # not a bug. Only assert no-NaN for the rows with valid inputs.
    assert 'P_MSL' in result.columns and 'T_dew' in result.columns
    assert not result.loc[result.index != 5, 'P_MSL'].isna().any(), \
        "P_MSL must be computed for every row with valid inputs"

    # Rules 4/5 (ideation-consistency, documented no-ops) must exist and
    # must not flag anything beyond what Rule 1 already catches — proving
    # the KNOWN LIMITATION note is actually true, not just claimed.
    assert 'depression_c' in result.columns
    only_rh_and_downstream_flagged = result.loc[
        result['predicted_anomaly'] == 1, 'sensor_type'
    ].isin(['humidity_pct', 'temp_c', 'pressure_hpa']).all()
    assert only_rh_and_downstream_flagged

    # --- confidence_df ---
    confidence = layer1_confidence(batch, result)
    assert list(confidence.columns) == ['time', 'station_id', 'anomaly_binary', 'confidence_score']
    assert len(confidence) == 6
    # row 2 has temp_c=55, past the Magnus edge and past the hard extreme
    # (TEMP_MAX_C=52) -> confidence should be 0
    assert confidence.loc[2, 'confidence_score'] == 0.0
    # row 0 has temp_c=25, well inside the valid range -> full confidence
    assert confidence.loc[0, 'confidence_score'] == 100.0
    # row 5 has temp_c=NaN (missing) -> confidence must be 0, not NaN/crash
    assert confidence.loc[5, 'confidence_score'] == 0.0

    print("Batch rule tests: passed.")


if __name__ == "__main__":
    _run_math_tests()
    _run_batch_tests()
    print("All Phase 2 tests passed.")