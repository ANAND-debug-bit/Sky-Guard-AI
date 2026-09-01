"""
Layer 5 — Spatial Consistency (v2)
==================================
SkyGuard AI — microservices/app/layers_v2/spatial.py

Provides CONTEXT, not detection: tells the fusion layer (L6) whether a
station's neighbours AGREE or DISAGREE at the same timestamp
(idea-pitch/01-architecture-and-layers.md L5; 02-thresholds.md).

Method (reference: microservices/app/layers/physics/spatial.py):
  - Haversine distance -> neighbours within RADIUS_KM.
  - Robust Z = |x - median(neighbours)| / (1.4826 * MAD)  (median/MAD is
    outlier-resistant, unlike mean/std).
  - Temperature is lapse-rate adjusted to a common elevation before
    comparing (else Shimla/Srinagar always look "anomalously cold").
  - Pressure compared ONLY after MSL normalization (reuses
    layers_v2.physics.msl_pressure — same formula/constants as L1).
  - Z >= Z_THRESHOLD => neighbours disagree (Met Norway TITAN default 3.1).
  - Never flags on its own: predicted_anomaly is always False; agreement
    lives in checks.spatial for L6.

Input/output contract (see AGENTS.md):
  input : readings = list of reading dicts for ALL stations at ONE
          timestamp; stations = {station_id: {lat, lon, elevation_m}}
          — the DataFrame is built inside and never crosses the boundary
  output: LIST of unified payload dicts, one per input reading
          {layer, station_id, timestamp, predicted_anomaly, checks,
           affected_sensors, reason}
"""

import math

import numpy as np
import pandas as pd

from layers_v2.physics import msl_pressure  # noqa: E402  (same constants as L1)

RADIUS_KM = 500.0           # plan: neighbour radius (03-data-sources)
MIN_NEIGHBORS_REQUIRED = 2  # TITAN wants 5, but the 15-station demo set
                            # gives most stations 1-4 (acknowledged limit)
MIN_NEIGHBORS_PREFERRED = 5  # prefer up to 5 nearest when available (v1)
Z_THRESHOLD = 3.1           # Met Norway TITAN default (02-thresholds.md)

