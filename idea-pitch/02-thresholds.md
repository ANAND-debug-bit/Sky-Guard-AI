# 02 — Thresholds (concrete, justified, sourced)

> Every number we'll cite in the PPT, with **why** and **where it comes from**.
> Each threshold has a source link. **tune** = needs validation on real data.
> **Critical fix from deep research:** pressure rate-of-change now splits into a *fault* threshold (tight) vs a *severe-weather alert* threshold (loose). The old single 3 hPa/hr value would flag normal weather constantly — MADIS uses 15 hPa/hr as the *validity* limit.

---

## Where the threshold data comes from (provenance)

| Source | What it gave us | URL |
|---|---|---|
| **NOAA MADIS** surface QC notes | Temp/pressure/humidity rate-of-change validity limits + dew-point internal consistency | https://madis.ncep.noaa.gov/madis_sfc_qc_notes.shtml |
| **Oklahoma Mesonet** (Fiebrich & Crawford 2001) | Step-test + persistence-test thresholds for stuck sensors | https://doi.org/10.1175/1520-0477(2001)082 |
| **European Commission JRC / WeatherXM QoD** | Citizen-station jump limits + constancy (frozen) duration thresholds | https://docs.weatherxm.com/weather-and-science/quality-mechanisms/obc-sqc-documentation.mdx |
| **Met Norway TITAN** | Robust Z-score (median/MAD) buddy-check default = 3.1 | https://asr.copernicus.org/articles/17/153/2020/ |
| **Euskalmet** (Lapuenta et al. 2012) | Spatial kriging Z = 2σ; lapse-rate correction caveat | https://doi.org/10.5194/asr-8-129-2012 |
| **CrowdQC+** (Meier et al. 2017) | Modified z-score α=0.01/0.05 → ±2.5–3σ; Qn estimator | https://github.com/dafenner/CrowdQCplus |
| **ECMWF / WDQMS** | PGE > 0.75 blacklisting; O-B monitoring | https://www.ecmwf.int/sites/default/files/elibrary/2018/80920-use-situ-surface-observations-ecmwf.pdf |
| **Australian Bureau of Meteorology** | Hard physical range bounds (Tmax, RH, wind) | https://www.bom.gov.au/climate/headers/qc.shtml |
| **WMO-No. 8 (CIMO Guide, 2024 ed.)** | Calibration cycles, QC framework L0–L5 | https://library.wmo.int/viewer/68695/ |
| **Constant Value Test** (AMT 2023) | Probabilistic frozen-sensor detection | https://amt.copernicus.org/articles/16/3085/2023/ |
| **Lanzante (1996), cited in TITAN** | Outliers ≈ >5σ from mean | https://asr.copernicus.org/articles/17/153/2020/ |

> **Honest note for the PPT:** IMD-specific threshold values are **not publicly documented**. We use MADIS/Mesonet/European values as defensible defaults and state that final values would be tuned to IMD station climatology. This transparency is itself a credibility win with judges.

---

## L1 — Physics / Plausibility (WMO L1 + L2)

### Range bounds (validity, WMO L1)

