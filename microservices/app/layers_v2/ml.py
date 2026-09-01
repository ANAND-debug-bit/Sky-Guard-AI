"""
Layer 2 — ML Anomaly Detection (Isolation Forest + SHAP) (v2)
=============================================================
SkyGuard AI — microservices/app/layers_v2/ml.py

Design follows idea-pitch/01-architecture-and-layers.md (L2) and
idea-pitch/02-thresholds.md (L2 thresholds), not the old reference file.

Works on a BATCH of readings (unlike L1, which is single-reading):

    input : batch_df + trained (model, explainer) + FEATURES
    output: per-row anomaly flag, blamed sensor (SHAP), reason

Model:
    IsolationForest (unsupervised, no labelled anomalies needed) trained on
    the clean baseline with
    FEATURES = [temp_c, pressure_hpa, humidity_pct, hour, doy_sin, doy_cos].
    hour + day-of-year sin/cos encode time so the model is period-aware
    (diurnal cycle + season) without a literal clock.

    contamination = 0.02  (idea-pitch/02-thresholds.md: 0.01-0.02 range)
    max_samples   = 256   (standard, per thresholds doc)

    SHAP TreeExplainer with check_additivity=False (required for IsoForest,
    see idea-pitch/05-explainability-xai.md). Blamed sensor = feature with
    the largest absolute SHAP value.
"""

import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import IsolationForest

FEATURES = [
    "temp_c",
    "pressure_hpa",
    "humidity_pct",
    "hour",
    "doy_sin",
    "doy_cos",
]


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive the ML features:
      - hour            : time of day (0-23), encodes the diurnal cycle
      - doy_sin/cos     : day-of-year encoded as a circle, encodes season
    """
    df = df.copy()
    ts = pd.to_datetime(df["timestamp"])
    doy = ts.dt.dayofyear
    df["hour"] = ts.dt.hour
    df["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    df["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    return df.reset_index(drop=True)


def _df_from_readings(readings) -> pd.DataFrame:
    """Build a DataFrame from plain dict inputs (contract: AGENTS.md)."""
    return pd.DataFrame(readings)


def train_ml_model(readings):
    """
    Train IsolationForest on the clean baseline and build the SHAP explainer.
    Input: plain list of reading dicts (see AGENTS.md payload contract) —
    the DataFrame is built inside and never crosses the boundary.
    Returns (model, explainer) to pass to isolation_forest_shap().
    """
    clean_df = _df_from_readings(readings)
    df = add_features(clean_df)
    model = IsolationForest(
        n_estimators=100,
        contamination=0.02,  # expected ~1-2% anomalies (thresholds doc)
        max_samples=256,
        random_state=42,
    )
    model.fit(df[FEATURES])
    # check_additivity=False is required for IsoForest (SHAP PR #784).
    # In shap>=0.51 the flag moved from the constructor to shap_values().
    explainer = shap.TreeExplainer(model)
    return model, explainer


def isolation_forest_shap(readings, model, explainer, features):
    """
    Run the trained IsolationForest on a batch of readings and blame a
    sensor via SHAP.

    Input: plain list of reading dicts (see AGENTS.md payload contract) —
    the DataFrame is built inside and never crosses the boundary.

    Returns a LIST of per-row payload dicts in the unified layer contract:
        {layer, station_id, timestamp, predicted_anomaly, checks,
         affected_sensors, reason}
    where checks.isolation_forest holds the flag and checks.shap holds the
    blamed feature + its |SHAP value|.

    Blamed sensor = feature with the largest |SHAP value| (idea-pitch XAI doc).
    Note the sign gotcha: SHAP explains the anomaly *score* (path length),
    not the predict() label — large |value| => short path => more anomalous.
    """
    batch_df = _df_from_readings(readings)
    batch_df = add_features(batch_df)

    batch_features = batch_df[features]
    predictions = model.predict(batch_features)

    # IsolationForest: -1 = anomaly, 1 = normal.
    anom_idx = batch_df.index[predictions == -1]

    # SHAP only on flagged rows (it is expensive).
    shap_map = {}  # row index -> (blamed_feature, |shap value|)
    if not anom_idx.empty:
        shap_values = explainer.shap_values(
            batch_df.loc[anom_idx, features], check_additivity=False
        )
        for i, idx in enumerate(anom_idx):
            row_shap_values = shap_values[i]
            top_feature_idx = np.argmax(np.abs(row_shap_values))
            blamed_feature = features[top_feature_idx]
            shap_map[idx] = (blamed_feature, float(abs(row_shap_values[top_feature_idx])))

    # Build one payload per row (aligned to the input batch order).
    payloads = []
    for idx, row in batch_df.iterrows():
        is_anomaly = idx in shap_map
        blamed, shap_abs = shap_map.get(idx, (None, None))

        payloads.append(
            {
                "layer": "L2",
                "station_id": row["station_id"],
                "timestamp": row["timestamp"],
                "predicted_anomaly": is_anomaly,
                "checks": {
                    "isolation_forest": {"flagged": is_anomaly},
                    "shap": {
                        "blamed_feature": blamed,
                        "abs_shap_value": shap_abs,
                    },
                },
                "affected_sensors": [blamed] if blamed else [],
                "reason": (
                    f"SHAP flagged '{blamed}' as primary driver of the "
                    f"multivariate anomaly (|SHAP|={shap_abs:.3f})."
                    if blamed
                    else None
                ),
            }
        )

    return payloads