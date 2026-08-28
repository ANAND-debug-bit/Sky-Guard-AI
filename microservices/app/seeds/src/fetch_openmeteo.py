"""
SkyGuard AI - Data Fetcher
Pulls historical hourly weather parameters (Temperature, Surface Pressure, Relative Humidity)
via the Open-Meteo Historical Weather API.
"""

import os
import requests
import pandas as pd
from stations import STATIONS

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "raw")
START_DATE = "2023-01-01"
END_DATE = "2024-12-31"

def fetch_station_data(station: dict) -> pd.DataFrame:
    """Fetch hourly weather records for a single station."""
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": station["lat"],
        "longitude": station["lon"],
        "start_date": START_DATE,
        "end_date": END_DATE,
        "hourly": "temperature_2m,relative_humidity_2m,surface_pressure",
        "timezone": "Asia/Kolkata"
    }
    
    print(f"Fetching data for {station['station_id']} ({station['name']})...")
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    
    hourly = payload.get("hourly", {})
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(hourly["time"]),
        "station_id": station["station_id"],
        "name": station["name"],
        "lat": station["lat"],
        "lon": station["lon"],
        "elevation_m": station["elevation_m"],
        "temp_c": hourly["temperature_2m"],
        "humidity_pct": hourly["relative_humidity_2m"],
        "pressure_hpa": hourly["surface_pressure"]
    })
    return df

def run():
    os.makedirs(DATA_DIR, exist_ok=True)
    all_frames = []
    
    for station in STATIONS:
        try:
            df_station = fetch_station_data(station)
            all_frames.append(df_station)
        except Exception as e:
            print(f"Error fetching data for {station['station_id']}: {e}")
            
    if all_frames:
        combined_df = pd.concat(all_frames, ignore_index=True)
        output_path = os.path.join(DATA_DIR, "aws_clean_baseline.parquet")
        combined_df.to_parquet(output_path, index=False)
        print(f"\nSaved {len(combined_df)} records across {len(all_frames)} stations to: {output_path}")

if __name__ == "__main__":
    run()