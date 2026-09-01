"""
SkyGuard AI — SIH-format 6-slide PDF generator (weasyprint).
Produces 3 standalone decks, each emphasizing a different narrative angle.
Landscape 16:9 slide style, SIH prescribed sections.
"""
import os
from weasyprint import HTML

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "pdf")
OUT_DIR = os.path.abspath(OUT_DIR)
os.makedirs(OUT_DIR, exist_ok=True)

# ---------- Shared CSS (16:9 landscape slides) ----------
CSS = """
@page {
  size: 297mm 167mm;        /* 16:9 landscape */
  margin: 0;
}
* { box-sizing: border-box; }
body { margin: 0; font-family: 'DejaVu Sans', 'Helvetica', sans-serif; color: #1a1a2e; }
.slide {
  page-break-after: always;
  width: 297mm; height: 167mm;
  padding: 9mm 14mm 8mm 14mm;
  position: relative; overflow: hidden;
  background: #ffffff;
}
.slide:last-child { page-break-after: auto; }

/* Title bar */
.titlebar {
  display: flex; justify-content: space-between; align-items: center;
  border-bottom: 2px solid #0a4d8c;
  padding-bottom: 2mm; margin-bottom: 3mm;
}
.titlebar .tt { font-size: 14pt; font-weight: 700; color: #0a4d8c; }
.titlebar .num { font-size: 9pt; color: #6b7280; }
.slide-tag { position: absolute; bottom: 4mm; right: 14mm; font-size: 8pt; color: #9ca3af; }

/* Headings */
h2.section { font-size: 11pt; color: #0a4d8c; margin: 2mm 0 1mm 0; border-left: 3px solid #f59e0b; padding-left: 2mm; }
h3 { font-size: 10pt; color: #0a4d8c; margin: 1.5mm 0 1mm 0; }

/* Body text */
p, li { font-size: 9pt; line-height: 1.28; margin: 0.4mm 0; }
ul { margin: 0.8mm 0 0.8mm 5mm; padding: 0; }
.tight li { margin: 0.2mm 0; }

/* Columns */
.cols { display: flex; gap: 6mm; }
.col { flex: 1; }

/* Boxes */
.box { background: #f0f6ff; border: 1px solid #bcd4f1; border-radius: 2mm; padding: 2mm 3mm; margin: 1.5mm 0; font-size: 9pt; line-height: 1.28; }
.box.accent { background: #fff7ed; border-color: #fed7aa; }
.box.green { background: #f0fdf4; border-color: #bbf7d0; }
.box.red { background: #fef2f2; border-color: #fecaca; }
.box strong.h { color: #0a4d8c; }

/* Title slide */
.cover {
  background: linear-gradient(135deg, #0a4d8c 0%, #1e3a8a 60%, #0f172a 100%);
  color: #fff; text-align: left;
  display: flex; flex-direction: column; justify-content: center;
  padding: 0 22mm;
}
.cover .kicker { font-size: 13pt; color: #fbbf24; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 4mm; }
.cover h1 { font-size: 34pt; margin: 0 0 3mm 0; line-height: 1.1; font-weight: 800; }
.cover .sub { font-size: 15pt; color: #cbd5e1; margin-bottom: 12mm; font-weight: 400; }
.cover .meta { font-size: 11pt; color: #e2e8f0; line-height: 1.7; }
.cover .meta b { color: #fff; }
.cover .badge { position: absolute; top: 14mm; right: 16mm; background: #fbbf24; color: #0f172a; font-size: 9pt; font-weight: 700; padding: 2mm 4mm; border-radius: 20mm; }

/* Tables */
table { width: 100%; border-collapse: collapse; font-size: 8pt; margin: 1mm 0; }
th { background: #0a4d8c; color: #fff; padding: 1mm 1.5mm; text-align: left; font-weight: 600; }
td { padding: 1mm 1.5mm; border-bottom: 1px solid #e5e7eb; vertical-align: top; line-height: 1.22; }
tr:nth-child(even) td { background: #f8fafc; }
.src { font-size: 7pt; color: #6b7280; }

/* Matrix */
.matrix { width: 100%; border-collapse: collapse; font-size: 8.5pt; margin: 1.5mm 0; }
.matrix td { border: 2px solid #0a4d8c; padding: 2mm; text-align: center; vertical-align: middle; height: 14mm; line-height: 1.2; }
.matrix .hdr { background: #0a4d8c; color: #fff; font-weight: 700; }
.matrix .fault { background: #fef2f2; color: #b91c1c; font-weight: 700; }
.matrix .reg { background: #fffbeb; color: #b45309; font-weight: 700; }
.matrix .health { background: #f0fdf4; color: #15803d; font-weight: 700; }
.matrix .check { background: #f5f3ff; color: #6d28d9; font-weight: 700; }

/* Pipeline diagram */
.pipeline { display: flex; align-items: center; gap: 1mm; margin: 2mm 0; flex-wrap: wrap; }
.pl-node { background: #0a4d8c; color: #fff; padding: 1.5mm 2mm; border-radius: 1.5mm; font-size: 8pt; font-weight: 600; text-align: center; min-width: 20mm; line-height: 1.15; }
.pl-node.edge { background: #f59e0b; }
.pl-node.cloud { background: #1e40af; }
.pl-node.fusion { background: #dc2626; }
.pl-arr { color: #6b7280; font-size: 10pt; font-weight: 700; }

/* KPI chips */
.chips { display: flex; gap: 2mm; flex-wrap: wrap; margin: 1.5mm 0; }
.chip { background: #0a4d8c; color: #fff; padding: 1.5mm 3mm; border-radius: 12mm; font-size: 8pt; font-weight: 600; }
.chip.amber { background: #f59e0b; } .chip.green { background: #16a34a; } .chip.red { background: #dc2626; }

/* References */
ol.refs { font-size: 7.5pt; line-height: 1.28; margin: 1mm 0 1mm 6mm; padding: 0; }
ol.refs li { margin: 0.5mm 0; color: #374151; }
ol.refs a { color: #0a4d8c; text-decoration: none; word-break: break-all; }

/* small helper */
.small { font-size: 8pt; color: #6b7280; }
.center { text-align: center; }
"""

# ---------- Shared content fragments ----------
COVER_META = """
<div class="meta">
<b>Problem Statement:</b> AI/ML-Based Intelligent Anomaly Detection for Automatic Weather Stations (AWS)<br>
<b>Theme:</b> Smart Automation &amp; Observational Networks &nbsp;|&nbsp; <b>Category:</b> Software (with Edge-AI hardware)<br>
<b>Parameters:</b> Temperature &deg;C &nbsp;&bull;&nbsp; Atmospheric Pressure hPa &nbsp;&bull;&nbsp; Relative Humidity %<br>
<b>Team ID:</b> ________ &nbsp;|&nbsp; <b>Team Name:</b> ________ &nbsp;|&nbsp; <b>Mentor:</b> ________
</div>
"""

