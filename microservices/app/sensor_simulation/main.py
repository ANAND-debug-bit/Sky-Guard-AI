import math
from pathlib import Path
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
import asyncio
import json
import pandas as pd
from inject import inject_all

PARQUET_PATH = (
    Path(__file__).parent / "../seeds/data/raw/aws_clean_baseline.parquet"
).resolve()
df = pd.read_parquet(PARQUET_PATH).sort_values("timestamp").reset_index(drop=True)
df_injected = inject_all(df)

STATIONS = {
    sid: g.reset_index(drop=True) for sid, g in df.groupby("station_id", sort=False)
}
STATIONS_INJECTED = {
    sid: g.reset_index(drop=True)
    for sid, g in df_injected.groupby("station_id", sort=False)
}

app = FastAPI()


@app.get("/v1/sensor/health")
async def get_health():
    return {
        "status": "running",
        "stations": sorted(str(s) for s in STATIONS.keys()),
        "injected_total_rows": int(len(df_injected)),
        "injected_anomaly_rows": int(df_injected["is_anomaly"].sum().item()),
    }


def _row_to_jsonable(row):
    out = {}
    for k, v in row.items():
        if isinstance(v, pd.Timestamp):
            out[k] = v.isoformat()
        elif isinstance(v, np.floating) and math.isnan(float(v)):
            out[k] = None
        elif isinstance(v, np.integer):
            out[k] = int(v)
        elif isinstance(v, np.floating):
            out[k] = float(v)
        elif isinstance(v, float) and math.isnan(v):
            out[k] = None
        else:
            out[k] = v
    return out


async def sensor_stream(rows):
    n = len(rows)
    if n == 0:
        return
    i = 0
    while True:
        row = _row_to_jsonable(rows.iloc[i])
        sid = row.pop("station_id")
        yield json.dumps({"id": sid, **row}) + "\n"
        i = (i + 1) % n
        await asyncio.sleep(1)


@app.get("/v1/sensor")
async def sensor():
    return StreamingResponse(sensor_stream(df), media_type="application/x-ndjson")


@app.get("/v1/sensor/injected")
async def sensor_injected():
    return StreamingResponse(
        sensor_stream(df_injected), media_type="application/x-ndjson"
    )


@app.get("/v1/sensor/injected/{station_id}")
async def sensor_injected_station(station_id: str):
    if station_id not in STATIONS_INJECTED:
        raise HTTPException(status_code=404, detail=f"unknown station: {station_id}")
    return StreamingResponse(
        sensor_stream(STATIONS_INJECTED[station_id]), media_type="application/x-ndjson"
    )


@app.get("/v1/sensor/{station_id}")
async def station(station_id: str):
    if station_id not in STATIONS:
        raise HTTPException(status_code=404, detail=f"unknown station: {station_id}")
    return StreamingResponse(
        sensor_stream(STATIONS[station_id]), media_type="application/x-ndjson"
    )
