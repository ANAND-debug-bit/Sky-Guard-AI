# 13 — The Raw Idea, In Detail (plain-language understanding)

> Written so anyone on the team can explain SkyGuard AI end-to-end without slides. This is the "understand it deeply" doc. The PPT lifts bullet points from here.

---

## The problem in plain English

Automatic Weather Stations (AWS) are little unmanned boxes with sensors for **temperature, pressure, and humidity**. They sit all over the country and report continuously. Their data feeds weather forecasts, aviation, farming, disaster warnings, climate research.

But the data is often **wrong**. Sensors break, get stuck, drift out of calibration, lose power, pick up electrical noise, or just glitch. A station in Delhi might suddenly say "55 °C with 92% humidity" while every nearby station says "35 °C / 60%." If that garbage flows into a forecast, the forecast is garbage.

**The old way:** humans set simple thresholds — "if temp > 50, flag it." This catches obvious garbage but misses subtle stuff: a sensor slowly drifting +0.3 °C/day, or a humidity sensor frozen at 88% while temp and pressure still move, or a temperature that's 45 °C (within range) but impossible *given* the humidity reading.

**Our way:** a 6-layer AI/ML pipeline that combines **physics, ML, forecasting, and neighbour consensus**, then **fuses** all those signals into one verdict that says not just "anomaly" but **which sensor, what kind of fault, how confident, and what to do about it.**

---

## The core insight (the one-sentence pitch)

> A single detector can't tell a broken sensor from a real heatwave. **Multiple detectors + neighbour consensus can.** That's the whole idea.

If only Delhi reports 55 °C → broken sensor. If Delhi *and* Lucknow *and* Jaipur all report 55 °C → it's a real heatwave, alert don't fix. The spatial layer is what separates fault from weather.

---

## The 6 layers, in plain language

