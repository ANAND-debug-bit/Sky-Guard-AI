# Agent instructions

## Scope and source of truth

- This is an idea-stage but runnable prototype, not a production system. Use `idea-pitch/` as the main plan for intended architecture, thresholds, domain sources, and pitch claims; use `README.md` for the shorter six-layer overview.
- Keep changes small, readable, and beginner-friendly. Do not add production hardening or spend time on obscure edge cases unless requested. Comment non-obvious logic and retain or add sources for domain-specific constants and claims.
- Follow `idea-pitch/01-architecture-and-layers.md` for intended behavior: cheap-to-expensive cascade, L1–L4 suspicion, L5 spatial context, and L6 fault-versus-weather fusion. Keep execution priority (L1 → L3 → L2 gap → L2 ML → L4 → L5 → L6) separate from root-cause priority (Frozen → Physics → Forecast → ML).
- Treat values in `idea-pitch/02-thresholds.md` as sourced starting defaults, not universally validated constants; preserve provenance and mark values that still need tuning. For injected, imbalanced anomaly evaluation, prefer PR-AUC/F2 or precision-at-fixed-recall over raw accuracy.
- Keep the pitch roadmap distinct from the current demo: Stage 1 is injected ERA5/Open-Meteo data, replay/offline benchmarking, and a single Python process. IMD integration, ESP32 edge deployment, TimescaleDB/Redis, React, and production MLOps are future/pilot architecture unless explicitly requested.
- The Markdown files are the pitch source; `idea-pitch/pdf/` is generated output. Edit the source or `idea-pitch/_gen/build_pdfs.py`, then regenerate PDFs rather than editing PDFs directly.
DONT RUN GIT COMMITS WITHOUT ASKING EXPLICITY FROM USER

## Layer payload contract (v2 — source of truth)

All layer functions in `microservices/app/layers_v2/` exchange **plain Python
structures** (dicts / lists of dicts), never DataFrames. DataFrames may exist
*inside* a function but are built from the dict input and never cross the
boundary.

Inputs:
- `reading` (one row): `{"timestamp", "station_id", "temp_c", "pressure_hpa", "humidity_pct"}` — sensor values may be `None` for dropout.
- `station` (metadata): `{"lat", "lon", "elevation_m"}`
- Batch layers take `readings: list[reading]`.

Unified output payload (every layer returns this shape):
```json
{
  "layer": "L1" | "L2" | "L4",
  "station_id": "...",
  "timestamp": "...",
  "predicted_anomaly": true/false,
  "checks": { "…layer-specific…" },
  "affected_sensors": ["temp_c", "…"],
  "reason": "human-readable explanation" | null
}
```
L2 returns a *list* of these payloads (one per input reading); L1/L4 return a
single payload. Entry points:
- L1 `evaluate_physics(reading, previous_reading=None, station=None) -> dict`
- L2 `train_ml_model(readings) -> (model, explainer)`; `isolation_forest_shap(readings, model, explainer, features) -> list[dict]`
- L4 `forecast_reading(pipeline, readings, n_context=20) -> dict`

## Structure and runtime

- Python code is under `microservices/app/`: `core/main.py` is the CLI (`stream` by default, `static`, or `accuracy`); layers are under `layers/` (`physics` = L1/L5/L6, `ml` = L2, `frozen` = L3, `forecasting` = L4). The core live path currently invokes ML and forecasting; the other layer scripts are standalone.
- Run the core from `microservices/app/core/`, not the repository root, because its relative imports and Parquet paths depend on that working directory. It expects `../seeds/data/raw/aws_clean_baseline.parquet` and `../seeds/aws_evaluation_dataset.parquet`.
- Start the sensor simulator from `microservices/app/` with `uvicorn sensor_simulation.main:app --port 8000`. It loads the baseline Parquet at import and provides `/v1/sensor`, `/v1/sensor/injected`, and `/v1/sensor/injected/HYD001` NDJSON streams.
- `backend/` is a CommonJS Express/Mongoose prototype. From that directory, `npm install` then `npm start`; it listens on port 3000, connects to local MongoDB `skyguard_db`, and immediately consumes the simulator stream, so start the simulator and MongoDB first. URLs and the Mongo URI are hardcoded in `backend/src/configs/index.js`; `.env` is not wired in.
- `Frontend/index.html` is a static stub, not a React application. Do not assume frontend tooling or routes exist.

## Focused commands

```bash
# from microservices/app/core
python main.py static
python main.py accuracy
python main.py stream       # needs the simulator; also the default mode

# standalone layer checks, from the repository root
python microservices/app/layers/physics/physics.py
python microservices/app/layers/frozen/frozen.py
python microservices/app/layers/physics/spatial.py
python microservices/app/layers/physics/fusion.py

# from the repository root
python idea-pitch/_gen/build_pdfs.py
```

- `microservices/app/requirements.txt` is empty; there is no configured Python test runner, linter, formatter, type checker, CI, or task runner. Use the standalone scripts and CLI modes above for focused verification and install the imported Python dependencies in the local environment.
- The first core run loads `amazon/chronos-2` from Hugging Face, so network access/model caching is required. `layers/physics/test_real_data.py` and `seeds/src/fetch_openmeteo.py` also require network access.
- `backend` has no API routes yet, and its `npm test` script is the intentional placeholder that exits with failure; do not treat it as a meaningful test suite.