PIPELINE_DIAGRAM = """
<div class="pipeline">
  <span class="pl-node edge">AWS<br>Sensor</span><span class="pl-arr">&rarr;</span>
  <span class="pl-node edge">ESP32-S3<br>Edge tier<br>L1+L3+IsoForest</span><span class="pl-arr">&rarr;</span>
  <span class="pl-node cloud">Gateway<br>L2 SHAP<br>L4 Chronos-2</span><span class="pl-arr">&rarr;</span>
  <span class="pl-node cloud">L5 Spatial<br>Robust Z</span><span class="pl-arr">&rarr;</span>
  <span class="pl-node fusion">L6 Fusion<br>2&times;2 Matrix</span><span class="pl-arr">&rarr;</span>
  <span class="pl-node">Alert +<br>Health +<br>Store</span>
</div>
"""

FUSION_MATRIX = """
<table class="matrix">
<tr><td class="hdr"></td><td class="hdr">Neighbours AGREE<br>(Z &lt; 3.1)</td><td class="hdr">Neighbours DISAGREE<br>(Z &ge; 3.1)</td></tr>
<tr><td class="hdr">Model flagged<br>(L1&ndash;L4)</td><td class="reg">REGIONAL_EVENT<br><span class="small">real weather &mdash; alert, not fault &mdash; Medium</span></td><td class="fault">SENSOR_FAULT<br><span class="small">sensor is broken &mdash; High</span></td></tr>
<tr><td class="hdr">No model flag</td><td class="health">HEALTHY<br><span class="small">all clear &mdash; no action</span></td><td class="check">CHECK_HEALTH<br><span class="small">subtle drift &mdash; schedule maintenance &mdash; Low</span></td></tr>
</table>
"""

THRESHOLD_TABLE = """
<table>
<tr><th>Check</th><th>Threshold</th><th>Source</th></tr>
<tr><td>Temp rate (fault)</td><td>|&Delta;T| &gt; 19.4 &deg;C/hr</td><td>NOAA MADIS (35&deg;F/hr)</td></tr>
<tr><td>Temp rate (alert)</td><td>|&Delta;T| &gt; 8 &deg;C/hr</td><td>Tightened watch level</td></tr>
<tr><td>Pressure rate (fault)</td><td>|&Delta;P| &gt; 15 hPa/hr</td><td>NOAA MADIS sea-level</td></tr>
<tr><td>Pressure rate (alert)</td><td>|&Delta;P| &gt; 3 hPa/hr</td><td>Cyclone-class (weather, not fault)</td></tr>
<tr><td>Humidity rate (fault)</td><td>|&Delta;RH| &gt; 50 %/hr</td><td>NOAA MADIS</td></tr>
<tr><td>Dew-point constraint</td><td>T<sub>dew</sub> &le; T<sub>air</sub> + 0.5&deg;C</td><td>Magnus / Alduchov&ndash;Eskridge; MADIS</td></tr>
<tr><td>Barometric altitude</td><td>|P &minus; P<sub>exp</sub>| &gt; 30 hPa</td><td>Barometric formula</td></tr>
<tr><td>Range bounds (India)</td><td>T &minus;40/+55&deg;C, RH 0&ndash;100%, P 300&ndash;1084</td><td>WMO records, BoM</td></tr>
<tr><td>Climatological</td><td>monthly mean &plusmn; 5&sigma;</td><td>WMO guideline / Lanzante 1996</td></tr>
<tr><td>Spatial robust-Z</td><td>Z &ge; 3.1 &rarr; disagree</td><td>Met Norway TITAN default</td></tr>
<tr><td>Frozen sensor</td><td>std &lt; 0.01 over &ge;10 readings</td><td>OK Mesonet persistence test</td></tr>
<tr><td>Forecast breach</td><td>actual &notin; [p5,p95] or severity &gt; 0.8</td><td>Chronos-2 corridor</td></tr>
<tr><td>Drift (Mann-Kendall)</td><td>p &lt; 0.05 + Theil&ndash;Sen slope</td><td>Standard trend test</td></tr>
<tr><td>ECMWF blacklist</td><td>PGE &gt; 0.75</td><td>ECMWF operational</td></tr>
</table>
"""

REFERENCES = """
<ol class="refs">
<li>WMO-No. 8, Guide to Instruments &amp; Methods of Observation (CIMO), 2024 ed. &mdash; https://library.wmo.int/viewer/68695/</li>
<li>NOAA MADIS surface QC notes &mdash; https://madis.ncep.noaa.gov/madis_sfc_qc_notes.shtml</li>
<li>ECMWF, Dahoui et al. (2023), ML detection &amp; classification of observation anomalies, Newsletter #174 &mdash; https://www.ecmwf.int/en/newsletter/174/</li>
<li>Spohn et al. (2026), Autoencoders for met QC, Met &Eacute;ann, <b>99.6% accuracy</b>, Environmental Data Science &mdash; https://www.cambridge.org/core/journals/environmental-data-science/article/machine-learning-approach-using-autoencoders-to-perform-quality-control-on-meteorological-data/4576781508080877E36C0CA6612E5590</li>
<li>Edge-Optimized Isolation Forest, IEEE ICISCOIS 2026 (<b>&lt;10ms, &lt;200KB</b>) &mdash; https://doi.org/10.1109/iciscois62701.2026.11447816</li>
<li>Kataria et al. (2026), 6-layer MLOps pipeline, <b>F1=0.91</b>, IEEE MENACOMM &mdash; https://doi.org/10.1109/menacomm69507.2026.11532803</li>
<li>Met Norway TITAN QC framework (L&oslash;pez et al. 2020) &mdash; https://asr.copernicus.org/articles/17/153/2020/ &nbsp;|&nbsp; ROVE engine &mdash; https://github.com/metno/rove</li>
<li>Chronos-2, Amazon (arXiv:2510.15821, Oct 2025, 120M params, multivariate) &mdash; https://huggingface.co/amazon/chronos-2</li>
<li>SHAP TreeExplainer on IsolationForest (PR #784) &mdash; https://github.com/shap/shap/pull/784</li>
<li>alibi-detect v0.13.0 (Seldon) &mdash; https://github.com/SeldonIO/alibi-detect</li>
<li>Fiebrich &amp; Crawford (2001), Oklahoma Mesonet QA, Bull. Amer. Meteor. Soc. &mdash; https://doi.org/10.1175/1520-0477(2001)082</li>
<li>ESP32-S3 Datasheet (Espressif) &mdash; https://documentation.espressif.com/esp32-s3_datasheet_en.html</li>
<li>Open-Meteo Archive API (ERA5, free, no key) &mdash; https://open-meteo.com/en/docs/historical-weather-api</li>
<li>NOAA Integrated Surface Database (ISD) &mdash; https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database</li>
<li>De Bruijn et al. (2016), injected-fault sensor benchmark, 5.78M points &mdash; https://doi.org/10.5220/0005637901850195</li>
<li>WMO Congress (Oct 2025), AI complements not replaces physics, transparency &amp; traceability &mdash; https://wmo.int/themes/artificial-intelligence</li>
<li>SIH 2026 Idea Presentation Format (6-slide PDF) &mdash; https://www.scribd.com/document/1075380264/SIH2026-IDEA-Presentation-Format</li>
</ol>
"""


