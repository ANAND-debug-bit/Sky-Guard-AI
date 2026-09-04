import pandas as pd
import numpy as np
import shap
from sklearn.ensemble import IsolationForest


def train_model(df):
    features = ['temp_c', 'pressure_hpa', 'humidity_pct', 'hour', 'temp_jump', 'pressure_jump']
    print("Starting....")
    isolation_forest = IsolationForest(n_estimators=100, contamination="auto", random_state=42)  # changed contamination to auto from 1%

    isolation_forest.fit(df[features])
    print("model trained")
    explainer = shap.TreeExplainer(isolation_forest)
    return isolation_forest, explainer

df = pd.read_parquet("../../seeds/data/raw/aws_clean_baseline.parquet")
df['timestamp'] = pd.to_datetime(df['timestamp'])
df = df.sort_values(['station_id', 'timestamp'])
df['temp_jump'] = df.groupby('station_id')['temp_c'].diff().fillna(0)
df['pressure_jump'] = df.groupby('station_id')['pressure_hpa'].diff().fillna(0)
df['hour'] = df['timestamp'].dt.hour
train_model(df)
