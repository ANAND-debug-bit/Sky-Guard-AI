# 01 — Architecture & Layers

> Source of truth for the pitch architecture. The AI-generated `plan-skyguard-ai/` folder is a rough impl sketch, not authoritative.

---

## Design Principles

1. **Cheap-to-expensive cascade.** Layers run in cost order; an earlier hard veto short-circuits the rest. A physically impossible reading never wastes a Chronos-2 forward pass.
2. **Standards-aligned.** Our 6 layers intentionally map to the WMO/ECMWF **L0–L5** QC framework (WMO-No. 8 CIMO Guide; MADIS; WDQMS). We're not inventing QC — we're automating + ML-augmenting it.
3. **Separate fault from weather.** Single-station detectors (L1–L4) flag *suspicion*; the spatial layer (L5) provides *context*; fusion (L6) disambiguates "sensor fault" vs "regional event."
4. **Every verdict is explained.** SHAP attribution + natural-language reason + confidence tier. No black-box alerts.
5. **Edge + cloud split.** Cheap deterministic + small-ML layers on ESP32-S3; heavy ML (Chronos-2, SHAP, spatial) on gateway/cloud.

---

## Data Flow (end to end)

```
AWS sensor (T, P, RH)
      │
      ▼
[ESP32-S3 edge tier] ── L1 physics + L3 frozen + small IsoForest + gap check
      │  (pre-filter; only *suspect* readings + window go upstream)
      ▼
[Gateway / cloud tier] ── L2 full ML (IsoForest+SHAP) + L4 Chronos-2 + L5 spatial
      │
      ▼
[L6 Fusion] ── verdict + confidence + root cause + (optional) imputed value
      │
      ├──▶ Alert (WebSocket push)
      ├──▶ Sensor health score update
      └──▶ Store (TimescaleDB)
```

**Why the split:** ESP32 can't run a 120M-param transformer or hold neighbour states. But it *can* catch ~70–80% of obvious faults locally (range, rate, frozen, dropout, small IsoForest), so the gateway only sees the interesting 20–30%. That's both the **real-time** and **energy-efficiency** judging criteria handled in one design choice.

---

## Layer Roles (deep)

### L1 — Physics Sanity (cheapest, deterministic)
Range bounds (climatological + station-specific ±5σ), dew-point constraint (`T_dew ≤ T_air`, Magnus/Alduchov–Eskridge), barometric altitude consistency, rate-of-change bounds. No training, instant, zero false negatives on physically impossible values. See `02-thresholds.md`.

### L2 — ML Anomaly (multivariate, explained)
**Isolation Forest** (unsupervised, no labelled-anomaly requirement) on `[temp, pressure, humidity, hour, (day-of-year sin/cos)]` → anomaly score `s(x,n)=2^(−E(h(x))/c(n))`. On flag → **SHAP TreeExplainer** attributes which feature drove the anomaly (see `05-explainability-xai.md` for the sign-convention gotcha). Plus **gap/dropout detection** (NaN patterns) and **trend/drift** via seasonal decomposition + Mann-Kendall. IsoForest alone does *not* catch slow drift — that's why trend/drift is a sibling sub-module.

### L3 — Frozen Sensor (deterministic)
Std-dev of window < threshold (≈0) **and/or** 2nd-derivative ≈ 0. Catches jammed/iced/dust-blocked sensors that produce values *within* normal range — invisible to L1/L2 individually. Reports *which* sensor is stuck; if all 3 frozen → data-logger/station failure, not a single sensor.

### L4 — Forecasting (Chronos-2, zero-shot)
**`amazon/chronos-2`** (120M, real model — HuggingFace; paper arXiv:2510.15821, Oct 2025). Multivariate natively (feeds T/P/RH jointly), 8192-step context. Forecast next reading → p5/p50/p95 corridor → breach severity = `|actual−p50| / corridor_width`; flag if severity > 0.8 or actual outside [p5,p95]. **Per-variable thresholds** because volatility differs. Run *only on suspect readings* (after L1–L3) to save latency/energy. Fallback: `autogluon/chronos-2-small` (28M) or univariate `amazon/chronos-bolt-*` if RAM constrained.

### L5 — Spatial Consistency (context, not detector)
Haversine → neighbours within radius (precomputed map). **Robust Z = `|x − median(neighbours)| / (1.4826 × MAD)`** (median/MAD = outlier-resistant, unlike mean/std). Pressure compared **only after MSL normalization** (else altitude alone looks anomalous). This layer never says "anomaly" on its own — it tells fusion whether neighbours *agree*.

### L6 — Fusion (the brain)

2×2 decision matrix (core of the system):

| | Neighbours AGREE (Z < 2) | Neighbours DISAGREE (Z ≥ 2) |
|---|---|---|
| **Model flagged** (any of L1–L4) | **REGIONAL_EVENT** (real weather, alert not fault) — Medium conf | **SENSOR_FAULT** — High conf |
| **No model flag** | **HEALTHY** — no action | **CHECK_HEALTH** (subtle drift/decalibration) — Low conf |

Plus fault-type + affected-sensor classification (priority: Frozen > Physics > Forecast > ML) and confidence tier (HIGH/MED/LOW) derived from *how many* layers agreed. See `06-fault-classification.md`.

---

## Layer Priority — two distinct orderings (don't conflate them in the PPT)

### A) Execution priority (who runs first / cheap-to-expensive)
**L1 → L3 → L2(gap) → L2(IsoForest) → L4 → L5 → L6.**
- L1 is O(1) arithmetic; if it hard-vetoes (impossible value), skip everything.
- L3 is O(window) std; cheap.
- L2 gap-check is O(1); IsoForest is O(trees × depth).
- L4 Chronos-2 is the heaviest (~50–200 ms/reading on GPU) → run only on readings that survived L1–L3 unsuspicious or that need a second opinion.
- L5 needs neighbour data from Redis → one MGET round trip.
- L6 is a decision table.

### B) Explanation / root-cause priority (who gets *blamed* in the verdict, when multiple flag)
**Frozen > Physics > Forecast > ML.**
1. **Frozen** — most specific diagnosis ("sensor is jammed" is actionable).
2. **Physics** — deterministic; if physics says impossible, it *is* impossible.
3. **Forecast** — time-series-specific; "deviates from expected pattern."
4. **ML** — catches what others miss but is least specific about *what* is wrong.

State this explicitly in the PPT — judges conflate "which runs first" with "which is most important." They're different axes.

---

## Why a layered system beats any single model

| Single-model failure mode | Our defense |
|---|---|
| IsoForest misses frozen values (constant ≈ "normal") | L3 catches it |
| IsoForest misses slow drift (each point near-normal) | L2 trend/drift + L4 forecast residual |
| Threshold-only misses multivariate combos (T=50 & RH=98) | L1 dew-point + L2 IsoForest |
| Any single detector false-positives a real heatwave | L5 spatial agreement → REGIONAL_EVENT, not fault |
| Black-box alert with no reason | SHAP + per-layer reason |

This is the **Detection Accuracy (20%)** and **Innovation (25%)** story in one slide.