def slide_header(num, title, section_label):
    return f"""<div class="titlebar"><div class="tt">{title}</div><div class="num">Slide {num} &bull; {section_label}</div></div>"""


def wrap(slides_html, title):
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{title}</title></head>
<body>{slides_html}</body></html>"""


# =====================================================================
# DECK 1 — GRAND CHALLENGE / SELF-HEALING  (max Innovation 25%)
# =====================================================================
deck1 = f"""
<!-- SLIDE 1: TITLE -->
<div class="slide cover">
  <div class="badge">SIH Idea Submission</div>
  <div class="kicker">SkyGuard AI</div>
  <h1>Self-Healing Weather<br>Observation Network</h1>
  <div class="sub">Intelligent Real-Time Anomaly Detection for T, P, RH Sensors in Automatic Weather Stations</div>
  {COVER_META}
</div>

<!-- SLIDE 2: PROPOSED SOLUTION -->
<div class="slide">
  {slide_header(2, "Proposed Solution", "Novelty + Complexity")}
  <div class="cols">
    <div class="col">
      <h2 class="section">The Problem</h2>
      <ul class="tight">
        <li>AWS data feeds forecasts, aviation, farming, disaster warnings &mdash; but is polluted by sensor faults, spikes, frozen values, dropout, drift, comms errors.</li>
        <li>Traditional threshold-only QC misses complex / hidden / multivariate anomalies.</li>
        <li>A single detector <b>cannot tell a broken sensor from a real heatwave.</b></li>
      </ul>
      <h2 class="section">Our Solution &mdash; in one line</h2>
      <div class="box accent"><strong class="h">A 6-layer edge+cloud AI fusion pipeline mirroring WMO L0&ndash;L5 QC, with SHAP explainability and a self-aware, self-healing sensor-health loop.</strong></div>
      <h2 class="section">The Core Insight</h2>
      <div class="box">If only Delhi reports 55&deg;C &rarr; <b>broken sensor.</b> If Delhi <i>and</i> Lucknow <i>and</i> Jaipur all report 55&deg;C &rarr; <b>real heatwave, alert don&rsquo;t fix.</b> Multi-layer + neighbour consensus separates fault from weather.</div>
    </div>
    <div class="col">
      <h2 class="section">The Fusion Matrix (the brain)</h2>
      {FUSION_MATRIX}
      <h2 class="section">Novelty Bullets</h2>
      <ul class="tight">
        <li><b>Self-healing loop:</b> composite health score + predictive time-to-failure + auto-imputation &mdash; direct answer to the grand challenge.</li>
        <li><b>Edge-deployed ML on ESP32-S3</b> &mdash; no competitor does per-station ML inference.</li>
        <li><b>Full physics + ML + foundation-forecast + spatial fusion</b> &mdash; not published as an integrated system.</li>
        <li><b>Transmit-only-on-suspicion</b> &rarr; 72% energy saving, ~10 mo battery vs ~3 mo.</li>
        <li><b>Explainable by construction</b> &mdash; SHAP + per-fault reason + confidence on every alert.</li>
      </ul>
    </div>
  </div>
  <div class="slide-tag">SkyGuard AI &bull; Deck 1: Grand Challenge</div>
</div>

<!-- SLIDE 3: TECHNICAL APPROACH -->
<div class="slide">
  {slide_header(3, "Technical Approach", "Clarity + Complexity")}
  <h2 class="section">Pipeline (Edge &rarr; Cloud &rarr; Fusion)</h2>
  {PIPELINE_DIAGRAM}
  <div class="cols">
    <div class="col">
      <h2 class="section">The 6 Layers</h2>
      <table>
        <tr><th>#</th><th>Layer</th><th>Role</th><th>WMO</th></tr>
        <tr><td>L1</td><td>Physics Sanity</td><td>Range, dew-point, barometric, rate</td><td>L1&ndash;L2</td></tr>
        <tr><td>L2</td><td>ML</td><td>Ext. IsoForest + SHAP + LSTM-AE + trend</td><td>L2</td></tr>
        <tr><td>L3</td><td>Frozen</td><td>std &lt; 0.01 / d&sup2;x/dt&sup2; &asymp; 0</td><td>L2</td></tr>
        <tr><td>L4</td><td>Forecasting</td><td>Chronos-2 corridor breach</td><td>L5</td></tr>
        <tr><td>L5</td><td>Spatial</td><td>Robust Z (median/MAD) vs Haversine neighbours</td><td>L3</td></tr>
        <tr><td>L6</td><td>Fusion</td><td>2&times;2 matrix &rarr; verdict + confidence + root cause</td><td>L4+</td></tr>
      </table>
      <h2 class="section">Self-Healing Sensor Health Score [0,1]</h2>
      <div class="box"><b>Health</b> = w&sub1;(1&minus;bias) + w&sub2;(1&minus;residual_rms) + w&sub3;availability + w&sub4;(1&minus;anomaly_rate) + w&sub5;(1&minus;age_degradation)</div>
      <div class="small">Tiers: &ge;0.85 Green / 0.6&ndash;0.85 Amber / 0.4&ndash;0.6 Orange / &lt;0.4 Red. Predict weeks-to-failure by trending the score &rarr; flag before bad data flows downstream &rarr; auto-upweight imputed values until fixed = <b>trustworthy data under all conditions.</b></div>
    </div>
    <div class="col">
      <h2 class="section">Tech Stack</h2>
      <table>
        <tr><th>Tier</th><th>Technology</th></tr>
        <tr><td>Edge</td><td>ESP32-S3, emlearn (IsoForest &lt;10KB), TFLite-Micro (int8 autoencoder)</td></tr>
        <tr><td>Gateway</td><td>Node.js + Fastify, WebSocket</td></tr>
        <tr><td>ML core</td><td>Python + FastAPI; scikit-learn (EIF), SHAP, LSTM-AE, amazon/chronos-2, alibi-detect</td></tr>
        <tr><td>Store</td><td>TimescaleDB (hypertable) + Redis (windows + neighbour map)</td></tr>
        <tr><td>Queue</td><td>BullMQ on Redis &rarr; horizontal scale</td></tr>
        <tr><td>Frontend</td><td>React + Leaflet (health-colour map) + Recharts (SHAP, corridor)</td></tr>
      </table>
      <h2 class="section">Data Sources</h2>
      <ul class="tight">
        <li><b>Open-Meteo Archive API</b> (ERA5, free, no key, hourly 1940&ndash;now)</li>
        <li><b>NOAA ISD</b> (real station-level noise, public domain)</li>
        <li><b>De Bruijn 2016</b> injected-fault benchmark (5.78M labelled pts)</li>
        <li><b>IMD AWS API</b> (api.imd.gov.in) &mdash; production integration path</li>
        <li><b>WMO OSCAR/Surface</b> &mdash; station metadata for neighbour map</li>
      </ul>
      <h2 class="section">Key Thresholds (sourced)</h2>
      <div class="small">{THRESHOLD_TABLE.split('</table>')[0]}</table></div>
    </div>
  </div>
  <div class="slide-tag">SkyGuard AI &bull; Deck 1: Grand Challenge</div>
