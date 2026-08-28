import pandas as pd
from predictor import predict
from chronos import Chronos2Pipeline
import numpy as np

DATA_DIR = "../../seeds/data/raw/aws_clean_baseline.parquet"
pipeline = Chronos2Pipeline.from_pretrained("amazon/chronos-2")
df = pd.read_parquet(DATA_DIR)


def create_result_df(df):
    result_df = pd.DataFrame()
    result_df["timestamp"] = df["timestamp"]
    result_df["station_id"] = df["station_id"]
    result_df["predicted_anomaly"] = 0
    result_df["sensor_type"] = None
    result_df["anomaly_value"] = np.nan
    result_df["anomaly_reason"] = None
    result_df["expected_cause"] = ""
    result_df["recommended_action"] = ""
    result_df["layer_used"] = "FORECASTING"
    return result_df


def forecasting_layer(pipeline, df):
    result_df = create_result_df(df)
    payload = predict(pipeline=pipeline, df=df)
    if payload["is_anomaly"]:
        result_df["sensor_type"] = payload["sensors"]
        result_df["predicted_anomaly"] = int(payload["is_anomaly"])
    return result_df


for _ in range(100):
    print(forecasting_layer(pipeline, df))
