"""
Layer 6 — Fusion / Final Decision
===================================
SkyGuard AI — microservices/app/layers/fusion/fusion.py

Combines "Model Flags" from Layers 1–4 (Physics, ML, Frozen, Forecasting)
with Layer 5's spatial agreement into a single final verdict, per the
team's truth table:

    Model Flags | Neighbours Agree (low spatial z) | Verdict
    ----------- | --------------------------------- | -----------------------------
         Y      |                N                  | High-confidence sensor fault
         Y      |                Y                  | Regional weather event
         N      |                N                  | Low-confidence corner case (health check)
         N      |                Y                  | Normal / no action

"Model Flags" = ANY of L1–L4 set predicted_anomaly == 1 for that
(time, station_id).

"Neighbours Agree" = L5 did NOT flag the row (predicted_anomaly == 0)
*and* had enough neighbours to actually make the call
(spatial_evaluable == True — see spatial.py's MIN_NEIGHBORS_REQUIRED).

That last clause matters: spatial.py is explicit that stations like
SHI001/SXR001 can have too few neighbours to evaluate at all. Collapsing
that into either "Agree" or "Disagree" would silently misrepresent what
L5 actually knows. So fusion treats "cannot evaluate" as a fifth, honest
state — VERDICT_INSUFFICIENT_SPATIAL — rather than forcing it into the
4-cell table. Model flags still drive predicted_anomaly in that case;
we just can't corroborate (or rule out) a regional event.
"""

import numpy as np
import pandas as pd


# ── Verdict labels ──────────────────────────────────────────────────────
VERDICT_SENSOR_FAULT = "high_confidence_sensor_fault"
VERDICT_REGIONAL_EVENT = "regional_weather_event"
VERDICT_LOW_CONFIDENCE = "low_confidence_corner_case"
VERDICT_NORMAL = "normal"
VERDICT_INSUFFICIENT_SPATIAL = "insufficient_spatial_data"

# Human-readable descriptions, so callers (e.g. the frontend/backend)
# don't have to hardcode the truth table again.
VERDICT_DESCRIPTIONS = {
    VERDICT_SENSOR_FAULT: "High-confidence sensor fault",
    VERDICT_REGIONAL_EVENT: "Regional weather event (not a fault, but an alert)",
    VERDICT_LOW_CONFIDENCE: "Generally healthy — low-confidence corner case, route for maintenance/health check",
    VERDICT_NORMAL: "Normal / no action",
    VERDICT_INSUFFICIENT_SPATIAL: "Spatial layer could not corroborate (too few neighbours) — verdict based on model layers only",
}

# Priority order for picking which model layer's diagnosis (sensor_type,
# anomaly_reason, expected_cause, recommended_action) becomes the PRIMARY
# explanation when more than one L1–L4 layer fires on the same row.
# Physics first (hardest, most direct physical impossibility), then
# Frozen (unambiguous stuck-sensor signature), then ML (statistical,
# SHAP-explained), then Forecasting (statistical, softest signal).
LAYER_PRIORITY = [
    "Layer 1: Physics Sanity Checks",
    "Layer 3: Frozen Sensor Detection",
    "Layer 2: ML (Isolation Forest + SHAP)",
    "FORECASTING",
]

CONTRACT_COLS = [
    "time", "station_id", "predicted_anomaly", "sensor_type",
    "anomaly_value", "anomaly_reason", "expected_cause",
    "recommended_action", "layer_used",
]

FUSION_OUTPUT_COLS = CONTRACT_COLS + [
    "model_flagged", "contributing_layers",
    "spatial_evaluable", "spatial_flagged", "neighbor_count",
    "spatial_z_temp", "spatial_z_pressure", "verdict", "verdict_description",
]


# ── Normalization helpers ────────────────────────────────────────────────