</div>

<!-- SLIDE 4: FEASIBILITY & VIABILITY -->
<div class="slide">
  {slide_header(4, "Feasibility &amp; Viability", "Risks + Mitigations + Sustainability")}
  <div class="cols">
    <div class="col">
      <h2 class="section">Feasibility</h2>
      <ul class="tight">
        <li><b>Standards-aligned:</b> 6 layers mirror WMO L0&ndash;L5 (CIMO Guide WMO-No. 8; MADIS; WDQMS) &mdash; not invented in a vacuum.</li>
        <li><b>Free, no-auth data:</b> Open-Meteo/ERA5 + NOAA ISD &mdash; no access blocker.</li>
        <li><b>Cheap hardware:</b> ESP32-S3 &asymp; &#8377;500; commodity cloud.</li>
        <li><b>Each component literature-validated:</b> ECMWF LSTM-AE (operational 2023); Met &Eacute;ann LSTM-AE 99.6% (2026); IEEE edge-IsoForest &lt;10ms (2026); Kataria 6-layer F1=0.91 (2026).</li>
        <li><b>Maturity ladder:</b> Idea &rarr; Pilot (1 region, 50 stations, IMD API) &rarr; Production (675+ IMD, K8s, audit logs, WMO traceability).</li>
      </ul>
    </div>
    <div class="col">
      <h2 class="section">Risks &amp; Mitigations</h2>
      <table>
        <tr><th>Risk</th><th>Mitigation</th></tr>
        <tr><td>Isolated stations (no buddies)</td><td>Multi-layer agreement + NWP O-B &ldquo;virtual buddy&rdquo; (ECMWF)</td></tr>
        <tr><td>IsoForest blind spots (clusters, drift, ghost clusters)</td><td>Extended IsoForest + LSTM-AE sibling + PSI-driven retrain</td></tr>
        <tr><td>ML flags real weather as anomaly</td><td>L5 spatial consensus &rarr; REGIONAL_EVENT; de-seasonalize inputs (ECMWF)</td></tr>
        <tr><td>Class imbalance &lt;5%</td><td>Eval with PR-AUC / F2, never raw accuracy</td></tr>
        <tr><td>ESP32 RAM / OTA / ADC noise</td><td>int8 quant, OTA rollback, calibration + filter</td></tr>
        <tr><td>Regulatory / black-box</td><td>SHAP + human-in-loop + deterministic fallback + audit log (WMO Congress Oct 2025)</td></tr>
        <tr><td>No telemetry integrity standard</td><td>HMAC-signed readings + tamper classifier (closes a WMO gap)</td></tr>
      </table>
      <h2 class="section">Sustainability</h2>
      <div class="chips">
        <span class="chip green">72% energy saving</span>
        <span class="chip green">~10 mo battery vs ~3 mo</span>
        <span class="chip green">Less e-waste</span>
        <span class="chip green">Fewer field trips</span>
      </div>
    </div>
  </div>
  <div class="slide-tag">SkyGuard AI &bull; Deck 1: Grand Challenge</div>
</div>

<!-- SLIDE 5: IMPACT & BENEFITS -->
<div class="slide">
  {slide_header(5, "Impact &amp; Benefits", "Scale + UX")}
  <div class="cols">
    <div class="col">
      <h2 class="section">Target Audience</h2>
      <ul class="tight">
        <li>IMD &amp; State met departments (675+ AWS)</li>
        <li>Aviation, agriculture, disaster management</li>
        <li>Climate research, NWP data assimilation</li>
        <li>Every national met service globally (NOAA ISD 20,000+ stations)</li>
      </ul>
      <h2 class="section">Scale of Impact</h2>
      <div class="chips">
        <span class="chip">675+ IMD stations</span>
        <span class="chip">20,000+ NOAA scale</span>
        <span class="chip amber">3 parameters &rarr; global applicability</span>
      </div>
      <h2 class="section">Benefits</h2>
      <table>
        <tr><th>Type</th><th>Benefit</th></tr>
        <tr><td><b>Social</b></td><td>Better forecasts &rarr; better disaster warnings &rarr; lives saved</td></tr>
        <tr><td><b>Economic</b></td><td>Less bad-data propagation &rarr; fewer wrong forecasts &rarr; lower economic loss; longer sensor life &rarr; lower maintenance cost</td></tr>
        <tr><td><b>Environmental</b></td><td>72% energy saving + longer field life &rarr; less e-waste, fewer truck rolls</td></tr>
        <tr><td><b>Operational</b></td><td>Predictive maintenance &rarr; fix sensors <i>before</i> bad data, not after</td></tr>
      </table>
    </div>
    <div class="col">
      <h2 class="section">User Experience &mdash; Every Alert Explained</h2>
      <div class="box"><b>Alert card</b> = verdict + confidence badge + <b>blamed sensor (SHAP)</b> + plain-English reason + recommended action + imputed value + source.</div>
      <div class="box accent"><b>Example:</b> &ldquo;SENSOR_FAULT (HIGH) &mdash; pressure_hpa blamed by SHAP (1.8). Sea-level pressure at 2205m altitude. Action: recalibrate barometer. Imputed P &asymp; 780 hPa (neighbour median).&rdquo;</div>
      <h2 class="section">Dashboard</h2>
      <ul class="tight">
        <li><b>Leaflet map</b> &mdash; stations coloured by health (green/amber/orange/red)</li>
        <li><b>Live alert feed</b> &mdash; colour-coded severity, expandable per-layer</li>
        <li><b>SHAP bar chart</b> &mdash; per-feature contribution for the flagged reading</li>
        <li><b>Forecast corridor chart</b> &mdash; p5&ndash;p95 band vs actual (red if breach)</li>
        <li><b>Sensor-health panel</b> &mdash; rolling score + trend + predicted time-to-failure</li>
      </ul>
      <h2 class="section">Expected Outputs (per problem statement)</h2>
      <div class="small">Real-time alerts &bull; severity + confidence &bull; root-cause class &bull; visualization dashboard &bull; sensor health status &bull; corrected-data estimation (optional) &mdash; <b>all delivered.</b></div>
    </div>
  </div>
  <div class="slide-tag">SkyGuard AI &bull; Deck 1: Grand Challenge</div>
