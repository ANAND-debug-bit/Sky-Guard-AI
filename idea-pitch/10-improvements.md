# 10 — Improvements (what can be made better)

> Concrete, prioritized upgrades to push the idea from "good" to "best in hackathon." Each marked by effort vs pitch payoff. You said "polish what we have, don't add new tech" — so these refine the existing 6 layers + health score, not new paradigms.

---

## P0 — Do these before the pitch (high payoff, low effort)

### 1. Fix the pressure rate-of-change conflation (DONE in `02-thresholds.md`)
**Was:** single 3 hPa/hr threshold flagged as fault.
**Now:** two-tier — 15 hPa/hr = fault (MADIS), 3 hPa/hr = severe-weather *alert candidate* (resolved to REGIONAL_EVENT by L6 if neighbours agree).
**Why:** the old value would false-alarm on every normal weather system. This fix is itself a slide-worthy point about doing the homework.

### 2. Tighten the spatial Z threshold to the published standard
**Was:** Z ≥ 2.0.
**Now:** Z ≥ 3.1 (Met Norway TITAN default). State we tune in [2.0, 3.5].
**Why:** 2.0 is too loose and would over-flag; 3.1 is the cited production value.

### 3. Add station-specific climatological bounds (±5σ monthly)
**Was:** fixed global range (−40/+55 °C).
**Now:** primary = monthly mean ± 5σ per station (WMO/Lanzante); global range as a hard backstop.
**Why:** a 35 °C reading is fine in May, anomalous in January. This is the single biggest accuracy improvement and it's cheap.

### 4. Replace "accuracy" with PR-AUC / F2 in the eval story
**Was:** implied accuracy.
**Now:** state we evaluate with **PR-AUC** and **F2-score** (recall-weighted) because anomalies are <1–5% of data — accuracy is misleading (Kataria 2026).
**Why:** judges who know ML will ding "99% accuracy" on imbalanced data. Pre-empt it.

### 5. Cite real production systems on the same slide as our architecture
Add ECMWF (LSTM-AE operational), MADIS, TITAN, Met Office buddy check to the "Research & References" slide. Our architecture *mirrors* WMO L0–L5 — say so explicitly. This converts "invented in a vacuum" → "standards-aligned + ML-augmented."

---

## P1 — Strong upgrades (medium effort, high payoff)

### 6. Add an LSTM-AE as an L2 sibling to Isolation Forest
**Why:** the two best papers (ECMWF 2023, Met Éireann 2026) both use **LSTM-AE**, not IsoForest, as the primary detector. Met Éireann hit **99.6% accuracy** with it. IsoForest alone has documented weaknesses (clustered anomalies, drift blindness, axis-aligned ghost clusters — Chabchoub 2022, Liu 2012).
**How:** L2 = Isolation Forest (fast, explainable via SHAP) **OR** LSTM-AE (catches temporal patterns + flatline IsoForest misses). Ensemble vote. SHAP still explains the IsoForest branch.
**Pitch line:** "Two complementary detectors — IsoForest for multivariate outliers (explained by SHAP), LSTM-AE for temporal/flatline patterns — ensemble-voted."

### 7. Use **Extended Isolation Forest (EIF)** instead of plain IsoForest
**Why:** plain IsoForest uses axis-parallel splits → creates "ghost clusters" of false high anomaly scores and isn't rotation-invariant (Hariri 2019, Chabchoub 2022). EIF uses random hyperplane splits → fixes both.
**How:** drop-in replacement (`eif` package / `sklearn`-compatible). Same SHAP story.
**Pitch line:** "We use Extended Isolation Forest to avoid the axis-aligned ghost-cluster failure mode of standard IsoForest."

### 8. Add **PSI-driven retraining** to the sensor-health loop
**Why:** concept drift makes a static IsoForest stale. Kataria 2026 shows **PSI > 0.2** triggers retrain and keeps F1 at 0.91.
**How:** monitor Population Stability Index of the input feature distribution per station; retrain the IsoForest on a rolling normal window when PSI > 0.2.
**Pitch line:** "Self-aware model freshness — PSI-driven retraining handles concept drift and seasonality automatically."

