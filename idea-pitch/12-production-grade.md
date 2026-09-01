# 12 — Production-Grade Upgrade Path

> What turns this from a hackathon idea into something a real met service (IMD/ECMWF/NOAA) would deploy. Use this for the SIH "Feasibility & Viability" slide's future-work progression and the "Potential for future work progression" judging criterion.

---

## The 3-stage maturity ladder

```
STAGE 1 — Hackathon Idea (now)        STAGE 2 — Pilot               STAGE 3 — Production
─────────────────────────             ─────────────────             ─────────────────────
Slides + architecture                 1 region, ~50 stations        National network, 675+ IMD
Injected anomalies on ERA5            Real IMD API data             Real-time ingest + 24/7 ops
Offline benchmark (PR-AUC/F2)         Live verdicts vs analyst      NWP O-B buddy + human review
Single Python process                 Docker Compose                K8s + autoscale + MQ
Markdown plan                         Demo dashboard                Grafana + alert routing
                                      A/B vs deterministic QC       Audit logs + WMO traceability
```

---

## MLOps (the biggest gap)

| Capability | Hackathon | Production | Source |
|---|---|---|---|
| Model versioning | none | **DVC/MLflow** — track model artifacts + training-data snapshots per station cluster | standard |
| Drift monitoring | none | **PSI (Population Stability Index)** on input features; **CSI** for concept drift; retrain when PSI>0.2 | Kataria 2026 (F1=0.91) |
| A/B threshold testing | none | Run deterministic QC + ML QC in parallel; compare false-alarm rates; promote threshold after N clean days | Kataria 2026 |
| Human-in-the-loop | none | AI proposes blacklist/maintenance; **human analyst dispositions** before action | ECMWF operational model |
| Audit logs | none | Every QC decision logged: who/what/when/why/which-layers/SHAP values | WMO-No. 8 / WIGOS traceability |
| Fallback path | n/a | If ML service down → fall back to deterministic L1+L3+L5 only → ops continues | operational reliability |
| Retraining trigger | manual | Seasonal (quarterly) + PSI-driven + post-REGIONAL_EVENT exclusion | ECMWF de-seasonalize practice |

---

## Data layer upgrades

| Hackathon | Production | Why |
|---|---|---|
| Open-Meteo/ERA5 gridded | **IMD AWS API** (api.imd.gov.in) + ERA5 as NWP background | Real station noise/dropout; ERA5 becomes the "virtual buddy" for isolated stations |
| 15-station demo | Full IMD 675+ network | Spatial buddy check reaches TITAN's min-5-buddies requirement |
| Single-region flat terrain | Terrain-aware: lapse-rate correction (−0.0065 °C/m) + inversion detector | Himalayas/Western Ghats — Euskalmet caveat |
| Injected anomalies | Injected + real ISD noise patterns + operational warning labels (semi-auto) | ECMWF-style semi-automatic labelling |
| One clean baseline | Per-station rolling climatology (monthly ±5σ) | Seasonal correctness |

---

## Imputation SOTA (the "corrected data estimation" deliverable, production-grade)

Priority-ordered ensemble with confidence weight per source:

| Priority | Method | Best for | Source |
|---|---|---|---|
| 1 | **Robust neighbour median** (L5) | When buddies agree | our L5 |
| 2 | **Kalman filter / structural time series** | Short gaps in smooth hourly series | Berman et al. 2019 — https://rmets.onlinelibrary.wiley.com/doi/10.1002/met.1873 |
| 3 | **Chronos-2 p50** (L4) | Isolated stations, multi-step | amazon/chronos-2 |
| 4 | **Analog method (NWP-derived)** | Regime changes, captures non-stationarity | Delle Monache et al. 2011 — https://journals.ametsoc.org/view/journals/mwre/139/11/2011mwr3653.1.xml |
| 5 | **missForest (RF-based)** | Large multivariate gaps | review: https://www.sciencedirect.com/science/article/pii/S2215016125003000 |

**Best practice per the review:** hybrid ensembles outperform single methods. Report imputed value + source + confidence; **never auto-overwrite** operational met data (advisory only, human approves).

