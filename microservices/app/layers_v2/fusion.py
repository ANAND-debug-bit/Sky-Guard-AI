"""
Layer 6 — Fusion / Final Decision (v2)
=======================================
SkyGuard AI — microservices/app/layers_v2/fusion.py

Combines the model-layer flags (L1 physics, L2 gap+ML, L3 frozen, L4
forecast) with L5 spatial agreement into one verdict, per the plan's
decision matrix (idea-pitch/06-fault-classification.md):

    Model flags? | Neighbours agree? | Verdict
    ------------ | ----------------- | -----------------------------
    yes          | no                | SENSOR_FAULT (high conf)
    yes          | yes               | REGIONAL_EVENT (med conf, alert)
    no           | no                | CHECK_HEALTH (low conf)
    no           | yes               | HEALTHY

Spatial that could not evaluate (isolated station) is kept as an honest
fifth state — VERDICT_INSUFFICIENT_SPATIAL — not forced into agree/
disagree (reference fusion.py behaviour, kept).

Confidence tiers (idea-pitch/05-explainability-xai.md):
  HIGH   >=2 model layers flag AND neighbours disagree
  MEDIUM 1 layer flags AND neighbours disagree; OR >=2 flag AND agree
  LOW    no model flag but spatial disagrees

Root-cause priority when multiple layers fire (plan: Frozen > Physics >
Forecast > ML): L3 > L1 > L4 > L2.

Input/output contract (see AGENTS.md):
  input : each of l1..l5 is a plain LIST of unified payload dicts from the
          corresponding layer (or None if that layer wasn't run)
  output: LIST of unified verdict payload dicts, one per unique
          (station_id, timestamp) seen across the inputs
"""

VERDICT_SENSOR_FAULT = "sensor_fault"
VERDICT_REGIONAL_EVENT = "regional_event"
VERDICT_CHECK_HEALTH = "check_health"
VERDICT_HEALTHY = "healthy"
VERDICT_INSUFFICIENT_SPATIAL = "insufficient_spatial"

VERDICT_DESCRIPTIONS = {
    VERDICT_SENSOR_FAULT: "High-confidence sensor fault",
    VERDICT_REGIONAL_EVENT: "Regional weather event (alert, not a fault)",
    VERDICT_CHECK_HEALTH: "Possible subtle drift — route for maintenance health check",
    VERDICT_HEALTHY: "Normal / no action",
    VERDICT_INSUFFICIENT_SPATIAL: (
        "Spatial layer could not corroborate (too few neighbours) — "
        "verdict based on model layers only"
    ),
}

# Root-cause priority: Frozen > Physics > Forecast > ML (plan). Gap is part
# of L2 (after physics in suspicion order); both L2 sub-modules share rank.
LAYER_PRIORITY = ["L3", "L1", "L4", "L2", "L2Gap"]

# Simple fault-type label per layer (plan fault taxonomy).
FAULT_TYPE_BY_LAYER = {
    "L1": "physics",
    "L2": "ml_anomaly",
    "L3": "frozen_sensor",
    "L4": "forecast_deviation",
}

# Gap sub-module lives under L2 (checks.gap); a payload that carries it is a
# dropout fault, not a multivariate ML anomaly.
GAP_LAYER_ID = "L2Gap"

# Verdicts that trigger an actual alert.
ALERT_VERDICTS = (VERDICT_SENSOR_FAULT, VERDICT_REGIONAL_EVENT)


def _key(payload: dict):
    """Join key: (station_id, timestamp)."""
    return (payload["station_id"], payload["timestamp"])


def _spatial_agreement(spatial_payload: dict):
    """
    Return (evaluable, neighbours_agree) from an L5 payload.
    neighbours_agree = both temp and pressure agree; None if not evaluable.
    """
    s = spatial_payload["checks"].get("spatial", {})
    if not s.get("evaluable"):
        return False, None
    agree = bool(s.get("temp_agree")) and bool(s.get("pressure_agree"))
    return True, agree


