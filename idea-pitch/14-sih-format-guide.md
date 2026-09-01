# 14 — SIH Format Guide (Smart India Hackathon)

> Official SIH idea-submission format + how we map our content to it. This is the template the 3 PDFs follow.

---

## SIH idea submission = exactly 6 slides, exported as PDF

**Verified format** (SIH 2025 / SIH 2026 guidelines, Ministry of Education Innovation Cell):

| Slide | Section | Required content |
|---|---|---|
| 1 | **Title Slide** | Problem Statement ID, PS Title, Theme, PS Category (Software/Hardware), Team ID, Team Name, Idea Title |
| 2 | **Proposed Solution** | Detailed solution explanation; how it addresses the problem; innovation & uniqueness |
| 3 | **Technical Approach** | Technologies used (languages, frameworks, hardware); methodology + process (flow charts, images, prototype) |
| 4 | **Feasibility & Viability** | Feasibility analysis; challenges & risks; strategies to overcome them |
| 5 | **Impact & Benefits** | Impact on target audience; benefits (social, economic, environmental) |
| 6 | **Research & References** | Details/links of reference and research work |

**Rules:**
- Max **6 slides** (title counts).
- **No paragraphs** — points / diagrams / infographics / pictures only.
- Save as **PDF**, upload to SIH portal.
- Idea must be **unique and novel.**
- Team = **6 members** (inc. leader + ≥1 female), same college, +1–2 mentors (5+ yrs exp).
- One team → max 2 Problem Statements.

**Sources:**
- SIH portal: https://sih.gov.in
- SIH 2026 Idea Presentation Format: https://www.scribd.com/document/1075380264/SIH2026-IDEA-Presentation-Format
- SIH 2025 template: https://www.scribd.com/presentation/884917405/SIH2025-IDEA-Presentation-Format
- SIH 2026 guidelines: https://www.scribd.com/document/1077654176/Guidelines-of-SIH2026

> **Note (pre-screening round, SIH 2026 Phase 2):** also requires a PPT per SIH format + a **demonstration video** (team-narrated, not AI-generated, must show prototype) + a **GitHub repo** with partial implementation. That's the *next* round — not the idea submission. For the idea round it's the 6-slide PDF only. (Since you said slides-only for the internal round, the 3 PDFs below are idea-round deliverables.)

---

## SIH evaluation criteria (official MIC)

1. Novelty of the idea
2. Complexity of the approach
3. Clarity and details in the prescribed format
4. Feasibility and practicability
5. Sustainability
6. Scale of impact
7. User experience
8. Potential for future work progression

Plus the problem-statement's own weights: Innovation 25%, Detection Accuracy 20%, Real-Time 15%, Explainability 10%, Scalability 10%, Deployability 10%, Visualization 5%, Energy 5%.

---

## How we map SkyGuard content to the 6 SIH slides

### Slide 1 — Title
- PS ID / PS Title: "AI/ML-Based Intelligent Anomaly Detection for Automatic Weather Stations (AWS)"
- Theme: (per your SIH portal — likely "Smart Automation" or "MedTech/Biotech/HealthTech" bucket depends on your PS list)
- Category: Software (with hardware edge component)
- Team ID / Team Name / Idea Title: **"SkyGuard AI — Self-Healing Weather Observation Network"**

### Slide 2 — Proposed Solution (Novelty + Complexity)
- The problem in 2 lines (AWS data pollution, threshold-only QC insufficient)
- Our solution in 1 line: **6-layer edge+cloud fusion pipeline mirroring WMO L0–L5, with SHAP explainability and a self-healing sensor-health loop**
- The core insight box: **single detector can't tell broken sensor from heatwave; multi-layer + neighbour consensus can** (the 2×2 fusion matrix mini-diagram)
- Novelty bullets: edge-deployed ML on ESP32 (no competitor does this); full physics+ML+forecast+spatial fusion not published; composite self-healing health score; transmit-only-on-suspicion (72% energy saving)
- Diagram: the 6-layer pipeline (L1→L6) + edge/cloud split

### Slide 3 — Technical Approach (Clarity + Complexity)
- **Tech stack table:** ESP32-S3 + emlearn + TFLite-Micro (edge) | Node.js + FastAPI + Python (gateway) | scikit-learn (EIF), SHAP, LSTM-AE, amazon/chronos-2, alibi-detect | TimescaleDB + Redis + BullMQ | React + Leaflet
- **Layer breakdown** (one row each): L1 physics (range/dew-point/barometric/rate), L2 ML (EIF + LSTM-AE + SHAP + trend), L3 frozen (std/2nd-deriv), L4 Chronos-2 corridor, L5 robust-Z spatial, L6 fusion matrix
- **Thresholds table** (the sourced ones): temp 19.4°C/hr fault / pressure 15 hPa/hr fault + 3 hPa/hr alert / RH 50%/hr / robust-Z 3.1 / dew-point +0.5°C tolerance / std<0.01 frozen
- **Data flow diagram:** AWS sensor → ESP32 edge filter → gateway ML → fusion → alert + health + store
- **Data sources:** Open-Meteo (ERA5, free, no key) + NOAA ISD (real station noise) + De Bruijn 2016 injected-anomaly benchmark + IMD API (production path)