---

## Alert routing & incident management (operational SLA)

| Stage | Action | SLA | Source |
|---|---|---|---|
| Detect | L1–L6 verdict in < 1 min per reading | < 1 min | Oklahoma Mesonet does 640K obs/day in <1 min |
| Triage | HIGH-confidence SENSOR_FAULT → immediate ticket to field tech | minutes | Oklahoma Mesonet trouble-ticket model |
| Review | ML proposes blacklist; QA meteorologist approves monthly | daily/monthly | ECMWF operational model |
| Escalate | SEVERE REGIONAL_EVENT → disaster-management channel | real-time | WMO "authoritative voice" principle |
| Track | Every sensor: open tickets, resolution status, repair history | continuous | Oklahoma Mesonet monthly QA report |
| Report | Monthly QA report: all problems + repairs + sensor-health trends | monthly | Oklahoma Mesonet / ECMWF |

---

## Security & integrity (our differentiated contribution)

**Verified gap:** WMO has **no mandate** for cryptographically signed AWS telemetry. We propose:
- **HMAC-signed readings** from ESP32 → gateway (shared key per station, rotated).
- **Tamper-detection classifier** trained on signed-vs-tampered patterns — flags replay/injection attacks as a distinct fault class.
- **Chain-of-custody audit log** — every reading + verdict + disposition traceable to a station + sensor serial + calibration certificate.
- Aligns with WMO Congress Oct 2025 emphasis on "openness, transparency, traceability."

**Pitch line:** "We close a verified WMO gap — no standard mandates signed AWS telemetry today; SkyGuard adds HMAC integrity + tamper detection as a first-class concern."

---

## Scalability (production numbers)

| Dimension | Hackathon | Production |
|---|---|---|
| Stations | 15 | 675+ (IMD) → 20,000+ (NOAA ISD scale) |
| Readings/day | ~4K (sim) | ~1.6M (675 × 288/day) → ~5.8M (NOAA scale) |
| Compute | 1 Python pod | K8s autoscale, stateless workers, BullMQ queue |
| Store | TimescaleDB single node | TimescaleDB cluster, hypertable partitioned by time + station |
| Cache | Redis single | Redis cluster (per-station windows + neighbour map) |
| Edge | 1 ESP32 sim | 675+ ESP32-S3 field units, OTA with rollback |
| Latency SLO | best-effort | p95 < 1 min end-to-end (Oklahoma Mesonet benchmark) |

---

## Regulatory alignment (WMO / national)

| Requirement | How we comply |
|---|---|
| WIGOS "known, traceable quality" | Audit log + SHAP explanation + deterministic fallback |
| WMO Congress Oct 2025: AI complements not replaces physics | Physics layer (L1) is never bypassed; ML layers augment |
| China AI-met regulation (if relevant): algorithm filing, data/content labelling | We label every AI-derived verdict as such in the audit log |
| NMHS authoritative voice | We never issue public warnings; we flag to the met service which decides |
| Calibration traceability (WMO-No. 8) | Sensor-health score includes calibration-age component; cycle tracking |

---

## Energy budget (production field unit)

| Mode | Current (mA) | Duty | mAh/day |
|---|---:|---|---:|
| Deep sleep (ESP32-S3 module) | 0.008 | ~99.9% | 0.19 |
| Sensor sample + edge ML (50 mA, 200 ms) | 50 | 288×/day | 8.06 |
| LoRa TX @17 dBm only on suspicion (330 mA, 1 s) | 330 | ~14×/day (5% anomaly) | 1.32 |
| **Total (anomaly-only transmit)** | | | **~9.6** |
| Always-transmit baseline | | | **~34.6** |
| **Saving** | | | **~72%** |

**Battery life (3000 mAh Li-ion + solar top-up):** ~10 months anomaly-only vs ~3 months always-transmit. Source: ESP32-S3 datasheet (7 µA deep sleep); Heltec V4 datasheet (LoRa TX currents); https://documentation.espressif.com/esp32-s3_datasheet_en.html
