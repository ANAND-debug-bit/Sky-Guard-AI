# Weather Anomaly Detection

A multi-layer pipeline that flags anomalies in weather station sensor data by combining **physics sanity checks**, **ML-based anomaly detection**, **sensor-fault pattern detection**, **forecasting**, and **spatial cross-validation** — before fusing everything into a final confidence verdict.

---

## Project Structure

```
project_root/
├── backend/
│   ├── node_modules/
│   ├── src/
│   ├── package-lock.json
│   ├── package.json
│   └── server.js
├── data/raw/
│   ├── aws_clean_baseline.parquet
│   └── aws_injected_evaluation.parquet
├── Frontend/                     # Dashboard visualization for catching live anomalies and sensor health on injected data
│   ├── dashboard.html
│   └── index.html
├── idea-pitch/
├── microservices/
│   ├── app/
│   │   ├── __pycache__/
│   │   │   └── backend.cpython-313.pyc
│   │   ├── core/
│   │   │   ├── __pycache__/
│   │   │   ├── config.py         # Dataset selection (specifies which dataset to use, e.g., the injected one)
│   │   │   ├── main.py           # Defines all analytical layers as callable functions
│   │   │   ├── sandbox.ipynb     # Testing accuracy, verifying dataset loading, and general checks
│   │   │   └── testing.ipynb     # Checks if variables for each layer have been successfully imported
│   │   ├── data/                 # Contains the clean baseline and injected evaluation datasets
│   │   │   ├── aws_clean_baseline.parquet
│   │   │   └── aws_evaluation_dataset.parquet
│   │   │
│   │   └── layers_v2/            # Core logic implementation for all analytical layers
│   │       ├── __pycache__/
│   │       ├── aging.py          # Detects gradual sensor degradation, drift, or calibration loss over time
│   │       ├── forecasting.py    # Using Chronos-2 to forecast values and flag deviations exceeding thresholds
│   │       ├── frozen.py         # Identifies stuck, or continuously repeating sensor readings
│   │       ├── fusion.py         # Combines all layers' decision to get a final verdict
│   │       ├── gap.py            # Identifies missing data points, communication drops, or incomplete payloads
│   │       ├── ml.py             # ML models (Isolation Forest + SHAP) for complex anomaly pattern recognition
│   │       ├── physics.py        # Validates readings against known physical laws and environmental constraints
│   │       └── spatial.py        # Compares the verdict with neighboring geographic stations for consistency and weather alerts
│   ├── seeds/
│   │   ├── data/raw/
│   │   │   └── aws_clean_baseline.parquet
│   │   ├── src/                  # Scripts for collecting data and defining columns from Open-Meteo
│   │   │   ├── __pycache__/
│   │   │   ├── fetch_openmeteo.py
│   │   │   ├── schema.py
│   │   │   └── stations.py
│   │   └── aws_evaluation_dataset.parquet
│   │
│   ├── sensor_simulation/        # V2 anomaly injection (inject.py) and FastAPI sensor streaming replay (main.py)
│   ├── backend.py
│   └── requirements.txt
├── frontend/
│   └── index.html
│   └── dashboard.html   
├── sample2/
├── src/__pycache__/
│   └── stations.cpython-313.pyc
├── venv/
├── .gitignore
├── AGENTS.md
├── aws_evaluation_dataset.parquet
├── README.md
├── requirements.txt
└── run.md
```

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

$$P_h = P_0 \, e^{-\frac{Mgh}{RT}}$$

A more practical, station-usable version — reducing station pressure to Mean Sea Level (MSL) pressure:

$$P_{MSL} = P_{station}\left(1 - \frac{0.0065\,h}{T + 0.0065\,h + 273.15}\right)^{-5.257}$$

If the reported pressure is inconsistent with what's expected from $P_{MSL}$, it's flagged as the **final plausible range check** for station pressure.

### 2) Temperature ↔ Humidity (Dew Point)

Uses the **Magnus formula**:

$$\gamma(T, RH) = \ln\!\left(\frac{RH}{100}\right) + \frac{aT}{b + T}$$

$$T_{dew} = \frac{b\,\gamma(T, RH)}{a - \gamma(T, RH)}$$

