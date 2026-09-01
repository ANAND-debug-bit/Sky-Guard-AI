# 11 — Strengths & Weaknesses (where this idea is good / where it fails)

> Honest self-assessment. SIH judges reward self-awareness — stating your own limits is better than hiding them. Lift the "Weaknesses" column into the Feasibility slide's risks-and-mitigations.

---

## Where this idea is GOOD (our moat)

| # | Strength | Why it's defensible | Evidence |
|---|---|---|---|
| 1 | **Standards-aligned architecture** — 6 layers mirror WMO L0–L5 (CIMO Guide WMO-No. 8; MADIS; WDQMS) | Not invented in a vacuum; met-services already use this layering. We automate + ML-augment it. | WMO-No. 8 2024 ed.; MADIS QC notes; TITAN |
| 2 | **Fault-vs-weather disambiguation** via spatial consensus | Directly answers the problem statement's hardest requirement. The 2×2 fusion matrix is the pitch's core insight. | Met Office buddy check; TITAN SCT; ECMWF O-B |
| 3 | **Explainability by construction** — SHAP on IsoForest + per-fault natural-language reason + confidence tier | Hits the 10% Explainability criterion head-on; no black-box alerts. | SHAP PR #784; problem statement lists SHAP/LIME as preferable |
| 4 | **Edge + cloud split with transmit-only-on-suspicion** | Unique vs all competitors (Vaisala/WeatherXM/Tomorrow.io all always-transmit). Wins Energy (5%) + Deployability (10%). | ESP32-S3 datasheet; IEEE 2026 edge-IF paper (Pi, not ESP32) |
| 5 | **Self-healing sensor-health loop** | Composite score + predictive time-to-failure + auto-imputation = direct answer to the grand challenge. | ECMWF blacklist; WDQMS indicators (we composite them) |
| 6 | **Zero-shot forecasting via Chronos-2** | No per-station training needed for the forecast layer → scales to new stations immediately. | amazon/chronos-2 (arXiv:2510.15821) |
| 7 | **Multiple redundancy per fault type** | No single detector's failure mode is uncovered — each fault has ≥2 layers that can catch it. | See `06-fault-classification.md` redundancy table |
| 8 | **Free, no-auth training data** (Open-Meteo/ERA5) + labelled benchmark (De Bruijn 2016) | No data-access blocker for the hackathon; reproducible eval. | Open-Meteo; NOAA ISD; De Bruijn 2016 |
| 9 | **Honest about limits** (isolated stations, microclimates, inversion) | Credibility. Judges penalize hand-waving more than acknowledged limits. | TITAN min-5-buddies; Euskalmet inversion caveat |
| 10 | **Quantified energy win** — ~72% transmit-energy reduction, ~10 mo battery vs ~3 mo | Concrete number for the 5% Energy criterion. | ESP32-S3 + Heltec V4 datasheets |

---

## Where this idea FAILS / is weak (and the mitigation)

### F1 — Spatial layer breaks for isolated & terrain-diverse stations
**Failure:** India has isolated stations (CCU/Kolkata, GAU/Guwahati have no buddies within 500 km) and extreme terrain (Himalayas, Western Ghats, valleys) where lapse-rate correction fails during inversions. Frontal boundaries create legitimate sharp gradients that look like outliers.
**Evidence:** TITAN requires min 5–10 buddies (we have 1–4 in the demo); Euskalmet notes lapse-rate fails in inversions; ECMWF notes frontal boundaries misflagged.
**Mitigation (state on slide):**
- Isolated stations → rely on L1–L4 multi-layer agreement instead of spatial; mark verdict as "spatial-unavailable."
- Terrain → add lapse-rate correction + inversion detector (disable spatial T-check when inversion detected).
- Frontal boundaries → require ≥2 layers + spatial disagreement for SENSOR_FAULT (never spatial alone).
- **Production:** use NWP background (O-B) as a "virtual buddy" for isolated stations (ECMWF approach).

### F2 — Isolation Forest has documented blind spots
**Failure:** misses clustered anomalies (masking), bad on high-dimensional data, creates axis-aligned ghost clusters, not rotation-invariant, run-to-run unstable, no built-in drift handling (Chabchoub 2022; Liu 2012; Hariri 2019).
**Mitigation:**
- Use **Extended Isolation Forest** (random hyperplane splits) → fixes ghost clusters + rotation issue.
- Add **LSTM-AE sibling** (Met Éireann 99.6%) → catches temporal/flatline patterns IsoForest misses.
- **PSI-driven retraining** → handles concept drift (Kataria 2026).
- De-seasonalize inputs first (ECMWF) → handles seasonality.