def _prep_model_layer(df: pd.DataFrame | None, fallback_label: str) -> pd.DataFrame:
    """
    Normalize one L1-L4 output to the shared contract columns, ready to
    key by (time, station_id). A missing/empty layer becomes an empty
    frame — fusion treats an omitted layer as "not run", never as "clean",
    by simply not counting it (see layer6_fusion's docstring).
    """
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=CONTRACT_COLS)
    out = df.copy()
    for col in CONTRACT_COLS:
        if col not in out.columns:
            out[col] = np.nan if col in ("predicted_anomaly", "anomaly_value") else None
    out["predicted_anomaly"] = out["predicted_anomaly"].fillna(0).astype(int)
    out["layer_used"] = out["layer_used"].fillna(fallback_label)
    return out[CONTRACT_COLS]


def _index_by_key(df: pd.DataFrame) -> dict:
    """(time, station_id) -> namedtuple row, for O(1) lookup during fusion."""
    if df.empty:
        return {}
    return {(r.time, r.station_id): r for r in df.itertuples(index=False)}


# ── Core fusion ───────────────────────────────────────────────────────────

def layer6_fusion(l1_df: pd.DataFrame | None = None,
                   l2_df: pd.DataFrame | None = None,
                   l3_df: pd.DataFrame | None = None,
                   l4_df: pd.DataFrame | None = None,
                   l5_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Layer 6: Fusion.

    Parameters
    ----------
    l1_df, l2_df, l3_df, l4_df : output of layer1_physics(), the ML
        isolation_forest_shap(), layer3_frozen_sensor(), and the
        forecasting layer respectively — each already in the shared
        contract shape (time, station_id, predicted_anomaly, ...).
        Any may be omitted (None/empty) if that layer wasn't run for
        this batch; the row is then judged on whichever layers WERE
        supplied, plus L5.
    l5_df : output of spatial.layer5_spatial(). Required to apply the
        truth table — if omitted, every row falls back to
        VERDICT_INSUFFICIENT_SPATIAL (model flags still drive
        predicted_anomaly).

    Returns
    -------
    pd.DataFrame with one row per (time, station_id) seen across any
    input, with the shared contract columns PLUS:
        model_flagged       : bool   — did ANY of L1-L4 flag this row
        contributing_layers : str    — comma-joined layer_used values that fired
        spatial_evaluable   : bool   — passthrough from L5
        spatial_flagged     : bool   — L5's own predicted_anomaly, passthrough
        neighbor_count       : int    — passthrough from L5
        spatial_z_temp        : float — passthrough from L5 (debugging/audit)
        spatial_z_pressure    : float — passthrough from L5 (debugging/audit)
        verdict               : one of the VERDICT_* constants above
        verdict_description   : human-readable string for the verdict
    """
    model_layers = [
        _prep_model_layer(l1_df, "Layer 1: Physics Sanity Checks"),
        _prep_model_layer(l2_df, "Layer 2: ML (Isolation Forest + SHAP)"),
        _prep_model_layer(l3_df, "Layer 3: Frozen Sensor Detection"),
        _prep_model_layer(l4_df, "FORECASTING"),
    ]
    l5_df = l5_df if l5_df is not None else pd.DataFrame()

    # Union of every (time, station_id) seen ANYWHERE, so a row isn't
    # silently dropped just because one layer didn't emit it for this key.
    key_frames = [df[["time", "station_id"]] for df in model_layers if not df.empty]
    if not l5_df.empty:
        key_frames.append(l5_df[["time", "station_id"]])

    if not key_frames:
        return pd.DataFrame(columns=FUSION_OUTPUT_COLS)

    all_keys = pd.concat(key_frames, ignore_index=True).drop_duplicates()

    indexed_layers = [_index_by_key(df) for df in model_layers]
    l5_indexed = _index_by_key(l5_df)

    rows = []
    for key_row in all_keys.itertuples(index=False):
        key = (key_row.time, key_row.station_id)

        # Which model layers fired on this row
        fired = [
            layer_idx[key]
            for layer_idx in indexed_layers
            if key in layer_idx and layer_idx[key].predicted_anomaly == 1
        ]
        model_flagged = len(fired) > 0
        contributing_layers = (
            ", ".join(sorted({r.layer_used for r in fired})) if fired else None
        )

        # Pick the primary explanation by LAYER_PRIORITY
        primary = None
        for wanted in LAYER_PRIORITY:
            match = next((r for r in fired if r.layer_used == wanted), None)
            if match is not None:
                primary = match
                break
        if primary is None and fired:
            primary = fired[0]

        # Spatial context for this row
        l5_row = l5_indexed.get(key)
        spatial_evaluable = bool(l5_row.spatial_evaluable) if l5_row is not None else False
        spatial_flagged = bool(l5_row.predicted_anomaly == 1) if l5_row is not None else False
        spatial_z_temp = getattr(l5_row, "temp_z", np.nan) if l5_row is not None else np.nan
        spatial_z_pressure = getattr(l5_row, "pressure_z", np.nan) if l5_row is not None else np.nan
        neighbor_count = getattr(l5_row, "neighbor_count", 0) if l5_row is not None else 0

        # ── Verdict per the team's truth table ──────────────────────────
        if l5_row is None or not spatial_evaluable:
            verdict = VERDICT_INSUFFICIENT_SPATIAL
        elif model_flagged and spatial_flagged:
            verdict = VERDICT_SENSOR_FAULT
        elif model_flagged and not spatial_flagged:
            verdict = VERDICT_REGIONAL_EVENT
        elif not model_flagged and spatial_flagged:
            verdict = VERDICT_LOW_CONFIDENCE
        else:
            verdict = VERDICT_NORMAL

        # ── Explanation fields ───────────────────────────────────────────
        # Sensor fault / regional event / insufficient-spatial-but-flagged:
        # explain via whichever model layer fired (physics > frozen > ML > forecast).
        if primary is not None:
            sensor_type = primary.sensor_type
            anomaly_value = primary.anomaly_value
            anomaly_reason = primary.anomaly_reason
            expected_cause = primary.expected_cause
            recommended_action = primary.recommended_action
        # Low-confidence corner case: no model layer fired, but L5 alone did —
        # surface L5's own diagnosis instead of leaving the row blank.
        elif verdict == VERDICT_LOW_CONFIDENCE and l5_row is not None:
            sensor_type = l5_row.sensor_type
            anomaly_value = l5_row.anomaly_value
            anomaly_reason = l5_row.anomaly_reason
            expected_cause = "No model layer corroborates a fault; possible early-stage drift/decalibration"
            recommended_action = "Route to maintenance for a health-check inspection (not an immediate fault alert)"
        else:
            sensor_type = None
            anomaly_value = np.nan
            anomaly_reason = None
            expected_cause = None
            recommended_action = None

        # Regional event / insufficient-spatial context note, appended
        # without overwriting the model layer's own reasoning.
        if verdict == VERDICT_REGIONAL_EVENT and anomaly_reason:
            anomaly_reason = f"{anomaly_reason} — neighbours agree, likely a real regional weather event, not a fault"
        elif verdict == VERDICT_INSUFFICIENT_SPATIAL and model_flagged and anomaly_reason:
            anomaly_reason = f"{anomaly_reason} — spatial cross-check unavailable ({neighbor_count} neighbour(s)); verify manually"

        rows.append({
            "time": key_row.time,
            "station_id": key_row.station_id,
            "predicted_anomaly": int(model_flagged),
            "sensor_type": sensor_type,
            "anomaly_value": anomaly_value,
            "anomaly_reason": anomaly_reason,
            "expected_cause": expected_cause,
            "recommended_action": recommended_action,
            "layer_used": "Layer 6: Fusion",
            "model_flagged": model_flagged,
            "contributing_layers": contributing_layers,
            "spatial_evaluable": spatial_evaluable,
            "spatial_flagged": spatial_flagged,
            "neighbor_count": neighbor_count,
            "spatial_z_temp": spatial_z_temp,
            "spatial_z_pressure": spatial_z_pressure,
            "verdict": verdict,
            "verdict_description": VERDICT_DESCRIPTIONS[verdict],
        })

    return pd.DataFrame(rows, columns=FUSION_OUTPUT_COLS)


# ── Tests ─────────────────────────────────────────────────────────────────

def _make_layer_row(time, station_id, predicted_anomaly, layer_used,
                     sensor_type=None, reason=None, cause=None, action=None):
    return pd.DataFrame([{
        "time": time, "station_id": station_id,
        "predicted_anomaly": predicted_anomaly,
        "sensor_type": sensor_type, "anomaly_value": np.nan,
        "anomaly_reason": reason, "expected_cause": cause,
        "recommended_action": action, "layer_used": layer_used,
    }])


def _make_l5_row(time, station_id, predicted_anomaly, spatial_evaluable,
                  neighbor_count, temp_z=0.0, pressure_z=0.0):
    return pd.DataFrame([{
        "time": time, "station_id": station_id,
        "predicted_anomaly": predicted_anomaly,
        "sensor_type": "temp_c" if predicted_anomaly else None,
        "anomaly_value": np.nan,
        "anomaly_reason": "Temperature disagrees with neighbours" if predicted_anomaly else None,
        "expected_cause": None, "recommended_action": None,
        "layer_used": "Layer 5: Spatial Consistency",
        "spatial_evaluable": spatial_evaluable,
        "neighbor_count": neighbor_count,
        "temp_z": temp_z, "pressure_z": pressure_z,
    }])


def _run_tests():
    t = pd.Timestamp("2026-08-29 10:00")

    # --- Case 1: Model=Y, Neighbours Agree=N -> HIGH-CONFIDENCE SENSOR FAULT ---
    l1 = _make_layer_row(t, "DEL001", 1, "Layer 1: Physics Sanity Checks",
                          sensor_type="temp_c", reason="Temp outside extremes",
                          cause="Sensor fault", action="Inspect sensor")
    l5 = _make_l5_row(t, "DEL001", 1, spatial_evaluable=True, neighbor_count=5, temp_z=4.2)
    result = layer6_fusion(l1_df=l1, l5_df=l5)
    assert len(result) == 1
    row = result.iloc[0]
    assert row["verdict"] == VERDICT_SENSOR_FAULT
    assert row["predicted_anomaly"] == 1
    assert row["sensor_type"] == "temp_c"
    assert row["contributing_layers"] == "Layer 1: Physics Sanity Checks"
    print("  \u2713 Case 1: Y,N -> high-confidence sensor fault")

    # --- Case 2: Model=Y, Neighbours Agree=Y -> REGIONAL WEATHER EVENT ---
    l2 = _make_layer_row(t, "BOM001", 1, "Layer 2: ML (Isolation Forest + SHAP)",
                          sensor_type="pressure_hpa", reason="SHAP flagged pressure_hpa",
                          cause="Multivariate deviation", action="Check calibration")
    l5b = _make_l5_row(t, "BOM001", 0, spatial_evaluable=True, neighbor_count=5, pressure_z=0.5)
    result = layer6_fusion(l2_df=l2, l5_df=l5b)
    row = result.iloc[0]
    assert row["verdict"] == VERDICT_REGIONAL_EVENT
    assert row["predicted_anomaly"] == 1
    assert "regional weather event" in row["anomaly_reason"]
    print("  \u2713 Case 2: Y,Y -> regional weather event")

    # --- Case 3: Model=N, Neighbours Agree=N -> LOW-CONFIDENCE CORNER CASE ---
    l5c = _make_l5_row(t, "NAG001", 1, spatial_evaluable=True, neighbor_count=5, temp_z=3.8)
    result = layer6_fusion(l5_df=l5c)
    row = result.iloc[0]
    assert row["verdict"] == VERDICT_LOW_CONFIDENCE
    assert row["predicted_anomaly"] == 0, "no model layer fired, so predicted_anomaly must stay 0"
    assert row["recommended_action"] == "Route to maintenance for a health-check inspection (not an immediate fault alert)"
    print("  \u2713 Case 3: N,N -> low-confidence corner case, routed for health check")

    # --- Case 4: Model=N, Neighbours Agree=Y -> NORMAL ---
    l5d = _make_l5_row(t, "HYD001", 0, spatial_evaluable=True, neighbor_count=5)
    result = layer6_fusion(l5_df=l5d)
    row = result.iloc[0]
    assert row["verdict"] == VERDICT_NORMAL
    assert row["predicted_anomaly"] == 0
    assert row["anomaly_reason"] is None
    print("  \u2713 Case 4: N,Y -> normal / no action")

    # --- Case 5: SHI001-style sparse station, model flagged, spatial can't corroborate ---
    l3 = _make_layer_row(t, "SHI001", 1, "Layer 3: Frozen Sensor Detection",
                          sensor_type="temp_c", reason="Sensor readings constant",
                          cause="Sensor jam", action="Physical inspection")
    l5e = _make_l5_row(t, "SHI001", 0, spatial_evaluable=False, neighbor_count=1)
    result = layer6_fusion(l3_df=l3, l5_df=l5e)
    row = result.iloc[0]
    assert row["verdict"] == VERDICT_INSUFFICIENT_SPATIAL
    assert row["predicted_anomaly"] == 1, "model flag must still drive predicted_anomaly even without spatial corroboration"
    assert "spatial cross-check unavailable" in row["anomaly_reason"]
    print("  \u2713 Case 5: sparse station (SHI001-like) -> insufficient_spatial_data, model flag preserved")

    # --- Case 6: no L5 input at all -> everything falls back to insufficient-spatial ---
    l1f = _make_layer_row(t, "JAI001", 1, "Layer 1: Physics Sanity Checks",
                           sensor_type="humidity_pct", reason="RH out of bounds")
    result = layer6_fusion(l1_df=l1f)  # l5_df omitted entirely
    row = result.iloc[0]
    assert row["verdict"] == VERDICT_INSUFFICIENT_SPATIAL
    assert row["predicted_anomaly"] == 1
    print("  \u2713 Case 6: no L5 at all -> insufficient_spatial_data, doesn't crash")

    # --- Case 7: priority ordering — physics beats ML when both fire ---
    l1g = _make_layer_row(t, "DEL002", 1, "Layer 1: Physics Sanity Checks",
                           sensor_type="pressure_hpa", reason="Pressure out of range")
    l2g = _make_layer_row(t, "DEL002", 1, "Layer 2: ML (Isolation Forest + SHAP)",
                           sensor_type="temp_c", reason="SHAP flagged temp_c")
    l5g = _make_l5_row(t, "DEL002", 1, spatial_evaluable=True, neighbor_count=5)
    result = layer6_fusion(l1_df=l1g, l2_df=l2g, l5_df=l5g)
    row = result.iloc[0]
    assert row["sensor_type"] == "pressure_hpa", "Physics must win priority over ML"
    assert "Layer 1" in row["contributing_layers"] and "Layer 2" in row["contributing_layers"]
    print("  \u2713 Case 7: multiple model layers fire -> physics wins priority, both listed as contributors")

    # --- Case 8: multi-row batch end-to-end, all four verdict types together ---
    l1_batch = pd.concat([l1, l1g], ignore_index=True)
    l2_batch = pd.concat([l2, l2g], ignore_index=True)
    l3_batch = l3
    l5_batch = pd.concat([l5, l5b, l5c, l5d, l5e, l5g], ignore_index=True)
    result = layer6_fusion(l1_df=l1_batch, l2_df=l2_batch, l3_df=l3_batch, l5_df=l5_batch)
    assert len(result) == 6, f"expected 6 unique (time, station) keys, got {len(result)}"
    verdicts = set(result["verdict"])
    assert VERDICT_SENSOR_FAULT in verdicts
    assert VERDICT_REGIONAL_EVENT in verdicts
    assert VERDICT_LOW_CONFIDENCE in verdicts
    assert VERDICT_NORMAL in verdicts
    assert VERDICT_INSUFFICIENT_SPATIAL in verdicts
    print("  \u2713 Case 8: multi-station batch produces all five verdict states correctly")

    print("\nAll Layer 6 (Fusion) tests passed. \u2713")


if __name__ == "__main__":
    _run_tests()