</div>

<!-- SLIDE 6: RESEARCH & REFERENCES -->
<div class="slide">
  {slide_header(6, "Research &amp; References", "Citations")}
  <h2 class="section">Academic &amp; Production-QC References</h2>
  {REFERENCES}
  <div class="slide-tag">SkyGuard AI &bull; Deck 1: Grand Challenge</div>
</div>
"""

# =====================================================================
# DECK 2 — TECHNICAL DEEP  (max Complexity + Clarity + Accuracy)
# =====================================================================
deck2 = f"""
<!-- SLIDE 1: TITLE -->
<div class="slide cover">
  <div class="badge">SIH Idea Submission</div>
  <div class="kicker">SkyGuard AI</div>
  <h1>6-Layer Fusion for<br>AWS Anomaly Detection</h1>
  <div class="sub">Physics &bull; ML &bull; Forecasting &bull; Spatial Consensus &mdash; WMO-L0&ndash;L5 aligned</div>
  {COVER_META}
</div>

<!-- SLIDE 2: PROPOSED SOLUTION -->
<div class="slide">
  {slide_header(2, "Proposed Solution", "Novelty + Complexity")}
  <h2 class="section">Solution &mdash; 6-Layer Fusion mirroring WMO L0&ndash;L5</h2>
  {PIPELINE_DIAGRAM}
  <div class="cols">
    <div class="col">
      <h2 class="section">Layer Roles</h2>
      <ul class="tight">
        <li><b>L1 Physics</b> &mdash; range, dew-point (Magnus), barometric altitude, rate-of-change. Deterministic.</li>
        <li><b>L2 ML</b> &mdash; Extended IsoForest + SHAP + LSTM-AE + Mann&ndash;Kendall drift + gap detection.</li>
        <li><b>L3 Frozen</b> &mdash; std &lt; 0.01 / d&sup2;x/dt&sup2; &asymp; 0; all-3-frozen &rarr; logger failure.</li>
        <li><b>L4 Forecasting</b> &mdash; Chronos-2 (120M, multivariate) corridor breach.</li>
        <li><b>L5 Spatial</b> &mdash; robust Z = |x&minus;median|/(1.4826&middot;MAD); MSL-normalize pressure.</li>
        <li><b>L6 Fusion</b> &mdash; 2&times;2 matrix &rarr; verdict + confidence + fault type + action.</li>
      </ul>
      <h2 class="section">Why 6 layers beat any single model</h2>
      <div class="small">IsoForest misses frozen &rarr; L3 catches &bull; misses slow drift &rarr; L2 trend + L4 residual &bull; threshold-only misses multivariate combos &rarr; L1 dew-point + L2 &bull; any detector false-positives a heatwave &rarr; L5 agreement &rarr; REGIONAL_EVENT &bull; black-box alert &rarr; SHAP + per-fault natural language.</div>
    </div>
    <div class="col">
      <h2 class="section">The Fusion Matrix</h2>
      {FUSION_MATRIX}
      <h2 class="section">Novelty</h2>
      <div class="box accent"><b>Full integration</b> of edge-deployed ML (ESP32) + physics + foundation-forecast + spatial fusion + self-healing health loop &mdash; <b>not published as a complete system.</b> Components individually validated by ECMWF (operational 2023) / Met &Eacute;ann (99.6%, 2026) / IEEE 2026 edge-IF.</div>
      <h2 class="section">Self-Healing Loop (grand-challenge answer)</h2>
      <div class="box green">Composite sensor-health score + predictive time-to-failure + auto-imputation &rarr; degraded sensor &rarr; downstream feeds upweight imputed values until fixed &rarr; <b>trustworthy data under all conditions.</b></div>
    </div>
  </div>
  <div class="slide-tag">SkyGuard AI &bull; Deck 2: Technical Deep</div>
</div>

<!-- SLIDE 3: TECHNICAL APPROACH -->
<div class="slide">
  {slide_header(3, "Technical Approach", "Thresholds + Stack + Eval")}
  <div class="cols">
    <div class="col">
      <h2 class="section">Concrete Thresholds (all sourced)</h2>
      {THRESHOLD_TABLE}
      <div class="small">Tuning: sweep each threshold on injected-anomaly benchmark; maximize <b>F1 / F2 / PR-AUC</b> (not accuracy &mdash; anomalies &lt;5% of data). Per-station monthly &plusmn;5&sigma; replaces global range in production.</div>
      <h2 class="section">Explainability (XAI)</h2>
      <ul class="tight">
        <li><b>SHAP TreeExplainer</b> on IsoForest &mdash; <code>check_additivity=False</code>; explains path length (sign gotcha documented).</li>
        <li>Blamed sensor = feature with largest |SHAP|.</li>
        <li>Confidence tier from #layers agreeing + spatial.</li>
        <li><b>alibi-detect v0.13.0</b> for streaming drift (MMDDriftOnline / FETDriftOnline).</li>
      </ul>
    </div>
    <div class="col">
      <h2 class="section">Tech Stack</h2>
      <table>
        <tr><th>Tier</th><th>Technology</th></tr>
        <tr><td>Edge</td><td>ESP32-S3, emlearn (IsoForest &lt;10KB), TFLite-Micro (int8 AE), LoRa/Wi-Fi</td></tr>
        <tr><td>Gateway</td><td>Node.js + Fastify + WebSocket</td></tr>
        <tr><td>ML core</td><td>Python + FastAPI; scikit-learn (EIF), SHAP, LSTM-AE, amazon/chronos-2, alibi-detect</td></tr>
        <tr><td>Store</td><td>TimescaleDB hypertable + Redis (windows, neighbour map)</td></tr>
        <tr><td>Queue/Scale</td><td>BullMQ &rarr; stateless K8s workers</td></tr>
        <tr><td>Frontend</td><td>React + Leaflet + Recharts</td></tr>
      </table>
      <h2 class="section">Real-Time Budget</h2>
      <table>
        <tr><th>Stage</th><th>Latency</th></tr>
        <tr><td>L1 + L3 + edge IsoForest</td><td>&lt;5 ms (edge)</td></tr>
        <tr><td>L2 full + L4 Chronos-2 (suspect only)</td><td>~50&ndash;200 ms (cloud)</td></tr>
        <tr><td>L5 spatial (Redis MGET)</td><td>~1&ndash;2 ms</td></tr>
        <tr><td>L6 fusion</td><td>&lt;1 ms</td></tr>
        <tr><td><b>Total (clean)</b></td><td><b>~5 ms</b> (edge short-circuit)</td></tr>
        <tr><td><b>Total (suspect)</b></td><td><b>~60&ndash;210 ms</b></td></tr>
      </table>
      <h2 class="section">Data</h2>
      <div class="small">Open-Meteo (ERA5) + NOAA ISD + De Bruijn 2016 benchmark + IMD API (prod) + WMO OSCAR/Surface metadata.</div>
    </div>
  </div>
  <div class="slide-tag">SkyGuard AI &bull; Deck 2: Technical Deep</div>
