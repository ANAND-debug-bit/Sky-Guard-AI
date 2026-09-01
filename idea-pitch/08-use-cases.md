# 08 — Use Cases (the "document explaining various use cases" deliverable)

> 10 worked scenarios. Each: situation → which layers fire → verdict → action. Lift these directly into PPT slides.

---

## UC-1 — The problem-statement example: 55 °C with high humidity, neighbours normal
**Situation:** Delhi AWS reports T=55 °C, RH=92%, pressure swinging; neighbouring stations (Lucknow, Jaipur) report ~35 °C / 60% / normal pressure.
**Layers:** L1 range (55<60 passes) → L1 dew-point: T_dew from 55°C/92% ≈ 53°C, `T_dew ≤ T_air+0.5` passes barely → L2 IsoForest: combo is a multivariate outlier → flag, SHAP blames temperature → L4 Chronos-2 corridor breach on T → L5: robust Z of T vs neighbours ≈ huge (≫2) → disagree.
**Verdict:** SENSOR_FAULT, HIGH, `fault_type=spike/ml_anomaly`, blamed=temp. **Action:** inspect temp sensor + wiring (EMI/lightning). Imputed T ≈ 35 °C (neighbour median).

## UC-2 — Sudden freeze mid-winter (real weather vs fault)
**Situation:** A cold wave drops temps 12 °C across 6 stations in 3 hrs.
**Layers:** L1 rate flags `\|ΔT\|>8°C/hr` at each → L2 IsoForest flags → L5: *neighbours agree* (all dropped) → Z low.
**Verdict:** REGIONAL_EVENT, MEDIUM. **Action:** issue cold-wave alert, *not* a maintenance dispatch. This is the canonical "don't cry wolf" case.

## UC-3 — Frozen humidity sensor in monsoon
**Situation:** RH reads 88.0, 88.0, 88.0, … for 18 hrs while T and P vary normally.
**Layers:** L1 passes (88% plausible) → L2 IsoForest may or may not flag (88 is normal-ish) → **L3: std(RH)<0.01 over 18 readings → FROZEN** → L5: neighbours' RH varies normally → disagree.
**Verdict:** SENSOR_FAULT, HIGH, `fault_type=frozen_sensor`, blamed=humidity. **Action:** physical inspection — likely dust/jam on RH element.

## UC-4 — Gradual pressure-sensor drift over 60 days
**Situation:** Barometer drifts +0.3 hPa/day; each daily reading within ±5 hPa of expected.
**Layers:** L1 passes every reading → L2 trend: Mann-Kendall p<0.05, Theil-Sen slope +0.3 hPa/day → L4: forecast residual grows over weeks → L5: station increasingly disagrees with neighbours.
**Verdict:** CHECK_HEALTH → SENSOR_FAULT (late), `fault_type=gradual_drift`. **Action:** schedule recalibration; health score drops to "Degraded" weeks before live alert would fire.

## UC-5 — Station power cut (total dropout)
**Situation:** All 3 sensors report NaN for a 4-hour window.
**Layers:** L2 gap detection: ALL_SENSORS NaN → "station power cut / logger failure."
**Verdict:** SENSOR_FAULT, `fault_type=gap`. **Action:** dispatch power/logger check; impute window from neighbours + Chronos-2 backcast.

## UC-6 — Sea-level pressure reported at Shimla (2205 m)
**Situation:** Shimla AWS reports P=1013 hPa (correct for sea-level, wrong for its altitude).
**Layers:** L1 barometric: `P_expected` at 2205 m ≈ 780 hPa; `|1013−780|=233 hPa ≫ 30` → flag `pressure_altitude_mismatch`.
**Verdict:** SENSOR_FAULT, HIGH, `fault_type=barometric_inconsistency`, blamed=pressure. **Action:** recalibrate barometer / check station config.

## UC-7 — Cross-sensor decoupling (temp faulty, humidity + pressure fine)
**Situation:** T spikes to 48 °C; RH and P at the same station stay normal; neighbours normal.
**Layers:** L1 rate flags T → L2 IsoForest flags (T outlier, RH/P normal) → L5 neighbours disagree on T.
**Verdict:** SENSOR_FAULT, `fault_type=cross_sensor_decoupling`, blamed=temp. **Action:** replace/inspect temp sensor only — *don't* touch the working RH/P sensors. The decoupling signal is what tells maintenance which unit to swap.

## UC-8 — Cyclone pressure drop (real severe weather)
**Situation:** Coastal stations' pressure drops 4 hPa/hr over 3 hrs as a cyclone approaches.
**Layers:** L1 rate: `\|ΔP\|>3 hPa/hr` → flag-as-alert (not fault) → L5: *all coastal neighbours show the same drop* → agree.
**Verdict:** REGIONAL_EVENT, MEDIUM, recommended_action = "SEVERE: rapid pressure drop across region — possible cyclone/storm." **Action:** severe-weather alert to disaster management.

## UC-9 — Isolated station (Guwahati, no neighbours in 500 km)
**Situation:** GAU001 reports anomalous T; no spatial check possible.
**Layers:** L1–L4 evaluate normally → L5 returns `no_neighbours` (assume agree) → fusion can't produce SENSOR_FAULT from spatial alone; relies on L1–L4 strength.
**Verdict:** SENSOR_FAULT only if ≥2 of L1–L4 agree (confidence from multi-layer agreement, not spatial). **Action:** standard fault alert; explicitly note "spatial layer unavailable" in the verdict so the operator knows the basis. *We state this limit honestly in the PPT.*

## UC-10 — Noise burst from loose connection
**Situation:** 12 readings in 20 minutes are erratic (±6 °C scatter) but none individually impossible.
**Layers:** L1 each reading passes range; some trip rate → L2 IsoForest flags several in the window → noise-burst pattern (>k outliers in N min) → L5 disagree.
**Verdict:** SENSOR_FAULT, `fault_type=noise_burst`, blamed=temp. **Action:** inspect electrical connections + shielding at the sensor head.

---

## Cross-cutting outputs (what the operator always gets)

Every verdict includes:
- **Severity** (HIGH / MEDIUM / LOW) + **confidence score**.
- **Root-cause class** (`fault_type`) + **blamed sensor** (from SHAP).
- **Natural-language reason** + **recommended action**.
- **Per-layer breakdown** (frontend expandable).
- **Imputed value + source** (optional).
- **Sensor-health-score update** (rolling).

---

## Mapping to the grand challenge

> *"Can AI build a self-aware and self-healing weather observation network capable of delivering trustworthy atmospheric data under all environmental conditions?"*

**Our answer — SkyGuard AI:**
- **Self-aware:** composite sensor-health score + predictive time-to-failure from rolling O-B bias, forecast residual RMS, anomaly rate, dropout rate, calibration age.
- **Self-healing:** degraded sensor → auto-upweight neighbour/Chronos-imputed values in downstream feeds until maintenance completes → trustworthy data flows uninterrupted.
- **Under all conditions:** layered fusion distinguishes fault from *any* genuine extreme (heatwave, cold wave, cyclone, monsoon) via spatial consensus — so real weather isn't suppressed and real faults aren't mistaken for weather.