Where $a = 17.625$, $b = 243.04\ °C$ (Alduchov–Eskridge constants), valid for $T \in [-40°C,\ 50°C]$.

**Hard physical constraint:**

$$T_{dew} \le T_{air} \qquad \text{(always true)}$$

- Since $RH = \dfrac{\text{actual water vapour}}{\text{max water vapour air can hold}} \times 100\%$, if $T_{dew} > T_{air}$ that implies $RH > 100\%$, which is physically **impossible** → flagged as a **humidity sensor fault**.
- **Depression check:** $(T_{air} - T_{dew})$ being extremely low (with reported low humidity) *or* extremely high (with reported high humidity) are **both suspicious signals**.

---

## Layer 2 — ML Anomaly Detection

### 1) Isolation Forest + SHAP

**Why Isolation Forest:** it's fast, unsupervised, needs no pre-training on "normal" data, and isolates anomalies as it requires no labeled anomaly data upfront.

**Idea:** given $n$ instances of a feature, recursively take a random split of a random feature range, dividing instances at each split — repeating until every instance is isolated (i.e., all points reduced to a leaf of 1). Since splits are random, anomalies (rare/sparse values) tend to get isolated in far fewer splits than densely-packed normal values.

**Problem with plain path length:** it's possible for a split to randomly separate a normal instance quickly by chance. So instead of relying on a single tree, a **collection of trees** is built and the **average path length** is computed across all of them.

**Anomaly score:**

$$s(x, n) = 2^{-\frac{E(h(x))}{c(n)}}$$

Where $h(x)$ is the path length of instance $x$, $E(h(x))$ is the average path length across all isolation trees, and $c(n)$ is a normalization value based on sample size $n$.

### 2) SHAP (SHapley Additive exPlanations)

**Purpose:** explains *exactly why* a value was predicted/flagged as anomalous, by attributing the model's decision to individual features.

**Shapley value:**

$$\varphi_i = \sum_{S \,\subseteq\, F \setminus \{i\}} \frac{|S|!\,\big(|F| - |S| - 1\big)!}{|F|!} \Big[f(S \cup \{i\}) - f(S)\Big]$$

Where $F$ is the full set of features, $S$ ranges over subsets of features not including feature $i$, $f(S)$ is the model output using only features in $S$, $f(S \cup \{i\})$ is the model output using $S$ plus feature $i$, and $\varphi_i$ is the Shapley value / SHAP score for feature $i$.

This yields a weight-based, linear model giving a ratio contribution ($-2 \to +2$) for each feature — telling us how much each feature (e.g. odour, taste, colour) contributed to the anomaly score for a given instance.

### 3) Time Series Decomposition + Rate of Change

Classical decomposition:

$$Y = Y_{trend} + Y_{seasonal} + Y_{residual}$$

- **Trend:** helps rule out that there are two available extremes $X_1, X_2$ of temp $(T_1, T_2)$ at Jan & Jun both reading, say, $8°C$. Given the theoretical seasonal averages ($T_{Jan} \approx 8°C$, $T_{Jun} \approx 34°C$), the residual is computed for each: $T_{residual}(Jan) \approx 0$ vs. $T_{residual}(Jun) \approx 26°C$ — a high residual = high error compared to seasonal expectation. This incorporates seasonal/time-aware context into the anomaly check, instead of flagging raw values in isolation.
- **Rate of change:**
  - **Temperature:** a change of $5$–$8°C$ in $10$ min is a rare condition; normal variation is $< 1°C$ in that window.
  - **Pressure:** a drop of $\ge 3\ \text{hPa/hr}$ is a severe weather alert (cyclone-like) — **not a fault**, but still worth flagging as an alert (not a sensor error).
- **Trend detection method:** the **Mann-Kendall trend test** is used to check for gradual upward/downward drift — it classifies each pair $(i, j)$ where the later value is larger than the previous one; if there's a gradual increase (day-over-day), later values will skew consistently higher than the theoretical/expected change.

---

## Layer 3 — Frozen Sensor Detection

If a sensor gets physically stuck/frozen, its readings stay (near) constant over time, which is itself anomalous for a live physical quantity.

$$\frac{d^2x}{dt^2} \approx 0 \qquad \frac{d^2y}{dt^2} \approx 0 \qquad \dots$$

