BACKEND_URL = "http://localhost:3000"
SENSOR_URL = "http://localhost:8000"

import numpy as np
import pandas as pd


def isolation_forest_shap(batch_df, model, explainer, features):
    result_df = pd.DataFrame()
    result_df["time"] = batch_df["timestamp"]
    result_df["station_id"] = batch_df["station_id"]
    result_df["predicted_anomaly"] = 0
    result_df["sensor_type"] = None
    result_df["anomaly_value"] = np.nan
    result_df["anomaly_reason"] = None
    result_df["expected_cause"] = (
        "Multivariate deviation from historical baseline"  # to improve
    )
    result_df["recommended_action"] = (
        "Check blamed sensor for calibration drift or transient faults"
    )
    result_df["layer_used"] = "Layer 2: ML (Isolation Forest + SHAP)"

    batch_features = batch_df[features]
    predictions = model.predict(batch_features)

    anom_idx = batch_df.index[predictions == -1]

    # shap
    if not anom_idx.empty:  # so that  shap doent get a data with no anomalies
        # 3. updating the anomaly flag from 0 to 1 for the broken rows
        result_df.loc[anom_idx, "predicted_anomaly"] = 1

        # shap
        shap_values = explainer.shap_values(batch_df.loc[anom_idx, features])

        for i, idx in enumerate(anom_idx):
            row_shap_values = shap_values[i]

            top_feature_idx = np.argmax(np.abs(row_shap_values))
            blamed_feature = features[top_feature_idx]

            result_df.loc[idx, "sensor_type"] = blamed_feature
            result_df.loc[idx, "anomaly_value"] = batch_df.loc[idx, blamed_feature]
            result_df.loc[idx, "anomaly_reason"] = (
                f"SHAP flagged '{blamed_feature}' as primary driver of the multivariate anomaly."
            )

    return result_df
