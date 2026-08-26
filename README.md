# Weather Anomaly Detection — Project Plan

A multi-layer pipeline that flags anomalies in weather station sensor data by combining **physics sanity checks**, **ML-based anomaly detection**, **sensor-fault pattern detection**, **forecasting**, and **spatial cross-validation** — before fusing everything into a final confidence verdict.

---

## Data Pipeline

```
Open-Meteo API (ERA5, Indian stations)
        +
   Anomaly Injection
        ↓
    Time Series DB
        ↓
Replay past data to simulate the model
```

- Historical weather data is pulled from the **Open-Meteo API** (ERA5 reanalysis, Indian stations).
- Synthetic anomalies are injected into the clean data so the pipeline can be tested against known ground truth.
- Data is stored in a time-series DB and **replayed** to simulate how the model would behave in real time.

---

## Layer 1 — Physics Sanity Checks

### 1) Temperature ↔ Pressure

Barometric formula relating pressure and altitude/temperature:

```
P_h = P_0 · e^(−Mgh / RT)
```

A more practical, station-usable version — reducing station pressure to Mean Sea Level (MSL) pressure:

```
P_MSL = P_station · (1 − 0.0065h / (T + 0.0065h + 273.15))^(−5.257)
```

- If the reported pressure is inconsistent with what's expected from `P_MSL`, it's flagged as the **final plausible range check** for station pressure.

### 2) Temperature ↔ Humidity (Dew Point)

Uses the **Magnus formula**:

```
γ(T, RH) = ln(RH / 100) + (a·T) / (b + T)

T_dew = (b · γ(T, RH)) / (a − γ(T, RH))
```

Where:
- `a = 17.625`, `b = 243.04°C` (Alduchov–Eskridge constants)
- Valid for `T ∈ [−40°C, 50°C]`

**Hard physical constraint:**

```
T_dew ≤ T_air   (always true)
```

- Since RH = (actual water vapour ÷ max water vapour air can hold) × 100%, if `T_dew > T_air` that implies `RH > 100%`, which is physically **impossible** → flagged as a **humidity sensor fault**.
- **Depression check:** `(T_air − T_dew)` being extremely low (with reported low humidity) *or* extremely high (with reported high humidity) are **both suspicious signals**.

---

## Layer 2 — ML Anomaly Detection

### 1) Isolation Forest + SHAP

**Why Isolation Forest:** it's fast, unsupervised, needs no pre-training on "normal" data, and isolates anomalies as it requires no labeled anomaly data upfront.

**Idea:** Given `n` instances of a feature, recursively take a random split of a random feature range, dividing instances at each split — repeating until every instance is isolated (i.e., all circles reduced to a leaf of 1). Since splits are random, anomalies (rare/sparse values) tend to get isolated in far fewer splits than densely-packed normal values.

**Problem with plain path length:** it's possible for a split to randomly separate a normal instance quickly by chance. So instead of relying on a single tree, a **collection of trees** is built and the **average path length** is computed across all of them.

**Anomaly score formula:**

```
s(x, n) = 2^(−E(h(x)) / c(n))
```

Where:
- `h(x)` = path length of instance `x`
- `E(h(x))` = average path length across all isolation trees
- `c(n)` = normalization value based on sample size `n`

### 2) SHAP (SHapley Additive exPlanations)

**Purpose:** explains *exactly why* a value was predicted/flagged as anomalous, by attributing the model's decision to individual features.

**Shapley value formula:**

```
φᵢ = Σ_{S⊆F\{i}} [ |S|! (|F|−|S|−1)! / |F|! ] · [f(S∪{i}) − f(S)]
```

Where:
- `F` = full set of features
- `S` = subsets of features not including feature `i`
- `f(S)` = model output using only features in `S`
- `f(S∪{i})` = model output using `S` plus feature `i`
- `φᵢ` = Shapley value / SHAP score for feature `i`

This yields a weight-based, linear model giving a ratio contribution `(-2 → +2)` for each feature — telling us how much each feature (e.g. odour, taste, colour) contributed to the anomaly score for a given instance.

### 3) Time Series Decomposition + Rate of Change

Classical decomposition:

```
Y = Y_trend + Y_seasonal + Y_residual
```

- **Trend:** helps rule out that there are two available extremes `X₁, X₂` of temp `(T₁, T₂)` at Jan & Jun both reading, say, 8°C. Given the theoretical seasonal averages (`T_Jan ≈ 8°C`, `T_Jun ≈ 34°C`), the residual is computed for each: `T_residual(Jan) ≈ 0` vs `T_residual(Jun) ≈ 26°C` — a high residual = high error compared to seasonal expectation. This incorporates seasonal/time-aware context into the anomaly check, instead of flagging raw values in isolation.
- **Rate of change:**
  - **Temperature:** a change of `5–8°C` in `10 min` is a rare condition; normal variation is `< 1°C` in that window.
  - **Pressure:** a drop of `≥ 3 hPa/hr` is a severe weather alert (cyclone-like) — **not a fault**, but still worth flagging as an alert (not a sensor error).
- **Trend detection method:** the **Mann-Kendall trend test** is used to check for gradual upward/downward drift — it classifies each pair `(i, j)` where the later value is larger than the previous one; if there's a gradual increase (day-over-day), later values will skew consistently higher than the theoretical/expected change.

---

## Layer 3 — Frozen Sensor Detection

If a sensor gets physically stuck/frozen, its readings stay (near) constant over time, which is itself anomalous for a live physical quantity.

```
d²x/dt² ≈ 0   or   d²y/dt² ≈ 0   ...
```

- All readings being practically constant/unchanged (second derivative ≈ 0) across the board → flagged as a **stuck/frozen sensor alert**.

