# 03 — Data Sources

> All sources we'll cite in the PPT, with how we use each. Prefer free + no-auth for the hackathon.

---

## Primary training / benchmark data

### Open-Meteo Archive API — **PRIMARY (hackathon)**
- **What:** Historical hourly weather from ERA5 reanalysis, ~5 km resolution, global, 1940→present.
- **Variables:** `temperature_2m`, `relative_humidity_2m`, `pressure_msl` (+ `surface_pressure`).
- **Access:** Free HTTP GET, **no API key** for non-commercial (≤10k calls/day).
- **Endpoint:** `https://archive-api.open-meteo.com/v1/archive`
- **License:** CC BY 4.0.
- **URL:** https://open-meteo.com/en/docs/historical-weather-api
- **Why primary:** zero-friction, ERA5-quality, covers all 3 of our variables, Indian lat/lon queryable directly. This is what we use to build the clean baseline + inject anomalies.

### ERA5 (ECMWF / Copernicus CDS) — authoritative upstream
- **What:** Global hourly reanalysis, 0.25° grid, 200+ variables.
- **Access:** `cdsapi` Python client (free account + API key) or Google Earth Engine or WeatherBench2.
- **License:** CC BY 4.0.
- **URL:** https://cds.climate.copernics.eu/datasets/reanalysis-era5-single-levels
- **Role:** cite as the scientific source behind Open-Meteo; use directly if we need variables Open-Meteo doesn't expose.

### NOAA ISD / ISD-Lite — **real station-level ground truth**
- **What:** Hourly + synoptic observations from 20,000+ surface stations globally. Station-level (not gridded) — closest to real AWS data.
- **Variables (ISD-Lite):** air temp, dew point, sea-level pressure, wind, cloud, precip.
- **License:** US public domain.
- **URL:** https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database
- **ISD-Lite files:** https://www.ncei.noaa.gov/pub/data/noaa/isd-lite/
- **Role:** realistic station noise + dropout patterns; labelled-free but has real AWS quirks (gaps, stuck values). Strong for the "practical deployability" slide.

---

## Indian-specific sources (cite for credibility)

### IMD (India Meteorological Department) AWS network
- **What:** 675+ AWS/ARG stations across India measuring T, RH, pressure, rainfall, wind, solar.
- **Access:** API at `https://api.imd.gov.in/api/v1/aws_data` — **requires auth**; historical via IMD Data Service Portal (dsp.imdpune.gov.in).
- **URL:** https://api.imd.gov.in/public/api_reference.html
- **Role:** the *actual* target network for this problem. Cite as deployment context; likely can't get free bulk access during hackathon but mention the integration path.

### ISRO MOSDAC
- Satellite + in-situ Indian data. Registration required.
- URL: https://mosdac.gov.in

### WMO OSCAR/Surface
- Station metadata (lat/lon/elevation) for the global network — needed for the spatial layer's Haversine neighbour map.
- URL: https://oscar.wmo.int/surface

---

## Anomaly-injected / labelled benchmarks (so we don't invent one)

### De Bruijn et al. (2016) — sensor-fault benchmark
- **What:** Injected faults (random, malfunction, bias, drift, polynomial drift) on Intel Lab, SensorScope, Smart Santander. **5.78M annotated points.**
- **Paper:** https://doi.org/10.5220/0005637901850195
- **Data:** http://tuananh.io/datasets
- **Role:** cite as prior-art labelled benchmark; we mirror their fault taxonomy (spike, drift, stuck, dropout, drift) for our own injection.

### CATS — Controlled Anomalies Time Series
- **What:** Benchmark with injected anomalies, labelled.
- **URL:** https://www.kaggle.com/datasets/patrickfleith/controlled-anomalies-time-series-dataset

### Kaggle (secondary)
- IoT Indoor Environmental Dataset (T/P/RH, 2-min cadence, Jan 2026): https://www.kaggle.com/datasets/kondasreenu/iot-based-indoor-environmental-dataset
- Sensor Anomaly Detection: https://www.kaggle.com/datasets/sakhirai/sensor-anomaly-detection
- Anomaly Detection Dataset (IoT): https://www.kaggle.com/datasets/igor0612/anomaly-detection-dataset
- EcoNET Climate Sensor Fault Detection (6.5M rows, 3.6% anomaly): https://github.com/Ishaan1402/climate-sensor-fault-detection

---

## Our data pipeline (the slide)

```
1. Open-Meteo Archive API  ──▶ clean baseline (ERA5-quality, hourly, Indian stations)
        │
2. Inject synthetic anomalies (spike/freeze/drift/dropout/decoupling/barometric)
        │   (ground-truth labels = anomaly_type, fault_severity)
        ▼
3. Store in TimescaleDB (hypertable on timestamp, per station_id)
        │
4. Replay as a stream ──▶ pipeline behaves as if live
        │
5. (Optional) Validate on NOAA ISD station data for realistic noise
        │
6. (Future) Plug into IMD AWS API for production deployment
```

**Pitch line:** "We don't need to wait for live AWS feeds — we replay ERA5-quality history with injected, labelled faults, so the system is evaluated against known ground truth."

---

## Station set (for the spatial layer demo)

15 Indian stations across climates/altitudes (Delhi, Shimla, Srinagar, Mumbai, Chennai, Kolkata, Kochi, Bengaluru, Hyderabad, Guwahati, Nagpur, Jaipur, Lucknow). Lat/lon/elevation from WMO OSCAR/Surface. Neighbour map precomputed by Haversine at 500 km radius. **Two stations (CCU, GAU) are isolated** — we acknowledge this honestly in the PPT as a known limit of the spatial layer.

---

## Licensing one-liner for the slide
"All training data is CC BY 4.0 (ERA5/Open-Meteo) or US public domain (NOAA ISD). No proprietary data dependencies."
