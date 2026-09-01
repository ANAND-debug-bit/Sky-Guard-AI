# 05 — Explainability (XAI)

> Explainability is 10% of the score and the easiest 10% to win if done right. The bar: **every alert says *why*, with a per-feature contribution and a confidence tier.**

---

## The core: SHAP on Isolation Forest

**Why SHAP:** Shapley values give a *principled, additive* attribution of the anomaly score to each feature. It's the gold-standard XAI method (preferable to LIME's local linear approx for tabular tree models). The problem statement lists "Explainable AI (SHAP/LIME) (Preferable)" — we use SHAP, the preferred one.

**Formula (Shapley):**
```
φᵢ = Σ_{S⊆F\{i}} [ |S|!(|F|−|S|−1)! / |F|! ] · [f(S∪{i}) − f(S)]
```
- F = full feature set {temp, pressure, humidity, hour, …}
- φᵢ = contribution of feature i to the model output

**Why Isolation Forest + SHAP:** IsoForest is unsupervised (no labelled anomalies needed), fast, and tree-based → SHAP's `TreeExplainer` gives *exact* Shapley values in polynomial time (not exponential).

---

## ⚠️ The sign-convention gotcha (say this in the PPT — judges love it)

SHAP on `sklearn.IsolationForest` does **NOT** explain the `predict()` label (+1/−1). It explains the **raw anomaly score (path length)**:

| Quantity | Sign meaning |
|---|---|
| SHAP value (large) | shorter path ⇒ **more anomalous** |
| `decision_function()` (negative) | outlier |
| `predict()` (−1) | anomaly |

**Conversion:** `score = 2^(−shap_explained / avg_path_length)`.

**Required code setting:** `TreeExplainer(model, check_additivity=False)` — otherwise SHAP errors on IsoForest (the additivity check assumes a standard tree objective).

**Practical rule we use:** the **feature with the largest *absolute* SHAP value** is the blamed sensor. We document the sign so the verdict reads correctly.

Source: SHAP PR #784 (https://github.com/shap/shap/pull/784).

---

## Blamed-sensor attribution (the XAI output)

```
Reading: temp=42.3, pressure=1005.8, humidity=35.2, hour=14

IsoForest predict = -1  → ANOMALY

SHAP |values|: { pressure: 1.8, temp: 0.3, humidity: 0.1, hour: 0.05 }
                          ^^^^
                   largest ⇒ blamed_sensor = "pressure_hpa"

verdict.reason = "SHAP attributes 1.8 to pressure_hpa (largest contributor)"
```

This is what makes our alert **actionable**: not just "anomaly" but "**pressure sensor** is the culprit — check barometer calibration."

---

## Per-fault natural-language explanations (the human layer on top of SHAP)

SHAP tells you *which feature*. The fusion layer maps that + the physics/forecast context to a **plain-English reason + recommended action**:

| Fault type | Natural-language reason | Recommended action |
|---|---|---|
| Spike | "Sudden 25 °C jump in 1 reading — voltage surge/EMI signature" | Inspect sensor wiring, lightning protection |
| Frozen | "Temperature std=0.0001 over 12 readings — sensor jammed" | Physical inspection for ice/dust/jam |
| Drift | "Mann-Kendall p<0.05, Theil-Sen slope +0.4 °C/day over 30d — decalibration" | Schedule recalibration |
| Dropout | "All 3 sensors NaN — station power/logger failure" | Dispatch power check |
| Impossible combo | "T_dew > T_air (RH>100%) — humidity sensor inconsistent with temp" | Recalibrate humidity sensor |
| Barometric | "Sea-level pressure at 2200 m altitude — barometer miscalibrated" | Recalibrate barometer |
| Cross-sensor decoupling | "Only temp anomalous; co-located P/RH + neighbours healthy" | Replace temp sensor |
| Regional event | "Neighbours show same anomaly — real weather, not a fault" | Monitor, no maintenance |

---

## Confidence score (not just a label)

We derive a 3-tier confidence from *how many layers agree* + spatial agreement, not a single model probability:

| Tier | Condition | Meaning |
|---|---|---|
| **HIGH** | ≥2 layers flag AND neighbours disagree | Very likely a real sensor fault |
| **MEDIUM** | 1 layer flags AND neighbours disagree; OR ≥2 flag AND neighbours agree | Probable fault OR regional weather |
| **LOW** | No model flag but spatial disagrees | Subtle drift — schedule check, don't alert |

Optional numeric confidence: `conf = (n_flagged_layers / 4) · spatial_weight`, where `spatial_weight = 1.0` if neighbours disagree, `0.5` if agree. **Tune.**

---

## XAI beyond SHAP (mention for the Innovation slide)

- **alibi-detect v0.13.0** — Seldon's purpose-built outlier/drift library with built-in explanation hooks; we use `MMDDriftOnline` / `FETDriftOnline` for *streaming drift* detection (IsoForest can't do online drift well).
- **Counterfactual / what-if** (post-hackathon): "What sensor value would have made this reading normal?" → feeds the **corrected/imputed value** optional deliverable.
- **Forecast-corridor visualization** — showing p5/p50/p95 band vs actual is itself an explanation: the user *sees* the breach.

---

## What goes on the UI (Visualization, 5%)

- **Alert card:** verdict + confidence badge (HIGH/MED/LOW) + blamed sensor + 1-line reason + recommended action.
- **SHAP bar chart:** per-feature contribution for the flagged reading.
- **Forecast corridor chart:** p5–p95 band with the actual reading marked (red if outside).
- **Sensor health panel:** rolling health score per sensor (see `07-sensor-health.md`).
- **Station map (Leaflet):** colour = station health (green/amber/red).

This single slide covers Explainability (10%) + Visualization (5%) together.