</div>

<!-- SLIDE 4: FEASIBILITY & VIABILITY -->
<div class="slide">
  {slide_header(4, "Feasibility &amp; Viability", "Production Ladder + MLOps")}
  <div class="cols">
    <div class="col">
      <h2 class="section">Production-Grade Maturity Ladder</h2>
      <table>
        <tr><th>Stage</th><th>Scope</th><th>Stack</th></tr>
        <tr><td><b>Idea</b> (now)</td><td>Slides + architecture; injected anomalies on ERA5</td><td>Markdown plan</td></tr>
        <tr><td><b>Pilot</b></td><td>1 region, ~50 stations, real IMD API, live dashboard</td><td>Docker Compose; A/B vs deterministic QC</td></tr>
        <tr><td><b>Production</b></td><td>675+ IMD, 24/7, NWP O-B virtual buddy, audit logs</td><td>K8s autoscale + BullMQ; Grafana; WMO traceability</td></tr>
      </table>
      <h2 class="section">MLOps (the real gap)</h2>
      <ul class="tight">
        <li><b>Model versioning:</b> DVC/MLflow per station cluster</li>
        <li><b>Drift monitoring:</b> PSI &gt; 0.2 &rarr; retrain (Kataria 2026, F1=0.91)</li>
        <li><b>A/B thresholds:</b> deterministic + ML in parallel</li>
        <li><b>Human-in-loop:</b> AI proposes blacklist, analyst dispositions (ECMWF model)</li>
        <li><b>Audit log:</b> every QC decision traceable (WMO-No. 8 / WIGOS)</li>
        <li><b>Fallback:</b> if ML down &rarr; L1+L3+L5 deterministic only</li>
      </ul>
    </div>
    <div class="col">
      <h2 class="section">Risks &amp; Mitigations</h2>
      <table>
        <tr><th>Failure mode</th><th>Mitigation</th></tr>
        <tr><td>Isolated / terrain / frontal</td><td>Multi-layer + NWP virtual buddy + lapse-rate + inversion detector</td></tr>
        <tr><td>IsoForest ghost clusters / drift</td><td>Extended IsoForest + LSTM-AE + PSI retrain + de-seasonalize</td></tr>
        <tr><td>ML flags real extreme weather</td><td>Spatial consensus + climatological bounds + exclude REGIONAL_EVENT from retrain</td></tr>
        <tr><td>Class imbalance</td><td>PR-AUC / F2 / precision-at-recall, not accuracy</td></tr>
        <tr><td>Labelled-data scarcity</td><td>Injected benchmark + semi-auto labels from ops warnings (ECMWF)</td></tr>
        <tr><td>ESP32 constraints</td><td>int8 + OTA rollback + ADC calibration</td></tr>
        <tr><td>Regulatory acceptance</td><td>Explainability + human-in-loop + deterministic fallback + audit (WMO Oct 2025)</td></tr>
        <tr><td>Telemetry integrity (WMO gap)</td><td>HMAC-signed readings + tamper classifier</td></tr>
      </table>
    </div>
  </div>
  <div class="slide-tag">SkyGuard AI &bull; Deck 2: Technical Deep</div>
</div>

<!-- SLIDE 5: IMPACT & BENEFITS -->
<div class="slide">
  {slide_header(5, "Impact &amp; Benefits", "Scale + UX + Outputs")}
  <div class="cols">
    <div class="col">
      <h2 class="section">Impact</h2>
      <ul class="tight">
        <li><b>Direct:</b> IMD 675+ AWS &rarr; cleaner data &rarr; better forecasts, disaster warnings, aviation safety.</li>
        <li><b>Scale:</b> every national met service (NOAA 20,000+, ECMWF, DWD, BoM, Met Office).</li>
        <li><b>3-parameter scope</b> &rarr; globally applicable to any T/P/RH AWS.</li>
      </ul>
      <h2 class="section">Benefits</h2>
      <table>
        <tr><th>Type</th><th>Benefit</th></tr>
        <tr><td>Social</td><td>Lives saved via better disaster warnings</td></tr>
        <tr><td>Economic</td><td>Fewer wrong forecasts; predictive maintenance lowers cost</td></tr>
        <tr><td>Environmental</td><td>72% energy saving; longer field life; less e-waste</td></tr>
        <tr><td>Scientific</td><td>Trustworthy climate-record inputs; traceable QC</td></tr>
      </table>
      <h2 class="section">Future Work Progression</h2>
      <ul class="tight">
        <li>Probabilistic Constant Value Test (AMT 2023) for frozen detection</li>
        <li>Conformal prediction for calibrated coverage intervals</li>
        <li>NWP O-B &ldquo;virtual buddy&rdquo; for isolated stations</li>
        <li>Federated learning across stations (privacy-preserving scale)</li>
        <li>Physics-Informed Neural Network hybrid</li>
      </ul>
    </div>
    <div class="col">
      <h2 class="section">User Experience</h2>
      <div class="box"><b>Every alert =</b> verdict + confidence (HIGH/MED/LOW) + blamed sensor (SHAP) + plain-English reason + recommended action + imputed value + source.</div>
      <h2 class="section">Dashboard</h2>
      <ul class="tight">
        <li>Leaflet map &mdash; station colour = health</li>
        <li>Live alert feed &mdash; severity colour-coded, per-layer expandable</li>
        <li>SHAP bar chart per flagged reading</li>
        <li>Chronos-2 forecast corridor (p5&ndash;p95) with actual marked</li>
        <li>Sensor-health panel + predicted time-to-failure</li>
      </ul>
      <h2 class="section">Expected Outputs (problem statement)</h2>
      <table>
        <tr><th>Output</th><th>Delivered by</th></tr>
        <tr><td>Real-time alerts</td><td>L6 &rarr; WebSocket</td></tr>
        <tr><td>Severity + confidence</td><td>L6 tier + numeric</td></tr>
        <tr><td>Root-cause classification</td><td>Fault-type priority (Frozen&gt;Physics&gt;Forecast&gt;ML)</td></tr>
        <tr><td>Visualization dashboard</td><td>React + Leaflet + Recharts</td></tr>
        <tr><td>Sensor health status</td><td>Composite score [0,1] + tier</td></tr>
        <tr><td>Corrected data (optional)</td><td>Imputation ensemble (neighbour &rarr; Kalman &rarr; Chronos &rarr; NWP analog)</td></tr>
      </table>
    </div>
  </div>
  <div class="slide-tag">SkyGuard AI &bull; Deck 2: Technical Deep</div>
