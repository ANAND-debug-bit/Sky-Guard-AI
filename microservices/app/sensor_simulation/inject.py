import numpy as np
import pandas as pd

SENSORS = ["temp_c", "pressure_hpa", "humidity_pct"]


def _init_eval_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df[SENSORS] = df[SENSORS].astype(float)
    df["is_anomaly"] = 0
    df["anomaly_type"] = "normal"
    df["affected_sensor"] = "none"
    return df


def inject_spikes(df: pd.DataFrame, frac: float = 0.004, seed: int = 42) -> pd.DataFrame:
    np.random.seed(seed)
    n = int(len(df) * frac)
    spike_indices = np.random.choice(df.index, size=n, replace=False)
    for index in spike_indices:
        sensor = np.random.choice(SENSORS)
        if sensor == "temp_c":
            df.loc[index, "temp_c"] += np.random.choice([+30.0, +40.0, -25.0])
        elif sensor == "humidity_pct":
            df.loc[index, "humidity_pct"] = np.random.choice([130.0, 145.0, -10.0])
        elif sensor == "pressure_hpa":
            df.loc[index, "pressure_hpa"] += np.random.choice([+80.0, -80.0])
        df.loc[index, "is_anomaly"] = 1
        df.loc[index, "anomaly_type"] = "spike"
        df.loc[index, "affected_sensor"] = sensor
    return df


def inject_frozen_sensor(df: pd.DataFrame, n_events: int = 20, duration_hours: int = 12, seed: int = 42) -> pd.DataFrame:
    np.random.seed(seed)
    stations = df["station_id"].unique()
    for _ in range(n_events):
        station = np.random.choice(stations)
        station_indices = df[df["station_id"] == station].index.to_numpy()
        if len(station_indices) > duration_hours:
            start_pos = np.random.randint(0, len(station_indices) - duration_hours)
            event_idx = station_indices[start_pos:start_pos + duration_hours]
            sensor = np.random.choice(SENSORS)
            frozen_val = df.loc[event_idx[0], sensor]
            df.loc[event_idx, sensor] = frozen_val
            df.loc[event_idx, "is_anomaly"] = 1
            df.loc[event_idx, "anomaly_type"] = "frozen_sensor"
            df.loc[event_idx, "affected_sensor"] = sensor
    return df


def inject_linear_dampened(df: pd.DataFrame, n_events: int = 20, duration_hours: int = 3, seed: int = 42) -> pd.DataFrame:
    np.random.seed(seed)
    stations = df["station_id"].unique()
    for _ in range(n_events):
        station = np.random.choice(stations)
        station_indices = df[df["station_id"] == station].index.to_numpy()
        if len(station_indices) > duration_hours:
            start_pos = np.random.randint(0, len(station_indices) - duration_hours)
            event_idx = station_indices[start_pos:start_pos + duration_hours]
            sensor = np.random.choice(SENSORS)
            start_val = df.loc[event_idx[0], sensor]
            end_val = start_val + np.random.choice([1.0, -1.0, 0.5, -0.5])
            perfect_straight_line = np.linspace(start_val, end_val, num=duration_hours)
            df.loc[event_idx, sensor] = perfect_straight_line
            df.loc[event_idx, "is_anomaly"] = 1
            df.loc[event_idx, "anomaly_type"] = "linear_dampened"
            df.loc[event_idx, "affected_sensor"] = sensor
    return df


def inject_gradual_drift(df: pd.DataFrame, n_events: int = 15, duration_hours: int = 240, seed: int = 42) -> pd.DataFrame:
    np.random.seed(seed)
    stations = df["station_id"].unique()
    for _ in range(n_events):
        station = np.random.choice(stations)
        station_indices = df[df["station_id"] == station].index.to_numpy()
        if len(station_indices) > duration_hours:
            start_pos = np.random.randint(0, len(station_indices) - duration_hours)
            event_idx = station_indices[start_pos:start_pos + duration_hours]
            sensor = np.random.choice(SENSORS)
            total_error = np.random.choice([2.5, -2.5, 3.0, -3.0])
            drift_array = np.linspace(0, total_error, num=duration_hours)
            df.loc[event_idx, sensor] += drift_array
            df.loc[event_idx, "is_anomaly"] = 1
            df.loc[event_idx, "anomaly_type"] = "gradual_drift"
            df.loc[event_idx, "affected_sensor"] = sensor
    return df