def fuse(l1=None, l2=None, l2_gap=None, l3=None, l4=None, l5=None) -> list:
    """
    l1, l2, l3, l4  : lists of unified payload dicts (or None if not run).
    l2_gap          : L2 gap/dropout payloads (or None). Passed separately so
                      fusion can classify a dropout as "gap" rather than the
                      generic ML anomaly label.
    l5              : list of L5 spatial payload dicts (or None).
    Returns a list of verdict payload dicts (unified layer contract).
    """
    # Gap is a distinct L2 sub-module; keep its own layer id for
    # contributing_layers and fault_type, but count it among L2 flags.
    layers = {
        "L1": l1 or [],
        "L2": l2 or [],
        "L2Gap": l2_gap or [],
        "L3": l3 or [],
        "L4": l4 or [],
    }
    spatial_by_key = {_key(p): p for p in (l5 or [])}

    # Union of every (station_id, timestamp) seen across the layers.
    all_keys = set()
    for layer_payloads in layers.values():
        all_keys.update(_key(p) for p in layer_payloads)
    all_keys.update(spatial_by_key.keys())

    verdicts = []
    for key in sorted(all_keys):
        station_id, timestamp = key

        # Model layers that fired on this row.
        fired = [
            layer_id
            for layer_id, payloads in layers.items()
            for p in payloads
            if _key(p) == key and p["predicted_anomaly"]
        ]

        # Spatial context.
        spatial = spatial_by_key.get(key)
        spatial_evaluable, neighbours_agree = (
            _spatial_agreement(spatial) if spatial is not None else (False, None)
        )

        # ---- Verdict matrix -------------------------------------------------
        # When spatial can't evaluate (isolated station) and no model layer
        # fired, the station is HEALTHY — not a false-positive alert.
        # When spatial can't evaluate but model layers *did* fire, we keep
        # INSUFFICIENT_SPATIAL so the operator knows the verdict lacks
        # spatial corroboration.
        if not spatial_evaluable and not fired:
            verdict = VERDICT_HEALTHY
        elif not spatial_evaluable and fired:
            verdict = VERDICT_INSUFFICIENT_SPATIAL
        elif fired and not neighbours_agree:
            verdict = VERDICT_SENSOR_FAULT
        elif fired and neighbours_agree:
            verdict = VERDICT_REGIONAL_EVENT
        elif not fired and not neighbours_agree:
            verdict = VERDICT_CHECK_HEALTH
        else:
            verdict = VERDICT_HEALTHY

        # ---- Confidence tier -----------------------------------------------
        n_fired = len(fired)
        if verdict == VERDICT_SENSOR_FAULT:
            confidence = "HIGH" if n_fired >= 2 else "MEDIUM"
        elif verdict == VERDICT_REGIONAL_EVENT:
            confidence = "MEDIUM" if n_fired >= 2 else "LOW"
        elif verdict == VERDICT_CHECK_HEALTH:
            confidence = "LOW"
        elif verdict == VERDICT_INSUFFICIENT_SPATIAL:
            confidence = "HIGH" if n_fired >= 2 else ("MEDIUM" if n_fired == 1 else "LOW")
        else:  # healthy
            confidence = None

        # ---- Primary explanation (root-cause priority) ---------------------
        # L2Gap outranks L2 (dropout is more specific than a generic ML flag).
        primary_layer = next(
            (lid for lid in LAYER_PRIORITY if lid in fired), None
        )
        fault_type = FAULT_TYPE_BY_LAYER.get(primary_layer) if primary_layer else None
        # L2Gap maps to the "gap" fault type (dropout), not generic ML.
        if primary_layer == GAP_LAYER_ID:
            fault_type = "gap"

        # Reason text per verdict.
        if verdict == VERDICT_SENSOR_FAULT:
            reason = (
                f"{n_fired} model layer(s) flagged this station while neighbours "
                "disagree — likely a sensor fault"
            )
        elif verdict == VERDICT_REGIONAL_EVENT:
            reason = (
                f"{n_fired} model layer(s) flagged this station and neighbours "
                "agree — likely a real regional weather event"
            )
        elif verdict == VERDICT_CHECK_HEALTH:
            reason = (
                "No model layer flagged, but station disagrees with neighbours — "
                "possible early-stage drift/decalibration"
            )
        elif verdict == VERDICT_INSUFFICIENT_SPATIAL:
            reason = (
                (
                    f"Spatial cross-check unavailable (isolated station); "
                    f"{n_fired} model layer(s) flagged"
                )
                if n_fired
                else "Spatial cross-check unavailable (isolated station); no model layer flagged"
            )
        else:
            reason = None

        # Affected sensors: union from fired layers.
        affected = []
        for layer_id, payloads in layers.items():
            for p in payloads:
                if _key(p) == key and p["predicted_anomaly"]:
                    affected.extend(p["affected_sensors"])
        affected = sorted(set(affected))

        verdicts.append(
            {
                "layer": "L6",
                "station_id": station_id,
                "timestamp": timestamp,
                # Any model-layer flag is an anomaly, even when spatial cannot
                # corroborate (reference fusion: "model flags still drive
                # predicted_anomaly"). CHECK_HEALTH/HEALTHY have no flag.
                "predicted_anomaly": bool(fired),
                "checks": {
                    "fusion": {
                        "model_flagged": bool(fired),
                        "contributing_layers": sorted(fired),
                        "spatial_evaluable": spatial_evaluable,
                        "neighbours_agree": neighbours_agree,
                        "verdict": verdict,
                        "verdict_description": VERDICT_DESCRIPTIONS[verdict],
                        "confidence": confidence,
                        "fault_type": fault_type,
                    }
                },
                "affected_sensors": affected,
                "reason": reason,
            }
        )

    return verdicts