---

## Layer 4 — Forecasting (Chronos-2)

Uses **Chronos-2** (pretrained time-series forecasting model) to predict the **next reading** from the recent feature history.

**Core idea:**

```
error = | predicted_reading − actual_reading |
```

- Chronos-2 forecasts what the next sensor reading *should* be, given the trend/pattern in recent readings.
- The **absolute error** between the predicted value and the actual incoming reading is computed.
- If this error is small → reading is consistent with the model's expectation → normal.
- If this error is large → the actual reading deviates significantly from what was forecasted → flagged as a possible **anomaly**.

**Open question — threshold:** the exact error threshold isn't finalized yet, since **volatility differs by variable** (pressure, temperature, and humidity all fluctuate at different natural rates/scales) — so the threshold will likely need to be set/tuned **per-variable** rather than as one fixed global cutoff.

---

## Layer 5 — Spatial Consistency

Incorporates overall regional weather change context instead of judging a single station in isolation.

**Steps:**
1. Find neighbouring stations in a given radius (using the **Haversine distance** formula).
2. Calculate a **robust Z-score** of a station's reading relative to its neighbours:

```
Z_robust = (x − median(x_neighbours)) / (1.4826 × MAD(x_neighbours))
```

Where:
- `MAD` = Median Absolute Deviation = `median(|xᵢ − median(x)|)`
- `1.4826` = scaling constant so MAD approximates the standard deviation for a normal distribution

**Why robust stats:** using median/MAD (instead of mean/std) means the metric is not skewed by outliers, so one faulty station doesn't distort the comparison baseline for its neighbours.

**Interpretation:** Low spatial Z-score → the station **agrees** with its neighbours (regionally consistent).

---

## Layer 6 — Fusion / Final Decision

Combines outputs from the earlier layers (**Model flags**, 4 layers total) with the **Layer 5 spatial agreement** (5th, last) into a final verdict:

| Model Flags | Neighbours Agree (Low Spatial Z) | Verdict |
|:---:|:---:|---|
| Y | N | **High-confidence sensor fault** |
| Y | Y | **Regional weather event** — not a fault, but an alert (regional weather change) |
| N | N | Generally healthy — low-confidence corner case (age-related, decalibrated fault, etc.) |
| N | Y | Neutral / no action |

Anything requiring a **health-bag check** on the sensor (age/decalibration related, low confidence) is routed for maintenance review rather than an immediate fault alert.

---

## Fault Classification (Probable Causes)

| Fault Type | Detected By Layer(s) | Probable Root Cause |
|---|---|---|
| **Spike** | Physics + ML | Voltage surge, EMI, lightning |
| **Freeze** | 2nd derivative (Frozen Layer) | Sensor jam, ice/dust blocking |
| **Gradual Drift** | ML layers alone (Physics won't catch it — each individual step is within physical bounds, but the *overall* trend bends abnormally over time; large-enough drift is eventually caught by the physics layer too) | Ageing / rusting / decalibration |
| **Dropout / Gap** | Missing values (NaN) | Power-cut / supply failure |
| **Cross-sensor Decoupling** | Physics layers + ML layers | A specific sensor develops a fault while other co-located sensors stay okay |
| **Noise Burst** | ML layers (a lot of outliers / erratic values in a short window) | Loose connection, electrical interference |
| **Impossible Combo** | Physics layers | e.g. pressure–altitude combo physically impossible, `RH ∉ (0,100)`, or `T < T_dew` |

**Notes from the plan:**
- **Gradual Drift** is the trickiest case — the physics layer will pass each individual reading since it's still within a plausible range, so the *overall* trend has to be watched instead (handled by the physics layer only as an eventual overstep, and otherwise caught by the ML layer). The ML-side detection for drift also needs different logic than a plain Isolation Forest run — Isolation Forest treats each point independently and isn't naturally suited to catching a slow, consistent trend, so drift detection leans on the trend-decomposition + Mann-Kendall test instead.
- **Cross-sensor Decoupling** is confirmed by checking that *only one* sensor at a station is producing bad readings while its co-located sensors (and its spatial neighbours) still look healthy — this is what separates it from a **Regional Weather Event** (Layer 6), where multiple/neighbouring sensors would agree.

---

## Sensor Degradation & Maintenance

Sensors degrade over time due to ageing, corrosion, and wear/tear. Because this degradation is **gradual**, the anomaly detectors above won't reliably catch it (each individual reading looks "fine").

→ **Solution:** maintain a running **sensor health score**, tracked independently of live anomaly detection, to flag sensors due for maintenance before they start producing bad data.

---

## Summary — All Layers

1. **Physics Sanity Checks** — Relations, Dew ↔ Air Temp, RH ∈ (0,100), physical bound checks, NWP-global extreme value bounds, rate-of-change bounds.
2. **ML Layer** — Isolation Forest + SHAP (explainability), Time Series Decomposition + Rate of Change (Mann-Kendall trend test).
3. **Frozen Sensor Layer** — 2nd derivative ≈ 0 detection.
4. **Forecasting Layer** — Chronos-2 predicts the next reading; absolute error vs. actual reading flags anomalies (threshold still to be tuned per-variable due to differing volatility).
5. **Spatial Consistency Layer** — Haversine-based neighbour matching + robust Z-score (median/MAD).
6. **Fusion Layer** — combines Model Flags + Spatial Agreement into a final confidence verdict (sensor fault vs. regional weather event vs. healthy).

Supporting: **Data pipeline** (Open-Meteo + anomaly injection → time-series DB → replay), **Fault classification table**, and **Sensor health/maintenance tracking**.