### Slide 4 — Feasibility & Viability (Feasibility + Sustainability + Future-work)
- **Feasibility:** standards-aligned (WMO L0–L5), free data, cheap ESP32-S3 (~₹500), runs on commodity cloud. Each component validated in literature (ECMWF 2023, Met Éireann 2026 99.6%, IEEE 2026 edge-IF).
- **Risks & mitigations table** (lift from `11-strengths-weaknesses.md` F1–F10): isolated stations → multi-layer agreement + NWP virtual buddy; IsoForest blind spots → EIF + LSTM-AE + PSI retrain; ML flags real weather → spatial consensus + de-seasonalize; class imbalance → PR-AUC/F2 not accuracy; ESP32 constraints → int8 + OTA rollback; regulatory → explainability + human-in-loop + deterministic fallback.
- **Maturity ladder:** Idea → Pilot (1 region, 50 stations, IMD API) → Production (675+ IMD, K8s, audit logs, WMO traceability)
- **Sustainability:** 72% energy saving, ~10 mo battery vs ~3 mo, less e-waste, less field trips

### Slide 5 — Impact & Benefits (Scale of impact + UX)
- **Target audience:** IMD, State met departments, aviation, agriculture, disaster management, climate research
- **Scale:** IMD 675+ AWS → NOAA ISD 20,000+ globally; every AWS network is a customer
- **Benefits:**
  - *Social:* better forecasts → better disaster warnings → lives saved
  - *Economic:* less bad-data propagation → fewer wrong forecasts → less economic loss; longer sensor life → lower maintenance cost
  - *Environmental:* 72% energy saving + longer field life → less e-waste
- **User experience:** every alert = verdict + confidence + blamed sensor (SHAP) + plain-English reason + recommended action + imputed value; dashboard = map (health colour) + alert feed + SHAP chart + forecast corridor

### Slide 6 — Research & References (the citations)
- WMO-No. 8 CIMO Guide 2024: https://library.wmo.int/viewer/68695/
- NOAA MADIS QC: https://madis.ncep.noaa.gov/madis_sfc_qc_notes.shtml
- ECMWF ML data checking (Dahoui 2023): https://www.ecmwf.int/en/newsletter/174/
- Met Éireann LSTM-AE 99.6% (Spohn 2026): https://www.cambridge.org/core/journals/environmental-data-science/article/machine-learning-approach-using-autoencoders-to-perform-quality-control-on-meteorological-data/4576781508080877E36C0CA6612E5590
- Edge IsoForest IEEE 2026: https://doi.org/10.1109/iciscois62701.2026.11447816
- 6-layer MLOps Kataria 2026 (F1=0.91): https://doi.org/10.1109/menacomm69507.2026.11532803
- Met Norway TITAN + ROVE: https://asr.copernicus.org/articles/17/153/2020/ , https://github.com/metno/rove
- Chronos-2 (arXiv:2510.15821): https://huggingface.co/amazon/chronos-2
- SHAP TreeExplainer IsoForest: https://github.com/shap/shap/pull/784
- alibi-detect v0.13.0: https://github.com/SeldonIO/alibi-detect
- Fiebrich & Crawford 2001 (Mesonet QA): https://doi.org/10.1175/1520-0477(2001)082
- ESP32-S3 datasheet: https://documentation.espressif.com/esp32-s3_datasheet_en.html
- Open-Meteo Archive API: https://open-meteo.com/en/docs/historical-weather-api
- NOAA ISD: https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database
- De Bruijn 2016 injected-fault benchmark: https://doi.org/10.5220/0005637901850195

---

## The 3 PDFs we generate (each is a full 6-slide SIH deck)

You asked for 3 different demo PPTs in SIH format. I produce three **complete, standalone** 6-slide SIH decks, each emphasizing a different narrative angle so you can pick the strongest:

| PDF | Narrative angle | Best for |
|---|---|---|
| **PDF 1 — Grand-Challenge / Self-Healing** | Leads with the self-aware, self-healing network (composite health score + predictive maintenance + auto-imputation). Matches the problem's grand-challenge line directly. | Maximum Innovation (25%) score; the "one slide judges remember" |
| **PDF 2 — Technical / Architecture-Deep** | Leads with the 6-layer fusion + WMO L0–L5 alignment + thresholds + edge/cloud split. Most rigorous. | Maximum Complexity + Clarity + Detection-Accacy score; defensible to technical judges |
| **PDF 3 — Edge + Energy + Deployability** | Leads with ESP32 edge-AI + transmit-only-on-suspicion + 72% energy saving + cheap hardware. | Maximum Energy (5%) + Deployability (10%) + Sustainability score; appeals to field-ops judges |

All three share the same evidence base (same thresholds, same references, same fusion matrix) — they differ in *emphasis and ordering*, not in facts. Pick the one that lands best with your judges, or blend slides across them.
