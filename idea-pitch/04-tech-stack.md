# 04 — Tech Stack

> Full stack for the pitch. Split into **Edge tier (ESP32-S3)** and **Gateway/Cloud tier**.

---

## Edge Tier — ESP32-S3 (on the AWS)

| Concern | Choice | Why |
|---|---|---|
| Board | **ESP32-S3** (not vanilla ESP32) | SIMD + ESP-NN vector instructions → ~7× faster ML inference; supports PSRAM for model weights. |
| Sensor input | T / P / RH sensors over I²C/SPI | Standard AWS sensors (BME280-class covers all 3 in one chip). |
| ML framework (trees) | **emlearn** (sklearn → C) | Production-ready; Isolation Forest (100 trees, 3 feats) ≈ **2–10 KB flash, <1 KB RAM**. Also has `eml_distance` for Mahalanobis. |
| ML framework (neural) | **TensorFlow Lite Micro** (Espressif fork, ESP-NN) | int8 autoencoder 5–50 KB flash, 30–80 KB tensor arena, 1–10 ms inference on S3. |
| Alt tree framework | **micromlgen** | Backup if emlearn misses a model type. |
| Edge pipeline stages | **emlearn for L1 + L3 + gap check + small IsoForest + tiny autoencoder** | These catch ~70–80% of faults locally; only suspect readings go upstream. |
| Comms | MQTT / HTTPS over Wi-Fi or LoRa | Push suspect reading + 20-point window to gateway. |
| Power | Solar + Li-ion (typical AWS) | Edge tier is ultra-low-power — int8 inference, no radio except on event. |

### What CAN'T run on ESP32 (be honest in the PPT)
- ❌ Chronos-2 (120M params) — needs gateway/cloud GPU.
- ❌ Full SHAP on IsoForest — needs the full model + SHAP lib.
- ❌ Spatial consistency — needs neighbour states (network-wide).
- ❌ MMDDriftOnline (alibi-detect) — streaming drift needs more RAM.
- ❌ Model retraining.

**This honest split is itself the Energy Efficiency (5%) + Practical Deployability (10%) slide.**

---

## Gateway / Cloud Tier

| Concern | Choice | Why |
|---|---|---|
| Ingestion / WS gateway | **Node.js + Fastify** + WebSocket | Low-latency ingest; pushes verdicts to frontend. |
| ML core | **Python + FastAPI** | Houses L2 (IsoForest+SHAP), L4 (Chronos-2), L5 (spatial), L6 (fusion). |
| ML libraries | **scikit-learn** (IsoForest), **shap** (TreeExplainer), **statsmodels** (decomposition), **pymannkendall** (Mann-Kendall), **alibi-detect** v0.13.0 (drift/outlier), **amazon/chronos-2** via `autogluon`/`chronos` | All current, source-backed. |
| Forecasting model | **`amazon/chronos-2`** (120M) primary; **`autogluon/chronos-2-small`** (28M) fallback; univariate `amazon/chronos-bolt-*` if RAM-constrained | Real HF repos (arXiv:2510.15821, Oct 2025). Multivariate natively, 8192 ctx. |
| Time-series store | **TimescaleDB** (Postgres hypertable on timestamp, partitioned by station_id) | Purpose-built for time-series + SQL familiarity. |
| Cache / window store | **Redis** (last 50 readings/station + precomputed neighbour map + latest reading/station) | Sub-ms window fetch; MGET for neighbours in one round trip. |
| Message queue (scale) | **BullMQ on Redis** | Decouple ingest from Python workers → horizontal scale. |
| Frontend | **React + Vite + Leaflet** (map), **Recharts/Chart.js** (charts), **WebSocket** (live feed) | Map = station health colour; SHAP bar; forecast corridor. |
| Dashboards (ops) | **Grafana** on TimescaleDB | Post-hackathon ops view. |
| Containerization | **Docker Compose** (hackathon) → **Kubernetes** (scale) | One-command boot for demo. |
| Logging | **structlog** (Python), **Winston/pino** (Node) | Structured logs. |
| Alerting | Webhook → Slack/Email on SENSOR_FAULT | Ops actionability. |
| CI/CD | GitHub Actions | Standard. |

---

## Library version sanity (verified 2026)

| Library | Status | Note |
|---|---|---|
| `amazon/chronos-2` | ✅ real, HF, 120M | arXiv:2510.15821 |
| `autogluon/chronos-2-small` | ✅ real, 28M | CPU-friendly fallback |
| `amazon/chronos-bolt-{tiny,mini,small,base}` | ✅ real | Univariate fast variants |
| `shap` TreeExplainer on IsoForest | ✅ works | Set `check_additivity=False`; explains path length not label (sign gotcha — see `05-explainability-xai.md`). |
| `alibi-detect` | ✅ v0.13.0 (Dec 2025) | MMDDriftOnline / FETDriftOnline for streaming drift; Mahalanobis online for outlier. |
| `emlearn` | ✅ production | sklearn → C; IsoForest fits in <10 KB. |
| TensorFlow Lite Micro (Espressif) | ✅ production | int8 quantized models. |

---

## Scalability story (for the 10% criterion)

- **Stateless Python workers** behind the gateway → horizontal scale by adding pods.
- **Redis** holds per-station windows + neighbour map → no shared mutable state in workers.
- **BullMQ** decouples ingest from inference → backpressure-safe under burst.
- **TimescaleDB** hypertable partitions by time → queries over months stay fast.
- **Per-station isolation**: each station's analysis is independent → trivially parallel across stations.
- **Edge pre-filter** reduces upstream load ~70–80% → gateway serves more stations per unit compute.

---

## Real-time budget (per reading, end-to-end)

| Stage | Latency | Where |
|---|---:|---|
| L1 physics | < 1 ms | edge |
| L3 frozen | < 1 ms | edge |
| L2 gap + IsoForest | ~1–5 ms | edge (small) / gateway (full) |
| L4 Chronos-2 (only if suspect) | ~50–200 ms | cloud GPU |
| L5 spatial (Redis MGET) | ~1–2 ms | gateway |
| L6 fusion | < 1 ms | gateway |
| **Total (clean reading)** | **~5 ms** (edge short-circuits, no cloud) | |
| **Total (suspect reading)** | **~60–210 ms** | |

Pitch this: "Sub-second verdicts on suspect readings; near-zero overhead on clean ones — because the edge tier filters first."