### F3 — ML flags extreme-but-real weather as anomalies
**Failure:** a model trained on "normal" will flag a genuine heatwave/cold-wave/cyclone as anomalous. ECMWF explicitly excludes severe weather from training.
**Mitigation:**
- L5 spatial agreement → if neighbours see the same extreme, it's REGIONAL_EVENT not fault (our fusion matrix).
- De-seasonalize + climatological ±5σ bounds → extremes within seasonal norms don't flag.
- Exclude flagged REGIONAL_EVENT windows from IsoForest retraining set.

### F4 — Class imbalance makes "accuracy" meaningless
**Failure:** anomalies are <1–5% of data; 99% accuracy can mean "flagged nothing."
**Mitigation:** evaluate with **PR-AUC, F2-score, precision-at-fixed-recall** — never raw accuracy (Kataria 2026). State this explicitly.

### F5 — Labelled anomaly data is scarce & expert-dependent
**Failure:** real QC labels need meteorologist review → expensive, few public labelled sets.
**Mitigation:**
- Use **injected-anomaly benchmark** (De Bruijn 2016 taxonomy + our own injection on ERA5) → controlled ground truth.
- Semi-automatic labelling from operational warnings (ECMWF approach) for production.

### F6 — ESP32 edge-AI real-world constraints
**Failure:** PSRAM access adds latency; ADC noise ±7% needs calibration/filtering; OTA updates risk corruption; radio TX peaks at 355 mA (WiFi) / 750 mA (LoRa @27 dBm) strain solar+battery budget.
**Mitigation:**
- int8 quantization (TFLite-Micro) + emlearn for trees → fits in <10 KB flash, <1 KB RAM.
- Sensor calibration + moving-average filter before ML inference.
- ESP-IDF OTA with rollback partition.
- Transmit-only-on-suspicion → radio duty cycle ~5% → battery lasts ~10 mo vs ~3 mo always-transmit.

### F7 — Regulatory/operational acceptance of AI QC
**Failure:** WMO requires "known, traceable quality"; black-box AI isn't auditable. China now requires algorithm filing + content labelling for AI met products (effective June 2025). NMHSs must remain the authoritative warning voice.
**Mitigation:**
- **Explainability by construction** (SHAP + reason + confidence) → auditable.
- **Human-in-the-loop** for blacklist/maintenance (ECMWF model) → AI proposes, human dispositions.
- **Fallback to deterministic QC** if ML unavailable → operational reliability.
- **Audit log** every QC decision (who/what/when/why) per WMO-No. 8.
- Position as "AI complements, doesn't replace" physics-based QC — matches WMO Congress Oct 2025 stance.

### F8 — Demo data ≠ real IMD AWS data
**Failure:** we can't get free bulk IMD AWS historical data (auth-gated); our demo uses ERA5 reanalysis (gridded, not raw station noise).
**Mitigation:**
- Validate noise realism on **NOAA ISD** (real station-level, public domain) alongside ERA5.
- State the IMD API integration path (`api.imd.gov.in/api/v1/aws_data`) for production.
- Inject realistic noise/dropout patterns from ISD into ERA5 clean baseline.

### F9 — 15-station demo is too sparse for robust spatial stats
**Failure:** TITAN needs 5–10 buddies; our demo set gives most stations 1–4 neighbours.
**Mitigation:** state this as a demo-scale limitation; production uses the full IMD 675+ station network where buddy counts are sufficient. The *method* is unchanged; only the demo is sparse.

### F10 — No cryptographic telemetry integrity
**Failure:** WMO has no mandate for signed AWS data → tamper/injection attacks undetected.
**Mitigation:** propose **HMAC-signed readings** + anomaly detector trained on tamper signatures as our security contribution (cheap, differentiated).

---

## The one-sentence pitch that captures both

> "SkyGuard AI is a standards-aligned, edge+cloud, multi-layer anomaly-detection system that **catches what single-detectors miss** (redundant fusion), **explains every verdict** (SHAP + confidence), **distinguishes faults from weather** (spatial consensus), and **self-heals** (health score + imputation) — while honestly bounded by terrain, station density, and the explainability that real met services require."