All readings being practically constant/unchanged (second derivative $\approx 0$) across the board → flagged as a **stuck/frozen sensor alert**.

---

## Layer 4 — Forecasting (Chronos-2)

Uses **Chronos-2** (pretrained time-series forecasting model) to predict the **next reading** from the recent feature history.

**Core idea:**

$$error = \big|\,predicted_{reading} - actual_{reading}\,\big|$$

- Chronos-2 forecasts what the next sensor reading *should* be, given the trend/pattern in recent readings.
- The **absolute error** between the predicted value and the actual incoming reading is computed.
- Small error → reading is consistent with the model's expectation → normal.
- Large error → the actual reading deviates significantly from what was forecasted → flagged as a possible **anomaly**.

**Open question — threshold:** the exact error threshold isn't finalized yet, since **volatility differs by variable** (pressure, temperature, and humidity all fluctuate at different natural rates/scales) — so the threshold will likely need to be set/tuned **per-variable** rather than as one fixed global cutoff.

---

## Layer 5 — Spatial Consistency

Incorporates overall regional weather change context instead of judging a single station in isolation.

**Steps:**
1. Find neighbouring stations in a given radius (using the **Haversine distance** formula).
2. Calculate a **robust Z-score** of a station's reading relative to its neighbours:

$$Z_{robust} = \frac{x - \text{median}(x_{neighbours})}{1.4826 \times \text{MAD}(x_{neighbours})}$$

$$\text{MAD} = \text{median}\big(|x_i - \text{median}(x)|\big)$$

The constant $1.4826$ scales MAD so it approximates the standard deviation for a normal distribution.

**Why robust stats:** using median/MAD (instead of mean/std) means the metric is not skewed by outliers, so one faulty station doesn't distort the comparison baseline for its neighbours.

**Interpretation:** low spatial Z-score → the station **agrees** with its neighbours (regionally consistent).

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
| **Impossible Combo** | Physics layers | e.g. pressure–altitude combo physically impossible, $RH \notin (0,100)$, or $T < T_{dew}$ |

**Notes from the plan:**
- **Gradual Drift** is the trickiest case — the physics layer will pass each individual reading since it's still within a plausible range, so the *overall* trend has to be watched instead (handled by the physics layer only as an eventual overstep, and otherwise caught by the ML layer). The ML-side detection for drift also needs different logic than a plain Isolation Forest run — Isolation Forest treats each point independently and isn't naturally suited to catching a slow, consistent trend, so drift detection leans on the trend-decomposition + Mann-Kendall test instead.
- **Cross-sensor Decoupling** is confirmed by checking that *only one* sensor at a station is producing bad readings while its co-located sensors (and its spatial neighbours) still look healthy — this is what separates it from a **Regional Weather Event** (Layer 6), where multiple/neighbouring sensors would agree.

---

## Sensor Degradation & Maintenance

Sensors degrade over time due to ageing, corrosion, and wear/tear. Because this degradation is **gradual**, the anomaly detectors above won't reliably catch it (each individual reading looks "fine").

→ **Solution:** maintain a running **sensor health score**, tracked independently of live anomaly detection, to flag sensors due for maintenance before they start producing bad data.

---

## Summary — All Layers

1. **Physics Sanity Checks** — pressure/altitude relation, dew point ↔ air temp, $RH \in (0,100)$, physical bound checks, NWP-global extreme value bounds, rate-of-change bounds.
2. **ML Layer** — Isolation Forest + SHAP (explainability), time series decomposition + rate of change (Mann-Kendall trend test).
3. **Frozen Sensor Layer** — second derivative $\approx 0$ detection.
4. **Forecasting Layer** — Chronos-2 predicts the next reading; absolute error vs. actual reading flags anomalies (threshold still to be tuned per-variable due to differing volatility).
5. **Spatial Consistency Layer** — Haversine-based neighbour matching + robust Z-score (median/MAD).
6. **Fusion Layer** — combines model flags + spatial agreement into a final confidence verdict (sensor fault vs. regional weather event vs. healthy).

**Supporting:** data pipeline (Open-Meteo + anomaly injection → time-series DB → replay), fault classification table, and sensor health/maintenance tracking.
