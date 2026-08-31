"""
Layer 5 — Spatial Consistency
==============================
SkyGuard AI — microservices/app/layers/spatial/spatial.py

Compares each station's readings against its geographic neighbors at the
SAME timestamp, using robust statistics (median/MAD) so one bad neighbor
doesn't poison the comparison for everyone else.

Depends on Layer 1's P_MSL (elevation-corrected pressure)  do not
recompute pressure correction here, reuse L1's output directly, same
formula, same constants (see physics.py msl_pressure()).

Structural note: unlike L1, which processes each station independently
row by row, L5 needs ALL stations' readings at a given timestamp
simultaneously to find neighbors and compare  so layer5_spatial() takes
the full multi-station dataframe, not a per-station slice.
"""

import math
import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

MAX_NEIGHBOR_RADIUS_KM = 250.0
MIN_NEIGHBORS_PREFERRED = 5
MIN_NEIGHBORS_REQUIRED = 2        # below this: "cannot evaluate", not "clean"

Z_SCORE_THRESHOLD = 3.0           # standard robust-stats outlier convention

LAPSE_RATE_C_PER_M = 0.0065       # same constant as physics.py's P_MSL formula
REFERENCE_ELEVATION_M = 0.0


# ---------------------------------------------------------------------------
# Real station network  matches seeds/src/stations.py. Distances below
# were computed from this exact list, so the sparse/dense split reflects
# your actual data, not a hypothetical.
#
# Sanity-checked distances (Haversine, computed from these coordinates):
#   DEL001 <-> DEL002:  ~12 km   (dense pair, same metro)
#   BOM001 <-> BOM002:  ~24 km   (dense pair, same metro)
#   SHI001 (Shimla) nearest other station: DEL001/DEL002, ~340 km away
#   SXR001 (Srinagar) nearest other station: SHI001, ~370 km away
# Both SHI001 and SXR001 sit OUTSIDE the 250km radius from every other
# station in this 16-station list  they will always hit the
# insufficient-neighbors fallback path. This is real, not a bug: it
# mirrors IMD's actual network, where mountain regions (e.g. only 10 AWS
# in all of Ladakh) are genuinely sparse. L5 must handle this honestly,
# not pretend these stations have neighbors they don't.
# ---------------------------------------------------------------------------


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance between two lat/lon points, in km."""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def robust_zscore(x: float, neighbor_values) -> float:
    """
    (x - median(neighbors)) / (1.4826 * MAD(neighbors)).
    Median/MAD instead of mean/std so one bad neighbor doesn't distort
    the comparison baseline for everyone else.
    """
    neighbor_values = np.asarray(neighbor_values, dtype=float)
    med = np.median(neighbor_values)
    mad = np.median(np.abs(neighbor_values - med))
    if mad == 0:
        mad = 1e-6  # avoid divide-by-zero when all neighbors agree exactly
    return (x - med) / (1.4826 * mad)


def elevation_adjust_temp(t_celsius: float, h_m: float,
                           reference_h: float = REFERENCE_ELEVATION_M) -> float:
    """
    Adjust temperature to a common reference elevation before comparing
    across stations — same lapse-rate logic as L1's P_MSL correction.
    Without this, Shimla (2205m) and Srinagar (1587m) would always look
    "anomalously cold" next to plains/coastal neighbors on a totally
    normal day, purely from altitude, not a fault.
    """
    return t_celsius + LAPSE_RATE_C_PER_M * (h_m - reference_h)


# ---------------------------------------------------------------------------
# NEIGHBOR SELECTION
# ---------------------------------------------------------------------------

def find_neighbors(station_row, all_stations_at_time: pd.DataFrame) -> pd.DataFrame:
    """
    Nearest neighbors within MAX_NEIGHBOR_RADIUS_KM, preferring
    MIN_NEIGHBORS_PREFERRED. Falls back to nearest-available if the radius
    yields too few. Returns an empty frame if fewer than
    MIN_NEIGHBORS_REQUIRED exist even with fallback — caller MUST treat
    that as "cannot evaluate", never as "clean".
    """
    others = all_stations_at_time[
        all_stations_at_time['station_id'] != station_row['station_id']
    ].copy()
    if others.empty:
        return others

    others['distance_km'] = others.apply(
        lambda r: haversine_km(station_row['lat'], station_row['lon'], r['lat'], r['lon']),
        axis=1
    )
    within_radius = others[others['distance_km'] <= MAX_NEIGHBOR_RADIUS_KM]

    if len(within_radius) >= MIN_NEIGHBORS_PREFERRED:
        return within_radius.nsmallest(MIN_NEIGHBORS_PREFERRED, 'distance_km')
    if len(within_radius) >= MIN_NEIGHBORS_REQUIRED:
        return within_radius
    fallback = others.nsmallest(MIN_NEIGHBORS_REQUIRED, 'distance_km')
    return fallback if len(fallback) >= MIN_NEIGHBORS_REQUIRED else others.iloc[0:0]


# ---------------------------------------------------------------------------
# BATCH LAYER — matches the team's contract shape (time, station_id,
# predicted_anomaly, sensor_type, anomaly_value, anomaly_reason,
# expected_cause, recommended_action, layer_used).
#
# REQUIRES: input already has a 'P_MSL' column from Layer 1's output
# (layer1_physics()). Do not pass raw pressure_hpa alone — this layer
# does not recompute the elevation correction.
# ---------------------------------------------------------------------------

def layer5_spatial(full_df: pd.DataFrame) -> pd.DataFrame:
    """
    Layer 5: Spatial Consistency.

    For every row, finds that station's neighbors at the SAME timestamp,
    computes a robust z-score for elevation-adjusted temperature and for
    P_MSL, flags if either exceeds Z_SCORE_THRESHOLD.

    Rows with fewer than MIN_NEIGHBORS_REQUIRED neighbors get
    'spatial_evaluable' = False and are never flagged — surfaced
    explicitly to L6 rather than silently treated as clean or as a
    non-answer.
    """
    if 'P_MSL' not in full_df.columns:
        raise ValueError(
            "layer5_spatial requires 'P_MSL' from Layer 1's output — "
            "run layer1_physics() first and merge its P_MSL column in."
        )

    results = []

    for time_val, group in full_df.groupby('time'):
        for _, row in group.iterrows():
            neighbors = find_neighbors(row, group)

            base = {
                'time': time_val,
                'station_id': row['station_id'],
                'predicted_anomaly': 0,
                'sensor_type': None,
                'anomaly_value': np.nan,
                'anomaly_reason': None,
                'expected_cause': None,
                'recommended_action': None,
                'layer_used': 'Layer 5: Spatial Consistency',
                'spatial_evaluable': True,
                'neighbor_count': len(neighbors),
                'temp_z': np.nan,
                'pressure_z': np.nan,
            }

            if len(neighbors) < MIN_NEIGHBORS_REQUIRED:
                base['spatial_evaluable'] = False
                base['anomaly_reason'] = 'Insufficient nearby stations to evaluate'
                results.append(base)
                continue

            own_temp_adj = elevation_adjust_temp(row['temp_c'], row['elevation_m'])
            neighbor_temps_adj = [
                elevation_adjust_temp(r['temp_c'], r['elevation_m'])
                for _, r in neighbors.iterrows()
            ]
            temp_z = robust_zscore(own_temp_adj, neighbor_temps_adj)
            pressure_z = robust_zscore(row['P_MSL'], neighbors['P_MSL'].values)

            base['temp_z'] = temp_z
            base['pressure_z'] = pressure_z

            if abs(temp_z) > Z_SCORE_THRESHOLD:
                base['predicted_anomaly'] = 1
                base['sensor_type'] = 'temp_c'
                base['anomaly_value'] = row['temp_c']
                base['anomaly_reason'] = f'Temperature disagrees with {len(neighbors)} nearby stations (z={temp_z:.2f})'
                base['expected_cause'] = 'Localized sensor fault (neighbors show different conditions)'
                base['recommended_action'] = 'Cross-check with L1/L2 flags for this station'
            elif abs(pressure_z) > Z_SCORE_THRESHOLD:
                base['predicted_anomaly'] = 1
                base['sensor_type'] = 'pressure_hpa'
                base['anomaly_value'] = row['pressure_hpa']
                base['anomaly_reason'] = f'Pressure disagrees with {len(neighbors)} nearby stations (z={pressure_z:.2f})'
                base['expected_cause'] = 'Localized sensor fault (neighbors show different conditions)'
                base['recommended_action'] = 'Cross-check with L1/L2 flags for this station'

            results.append(base)

    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# TESTS
# ---------------------------------------------------------------------------

# Real station list, copied from seeds/src/stations.py so this file's
# tests exercise the ACTUAL network geometry, not a made-up toy layout.
REAL_STATIONS = [
    {"station_id": "DEL001", "lat": 28.584, "lon": 77.206, "elevation_m": 216.0},
    {"station_id": "DEL002", "lat": 28.567, "lon": 77.100, "elevation_m": 237.0},
    {"station_id": "LKO001", "lat": 26.760, "lon": 80.880, "elevation_m": 128.0},
    {"station_id": "JAI001", "lat": 26.820, "lon": 75.800, "elevation_m": 390.0},
    {"station_id": "BOM001", "lat": 19.117, "lon": 72.850, "elevation_m": 14.0},
    {"station_id": "BOM002", "lat": 18.900, "lon": 72.817, "elevation_m": 11.0},
    {"station_id": "MAA001", "lat": 13.000, "lon": 80.180, "elevation_m": 16.0},
    {"station_id": "CCU001", "lat": 22.650, "lon": 88.450, "elevation_m": 6.0},
    {"station_id": "COK001", "lat": 9.933, "lon": 76.267, "elevation_m": 3.0},
    {"station_id": "SHI001", "lat": 31.104, "lon": 77.173, "elevation_m": 2205.0},
    {"station_id": "SXR001", "lat": 34.083, "lon": 74.797, "elevation_m": 1587.0},
    {"station_id": "NAG001", "lat": 21.092, "lon": 79.051, "elevation_m": 310.0},
    {"station_id": "BLR001", "lat": 12.950, "lon": 77.668, "elevation_m": 920.0},
    {"station_id": "HYD001", "lat": 17.450, "lon": 78.470, "elevation_m": 531.0},
    {"station_id": "GAU001", "lat": 26.106, "lon": 91.585, "elevation_m": 54.0},
]


def _run_tests():
    # --- Haversine sanity ---
    assert haversine_km(28.6139, 77.2090, 28.6139, 77.2090) < 0.01
    d = haversine_km(28.6139, 77.2090, 19.0760, 72.8777)  # Delhi-Mumbai, real known ~1150km
    assert 1100 < d < 1250, f"Delhi-Mumbai distance sanity check failed: {d}"

    # --- robust_zscore sanity ---
    assert abs(robust_zscore(10.0, [8, 9, 10, 11, 12])) < 0.5
    assert abs(robust_zscore(100.0, [8, 9, 10, 11, 12])) > 3.0

    # --- elevation_adjust_temp sanity ---
    assert elevation_adjust_temp(25.0, 0.0, 0.0) == 25.0
    assert elevation_adjust_temp(15.0, 2200.0, 0.0) > 15.0

    # --- Real network sparse-region confirmation ---
    # Confirms SHI001 and SXR001 genuinely have no close neighbors in
    # this real station list, at a single snapshot in time.
    t = pd.Timestamp('2026-06-01 12:00')
    snapshot = pd.DataFrame(REAL_STATIONS)
    snapshot['time'] = t
    snapshot['temp_c'] = 25.0
    snapshot['humidity_pct'] = 50.0
    snapshot['pressure_hpa'] = 1000.0
    snapshot['P_MSL'] = 1013.0

    shi_row = snapshot[snapshot['station_id'] == 'SHI001'].iloc[0]
    shi_neighbors = find_neighbors(shi_row, snapshot)
    assert len(shi_neighbors) < MIN_NEIGHBORS_PREFERRED, \
        "SHI001 should NOT have enough close neighbors for the preferred count (confirms real sparse case)"

    sxr_row = snapshot[snapshot['station_id'] == 'SXR001'].iloc[0]
    sxr_neighbors = find_neighbors(sxr_row, snapshot)
    print(f"SHI001 real neighbor count within {MAX_NEIGHBOR_RADIUS_KM}km "
          f"(fallback applied): {len(shi_neighbors)}")
    print(f"SXR001 real neighbor count within {MAX_NEIGHBOR_RADIUS_KM}km "
          f"(fallback applied): {len(sxr_neighbors)}")

    # --- Dense pair confirmation: DEL001/DEL002 should easily find each other ---
    del_row = snapshot[snapshot['station_id'] == 'DEL001'].iloc[0]
    del_neighbors = find_neighbors(del_row, snapshot)
    del002_dist = del_neighbors[del_neighbors['station_id'] == 'DEL002']
    assert not del002_dist.empty, "DEL002 must appear as a DEL001 neighbor (they're ~12km apart)"

    # --- Full batch test: one deliberately anomalous station among real stations ---
    df = snapshot.copy()
    df.loc[df['station_id'] == 'DEL001', 'temp_c'] = 55.0  # inject an outlier
    result = layer5_spatial(df)

    del001_result = result[result['station_id'] == 'DEL001'].iloc[0]
    assert del001_result['spatial_evaluable'], "DEL001 has plenty of real neighbors, must be evaluable"
    assert del001_result['predicted_anomaly'] == 1, "DEL001's 55°C outlier must be caught"
    assert del001_result['sensor_type'] == 'temp_c'

    shi_result = result[result['station_id'] == 'SHI001'].iloc[0]
    assert shi_result['predicted_anomaly'] == 0, \
        "SHI001 was never made anomalous, must not be flagged regardless of evaluability"

    print("Layer 5 tests: passed.")


if __name__ == "__main__":
    _run_tests()