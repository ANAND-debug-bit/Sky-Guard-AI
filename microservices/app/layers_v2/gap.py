"""
Layer 2 — Gap / Dropout Detection (v2)
=======================================
SkyGuard AI — microservices/app/layers_v2/gap.py

Flags readings with missing sensor values (NaN/None). This is the L2 gap
sub-module (execution order: L1 -> L3 -> L2 gap -> L2 IsoForest -> L4),
per idea-pitch/01-architecture-and-layers.md.

Semantics (from the reference ml_code.py `gap_detection`):
  - any sensor missing  -> dropout anomaly
  - ALL sensors missing -> station power cut / data-logger failure
  - subset missing      -> individual sensor fault (theft / disconnect)

Input/output contract (see AGENTS.md):
  input : plain list of reading dicts (AGENTS.md contract) — the
          DataFrame is built inside and never crosses the boundary
  output: LIST of unified payload dicts, one per input reading
          {layer, station_id, timestamp, predicted_anomaly, checks,
           affected_sensors, reason}
"""

import pandas as pd

SENSOR_KEYS = ["temp_c", "pressure_hpa", "humidity_pct"]


def detect_gaps(readings) -> list:
    """
    Run the L2 gap check on a batch of readings.

    readings : plain list of reading dicts (AGENTS.md contract).
    Returns a list of per-reading payload dicts (unified layer contract).
    """
    df = pd.DataFrame(readings)
    payloads = []

    for _, row in df.iterrows():
        missing = [
            s for s in SENSOR_KEYS if row[s] is None or pd.isna(row[s])
        ]
        is_gap = len(missing) > 0
        all_missing = len(missing) == len(SENSOR_KEYS)

        payload = {
            "layer": "L2",
            "station_id": row["station_id"],
            "timestamp": row["timestamp"],
            "predicted_anomaly": is_gap,
            "checks": {
                "gap": {s: (s in missing) for s in SENSOR_KEYS},
                "all_sensors_missing": all_missing,
            },
            "affected_sensors": missing,
            "reason": None,
        }

        if is_gap:
            if all_missing:
                payload["reason"] = (
                    "All sensors missing (NaN) — station power cut or "
                    "data-logger failure"
                )
            else:
                payload["reason"] = (
                    f"Missing value(s): {', '.join(missing)} — individual "
                    "sensor theft, disconnection, or failure"
                )

        payloads.append(payload)

    return payloads