### 9. De-seasonalize before ML (ECMWF's trick)
**Why:** ECMWF explicitly de-seasonalizes data before training their LSTM-AE, because climate normals shift monthly and raw values would make summer look anomalous relative to winter (Dahoui 2023).
**How:** subtract the station's monthly climatology (or use the seasonal-decomposition residual) as the input to IsoForest/LSTM-AE, not raw T/P/RH.
**Pitch line:** "We de-seasonalize inputs before ML detection, following ECMWF's operational practice — so the model sees anomalies, not seasons."

### 10. Make imputation a 3-source ensemble (not a single value)
**Was:** imputed value = neighbour median OR Chronos p50 OR seasonal.
**Now:** priority-ordered ensemble with confidence:
1. Neighbour robust-median (L5) — best when buddies agree.
2. **Kalman filter / structural time series** — best for short gaps in smooth series (Berman 2019).
3. Chronos-2 p50 (L4) — best for isolated stations.
4. Analog method (NWP-derived) — best for regime changes (Delle Monache 2011).
**Pitch line:** "Imputation is a source-ordered ensemble — neighbour consensus, Kalman smoothing, foundation-model forecast, NWP analog — each with a confidence weight."

### 11. Add **human-in-the-loop** for blacklist/maintenance (ECMWF model)
**Why:** ECMWF's operational system *proposes* blacklist updates automatically but a human analyst *approves* them monthly. WMO Congress (Oct 2025) emphasized AI must "complement, not replace" physics-based methods and remain "transparent and traceable."
**How:** our sensor-health score auto-flags, but a maintenance ticket is routed for human review before any sensor is blacklisted. Audit log every decision.
**Pitch line:** "AI proposes, human dispositions — WMO-aligned traceability, no black-box auto-blacklisting."

---

## P2 — Nice-to-have (higher effort, lower idea-stage payoff)

### 12. Probabilistic frozen-sensor detection (CVT)
Replace fixed `std<0.01` with the **Constant Value Test** (AMT 2023): P(same value | μ, σ, φ₁, resolution). Adapts to each station's natural variability. Mention as the production upgrade over our fixed threshold.

### 13. Conformal prediction for calibrated intervals
Replace Chronos-2's p5/p95 with **conformal prediction** for guaranteed-coverage intervals. Mathematically rigorous; hard to defend at idea stage without a demo. Keep as "future work."

### 14. Terrain-aware spatial check
Add lapse-rate correction (−0.0065 °C/m) for mountain/valley neighbours, with an **inversion detector** to disable it during temperature inversions (Euskalmet caveat). Improves spatial accuracy in mountainous India (Himalayas, Western Ghats).

### 15. OTA model update with rollback
For the ESP32 edge tier: ESP-IDF OTA with fail-safe boot partition. Mention under "practical deployability" — real field devices need safe remote updates.

### 16. Signed telemetry (security)
WMO has **no mandate** for cryptographic signing of AWS telemetry (verified gap). Propose HMAC-signed readings + tamper-detection as our security contribution. Cheap to add to the pitch, differentiated.

---

## What I did NOT add (you said no new paradigms)
- ❌ Federated learning — would be a great scalability story but you said polish, not expand.
- ❌ Physics-Informed Neural Networks — high novelty but hard to defend at idea stage.
- ❌ Digital twin per station — elegant but new concept.
- ❌ Causal inference — high novelty, very hard to demo.

If you change your mind on any of these, say the word and I'll integrate.

---

## Improvement priority matrix (for your time budget)

| Improvement | Effort | Pitch payoff | Do it? |
|---|---|---|---|
| 1. Fix pressure threshold | done | high | ✅ done |
| 2. Z=3.1 | trivial | high | ✅ do |
| 3. Climatological ±5σ | low | high | ✅ do |
| 4. PR-AUC/F2 eval | low | high | ✅ do |
| 5. Cite production systems | low | high | ✅ do |
| 6. LSTM-AE sibling | medium | high | ✅ strongly recommend |
| 7. Extended IsoForest | low | medium | ✅ do |
| 8. PSI retraining | medium | high | ✅ do |
| 9. De-seasonalize | low | high | ✅ do |
| 10. Imputation ensemble | low | medium | ✅ do |
| 11. Human-in-the-loop | low | high | ✅ do |
| 12. Probabilistic CVT | medium | medium | mention only |
| 13. Conformal | high | low at idea stage | future work |
| 14. Terrain-aware spatial | medium | medium | mention only |
| 15. OTA rollback | low | medium | mention |
| 16. Signed telemetry | low | medium | ✅ do (cheap differentiation) |