</div>

<!-- SLIDE 6: REFERENCES -->
<div class="slide">
  {slide_header(6, "Research &amp; References", "Citations")}
  {REFERENCES}
  <div class="slide-tag">SkyGuard AI &bull; Deck 2: Technical Deep</div>
</div>
"""

# =====================================================================
# DECK 3 — ENERGY + DEPLOYABILITY  (max Energy 5% + Deployability 10%)
# =====================================================================
deck3 = f"""
<!-- SLIDE 1: TITLE -->
<div class="slide cover">
  <div class="badge">SIH Idea Submission</div>
  <div class="kicker">SkyGuard AI</div>
  <h1>Edge-AI Weather QC<br>Transmit-Only-on-Suspicion</h1>
  <div class="sub">72% energy saving &bull; ~10-month battery &bull; self-healing AWS network</div>
  {COVER_META}
</div>

<!-- SLIDE 2: PROPOSED SOLUTION -->
<div class="slide">
  {slide_header(2, "Proposed Solution", "Novelty + Deployability")}
  <div class="cols">
    <div class="col">
      <h2 class="section">The Insight</h2>
      <div class="box accent"><b>Most AWS faults are catchable on-device with a tiny model.</b> Why radio every reading upstream when ~70&ndash;80% of readings are clean? <b>Transmit only on suspicion</b> &rarr; massive energy + bandwidth saving.</div>
      <h2 class="section">Edge + Cloud Split</h2>
      {PIPELINE_DIAGRAM}
      <h2 class="section">On-ESP32 (catches ~70&ndash;80% locally)</h2>
      <ul class="tight">
        <li>L1 Physics (range, dew-point, barometric, rate) &mdash; O(1) arithmetic</li>
        <li>L3 Frozen (std &lt; 0.01) &mdash; O(window)</li>
        <li>Gap/dropout detection</li>
        <li><b>int8 Isolation Forest</b> via emlearn &mdash; &lt;10 KB flash, &lt;1 KB RAM, &lt;10ms inference</li>
        <li><b>int8 MLP autoencoder</b> via TFLite-Micro &mdash; 5&ndash;50 KB flash, 30&ndash;80 KB arena, 1&ndash;10ms (ESP32-S3 with ESP-NN)</li>
      </ul>
    </div>
    <div class="col">
      <h2 class="section">On Gateway/Cloud (only suspect readings)</h2>
      <ul class="tight">
        <li>L2 full ML (Ext. IsoForest + SHAP + LSTM-AE + trend)</li>
        <li>L4 Chronos-2 (120M, multivariate) corridor breach</li>
        <li>L5 Spatial robust-Z (needs network-wide neighbour state)</li>
        <li>L6 Fusion 2&times;2 matrix</li>
      </ul>
      <h2 class="section">The Fusion Matrix</h2>
      {FUSION_MATRIX}
      <h2 class="section">Novelty</h2>
      <ul class="tight">
        <li><b>No competitor does per-station edge ML</b> (Vaisala embeds in firmware; WeatherXM/Tomorrow.io always-transmit). IEEE 2026 did edge-IF on Raspberry Pi, not ESP32.</li>
        <li><b>Transmit-only-on-suspicion</b> is a unique energy/deployability story.</li>
        <li>ESP32-S3 &asymp; &#8377;500 vs industrial AWS &rarr; <b>democratizes weather QC.</b></li>
      </ul>
    </div>
  </div>
  <div class="slide-tag">SkyGuard AI &bull; Deck 3: Energy &amp; Deployability</div>
</div>

<!-- SLIDE 3: TECHNICAL APPROACH -->
<div class="slide">
  {slide_header(3, "Technical Approach", "Energy Budget + Stack + Thresholds")}
  <div class="cols">
    <div class="col">
      <h2 class="section">ESP32-S3 Energy Budget (measured/datasheet)</h2>
      <table>
        <tr><th>Mode</th><th>Current</th><th>Source</th></tr>
        <tr><td>Deep sleep (module)</td><td>8 &micro;A</td><td>ESP32-S3 datasheet</td></tr>
        <tr><td>WiFi TX 20.5 dBm</td><td>355 mA peak</td><td>ESP32-S3 WROOM-1</td></tr>
        <tr><td>LoRa TX 17 dBm</td><td>330 mA</td><td>Heltec V4 datasheet</td></tr>
        <tr><td>LoRa TX 27 dBm</td><td>750 mA</td><td>Heltec V4 datasheet</td></tr>
        <tr><td>Sensor sample + edge ML</td><td>~50 mA &times; 200 ms</td><td>estimated</td></tr>
      </table>
      <h2 class="section">Daily Energy (5-min sampling, 288/day)</h2>
      <table>
        <tr><th>Strategy</th><th>mAh/day</th></tr>
        <tr><td>Always-transmit (LoRa @17dBm)</td><td>~34.6</td></tr>
        <tr><td>Anomaly-only transmit (5% rate)</td><td><b>~9.6</b></td></tr>
        <tr><td><b>Saving</b></td><td><b>~72%</b></td></tr>
      </table>
      <div class="box green"><b>Battery life (3000 mAh):</b> ~10 months anomaly-only vs ~3 months always-transmit. Source: ESP32-S3 + Heltec V4 datasheets.</div>
    </div>
    <div class="col">
      <h2 class="section">Stack</h2>
      <table>
        <tr><th>Tier</th><th>Technology</th></tr>
        <tr><td>Edge</td><td>ESP32-S3 + emlearn + TFLite-Micro + LoRa/Wi-Fi</td></tr>
        <tr><td>Gateway</td><td>Node.js + Fastify + WebSocket</td></tr>
        <tr><td>ML core</td><td>Python + FastAPI; EIF, SHAP, LSTM-AE, chronos-2, alibi-detect</td></tr>
        <tr><td>Store/Cache</td><td>TimescaleDB + Redis + BullMQ</td></tr>
        <tr><td>Frontend</td><td>React + Leaflet + Recharts</td></tr>
      </table>
      <h2 class="section">Key Thresholds (sourced)</h2>
      <div class="small">{THRESHOLD_TABLE.split('</table>')[0]}</table></div>
      <h2 class="section">OTA &amp; Field Reliability</h2>
      <ul class="tight">
        <li>ESP-IDF OTA with fail-safe boot + rollback partition</li>
        <li>ADC calibration + moving-average filter before ML (ESP32 ADC noise &plusmn;7%)</li>
        <li>int8 quantization mandatory (no FP-heavy ops)</li>
        <li>Deterministic fallback if cloud unreachable</li>
      </ul>
    </div>
  </div>
  <div class="slide-tag">SkyGuard AI &bull; Deck 3: Energy &amp; Deployability</div>