LAPSE_RATE_C_PER_M = 0.0065
REFERENCE_ELEVATION_M = 0.0


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance between two lat/lon points, in km."""
    R = 6371.0
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lon2) - float(lon1))
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))


def robust_zscore(x: float, neighbor_values) -> float:
    """
    (x - median(neighbors)) / (1.4826 * MAD(neighbors)).
    Median/MAD so one bad neighbor doesn't distort the baseline.
    """
    neighbor_values = np.asarray(neighbor_values, dtype=float)
    med = np.median(neighbor_values)
    mad = np.median(np.abs(neighbor_values - med))
    if mad == 0:
        mad = 1e-6  # avoid divide-by-zero when all neighbors agree exactly
    return float((x - med) / (1.4826 * mad))


def _elevation_adjust_temp(t_celsius: float, h_m: float) -> float:
    """Lapse-rate adjust temperature to a common reference elevation."""
    return t_celsius + LAPSE_RATE_C_PER_M * (h_m - REFERENCE_ELEVATION_M)


def _find_neighbors(own_id: str, own_meta: dict, all_meta: dict) -> list:
    """
    Neighbours for comparison. Prefers stations within RADIUS_KM; if fewer
    than MIN_NEIGHBORS_REQUIRED exist there, falls back to the nearest
    stations overall (reference layer behaviour). Returns [] only when even
    the fallback fails (genuinely isolated station).
    """
    others = [s for s in all_meta if s != own_id]
    dists = []
    for sid in others:
        m = all_meta[sid]
        dists.append(
            (
                sid,
                haversine_km(own_meta["lat"], own_meta["lon"], m["lat"], m["lon"]),
            )
        )
    dists.sort(key=lambda x: x[1])

    within = [sid for sid, d in dists if d <= RADIUS_KM]
    if len(within) >= MIN_NEIGHBORS_REQUIRED:
        # Prefer up to MIN_NEIGHBORS_PREFERRED nearest when available (v1).
        if len(within) >= MIN_NEIGHBORS_PREFERRED:
            preferred = {sid for sid, _ in dists[:MIN_NEIGHBORS_PREFERRED]}
            return [sid for sid in within if sid in preferred]
        return within

    # Fallback: nearest stations overall (demo network is sparse).
    fallback = [sid for sid, _ in dists[:MIN_NEIGHBORS_REQUIRED]]
    return fallback if len(fallback) >= MIN_NEIGHBORS_REQUIRED else []


def evaluate_spatial(readings, stations) -> list:
    """
    Run the L5 spatial-context check for every station at one timestamp.

    readings : list of reading dicts (AGENTS.md contract), ALL stations
               at the same timestamp.
    stations : dict {station_id: {"lat": ..., "lon": ..., "elevation_m": ...}}
    Returns a list of payload dicts (unified layer contract).
    """
    df = pd.DataFrame(readings)

    # Index the snapshot by station_id for O(1) neighbor lookups. A neighbor
    # listed in `stations` may be absent from this snapshot (missing reading
    # at this timestamp) — those are skipped, not crashed on.
    row_by_station = {str(r["station_id"]): r for _, r in df.iterrows()}

    payloads = []
    for _, row in df.iterrows():
        own_id = str(row["station_id"])
        own_meta = stations.get(own_id)
        payload = {
            "layer": "L5",
            "station_id": own_id,
            "timestamp": row["timestamp"],
            "predicted_anomaly": False,  # L5 never flags on its own
            "checks": {"spatial": {}},
            "affected_sensors": [],
            "reason": None,
        }

        if own_meta is None:
            payload["checks"]["spatial"] = {
                "evaluable": False,
                "reason": "station metadata missing",
            }
            payload["reason"] = "station metadata missing — cannot evaluate"
            payloads.append(payload)
            continue

        # Guard: if the station's own sensor values are NaN, spatial
        # comparison is meaningless (can't compute z-score against neighbours).
        if pd.isna(row["temp_c"]) or pd.isna(row["pressure_hpa"]):
            payload["checks"]["spatial"] = {
                "evaluable": False,
                "reason": "own sensor values missing (NaN)",
            }
            payload["reason"] = "own sensor values missing — cannot evaluate"
            payloads.append(payload)
            continue

        neighbors = _find_neighbors(own_id, own_meta, stations)
        # Keep only neighbours that actually reported at this timestamp.
        neighbors = [nb for nb in neighbors if nb in row_by_station]
        if not neighbors:
            # Isolated station (e.g. SHI001/SXR001): assume agree, surface honestly.
            payload["checks"]["spatial"] = {
                "evaluable": False,
                "neighbor_count": 0,
                "reason": "insufficient nearby stations",
            }
            payload["reason"] = (
                "insufficient nearby stations — neighbours assumed to agree"
            )
            payloads.append(payload)
            continue

        # Temperature: lapse-adjusted, compared across neighbours.
        own_temp = _elevation_adjust_temp(
            float(row["temp_c"]), own_meta["elevation_m"]
        )
        nb_temps = []
        for nb in neighbors:
            nb_row = row_by_station[nb]
            if pd.isna(nb_row["temp_c"]):
                continue  # neighbour missing this sensor -> skip, not crash
            nb_temps.append(
                _elevation_adjust_temp(
                    float(nb_row["temp_c"]), stations[nb]["elevation_m"]
                )
            )
        if len(nb_temps) < 1:
            payload["checks"]["spatial"] = {
                "evaluable": False,
                "neighbor_count": 0,
                "reason": "neighbours missing sensor values",
            }
            payload["reason"] = "neighbours missing sensor values — cannot evaluate"
            payloads.append(payload)
            continue
        temp_z = float(robust_zscore(own_temp, nb_temps))

        # Pressure: only after MSL normalization (altitude would otherwise
        # look anomalous).
        own_p_msl = msl_pressure(
            float(row["pressure_hpa"]), float(row["temp_c"]), own_meta["elevation_m"]
        )
        nb_p_msl = []
        for nb in neighbors:
            nb_row = row_by_station[nb]
            if pd.isna(nb_row["pressure_hpa"]) or pd.isna(nb_row["temp_c"]):
                continue
            nb_p_msl.append(
                msl_pressure(
                    float(nb_row["pressure_hpa"]),
                    float(nb_row["temp_c"]),
                    stations[nb]["elevation_m"],
                )
            )
        if len(nb_p_msl) < 1:
            payload["checks"]["spatial"] = {
                "evaluable": False,
                "neighbor_count": 0,
                "reason": "neighbours missing pressure values",
            }
            payload["reason"] = "neighbours missing pressure values — cannot evaluate"
            payloads.append(payload)
            continue
        pressure_z = float(robust_zscore(own_p_msl, nb_p_msl))

        payload["checks"]["spatial"] = {
            "evaluable": True,
            "neighbor_count": len(neighbors),
            "temp_z": round(temp_z, 3),
            "pressure_z": round(pressure_z, 3),
            "temp_agree": abs(temp_z) < Z_THRESHOLD,
            "pressure_agree": abs(pressure_z) < Z_THRESHOLD,
        }
        payload["reason"] = (
            f"{len(neighbors)} neighbours: temp_z={temp_z:.2f} "
            f"({'agree' if abs(temp_z) < Z_THRESHOLD else 'disagree'}), "
            f"pressure_z={pressure_z:.2f} "
            f"({'agree' if abs(pressure_z) < Z_THRESHOLD else 'disagree'})"
        )
        payloads.append(payload)

    return payloads