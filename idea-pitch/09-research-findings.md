# 09 — Research Findings (what's already out there)

> SOTA papers, production QC systems, and competitors — so we can position our idea as novel, not reinvented. Lift directly into the SIH "Research & References" slide.

---

## A. Key academic papers (2020–2026)

| # | Title | Authors / Venue / Year | Method | URL |
|---|---|---|---|---|
| 1 | Use of ML for detection & classification of observation anomalies | Dahoui et al., ECMWF Newsletter #174, 2023 | **LSTM autoencoder** (unsupervised) + **Random Forest** severity classifier; short-term (3 mo) + long-term (12 mo) for drift. **Operational at ECMWF.** | https://www.ecmwf.int/en/newsletter/174/earth-system-science/use-machine-learning-detection-and-classification |
| 2 | ML using autoencoders to perform QC on meteorological data | Spohn et al., Environmental Data Science (Cambridge), 2026 | Compares AE / VAE / **LSTM-AE** for temp QC at Met Éireann. **LSTM-AE 99.6% accuracy**, replicates 79% of manual flags, only 5 FN + 6 FP over a full year. | https://www.cambridge.org/core/journals/environmental-data-science/article/machine-learning-approach-using-autoencoders-to-perform-quality-control-on-meteorological-data/4576781508080877E36C0CA6612E5590 |
| 3 | Anomaly Detection in Weather Phenomena | Springer Int. J. Computational Intelligence Systems, 2024 | **Isolation Forest + Autoencoders** on Romania weather 2009–2023. At 95% MSE threshold both detect ~16% anomalies; K-means clusters anomalies by region. | https://link.springer.com/article/10.1007/s44196-024-00536-2 |
| 4 | Deep Learning for Anomaly Detection in Spatio-Temporal Maharashtra Weather | IJISAE, 2024 | One-Class SVM, Isolation Forest, AE, **LSTM-AE** on IMD data. LSTM-AE found 455 anomalies vs 751 standard AE (less noise-sensitive). | https://ijisae.org/index.php/IJISAE/article/download/4502/3162/9492 |
| 5 | Edge-Optimized Isolation Forest for Real-Time Environmental Anomaly Detection | IEEE ICISCOIS, 2026 | **Isolation Forest ~80 trees / 4 features** (humidity, temp, gas, pressure). **<2% FPR, <10ms inference, <200KB model.** Deployed on Raspberry Pi. | https://doi.org/10.1109/iciscois62701.2026.11447816 |
| 6 | Anomaly Detection & Exceedance Forecasting in IoT Sensor Networks: An MLOPS Pipeline | IEEE MENACOMM, 2026 | **6-layer MLOps pipeline**: IF + LSTM-AE + XGBoost ensemble with **PSI-driven retraining**. **F1=0.91** vs Z-score baseline F1=0.78. Sub-200ms latency. | https://doi.org/10.1109/menacomm69507.2026.11532803 |
| 7 | Sentinel-Net for anomaly events detection of meteorological stations | PMC, 2025 | Unsupervised edge-oriented detector for station imagery. Multi-scale features + spatial attention + hybrid MSE-SSIM loss. PSNR 29.72 dB, AUC 0.96, 0.07s/image. | https://pmc.ncbi.nlm.nih.gov/articles/PMC12789430/ |
| 8 | Flatline Anomaly Detection in AWS Temperature Sensor Data Using LSTM Autoencoder | Jurnal Penelitian dan Pengembangan IPA, 2026 | **LSTM-AE for flatline/stuck sensor**. Normal-only training. Anomaly threshold 0.01177 MSE. 0.578% of windows flagged. | https://doi.org/10.29303/jppipa.v12i4.14486 |
| 9 | Constant Value Test (probabilistic frozen-sensor detection) | AMT, 2023 | P(same value) given μ, σ, φ₁ (lag-1 autocorr) and resolution. Adapts to local variability — better than fixed std threshold. | https://amt.copernicus.org/articles/16/3085/2023/ |
| 10 | Fiebrich & Crawford — Mesonet QA | Bull. Amer. Meteor. Soc., 2001 | Step tests + persistence tests; the canonical reference for AWS QC thresholds. | https://doi.org/10.1175/1520-0477(2001)082 |

> **Pitch use:** cite #1 (ECMWF operational) + #2 (99.6% LSTM-AE) + #5 (edge IsoForest <200KB) + #6 (6-layer MLOps F1=0.91) as proof each *component* of our stack is validated. Then argue our *integration* is the novelty.

---

## B. Production QC systems (what national met services actually run)