</div>

<!-- SLIDE 4: FEASIBILITY & VIABILITY -->
<div class="slide">
  {slide_header(4, "Feasibility &amp; Viability", "Deployability + Risks")}
  <div class="cols">
    <div class="col">
      <h2 class="section">Practical Deployability</h2>
      <ul class="tight">
        <li><b>Cost:</b> ESP32-S3 &asymp; &#8377;500/station vs industrial AWS (&#8377;lakhs).</li>
        <li><b>Standards-aligned:</b> WMO L0&ndash;L5 (CIMO Guide WMO-No. 8; MADIS; WDQMS).</li>
        <li><b>Free data:</b> Open-Meteo (ERA5, no key) + NOAA ISD (public domain).</li>
        <li><b>Drop-in:</b> works with existing IMD AWS API for production ingest.</li>
        <li><b>Components validated:</b> edge-IF IEEE 2026 (&lt;10ms/&lt;200KB); Met &Eacute;ann LSTM-AE 99.6%; ECMWF ML operational.</li>
        <li><b>Scale path:</b> 15 demo &rarr; 675 IMD &rarr; 20,000+ NOAA; K8s + BullMQ + TimescaleDB.</li>
        <li><b>Security:</b> HMAC-signed telemetry + tamper classifier (closes a verified WMO gap &mdash; no standard mandates signed AWS data).</li>
      </ul>
    </div>
    <div class="col">
      <h2 class="section">Risks &amp; Mitigations</h2>
      <table>
        <tr><th>Risk</th><th>Mitigation</th></tr>
        <tr><td>ESP32 PSRAM latency</td><td>int8 quant; weights in flash not PSRAM where possible</td></tr>
        <tr><td>OTA corruption</td><td>ESP-IDF rollback partition; fail-safe boot</td></tr>
        <tr><td>ADC noise &plusmn;7%</td><td>Calibration + moving-average filter pre-ML</td></tr>
        <tr><td>Radio TX peak current</td><td>Transmit-only-on-suspicion &rarr; ~5% duty cycle; solar + Li-ion buffer</td></tr>
        <tr><td>IsoForest blind spots</td><td>Extended IF + LSTM-AE sibling + PSI retrain</td></tr>
        <tr><td>ML flags real weather</td><td>Spatial consensus &rarr; REGIONAL_EVENT; de-seasonalize</td></tr>
        <tr><td>Isolated stations</td><td>Multi-layer agreement + NWP virtual buddy</td></tr>
        <tr><td>Regulatory / black-box</td><td>SHAP + human-in-loop + deterministic fallback + audit log</td></tr>
      </table>
      <h2 class="section">Sustainability</h2>
      <div class="chips"><span class="chip green">72% energy</span><span class="chip green">~10 mo battery</span><span class="chip green">Less e-waste</span><span class="chip green">Fewer field trips</span></div>
    </div>
  </div>
  <div class="slide-tag">SkyGuard AI &bull; Deck 3: Energy &amp; Deployability</div>
</div>

<!-- SLIDE 5: IMPACT & BENEFITS -->
<div class="slide">
  {slide_header(5, "Impact &amp; Benefits", "Scale + UX")}
  <div class="cols">
    <div class="col">
      <h2 class="section">Target Audience</h2>
      <ul class="tight">
        <li>IMD &amp; State met depts (675+ AWS)</li>
        <li>Aviation, agriculture, disaster mgmt</li>
        <li>Climate research, NWP assimilation</li>
        <li>Low-cost / citizen weather networks (democratization)</li>
      </ul>
      <h2 class="section">Scale</h2>
      <div class="chips"><span class="chip">675+ IMD</span><span class="chip">20,000+ NOAA</span><span class="chip amber">&#8377;500/station</span></div>
      <h2 class="section">Benefits</h2>
      <table>
        <tr><th>Type</th><th>Benefit</th></tr>
        <tr><td>Social</td><td>Better disaster warnings &rarr; lives saved</td></tr>
        <tr><td>Economic</td><td>&#8377;500 vs &#8377;lakhs hardware; predictive maintenance; 72% less energy</td></tr>
        <tr><td>Environmental</td><td>~10 mo battery; less e-waste; fewer truck rolls</td></tr>
        <tr><td>Operational</td><td>Fix sensors before bad data flows; self-healing imputation</td></tr>
      </table>
    </div>
    <div class="col">
      <h2 class="section">User Experience &mdash; Explained Alerts</h2>
      <div class="box"><b>Alert card</b> = verdict + confidence + blamed sensor (SHAP) + reason + action + imputed value.</div>
      <h2 class="section">Dashboard</h2>
      <ul class="tight">
        <li>Leaflet map &mdash; station colour = health</li>
        <li>Live alert feed &mdash; severity colour-coded</li>
        <li>SHAP bar chart per flagged reading</li>
        <li>Chronos-2 forecast corridor chart</li>
        <li>Sensor-health panel + predicted time-to-failure</li>
      </ul>
      <h2 class="section">Expected Outputs (problem statement)</h2>
      <div class="small">Real-time alerts &bull; severity + confidence &bull; root-cause class &bull; dashboard &bull; sensor health &bull; corrected-data estimation &mdash; <b>all delivered.</b></div>
      <h2 class="section">Self-Healing Loop</h2>
      <div class="box green">Degraded sensor &rarr; auto-upweight neighbour/Chronos-imputed values downstream &rarr; <b>trustworthy data flows uninterrupted</b> &rarr; the grand-challenge answer.</div>
    </div>
  </div>
  <div class="slide-tag">SkyGuard AI &bull; Deck 3: Energy &amp; Deployability</div>
</div>

<!-- SLIDE 6: REFERENCES -->
<div class="slide">
  {slide_header(6, "Research &amp; References", "Citations")}
  {REFERENCES}
  <div class="slide-tag">SkyGuard AI &bull; Deck 3: Energy &amp; Deployability</div>
</div>
"""

# ---------- Render ----------
decks = [
    ("SkyGuard_AI_Deck1_GrandChallenge.pdf", deck1),
    ("SkyGuard_AI_Deck2_TechnicalDeep.pdf", deck2),
    ("SkyGuard_AI_Deck3_EnergyDeployable.pdf", deck3),
]

for fname, html in decks:
    path = os.path.join(OUT_DIR, fname)
    HTML(string=wrap(html, fname), base_url=OUT_DIR).write_pdf(path, stylesheets=[__import__('weasyprint').CSS(string=CSS)])
    size = os.path.getsize(path)
    print(f"WROTE {path}  ({size/1024:.1f} KB)")

print("DONE")
