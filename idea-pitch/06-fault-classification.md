# 06 — Fault Classification

> Maps each fault type → which layer catches it → threshold → root cause → action → WMO QC level. This is the "root-cause classification" expected output and the Detection Accuracy evidence.

---

## Fault taxonomy (7 types)

| Fault | Detected by | Threshold / signal | Root cause | Recommended action | WMO level |
|---|---|---|---|---|---|
| **Spike** | L1 (rate) + L2 (IsoForest) + L4 (corridor breach) | `\|ΔT\|>8°C/hr` OR IsoForest `-1` OR actual∉[p5,p95] | Voltage surge, EMI, lightning, ADC glitch | Inspect wiring, surge protection, grounding | L2 internal |
| **Frozen / stuck** | L3 (std/2nd-deriv) + L4 (flat-line vs forecast) | `std<0.01` over ≥10 readings OR `max\|d²x/dt²\|<0.01` | Sensor jam, ice, dust, mechanical block | Physical inspection, clean/de-ice | L2 internal |
| **Gradual drift** | L2 (Mann-Kendall + Theil-Sen) + L4 (growing residual) | MK p<0.05 + slope exceeds expected seasonal drift | Ageing, corrosion, decalibration | Schedule recalibration; track in health score | L2 / L5 |
| **Dropout / gap** | L2 gap detection | Any sensor NaN (partial) / all NaN (full) | Power cut, logger failure, comms loss | Dispatch power/logger check | L1/L2 |
| **Cross-sensor decoupling** | L1 (dew-point) + L2 (IsoForest combo) + L5 (neighbours OK) | `T_dew>T_air` OR multivariate IsoForest anomaly with co-located + neighbour sensors healthy | One sensor fails while others at same station stay OK | Replace flagged sensor | L2/L3 |
| **Noise burst** | L2 (many IsoForest outliers in short window) | >k outliers in N-minute window (tune k,N) | Loose connection, electrical interference | Inspect connections, shielding | L2 |
| **Impossible combo / barometric** | L1 (range, dew-point, altitude) | RH∉(0,100), T<T_dew, `\|P−P_expected\|>30hPa` | Sensor miscalibration / wrong config | Recalibrate affected sensor | L1 plausibility |

---

## The disambiguation: fault vs regional weather (the pitch's key insight)

Single-station detectors can't tell a heatwave from a broken sensor. **L5 spatial + L6 fusion** resolve it:

| Detectors flag? | Neighbours agree? | Verdict | Example |
|---|---|---|---|
| Yes | No | **SENSOR_FAULT** (High) | One station 55°C, neighbours 35°C → broken sensor |
| Yes | Yes | **REGIONAL_EVENT** (Med) | All stations 55°C → heatwave, alert not fault |
| No | No | **CHECK_HEALTH** (Low) | Subtle drift, schedule maintenance |
| No | Yes | **HEALTHY** | All clear |

**Example use case from the problem statement:** AWS reports 55°C with high humidity + abnormal pressure while neighbours normal → L1/L2 flag + L5 disagrees → **SENSOR_FAULT**, alert + corrective action. This is literally our fusion matrix in action.

---

## Why each fault needs *multiple* layers (defensive redundancy)

| Fault | Single-layer failure mode | Backup layer |
|---|---|---|
| Spike inside range (e.g. 35→45°C) | L1 range passes | L1 rate + L2 IsoForest + L4 corridor catch it |
| Frozen value inside normal range | L1/L2 IsoForest pass (constant ≈ "normal") | L3 catches; L4 catches if weather should be changing |
| Slow drift, each point in range | L1 passes every individual point | L2 trend (Mann-Kendall) + L4 growing residual |
| Multivariate combo (T=50 & RH=98) | Univariate checks pass | L1 dew-point + L2 multivariate IsoForest |
| Real heatwave | Looks like a spike to single-station detectors | L5 spatial agreement → REGIONAL_EVENT, not fault |

**Pitch line:** "No single detector is sufficient. The layered fusion is what gives both high recall *and* low false alarms."

---

## Optional: corrected / imputed value

For each flagged reading, suggest an imputed value from the *most trusted available source*, in priority order:

1. **Median of agreeing neighbours** (L5, robust) — best when neighbours agree.
2. **Chronos-2 p50 forecast** (L4) — best when neighbours unavailable (isolated station).
3. **Seasonal expected value** (L2 decomposition trend+seasonal) — fallback.

Report imputed value + source + confidence. Mark as "optional/advisory, not for automatic overwrite" — operational met data shouldn't be silently rewritten.

---

## Mapping to injected-anomaly benchmark (Detection Accuracy evidence)

| Injected `anomaly_type` | Expected verdict | Expected `fault_type` |
|---|---|---|
| `spike` | SENSOR_FAULT | spike / out_of_range |
| `frozen_sensor` | SENSOR_FAULT | frozen_sensor |
| `linear_dampened` | SENSOR_FAULT or CHECK_HEALTH | frozen_sensor (low std) |
| `gradual_drift` | CHECK_HEALTH → SENSOR_FAULT (late) | ml_anomaly / forecast_deviation |
| `dropout_power_cut` | SENSOR_FAULT | gap |
| `cross_sensor_decoupling` | SENSOR_FAULT | impossible_combo / ml_anomaly |
| `noise_burst` | SENSOR_FAULT | ml_anomaly / spike |
| `barometric_altitude_inconsistency` | SENSOR_FAULT | barometric_inconsistency |
| `normal` | HEALTHY | null |

Use this mapping to compute **precision / recall / F1** on the injected benchmark — the concrete Detection-Accuracy numbers for the PPT.
