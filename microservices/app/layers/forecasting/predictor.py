import pandas as pd
import numpy as np


def predict(pipeline, df, N=20):
    sensor_names = ["temperature", "humidity", "pressure"]
    inputs = np.array(
        [
            [
                df.temp_c.values[-N - 1 : -1],
                df.humidity_pct.values[-N - 1 : -1],
                df.pressure_hpa.values[-N - 1 : -1],
            ]
        ]
    )

    quantiles, mean = pipeline.predict_quantiles(
        inputs, prediction_length=1, quantile_levels=[0.05, 0.5, 0.95]
    )

    actual = [
        df.temp_c.values[-1],
        df.humidity_pct.values[-1],
        df.pressure_hpa.values[-1],
    ]

    forecast = quantiles[0].tolist()

    payload = {"is_anomaly": False, "sensors": []}

    for i, reading in enumerate(forecast):

        p5, p50, p95 = reading[0]

        corridor_width = p95 - p5

        upper_breach = np.maximum(0.0, actual[i] - p95)
        lower_breach = np.maximum(0.0, p5 - actual[i])

        total_breach = upper_breach + lower_breach

        if corridor_width > 0:
            severity = total_breach / corridor_width
        else:
            severity = 0.0

        severity = np.round(severity, 4)

        predicted_anomaly = severity > 0.8 or abs(actual[i] - p50) > corridor_width

        if predicted_anomaly:
            payload["is_anomaly"] = True
            payload["sensors"].append(sensor_names[i])

    return payload
