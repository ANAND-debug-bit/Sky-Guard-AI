# SkyGuard AI — Idea Pitch (PPT Source)

> Internal hackathon: **idea + plan only. No code in this round.**
> This folder is the theory/plan backbone you lift into slides.
> The AI-generated `plan-skyguard-ai/` folder is a rough implementation sketch and is **not** the source of truth for the pitch.

---

## Elevator Pitch (one slide)

Automatic Weather Stations (AWS) feed forecasting, aviation, agriculture, and disaster response — but their data is polluted by sensor faults, spikes, frozen values, dropout, drift, and communication errors. Traditional threshold-only QC misses complex, hidden, multivariate anomalies. **SkyGuard AI** is a 6-layer, AI/ML, real-time anomaly-detection system for Temperature, Pressure, and Humidity that fuses **physics, ML, forecasting, and spatial consensus** to separate genuine weather events from sensor faults, explains every verdict with **SHAP**, predicts sensor degradation, and ships in an **edge + cloud split** that runs partly on ESP32. The grand challenge: a self-aware, self-healing weather network.

---

## The 6 Layers (one-liner each)

| # | Layer | One-line role | Mirrors WMO QC |
|---|---|---|---|
| L1 | Physics Sanity | Hard physical / climatological / rate-of-change bounds | L1 Plausibility + L2 Internal |
| L2 | ML Anomaly | Isolation Forest + SHAP + gap detection + trend/drift | L2 + statistical |
| L3 | Frozen Sensor | Std-dev / 2nd-derivative ≈ 0 over a window | L2 Internal |
| L4 | Forecasting | Chronos-2 predicts next reading; corridor breach = anomaly | L5 Forecast consistency |
| L5 | Spatial Consistency | Robust Z (median/MAD) vs Haversine neighbours | L3 Spatial / buddy |
| L6 | Fusion | 2×2 decision matrix → verdict + confidence + root cause | L4+ aggregation |

**Key novelty pitch:** our layering intentionally mirrors the **WMO/ECMWF L0–L5 QC framework** (WMO-No. 8, MADIS, WDQMS) — so the design is standards-aligned, not invented in a vacuum.

---

## Judging Criteria Scorecard (how we win each)

| Criterion | Weight | Our Angle |
|---|---:|---|
| Innovation & Novelty | 25% | Layered fusion that mirrors WMO L0–L5; SHAP explainability on IsoForest; Chronos-2 zero-shot forecasting; edge+cloud split; composite sensor-health score for self-healing. |
| Detection Accuracy | 20% | Multi-signal voting reduces single-layer false positives; robust stats (median/MAD) for spatial; injected-anomaly benchmark eval. |
| Real-Time Capability | 15% | Cheap layers run first (short-circuit); heavy Chronos-2 only on suspect readings; edge pre-filter on ESP32; Redis window cache. |
| Explainability | 10% | SHAP per-feature attribution + per-fault natural-language reason + confidence score; every alert says *why*. |
| Scalability | 10% | Stateless Python workers behind gateway; Redis cache; per-station windows; neighbour map precomputed. |
| Practical Deployability | 10% | Standards-aligned (WMO), uses real free data (Open-Meteo/ERA5/NOAA ISD), runs on commodity ESP32-S3 + gateway. |
| Visualization / UI | 5% | Live station map (Leaflet), colour = health, alert feed, SHAP bar chart, forecast-corridor chart. |
| Energy Efficiency | 5% | Edge tier: int8 IsoForest via emlearn (<10 KB flash), tiny autoencoder via TFLite-Micro; cloud only for heavy layers. |

---

## File Index

| File | What's inside |
|---|---|
| [01-architecture-and-layers.md](./01-architecture-and-layers.md) | Full pipeline, data flow, layer roles, execution + explanation priority, fusion matrix |
| [02-thresholds.md](./02-thresholds.md) | Every concrete threshold with justification + source |
| [03-data-sources.md](./03-data-sources.md) | All datasets with links + how we use each |
| [04-tech-stack.md](./04-tech-stack.md) | Full stack, edge vs cloud split, libraries |
| [05-explainability-xai.md](./05-explainability-xai.md) | SHAP, sign-convention gotcha, per-fault explanations, confidence score |
| [06-fault-classification.md](./06-fault-classification.md) | Fault types → detection layer → threshold → action → WMO level |
| [07-sensor-health.md](./07-sensor-health.md) | Degradation tracking, composite health score, predictive maintenance |
| [08-use-cases.md](./08-use-cases.md) | 10 worked use cases (the "document explaining use cases" deliverable) |
| [09-research-findings.md](./09-research-findings.md) | SOTA papers, production QC systems, competitors, novelty assessment |
| [10-improvements.md](./10-improvements.md) | Concrete prioritized upgrades (P0/P1/P2 + effort/payoff matrix) |
| [11-strengths-weaknesses.md](./11-strengths-weaknesses.md) | Where the idea is good / where it fails + mitigations |
| [12-production-grade.md](./12-production-grade.md) | Hackathon → Pilot → Production ladder, MLOps, imputation, security |
| [13-raw-idea-detailed.md](./13-raw-idea-detailed.md) | Plain-language full idea walkthrough (team understanding doc) |
| [14-sih-format-guide.md](./14-sih-format-guide.md) | SIH 6-slide format, criteria, content mapping per slide |
| **PDFs (SIH format, 6 slides each — generated)** | |
| `pdf/SkyGuard_AI_Deck1_GrandChallenge.pdf` | Narrative: self-healing network (max Innovation) |
| `pdf/SkyGuard_AI_Deck2_TechnicalDeep.pdf` | Narrative: 6-layer fusion + WMO alignment (max Complexity/Accuracy) |
| `pdf/SkyGuard_AI_Deck3_EnergyDeployable.pdf` | Narrative: edge-AI + energy + deployability (max Energy/Deployability) |
