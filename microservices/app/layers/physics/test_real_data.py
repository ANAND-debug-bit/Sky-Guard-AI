"""
Phase 4 — Run Layer 1 against REAL data.
==========================================
Fetches real historical weather data for an Indian station from the
Open-Meteo Archive API (ERA5 reanalysis, no API key needed) and runs it
through layer1_physics() to see the actual false-positive rate on
genuine clean weather not just the hand-built test batch.
"""

import requests
import pandas as pd

from physics import layer1_physics, layer1_confidence

#CHECKING FOR DELHI
STATION_NAME = "Delhi"
LATITUDE = 28.6139
LONGITUDE = 77.2090
START_DATE = "2026-06-01"   # pick a monsoon-season window on purpose —
END_DATE = "2026-08-28"     # this is where L1's soft signals get stressed most


def fetch_real_data(lat, lon, start, end):
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start,
        "end_date": end,
        "hourly": "temperature_2m,relative_humidity_2m,surface_pressure",
        "timezone": "auto",
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    elevation_m = data.get("elevation", 216.0)  # API returns real station elevation

    df = pd.DataFrame({
        "time": pd.to_datetime(data["hourly"]["time"]),
        "temp_c": data["hourly"]["temperature_2m"],
        "humidity_pct": data["hourly"]["relative_humidity_2m"],
        "pressure_hpa": data["hourly"]["surface_pressure"],
    })
    df["station_id"] = STATION_NAME
    df["elevation_m"] = elevation_m
    return df


def main():
    print(f"Fetching real data for {STATION_NAME} ({LATITUDE}, {LONGITUDE}), "
          f"{START_DATE} to {END_DATE}...")
    batch = fetch_real_data(LATITUDE, LONGITUDE, START_DATE, END_DATE)
    print(f"Got {len(batch)} hourly readings.\n")

    result = layer1_physics(batch)
    confidence = layer1_confidence(batch, result)

    total = len(result)
    flagged = (result["predicted_anomaly"] == 1).sum()
    flagged_pct = 100 * flagged / total

    print("=" * 60)
    print(f"RESULTS — {STATION_NAME}, {total} real readings")
    print("=" * 60)
    print(f"Flagged as anomaly: {flagged} / {total}  ({flagged_pct:.2f}%)")
    print()

    if flagged > 0:
        print("Breakdown by reason:")
        print(result.loc[result["predicted_anomaly"] == 1, "anomaly_reason"]
              .value_counts().to_string())
        print()
        print("Sample flagged rows (first 10):")
        print(result.loc[result["predicted_anomaly"] == 1,
                          ["time", "sensor_type", "anomaly_value", "anomaly_reason"]]
              .head(10).to_string(index=False))
    else:
        print("Nothing flagged — clean run on real monsoon-season data.")

    print()
    print(f"Mean confidence score: {confidence['confidence_score'].mean():.1f}")
    low_confidence = (confidence["confidence_score"] < 100).sum()
    if low_confidence:
        print(f"Readings with reduced confidence (near Magnus boundary): {low_confidence}")


if __name__ == "__main__":
    main()