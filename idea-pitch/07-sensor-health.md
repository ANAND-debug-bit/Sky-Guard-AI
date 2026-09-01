# 07 — Sensor Health & Predictive Maintenance

> Covers two expected outputs: **"Sensor health status"** and **"Predict possible sensor degradation and maintenance requirements."** Also the backbone of the "self-healing network" grand challenge.

---

## The problem the live detectors *don't* solve

All 6 live layers evaluate **one reading at a time**. Gradual degradation (ageing, corrosion, slow decalibration) produces readings that are each *individually* within plausible range — so live detection catches it late, only once drift is large enough to breach a threshold. By then the sensor has been emitting subtly bad data for weeks.

**→ Solution:** a **running sensor-health score**, tracked *independently* of live anomaly detection, that flags sensors *before* they emit bad data.

---

## Composite Sensor Health Score (our formulation)

**No WMO-standard formula exists** (verified — WDQMS uses trueness/precision/gross-error-rate indicators; ECMWF uses O-B blacklist criteria; both are ad hoc). We define a composite score in **[0, 1]** per sensor per station:

```
Health = w₁·(1 − normalized_bias)
       + w₂·(1 − normalized_residual_rms)
       + w₃·(data_availability)
       + w₄·(1 − anomaly_rate)
       + w₅·(1 − age_degradation)
```

| Component | What it measures | Source |
|---|---|---|
| **normalized_bias** | Rolling O-B (observation − forecast/neighbor median) bias, normalized | ECMWF O-B monitoring; WDQMS trueness |
| **normalized_residual_rms** | RMS of L4 forecast residuals over rolling window | WDQMS precision |
| **data_availability** | % of expected readings actually received (dropout rate) | IMD monitors this hourly |
| **anomaly_rate** | % of readings flagged by L1–L4 over rolling window | Our pipeline |
| **age_degradation** | Time since last calibration ÷ recommended cycle | WMO-No. 8 calibration cycle |

**Weights (tune, starting defaults):** w₁=0.3, w₂=0.25, w₃=0.15, w₄=0.2, w₅=0.1.

**Health tiers:**
| Score | Status | UI colour | Action |
|---|---|---|---|
| ≥ 0.85 | Healthy | 🟢 Green | None |
| 0.6–0.85 | Watch | 🟡 Amber | Increase monitoring, log |
| 0.4–0.6 | Degraded | 🟠 Orange | Schedule recalibration within cycle |
| < 0.4 | Critical | 🔴 Red | Dispatch maintenance now |

---

## Degradation signals we track (per sensor, rolling 30-day window)

1. **O-B bias trend** — ECMWF-style: persistent observation-minus-background departure. Drift = growing bias. (Source: ECMWF Newsletter 162.)
2. **Forecast residual RMS** — L4 residuals increasing over time ⇒ sensor diverging from physical expectation.
3. **Anomaly rate** — fraction of readings flagged by L1–L4. Creep upward ⇒ degradation.
4. **Dropout rate** — data availability falling ⇒ power/logger/comms degradation. (IMD monitors hourly.)
5. **Buddy-check failure rate** — ECMWF WDQMS: gross-error rate > 15%/month triggers investigation.
6. **Calibration age** — WMO-No. 8: T/P sensors recalibrate 1–2 yr; RH annually. Approaching cycle ⇒ preemptive flag.

---

## Predictive maintenance (the "self-aware / self-healing" story)

- **Predict** time-to-failure: fit a simple trend to the health score → estimate weeks until it crosses 0.4. Flag sensors predicted to breach within the next calibration cycle.
- **Recommend** maintenance type from the dominant degradation signal:
  - Bias dominant → recalibrate.
  - Dropout dominant → power/logger/comms dispatch.
  - Anomaly-rate dominant → physical inspection.
  - Age dominant → routine cycle replacement.
- **Self-healing loop**: degraded sensor → upweight neighbour/imputed values in downstream feeds until fixed → reduces bad-data propagation. This is the "trustworthy data under all conditions" answer to the grand challenge.

---

## Why this wins the Practical Deployability (10%) + Innovation (25%) slides

- **Deployability:** mirrors real national-met-service practice (ECMWF blacklisting, WDQMS, IMD battery/GPS monitoring) — not invented.
- **Innovation:** combines signals the met services track *separately* into a single composite score with predictive time-to-failure + auto-imputed fallback → that's the self-aware/self-healing pitch.

---

## Sources

- WMO-No. 8 (2024) — calibration cycles, QC framework: https://library.wmo.int/viewer/68695/
- ECMWF observation monitoring / O-B: https://www.ecmwf.int/sites/default/files/elibrary/2018/80920-use-situ-surface-observations-ecmwf.pdf
- ECMWF Newsletter 162 (automatic checking): https://www.ecmwf.int/en/newsletter/162/meteorology/recent-developments-automatic-checking-earth-system-observations
- WDQMS quality indicators: https://confluence.ecmwf.int/spaces/WIGOSWT/pages/181123483/3.3+Data+quality
- IMD AWS monitoring (battery/GPS/availability): https://doi.org/10.54302/mausam.v66i1.370
- MADIS QC: https://madis.ncep.noaa.gov/madis_sfc_qc_notes.shtml