| Parameter | Lower | Upper | Source / justification |
|---|---:|---:|---|
| Temperature | **−40 °C** | **+55 °C** | India-restricted subset of WMO record extremes (−89.2 °C Vostok, +56.7 °C Death Valley). BoM uses −60/+60 globally (https://www.bom.gov.au/climate/headers/qc.shtml). Tighter for India because Indian AWS never see poles. |
| Relative Humidity | **0 %** | **100 %** | Physical hard limit. Allow tiny tolerance (100.5%) for sensor noise. |
| Pressure (station) | **300 hPa** | **1084 hPa** | WMO record range (low 870 hPa Typhoon Tip; high 1083.8 hPa Siberia). For India: ~600–1060 hPa. **Tune** by station altitude. |

**Better than fixed global bounds:** station-specific climatological bounds = **monthly mean ± 5σ** (WMO general guideline, Lanzante 1996, cited in TITAN). So a 35 °C reading is normal in May, anomalous in January — use rolling monthly stats, not annual.

### Dew-point constraint (internal consistency, WMO L2)

Magnus formula (Alduchov–Eskridge, valid T ∈ [−40, 50] °C):
```
γ = ln(RH/100) + (17.625·T)/(243.04+T)
T_dew = (243.04·γ)/(17.625−γ)
```
**Hard constraint:** `T_dew ≤ T_air + 0.5 °C` (0.5 °C tolerance for sensor imprecision). Violation ⇒ `impossible_combo` (humidity sensor lying).
- **MADIS confirms:** "Dewpoint temperature must not exceed air temperature at the same station; if it does, both are flagged." (https://madis.ncep.noaa.gov/madis_RSAS_qc_notes.shtml)
- **Met Office HadISD** also runs a "Dew point depression" + "Supersaturation" check.

### Barometric altitude consistency (L1)

```
P_expected = 1013.25 · (1 − 0.0065·h/(T+273.15))^5.257
```
Flag if `|P_actual − P_expected| > 30 hPa`. 30 hPa tolerance ≫ typical weather variation (±5–15 hPa). Catches a sea-level pressure reading at 2200 m altitude (Shimla should read ~780 hPa, not 1013).

### Rate of change (temporal consistency, WMO L2) — ⚠️ CORRECTED

**The key fix:** separate *fault* detection from *severe-weather alerting*. A cyclone-class pressure drop is real weather, not a sensor fault — the fusion layer (L6) decides which using spatial agreement.

| Parameter | Fault threshold (→ SENSOR_FAULT) | Alert threshold (→ REGIONAL_EVENT if neighbours agree) | Source |
|---|---|---|---|
| Temperature | **\|ΔT\| > 19.4 °C/hr** (MADIS 35°F/hr) → fault | **\|ΔT\| > 8 °C/hr** → alert candidate | MADIS validity: https://madis.ncep.noaa.gov/madis_sfc_qc_notes.shtml ; 8°C is our tightened "watch" level. **Tune.** |
| Pressure | **\|ΔP\| > 15 hPa/hr** (MADIS sea-level) → fault | **\|ΔP\| > 3 hPa/hr** → severe-weather alert candidate (cyclone-class) | MADIS: 15 mb/hr validity, 10 mb altimeter 1-hr, 30.5 mb absolute. https://madis.ncep.noaa.gov/madis_sfc_qc_notes.shtml |
| Humidity | **\|ΔRH\| > 50 %/hr** (MADIS) → fault | **\|ΔRH\| > 20 %/hr** → alert candidate | MADIS: ±50%/hr validity. https://madis.ncep.noaa.gov/madis_sfc_qc_notes.shtml |

**Step-test (5-min) alternative** (Oklahoma Mesonet, Fiebrich & Crawford 2001):
- Temp: 10 °C per 5 min → fault
- Pressure: 10 mb per 5 min → fault
- Humidity: 20% per 5 min → fault
Source: https://doi.org/10.1175/1520-0477(2001)082

**Why this matters for the pitch:** the README's single "3 hPa/hr → flag" conflated *fault* with *weather*. The corrected two-tier scheme is what real met services do and is exactly the "distinguish genuine meteorological events from sensor anomalies" requirement from the problem statement. Call this out on the slide — it shows we did the homework.

---

## L2 — ML

### Isolation Forest
- `contamination = 0.01–0.02` (expected anomaly fraction; ~1–2%).
- `n_estimators = 100`, `max_samples = 256` (standard).
- Anomaly score `s(x,n) = 2^(−E(h(x))/c(n))`; `predict = -1` ⇒ anomaly.
- **Tune** contamination against the injected-anomaly benchmark (target F1, precision-at-fixed-recall).

### SHAP (on IsoForest)
- `TreeExplainer`, **`check_additivity=False`** (required for IsoForest — see `05-explainability-xai.md`).
- Blamed sensor = feature with **largest absolute SHAP value**.
- **Sign gotcha:** SHAP explains *path length*, not the `predict()` label. Higher SHAP ⇒ shorter path ⇒ *more anomalous*.

### Trend / drift (Mann-Kendall)
- Window: **≥ 30 points** for the test to be meaningful.
- Two-sided p-value **< 0.05** ⇒ significant monotonic trend.
- Pair with **Theil–Sen slope** to quantify drift rate (e.g. °C/day). Flag if slope magnitude exceeds expected seasonal drift.

### Seasonal decomposition
- `Y = trend + seasonal + residual`. Flag if `|residual| > k·σ_residual` with **k = 3** (3σ) on the residual distribution. **Tune k.**

### Frozen-sensor on L2 side (complements L3)
- **Oklahoma Mesonet persistence test:** daily std dev ≤ 0.1 °C → suspect; daily range ≤ 0.1 °C → warning. (https://doi.org/10.1175/1520-0477(2001)082)
- **WMO recommendation (via WeatherXM):** T/RH/wind/pressure should not remain constant for > 1 hour (60 min).
- **WeatherXM constancy durations:** T = 240 min, Pressure = 120 min, Wind = 360 min; max constancy 1440 min (24 hr).

---

## L3 — Frozen Sensor

| Metric | Threshold | Source / Why |
|---|---:|---|
| `std(window) < 0.01` | flag frozen | Below any natural variability (stable weather still varies ±0.1 °C/hr ⇒ std ≈ 0.3–0.5). Conservative. |
| `max(|2nd derivative|) < 0.01` | (alt/confirm) | Matches README's `d²x/dt² ≈ 0`. PPT polish; functionally ≡ std check. |
| Min window | **10 non-null readings** | Avoid false freeze on short/NaN-heavy windows. |
| Constant-value duration | **> 60 min** (WMO) / **> 120 min** (pressure, WeatherXM) / **> 240 min** (T, WeatherXM) | WMO + WeatherXM QoD. |
| FLASC (NREL) method | `std < 0.001` over 3 consecutive readings | https://natlabrockies.github.io/flasc/ — stricter, for fast-cadence. |
| All 3 frozen | ⇒ logger/station failure, not single sensor | Different fault class, different action. |
| **Probabilistic CVT (advanced)** | Data-driven P(same value) given μ, σ, φ₁ (lag-1 autocorrelation) | https://amt.copernicus.org/articles/16/3085/2023/ — adapts to local variability; mention for the Innovation slide as the production upgrade. |

---

## L4 — Forecasting (Chronos-2)

- Model: **`amazon/chronos-2`** (120M) primary; **`autogluon/chronos-2-small`** (28M) fallback.
- Context: last **N = 20** readings (tunable up to 8192).
- Output: p5 / p50 / p95 corridor.
- Flag if **`actual ∉ [p5, p95]`** OR **severity = |actual−p50| / corridor_width > 0.8**.
- **Per-variable breach thresholds** (volatility differs):
  - Temperature: severity > 0.8
  - Pressure: tighter acceptable corridor (pressure is smoother)
  - Humidity: looser (humidity is noisier)
- NaN handling: forward-fill + back-fill the window before predict.
- **Latency budget:** ~50–200 ms/reading on GPU; run **only on suspect readings** to keep real-time + energy budgets.

---

## L5 — Spatial Consistency

| Parameter | Value | Source / Justification |
|---|---:|---|
| Neighbour radius | **500 km** | India station density; tunable per region. |
| Robust Z threshold | **Z ≥ 3.1 ⇒ neighbours disagree** (TITAN default) | Met Norway TITAN uses 3.1 robust (median/MAD). We previously used 2.0; tighten to 3.1 to match the standard. **Tune 2.0–3.5.** |
| Min neighbours | **≥ 5** (TITAN) | TITAN requires 5–10 buddies for a reliable check. Our 15-station demo set may only have 1–4 → we acknowledge this as a demo limitation and state the production requirement. |
| MAD scaling | `1.4826` | Constant making MAD ≈ σ for normal data. |
| Pressure comparison | **MSL-normalize first** | Altitude differences alone look anomalous otherwise. |
| Priority sensor for spatial | **Temperature > Humidity > Pressure** | T most spatially coherent; P needs MSL normalization. |
| Lapse-rate correction (T) | **−0.0065 °C/m** | Standard; **fails during inversions** (Euskalmet caveat) — state as a known limit. |
| Event-based buddy (precip) | **90% of neighbours must agree** | TITAN event buddy. |

**Edge case (state honestly):** isolated stations (CCU/Kolkata, GAU/Guwahati at 500 km) → spatial layer returns "can't check, assume OK" → only L1–L4 feed fusion. Real met services hit this too (TITAN requires min 5 buddies).

---

## L6 — Fusion

No new thresholds — it's a decision table. Two derived signals:
- `model_flagged = any(L1..L4 flagged)`
- `neighbours_agree = (spatial.Z < 3.1)` (or True if spatial couldn't run)

Confidence tier (derived):
- **HIGH**: ≥ 2 layers agree AND neighbours disagree.
- **MEDIUM**: 1 layer flags AND neighbours disagree; OR ≥2 layers agree AND neighbours agree (regional).
- **LOW**: no model flag but spatial disagrees (CHECK_HEALTH case).

---

## Threshold-tuning strategy (one PPT slide)

1. **Start** with the published values above (MADIS/Mesonet/TITAN/ECMWF — defensible, cited).
2. **Inject** known anomalies (spike, freeze, drift, dropout, decoupling, barometric) into clean ERA5 data → labelled benchmark.
3. **Sweep** each threshold; pick the value maximizing **F1** (or **F2** if recall-priority, or precision-at-fixed-recall) on the benchmark. Use **PR-AUC**, not accuracy — anomalies are <1–5% of data so accuracy is misleading (Kataria 2026).
4. **Per-station climatological bounds**: replace global range with monthly ±5σ once enough history exists.
5. **Seasonal drift of thresholds**: a 35 °C reading is normal in May, anomalous in January — rolling monthly stats, not annual.
6. **A/B test in production**: run deterministic QC + ML QC in parallel, compare false-alarm rates (Kataria 2026 MLOps pipeline pattern).
7. **PSI-driven retraining**: Population Stability Index > 0.2 triggers model retrain (Kataria 2026).

This tuning story is the **Detection Accuracy (20%)** evidence path.