def inject_dropout(df: pd.DataFrame, n_events: int = 25, duration_hours: int = 6, seed: int = 42) -> pd.DataFrame:
    np.random.seed(seed)
    stations = df["station_id"].unique()
    for _ in range(n_events):
        station = np.random.choice(stations)
        station_indices = df[df["station_id"] == station].index.to_numpy()
        if len(station_indices) > duration_hours:
            start_pos = np.random.randint(0, len(station_indices) - duration_hours)
            event_idx = station_indices[start_pos:start_pos + duration_hours]
            outage_type = np.random.choice(["whole_station", "single_sensor"])
            if outage_type == "whole_station":
                df.loc[event_idx, SENSORS] = np.nan
                affected = "all_sensors"
            else:
                sensor = np.random.choice(SENSORS)
                df.loc[event_idx, sensor] = np.nan
                affected = sensor
            df.loc[event_idx, "is_anomaly"] = 1
            df.loc[event_idx, "anomaly_type"] = "dropout_power_cut"
            df.loc[event_idx, "affected_sensor"] = affected
    return df


def inject_cross_sensor_decoupling(df: pd.DataFrame, n_events: int = 15, duration_hours: int = 8, seed: int = 42) -> pd.DataFrame:
    np.random.seed(seed)
    stations = df["station_id"].unique()
    for _ in range(n_events):
        station = np.random.choice(stations)
        station_indices = df[df["station_id"] == station].index.to_numpy()
        if len(station_indices) > duration_hours:
            start_pos = np.random.randint(0, len(station_indices) - duration_hours)
            event_idx = station_indices[start_pos:start_pos + duration_hours]
            df.loc[event_idx, "temp_c"] = np.random.choice([48.0, 50.0, 52.0])
            df.loc[event_idx, "humidity_pct"] = np.random.choice([95.0, 98.0, 99.0])
            df.loc[event_idx, "is_anomaly"] = 1
            df.loc[event_idx, "anomaly_type"] = "cross_sensor_decoupling"
            df.loc[event_idx, "affected_sensor"] = "temp_humidity"
    return df


def inject_noise_burst(df: pd.DataFrame, n_events: int = 20, duration_hours: int = 10, seed: int = 42) -> pd.DataFrame:
    np.random.seed(seed)
    stations = df["station_id"].unique()
    for _ in range(n_events):
        station = np.random.choice(stations)
        station_indices = df[df["station_id"] == station].index.to_numpy()
        if len(station_indices) > duration_hours:
            start_pos = np.random.randint(0, len(station_indices) - duration_hours)
            event_idx = station_indices[start_pos:start_pos + duration_hours]
            sensor = np.random.choice(SENSORS)
            noise = np.random.normal(loc=0.0, scale=5.0, size=duration_hours)
            df.loc[event_idx, sensor] += noise
            df.loc[event_idx, "is_anomaly"] = 1
            df.loc[event_idx, "anomaly_type"] = "noise_burst"
            df.loc[event_idx, "affected_sensor"] = sensor
    return df


def inject_barometric(df: pd.DataFrame, n_events: int = 15, duration_hours: int = 12, seed: int = 42) -> pd.DataFrame:
    np.random.seed(seed)
    high_stations = df[df["elevation_m"] > 500]["station_id"].unique()
    if len(high_stations) == 0:
        high_stations = df["station_id"].unique()
    for _ in range(n_events):
        station = np.random.choice(high_stations)
        station_indices = df[df["station_id"] == station].index.to_numpy()
        if len(station_indices) > duration_hours:
            start_pos = np.random.randint(0, len(station_indices) - duration_hours)
            event_idx = station_indices[start_pos:start_pos + duration_hours]
            df.loc[event_idx, "pressure_hpa"] = np.random.choice([1013.25, 1015.0, 1010.5])
            df.loc[event_idx, "is_anomaly"] = 1
            df.loc[event_idx, "anomaly_type"] = "barometric_altitude_inconsistency"
            df.loc[event_idx, "affected_sensor"] = "pressure_hpa"
    return df


def inject_all(df: pd.DataFrame) -> pd.DataFrame:
    df = _init_eval_columns(df)
    df = inject_spikes(df)
    df = inject_frozen_sensor(df)
    df = inject_linear_dampened(df)
    df = inject_gradual_drift(df)
    df = inject_dropout(df)
    df = inject_cross_sensor_decoupling(df)
    df = inject_noise_burst(df)
    df = inject_barometric(df)
    return df