| System | Org | Layers / checks | ML? | URL |
|---|---|---|---|---|
| **MADIS** | NOAA | L1 validity, L2 temporal/internal/statistical-spatial, L3 buddy | No (rules + stats) | https://madis.ncep.noaa.gov/madis_sfc_qc.shtml |
| **Automatic Data Checking + Blacklist** | ECMWF | Static plausibility → LSTM-AE → RF severity; PGE>0.75 blacklist; monthly human review | **Yes (LSTM+RF)** | https://www.ecmwf.int/en/forecasts/quality-our-forecasts/monitoring-observing-system |
| **QualiMet (QC1–QC4)** | DWD (Germany) | Formal → individual criteria → auto correct → historic/subjective; QN (1–10) + QB (0–7) flags | No | https://www.dwd.de/EN/climate_environment/climatemonitoring/climatedatamanagement/qualityassurance/quali.html |
| **MIDAS / SAMOS / CODETS** | Met Office (UK) | Excellent/Good/Satisfactory/Unsatisfactory; Good/Suspect/Erroneous; **MetOfficeBuddyCheck** (open-source in JCSDA/ufo) with PGE | No (stats) | https://www.metoffice.gov.uk/weather/learn-about/how-forecasts-are-made/observations/obs-critical-for-weather--climate ; https://github.com/JCSDA/ufo |
| **ACORN-SAT QC** | BoM (Australia) | Near-real-time screen → full QC weeks later; domain/spatial/spatial-temporal/NWP/trend/Bayesian model averaging. Hard bounds Tmax −60/+60, Tmin −30 (−40 if >1000m) | No | https://www.bom.gov.au/climate/headers/qc.shtml |
| **TITAN + ROVE** | Met Norway | Range → metadata → modified z-score → Pearson vs monthly median → buddy → SCT. **ROVE** = gRPC real-time engine. Robust Z default **3.1**. | No (robust stats) | https://asr.copernicus.org/articles/17/153/2020/ ; https://github.com/metno/rove |
| **CrowdQC+** | Citizen-station R package | 5 main + 4 optional QC levels; modified z-score with **Qn estimator** (Rousseeuw & Croux 1993) | No | https://github.com/dafenner/CrowdQCplus |
| **WeatherXM QoD** | WeatherXM (decentralized) | OBC + SQC with WMO-based thresholds: range, persistence (constancy), jump | No | https://docs.weatherxm.com/weather-and-science/quality-mechanisms/obc-sqc-documentation.mdx |

**Key takeaway for the pitch:** *only ECMWF uses ML operationally*, and even there it runs **post-assimilation on observation statistics, not at the edge on individual readings**. Most national services still use rules + robust stats. Our edge-deployed, per-reading, physics+ML+forecast+spatial fusion is genuinely ahead of the public state.

---

## C. Is our 6-layer idea novel? (honest assessment)

**Components all exist individually. The full integration does not appear to exist as a published system.**

| Our component | Closest prior art | What's new in ours |
|---|---|---|
| Isolation Forest on met data | Springer 2024 (Romania) | Edge-deployed on ESP32 (IEEE 2026 did it on Raspberry Pi, not ESP32) |
| LSTM-AE for QC | ECMWF 2023, Met Éireann 2026 | We use Chronos-2 (zero-shot, no per-station training) |
| Physics/rule layer | MADIS, TITAN, WMO-No. 8 | Standard — we cite, don't claim novelty |
| Spatial buddy check | Met Office ufo, TITAN, CrowdQC+ | Robust Z (median/MAD) — standard; we add MSL normalization for pressure |
| Forecast-informed QC | ECMWF O-B monitoring | We use a foundation forecasting model (Chronos-2) directly for corridor breach |
| Sensor health / self-healing | ECMWF blacklist, WDQMS | Composite score + predictive time-to-failure + auto-imputation = our framing |
| Edge + cloud split | IEEE 2026 (Pi), not ESP32 | ESP32-S3 transmit-only-on-suspicion = energy story |

**Verdict (for the slide):** "Individual layers are validated by ECMWF/Met Éireann/IEEE literature. The novel contribution is **the unified edge+cloud fusion pipeline with SHAP explainability and a self-healing sensor-health loop** — this exact combination has not been published."

---

## D. Competitors / comparable products

| Company / Project | What they do | How we differ | URL |
|---|---|---|---|
| **Tomorrow.io** (ex ClimaCell) | Weather intelligence, virtual sensing, AI forecasting | Focus is forecasting, **not sensor QC**. No edge-AI per station. | https://www.tomorrow.io/ |
| **Vaisala** | Industrial AWS + embedded QC in firmware | Hardware-bound, expensive per station. We're software + cheap ESP32. | https://www.vaisala.com/ |
| **WeatherXM** | Decentralized weather net + QoD scoring | **Most similar.** Uses WMO range/persistence/jump checks. **No ML layer.** | https://docs.weatherxm.com/ |
| **Met Office SAMOS/CODETS** | Semi-auto observing + QC | Legacy, rule-based, human-in-loop. No ML. | https://artefacts.ceda.ac.uk/badc_datadocs/ukmo-midas/ukmo_guide.html |

**Open-source QC pipelines on GitHub (cite as related work, not competitors):**
- `metno/rove` — Met Norway real-time QC engine (~50★): https://github.com/metno/rove
- `jkittner/meteo-qc` — Python met QC (~100★): https://github.com/jkittner/meteo-qc
- `dafenner/CrowdQCplus` — citizen-station QC in R (~20★): https://github.com/dafenner/CrowdQCplus
- `JCSDA/ufo` — Unified Frame for Observation processing incl. MetOfficeBuddyCheck (~200★): https://github.com/JCSDA/ufo
- `weatherxm-network/qod` — WeatherXM QoD (~10★): https://github.com/weatherxm-network/qod

---

## E. The honest "what's missing in the field" gaps we exploit

1. **No public met service runs ML at the edge of the AWS** — ECMWF's ML is post-assimilation on stats. We put a small IsoForest on the ESP32 itself.
2. **No public system fuses physics + ML + foundation-forecast + spatial in one pipeline** for AWS — components exist separately.
3. **No standard sensor-health score exists** (WDQMS uses trueness/precision/gross-error indicators; ECMWF uses blacklist criteria; both ad hoc). We propose a composite + predictive maintenance.
4. **Energy-aware transmit-only-on-suspicion** is unique — every competitor always transmits.
5. **WMO has no mandate for cryptographically signed AWS telemetry** (gap we can mention as future security work).