### Layer 1 — Physics Sanity (the "is this even physically possible?" check)
Cheapest, runs first. Four sub-checks:
1. **Range:** Is the value within physical limits? (Temp −40 to +55 °C, RH 0–100%, pressure 300–1084 hPa.) India-restricted; tighter than global. Better: station-specific monthly mean ± 5σ (so 35 °C is fine in May, suspicious in January).
2. **Dew point:** Compute dew point from temp + humidity using the Magnus formula. Dew point can **never** exceed air temp (that would mean RH > 100%, impossible). If it does → humidity sensor is lying.
3. **Barometric:** Pressure drops with altitude. A station at 2200 m (Shimla) should read ~780 hPa, not 1013. If reported pressure is > 30 hPa off what altitude predicts → barometer miscalibrated.
4. **Rate of change:** Weather changes gradually. Temp jumping 19 °C in an hour = fault (MADIS limit). Pressure dropping 3 hPa/hr = *alert candidate* (could be a cyclone — neighbours decide if it's real). Pressure dropping 15 hPa/hr = fault.

**Why it matters:** catches impossible values instantly, zero training, zero false negatives on physically impossible readings. If this layer hard-vetoes, we skip the expensive layers.

### Layer 2 — ML Anomaly (the "does this combination look weird?" check)
**Isolation Forest** — an unsupervised model that isolates anomalies by random splitting. Anomalies (rare/sparse) get isolated in few splits; normal points (dense) take many. Average path length across 100 trees → anomaly score. No labelled data needed.

But IsoForest has blind spots (misses clustered anomalies, misses slow drift, misses frozen values that are "within range"). So we add:
- **Extended Isolation Forest** (random hyperplane splits — fixes the axis-aligned ghost-cluster bug).
- **LSTM Autoencoder** sibling (reconstructs the normal temporal pattern; high reconstruction error = anomaly). This is what ECMWF (2023) and Met Éireann (2026, 99.6% accuracy) use. Catches temporal/flatline patterns IsoForest misses.
- **Trend/drift detection** via Mann-Kendall test + Theil-Sen slope — catches slow decalibration that individual-point detectors miss.
- **Gap/dropout detection** — NaN patterns: all sensors NaN = power cut; some NaN = individual sensor failure.

**Explainability:** when IsoForest flags, **SHAP** attributes the anomaly score to each feature → we know *which sensor* drove the verdict. (SHAP explains path length, not the predict label — sign gotcha, documented.)

**De-seasonalize first** (ECMWF's trick): feed the model *residuals* after removing seasonal climatology, so summer doesn't look anomalous relative to winter.

### Layer 3 — Frozen Sensor (the "is the sensor stuck?" check)
A real physical quantity always fluctuates. If temperature reads 28.3, 28.3, 28.3, 28.3, … for 12 hours → sensor is jammed (ice, dust, mechanical). Detection: std-dev of the window < 0.01, or 2nd-derivative ≈ 0. If all 3 sensors frozen → the whole data logger is dead, not one sensor.

### Layer 4 — Forecasting (the "what should the next reading be?" check)
**Chronos-2** (Amazon's foundation forecasting model, 120M params, real HuggingFace repo) predicts the next reading from the last 20. It gives a p5/p50/p95 confidence corridor. If the actual reading lands outside [p5, p95], or the breach severity > 0.8 → anomaly. Per-variable thresholds because pressure is smoother than humidity.

**Why it's powerful:** zero-shot — no per-station training. Works on a new station immediately. Catches a 45 °C reading that's "within range" but way above what the trend predicted.

**Cost:** the heaviest layer (~50–200 ms on GPU). So we run it **only on readings that survived L1–L3 unsuspicious or need a second opinion** — saves latency and energy.

### Layer 5 — Spatial Consistency (the "do the neighbours agree?" check)
This layer **doesn't detect anomalies** — it provides context. Find neighbours within 500 km (Haversine). Compute a **robust Z-score**: `|my_value − median(neighbours)| / (1.4826 × MAD)`. Use median/MAD (not mean/std) so one faulty neighbour doesn't skew the baseline. Z ≥ 3.1 (TITAN's default) → neighbours disagree.

**Pressure caveat:** must normalize to sea level (MSL) before comparing, else altitude differences alone look anomalous (Delhi 990 hPa vs Shimla 780 hPa is normal, not a fault).

**Honest limits:** isolated stations (Kolkata, Guwahati) have no neighbours → can't run this layer → we say so. Terrain (mountains/valleys) needs lapse-rate correction, which fails during inversions → we say so.

### Layer 6 — Fusion (the brain — the 2×2 decision matrix)

| | Neighbours AGREE (Z<3.1) | Neighbours DISAGREE (Z≥3.1) |
|---|---|---|
| **Model flagged** (L1–L4) | **REGIONAL_EVENT** — real weather, alert not fault (Medium) | **SENSOR_FAULT** — sensor is broken (High) |
| **No model flag** | **HEALTHY** — all clear | **CHECK_HEALTH** — subtle drift, schedule maintenance (Low) |

Plus fault-type classification (priority: Frozen > Physics > Forecast > ML) + confidence tier (from how many layers agreed).

**The magic:** this matrix is what separates "Delhi sensor says 55 °C, broken" from "heatwave across North India, real." Single-detector systems can't do this.

---

## The self-healing loop (the grand-challenge answer)

Live detection evaluates one reading at a time. But sensors **degrade slowly** — each reading is individually "fine" until the drift is huge. By then, weeks of subtly bad data have flowed downstream.

**Solution — composite Sensor Health Score [0,1]:**
```
Health = w₁·(1 − bias) + w₂·(1 − residual_rms) + w₃·availability
       + w₄·(1 − anomaly_rate) + w₅·(1 − age_degradation)
```
- **bias:** rolling observation-vs-forecast/neighbor bias (ECMWF O-B).
- **residual_rms:** RMS of Chronos-2 forecast residuals (WDQMS precision).
- **availability:** % readings actually received (IMD monitors this hourly).
- **anomaly_rate:** % flagged by L1–L4 (our pipeline).
- **age_degradation:** time-since-calibration ÷ WMO cycle (T/P 1–2 yr, RH annual).

**Tiers:** ≥0.85 Green / 0.6–0.85 Amber / 0.4–0.6 Orange (schedule recal) / <0.4 Red (dispatch now).

**Predictive:** fit a trend to the score → estimate weeks-to-failure → flag before it breaches.

**Self-healing:** degraded sensor → downstream feeds auto-upweight neighbour/Chronos-imputed values until fixed → **trustworthy data flows uninterrupted**. That's the "self-aware, self-healing network" the grand challenge asks for.

---

## The edge + cloud split (energy + deployability story)

**ESP32-S3 on the station runs:** L1 physics + L3 frozen + gap check + a small int8 Isolation Forest (emlearn, <10 KB flash) + tiny autoencoder (TFLite-Micro). This catches ~70–80% of faults locally.

**Gateway/cloud runs:** full L2 (IsoForest+SHAP+LSTM-AE), L4 (Chronos-2), L5 (spatial), L6 (fusion).

**Transmit-only-on-suspicion:** the ESP32 only radios upstream when it sees something suspect. ~72% transmit-energy saving → battery lasts ~10 months vs ~3 months always-transmit. This is the Energy Efficiency (5%) + Practical Deployability (10%) story in one design choice.

---

## Why this wins (mapped to SIH judging)

| SIH criterion | How we win it |
|---|---|
| Novelty (25%) | Edge+cloud fusion + self-healing loop + SHAP-on-IsoForest; full integration not published before |
| Complexity (SIH) | 6-layer fusion + foundation forecasting + edge ML + robust spatial stats |
| Clarity (SIH) | This doc + the architecture diagram + the 2×2 matrix |
| Feasibility (SIH) | Standards-aligned (WMO L0–L5), free data, runs on cheap ESP32, honest about limits |
| Sustainability (SIH) | 72% energy saving, longer field life, less e-waste |
| Scale of impact (SIH) | Every AWS network globally; IMD 675+ stations; NOAA 20,000+ |
| User experience (SIH) | Every alert explained (SHAP + reason + confidence + action) |
| Future work (SIH) | Clear pilot→production ladder (see `12-production-grade.md`) |
| Detection accuracy (problem weights) | Multi-layer redundancy + PR-AUC/F2 eval on injected benchmark |
| Real-time (problem weights) | Edge pre-filter + cheap-layers-first cascade + <1 min SLO |
| Explainability (problem weights) | SHAP + per-fault natural language + confidence tier |
| Scalability (problem weights) | Stateless workers + Redis + BullMQ + TimescaleDB |
| Visualization (problem weights) | Leaflet map (health colour) + alert feed + SHAP bar + forecast corridor |

---

## The deliverables we claim (matches problem statement "Expected Outputs")

| Expected output | Where in our system |
|---|---|
| Real-time anomaly alerts | L6 verdict → WebSocket push |
| Severity & confidence scores | L6 confidence tier (HIGH/MED/LOW) + numeric |
| Root-cause classification | `fault_type` from fusion priority (Frozen>Physics>Forecast>ML) |
| Visualization dashboard | Leaflet map + alert feed + SHAP chart + forecast corridor |
| Sensor health status | Composite health score [0,1] + tier |
| Corrected data estimation (optional) | Imputation ensemble: neighbour median → Kalman → Chronos p50 → NWP analog |
