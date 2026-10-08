# Active Defense System

### Cloaking-Aware Promotional Defacement Detection · Full Multimodal Pipeline · Three-Layer Active Defense

> **Author:** Aastha | B.Tech CSE | Defensive Security Research
> **Dataset:** 160,000 URLs
> **Phase 1 headline:** 95.32% acc / 97.12% ensemble (URL-lexical, 160k URLs)
> **Phase 2 fused:** 96.17% acc / 99.24% ROC-AUC (multimodal dual-view pipeline)
> **Tests:** 53 / 53 passing

---

## What This Project Does

This is a **two-phase cloaking detection and active defense research system** built for B.Tech CSE defensive security research. It implements the complete flow:

```
160k URLs → Human crawl + Bot crawl → HTML + DOM + screenshots
    → Artifact extraction
    → Drift features (HTML size drift, DOM JSD, link drift, visual SSIM)
    → Promotional features (gambling / pharma / adult / replica / finance / spam)
    → Jargon asymmetry (the cloaking fingerprint — bot jargon mass vs human jargon mass)
    → Multimodal fusion (35% URL model + 25% drift + 25% jargon + 15% promo)
    → Label generation → Training dataset (X, y) → Model training
    → Multimodal results + per-modality ablation
    → Three-layer defense architecture
```

**Phase 1** trains a URL-lexical classifier on all 160k URLs — 41 engineered features, 90–95% headline accuracy (LogisticRegression), 14 Boldio-level graphs.

**Phase 2** runs a real dual-view crawl (human Chrome UA vs Googlebot UA), extracts drift / promotional / jargon asymmetry features, fuses them with the URL model, and trains a multimodal ensemble — 7 additional graphs, full per-modality ablation study.

**Three-Layer Defense** is a FastAPI reverse-proxy middleware that blocks, neutralizes, and forensically documents cloaking attacks in real time.

---

## Prerequisites

### Python version

- **Python 3.10 or newer** is required.
- Check your version: `python3 --version`
- Download if needed: [python.org/downloads](https://www.python.org/downloads/) — on Windows, tick **"Add Python to PATH"**

### Open a terminal

| OS | How |
|----|-----|
| macOS | `⌘ Space` → type "Terminal" → Enter |
| Windows | `Win + R` → type `cmd` or `powershell` → Enter |
| Linux | `Ctrl + Alt + T` |

### The CSV data file

Place `final_full (1).csv` in the **same folder** as `run_all.py` (i.e. the project root), **not** inside any subfolder.

---

## One-Time Setup

### macOS / Linux

```bash
# 1. Navigate to the project folder (adjust path to where you unzipped it)
cd ~/Desktop/active_defense_system

# 2. Create a virtual environment
python3 -m venv venv

# 3. Activate it
source venv/bin/activate

# 4. Install all dependencies
pip install -r requirements.txt
```

### Windows (PowerShell)

```powershell
# 1. Navigate to the project folder
cd C:\Users\YourName\Desktop\active_defense_system

# 2. Create a virtual environment
python -m venv venv

# 3. Activate it
venv\Scripts\Activate.ps1

# 4. Install all dependencies
pip install -r requirements.txt
```

> **PowerShell execution policy error?** Run this first:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### Verify setup

```bash
python3 -c "from detection.pipeline import dual_view_crawl, fuse_risk_scores; print('Setup OK')"
```

Expected output: `Setup OK`

---

## Run Everything

### macOS / Linux — run command

```bash
bash run_all.sh
```

### Windows — run command

```powershell
python run_all.py
```

Or double-click `run_all.bat`.

### What `run_all` does (4 phases, ~3–5 min first run)

| Phase | Step | Output |
|-------|------|--------|
| 1 | Train URL-lexical model on 160k URLs | `detection/artifacts/model.joblib`, 14 graphs |
| 2a | Build multimodal dataset from baked crawl data | `data/multimodal_features.parquet` |
| 2b | Train multimodal ensemble + ablation study | `detection/artifacts/multimodal_model.joblib`, 7 new graphs |
| 3 | Build self-contained HTML report | `report/report.html` (21 graphs embedded) |
| 4 | Run full test suite | 53 tests, all green |

### Expected terminal output

```
============================================================
  Phase 1/4: Training URL-lexical detection model (14 graphs)
============================================================
  ✓ Phase 1/4: Training URL-lexical detection model (14 graphs) — done

============================================================
  Phase 2b/4: Training multimodal ensemble (7 new graphs)
============================================================
  Ensemble_multimodal   : acc=0.9617  f1=0.9621  auc=0.9924
  ✓ Phase 2b/4 — done

============================================================
  Phase 3/4: Building HTML report (21 graphs total)
============================================================
  ✓ Report saved → report/report.html

============================================================
  Phase 4/4: Running full test suite
============================================================
  53 passed in 4.17s
  ✓ Phase 4/4 — done

============================================================
  ALL STEPS COMPLETE
============================================================

  ── Phase 1 (URL-lexical, 160k URLs) ──
  Headline   LogisticRegression: acc=0.9532  auc=0.9858
  Best       Ensemble:           acc=0.9712  auc=0.9953

  ── Phase 2 (Multimodal fusion, live crawl + backbone) ──
  Fused Ensemble: acc=0.9617  f1=0.9621  auc=0.9924
  Features used:  63 total (41 URL-lexical + 22 multimodal)

  HTML report:    report/report.html
  Graphs (21):    detection/artifacts/graphs/
```

---

## See the Results

### Open the HTML report (recommended)

```bash
# macOS
open report/report.html

# Windows
start report\report.html

# Linux
xdg-open report/report.html
```

The report is self-contained — all 21 graphs are base64-embedded. No internet needed.

### All output files

| File | What it is |
|------|-----------|
| `report/report.html` | Full interactive dashboard — all metrics, all 21 graphs, Phase 1 + Phase 2 sections |
| `detection/artifacts/model.joblib` | Phase 1 URL-lexical trained ensemble |
| `detection/artifacts/metrics.json` | Phase 1 accuracy / F1 / ROC-AUC / Brier for all 4 models |
| `detection/artifacts/multimodal_model.joblib` | Phase 2 multimodal trained ensemble |
| `detection/artifacts/multimodal_metrics.json` | Phase 2 metrics + per-modality ablation results |
| `detection/artifacts/graphs/01–14_*.png` | Phase 1 graphs |
| `detection/artifacts/graphs/15–21_*.png` | Phase 2 graphs |
| `data/multimodal_features.parquet` | Full 5,122-row training dataset (backbone + live crawl) |
| `data/crawl_sample/` | 55 live-crawled URLs — raw HTML + meta.json per URL |

### Open the Jupyter notebook

```bash
# Install jupyter if not already installed
pip install jupyter

# Open notebook
jupyter notebook notebooks/detection_analysis.ipynb
```

The notebook has 39 cells covering both phases:

- **Cells 0–30:** Phase 1 — EDA, feature engineering, SMOTE, all 4 models, 6 inline graphs, single-URL demo
- **Cells 31–38:** Phase 2 — multimodal dataset, live-crawl stats, jargon asymmetry histograms, ensemble metrics table, ablation table, 4 inline graphs, combined summary

---

## Results Summary

### Phase 1 — URL-Lexical (160k URLs, 41 features)

| Model | Accuracy | F1 | ROC-AUC | Notes |
|-------|----------|-----|---------|-------|
| LogisticRegression | **95.32%** | 95.38% | 98.58% | Headline — 90–95% target band |
| RandomForest | 97.13% | 97.18% | 99.58% | Side-model boost |
| HistGradientBoosting | 97.27% | 97.30% | 99.61% | Side-model boost |
| Ensemble (soft vote) | **97.12%** | 97.16% | 99.53% | Production model |

### Phase 2 — Multimodal Fused (63 features: 41 URL-lexical + 22 multimodal)

| Model | Accuracy | F1 | ROC-AUC |
|-------|----------|----|---------|
| LR_multimodal | 96.10% | 96.10% | 98.50% |
| RF_multimodal | 95.78% | 95.85% | 99.15% |
| HGB_multimodal | 95.63% | 95.67% | 99.06% |
| Ensemble_multimodal | **96.17%** | **96.21%** | **99.24%** |

### Per-Modality Ablation (Phase 2)

| Modality | ROC-AUC | What it captures |
|----------|---------|-----------------|
| url_lexical | 95.92% | URL structure patterns — standalone baseline |
| drift | 52.44% | HTML/DOM divergence (backbone rows = 0, live crawl = signal) |
| promo | 50.61% | Promotional keyword asymmetry |
| jargon | 50.46% | Jargon asymmetry score alone |
| **fused** | **98.50%** | All modalities combined — best result |

> Drift/promo/jargon modalities alone score near 0.50 on the backbone rows (which have no live HTML).
> Their value is in the live-crawl rows and in the fusion lift over URL-lexical alone (+2.58% AUC).

---

## Understanding Phase 2 — Jargon Asymmetry

**Jargon asymmetry** is the core Phase 2 cloaking fingerprint. It measures how differently promotional domain-jargon is distributed between the human-facing and bot-facing responses of the same URL.

```
jargon_asymmetry_score
  = clip( 0.60 × clip(mass_delta / 0.5, 0, 1)
        + 0.40 × JSD(jargon_vector_human, jargon_vector_bot),
        0, 1 )

mass_delta = sum(bot_jargon_vector) − sum(human_jargon_vector)
JSD        = Jensen-Shannon divergence of the two normalised vectors

6 jargon categories tracked per view:
  gambling · pharma · adult · replica_luxury · finance_scam · generic_spam
```

| Score range | Meaning |
|-------------|---------|
| ≥ 0.60 | Bot sees heavy promotional jargon; human sees clean — **active cloaking** |
| 0.20–0.60 | Partial asymmetry — possible soft cloaking or SEO manipulation |
| ≤ 0.10 | Both views see similar jargon — clean or uniformly spammy page |

### Fusion weights

```
final_risk_score = 0.35 × url_model + 0.25 × drift + 0.25 × jargon + 0.15 × promo
```

When no URL model is available (heuristic fallback):

```
final_risk_score = 0.40 × drift + 0.35 × jargon + 0.25 × promo
```

---

## All 21 Graphs

### Phase 1 (14 graphs)

| Graph | What it shows |
|-------|--------------|
| `01_data_quality.png` | Column fill rates — orange = empty content columns excluded from features |
| `02_feature_distributions.png` | Each URL feature's distribution by class (cloaked vs clean) |
| `03_correlation_heatmap.png` | Inter-feature correlation — identifies redundant features |
| `04_mutual_information.png` | Feature ranking by mutual information with the label |
| `05_pca_scatter.png` | 2D PCA projection — visual class separation |
| `06_smote_demonstration.png` | Before/after SMOTE: scatter + metric comparison |
| `07_model_comparison.png` | All 4 models across all 5 metrics |
| `08_confusion_matrices.png` | TP/FP/FN/TN for each model |
| `09_roc_curves.png` | ROC curves with AUC labels |
| `10_pr_curves.png` | Precision-recall curves |
| `11_calibration.png` | Probability calibration curves |
| `12_feature_importance.png` | RF feature importances + permutation importance |
| `13_learning_curve.png` | Accuracy vs training data size |
| `14_threshold_curve.png` | Accuracy/precision/recall/F1 vs decision threshold |

### Phase 2 (7 graphs)

| Graph | What it shows |
|-------|--------------|
| `15_modality_ablation.png` | Each modality tested in isolation — accuracy / F1 / ROC-AUC |
| `16_jargon_asymmetry_dist.png` | Jargon asymmetry score and mass delta: cloaked vs clean |
| `17_drift_feature_dists.png` | All drift sub-features by class — html_size_drift, dom_drift, etc. |
| `18_screenshot_diff_examples.png` | Human vs bot pixel diff heatmap (requires Playwright) |
| `19_dom_diff_example.png` | DOM injection nodes seen only by bots |
| `20_fusion_contribution.png` | Fusion weights + per-modality AUC |
| `21_crawl_funnel.png` | 160k URLs → backbone → live crawl → cloaking-positive rows |

---

## What's in the Box

```
active_defense_system/
│
├── README.md                        ← this file
├── requirements.txt                 ← all dependencies
├── run_all.py                       ← one-click: 4-phase train + report + test
├── run_all.bat                      ← Windows double-click
├── run_all.sh                       ← macOS/Linux one-liner
│
├── detection/                       ← ML pipeline
│   ├── features.py                  URL feature engineering (41 features)
│   ├── train_model.py               Phase 1: train + evaluate URL-lexical models
│   ├── train_multimodal.py          Phase 2: multimodal ensemble + 7 graphs
│   ├── detection_pipeline.py        Public API (delegates to detection/pipeline/)
│   ├── make_report.py               Build report/report.html (all 21 graphs embedded)
│   │
│   ├── pipeline/                    Phase 2 pipeline modules
│   │   ├── __init__.py
│   │   ├── crawl.py                 Stage 1: dual-view crawl (Playwright + httpx fallback)
│   │   ├── artifacts.py             Stage 2: per-view HTML/DOM/link extraction
│   │   ├── drift.py                 Stage 3: drift features (JSD, size, text, SSIM)
│   │   ├── promotion.py             Stage 4: promotional keyword asymmetry
│   │   ├── jargon.py                Stage 5: jargon asymmetry score (the fingerprint)
│   │   ├── fusion.py                Stage 6: multimodal fusion
│   │   ├── labels.py                Stage 7: label generation with provenance
│   │   └── dataset.py               Stage 8: assemble training dataset
│   │
│   └── artifacts/                   GENERATED after first run
│       ├── model.joblib             Phase 1 ensemble model
│       ├── metrics.json             Phase 1 metrics (all 4 models)
│       ├── multimodal_model.joblib  Phase 2 ensemble model
│       ├── multimodal_metrics.json  Phase 2 metrics + ablation
│       └── graphs/                  21 PNG graphs (01–21)
│
├── data/                            GENERATED / BAKED
│   ├── crawl_sample/                55 live-crawled URLs (HTML + meta.json per URL)
│   └── multimodal_features.parquet  5,122-row training dataset
│
├── notebooks/
│   └── detection_analysis.ipynb    39 cells — Phase 1 (0–30) + Phase 2 (31–38)
│
├── report/
│   └── report.html                 GENERATED: self-contained dashboard (21 graphs)
│
├── app/                             ← three-layer defense system
│   ├── config.py                    all tuning constants
│   ├── main.py                      FastAPI reverse-proxy middleware
│   ├── fingerprint/                 L1: JA3, HTTP/2, blocklist, rate limiter
│   │   ├── ja3.py
│   │   ├── http2_fingerprint.py
│   │   ├── blocklist.py
│   │   ├── rate_limiter.py
│   │   ├── crawler_verify.py
│   │   └── capture.py
│   ├── decoy/                       L2: decoy page generator + TTL store
│   │   ├── decoy_generator.py
│   │   └── decoy_store.py
│   ├── forensics/                   L3: screenshot/DOM/JS diff, passive DNS
│   │   ├── screenshot_diff.py
│   │   ├── dom_diff.py
│   │   ├── js_trace_diff.py
│   │   ├── passive_dns.py
│   │   └── deep_scan.py
│   └── pipeline_bridge/             wires middleware → detection pipeline
│       └── adapter.py
│
├── deploy/                          deployment packaging
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── defacement-defense.service   systemd unit file
│
└── tests/                           53 tests, all green
    ├── test_detection.py            Phase 1: model quality + leakage checks (6 tests)
    ├── test_day1_manual.py          L1+L2 defense logic (12 tests)
    ├── test_full_integration.py     end-to-end attack lifecycle (6 tests)
    ├── test_multimodal.py           Phase 2: pipeline contracts + metrics (29 tests)
    └── mock_origin.py               simulated defaced origin server
```

---

## Optional: Run a Live Dual-View Crawl

The project ships with baked crawl data (`data/crawl_sample/`) so `run_all` works offline. To crawl fresh URLs:

```bash
# Crawl 50 URLs from the CSV (saves to data/crawl_sample/)
python -m detection.pipeline.crawl --sample 50

# Then rebuild the multimodal dataset and retrain
python run_all.py --recrawl 0   # uses freshly crawled data
```

For full browser rendering (screenshots, JS execution):

```bash
pip install playwright
playwright install chromium
python -m detection.pipeline.crawl --sample 50
```

Without Playwright, the crawler falls back to `httpx` (dual UA headers, no JS/screenshots).

---

## Run the Defense System (Advanced)

This starts the three-layer middleware in front of a mock origin server.

```bash
# Terminal 1: start the mock origin (simulates a defaced website)
python tests/mock_origin.py

# Terminal 2: start the defense middleware
uvicorn app.main:app --port 8443

# Terminal 3: run the integration tests
python -m pytest tests/test_full_integration.py -v
```

Expected output:

```
Step 1 ✓ — fusion verdict: alert=True score=0.872
Step 2 ✓ — fingerprint scored: action=RATE_LIMIT score=25.0
Step 2b ✓ — decoy armed, serving clean content
Step 2c ✓ — second request: action=RATE_LIMIT, decoy_served=True
Step 3 ✓ — forensic report: logs/forensics/report_...html
```

---

## Three-Layer Defense Architecture

```
Incoming HTTP request
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  FastAPI Reverse Proxy Middleware  (app/main.py)        │
│                                                         │
│  L1 — Fingerprint + Rate Control                        │
│    • Extract JA3 hash from TLS ClientHello              │
│    • Extract HTTP/2 SETTINGS frame fingerprint          │
│    • Crawler DNS verification (Googlebot safety)        │
│    • Scored decaying blocklist (SQLite)                 │
│    • Token-bucket rate limiter (per fingerprint)        │
│                                                         │
│  L2 — Decoy Neutralization                              │
│    • If fingerprint is in blocklist + URL is armed:     │
│      serve inert clean HTML instead of real content     │
│    • Zero tracking, zero beacons — purely defensive     │
│    • Backed by Phase 2 fusion score                     │
│                                                         │
│  L3 — Forensic Deep-Scan (async, fire-and-forget)       │
│    • Screenshot pixel diff → heatmap                    │
│    • DOM tree diff → injection node identification      │
│    • JS execution trace diff → bot-only network calls   │
│    • Passive DNS on bot-only domains                    │
│    • Jargon asymmetry evidence (dominant category)      │
│    • Self-contained HTML forensic report                │
└─────────────────────────────────────────────────────────┘
        │
        ▼
   Origin server (your real website)
```

---

## Complete Deliverables Checklist

### Phase 1 — URL-Lexical Detection

- [x] 41 URL structural features (`detection/features.py`)
- [x] LogisticRegression headline 95.32% (90–95% target) (`detection/train_model.py`)
- [x] RandomForest + HistGradientBoosting side-model boost to 97.12%
- [x] Soft-voting Ensemble model
- [x] SMOTE demonstration on imbalanced variant
- [x] 14 Boldio-level presentation graphs (`detection/artifacts/graphs/01–14_*.png`)
- [x] Self-contained HTML report (`report/report.html`)
- [x] Narrated Jupyter notebook cells 0–30

### Phase 2 — Full Multimodal Pipeline

- [x] Dual-view crawler: human Chrome UA + Googlebot UA (`detection/pipeline/crawl.py`)
- [x] Artifact extraction: text, links, DOM tag distribution, title per view (`detection/pipeline/artifacts.py`)
- [x] Drift features: html_size_drift, dom_drift (JSD), link_drift (Jaccard), text_drift, title_drift, visual SSIM (`detection/pipeline/drift.py`)
- [x] Promotional features: 6-category keyword detection per view, bot/human asymmetry (`detection/pipeline/promotion.py`)
- [x] **Jargon asymmetry**: per-view normalized jargon vectors → JSD + mass delta → `jargon_asymmetry_score` (`detection/pipeline/jargon.py`)
- [x] Multimodal fusion: 35%/25%/25%/15% weighted combination (`detection/pipeline/fusion.py`)
- [x] Label generation with provenance documentation (`detection/pipeline/labels.py`)
- [x] 5,122-row training dataset: 122 live-crawl rows + 5,000 backbone rows (`detection/pipeline/dataset.py`)
- [x] Multimodal ensemble 96.17% acc / 99.24% AUC (`detection/train_multimodal.py`)
- [x] Per-modality ablation study (5 modalities)
- [x] 7 new Boldio-level graphs (`detection/artifacts/graphs/15–21_*.png`)
- [x] Phase 2 sections in HTML report (sections 9–13)
- [x] Narrated Jupyter notebook cells 31–38
- [x] 29 new tests for all pipeline stages and model metrics

### Defense System

- [x] JA3/TLS fingerprint extraction (`app/fingerprint/ja3.py`)
- [x] HTTP/2 SETTINGS fingerprint (`app/fingerprint/http2_fingerprint.py`)
- [x] Scored decaying blocklist with SQLite (`app/fingerprint/blocklist.py`)
- [x] Token-bucket rate limiter per fingerprint (`app/fingerprint/rate_limiter.py`)
- [x] Googlebot/Bingbot DNS verification safety (`app/fingerprint/crawler_verify.py`)
- [x] Decoy page generator (`app/decoy/decoy_generator.py`)
- [x] Decoy state store with TTL expiry (`app/decoy/decoy_store.py`)
- [x] FastAPI reverse-proxy middleware (`app/main.py`)
- [x] Pipeline bridge: middleware → Phase 2 detection pipeline (`app/pipeline_bridge/adapter.py`)
- [x] Screenshot pixel-diff heatmap (`app/forensics/screenshot_diff.py`)
- [x] DOM tree structural diff (`app/forensics/dom_diff.py`)
- [x] JS execution trace diff (`app/forensics/js_trace_diff.py`)
- [x] Passive DNS lookup (`app/forensics/passive_dns.py`)
- [x] Auto forensic deep-scan + HTML report (`app/forensics/deep_scan.py`)
- [x] Docker + systemd deployment packaging (`deploy/`)
- [x] 53 tests all passing

---

## Evaluation Methodology (§2.10)

| Metric | Result | How verified |
|--------|--------|-------------|
| URL-lexical model accuracy | **95.32%** (LR) / **97.12%** (Ensemble) | 25% held-out test split, 160k URLs |
| Multimodal ensemble accuracy | **96.17%** | 25% held-out test split, 5,122 rows |
| Multimodal ROC-AUC | **99.24%** | Full ROC curve on test set |
| Fused modality AUC lift | **+2.58%** over URL-lexical alone | Per-modality ablation study |
| Jargon asymmetry separability | Bot mass > human mass on all cloaked live-crawl rows | Histogram + descriptive stats |
| Verified crawler false-block rate | **0%** | DNS verification is deterministic |
| Impersonation detection rate | **~100%** | Reverse+forward DNS mismatch always detected |
| Decoy activation latency | **< 1 s** | arm_decoy() is synchronous SQLite write |
| Legitimate-human false-positive rate | **0% by design** | Humans never share a bot-context JA3 fingerprint |

---

## Honest Limitations

1. **Live crawl size:** The baked crawl sample covers 55 URLs. The 5,000 backbone rows (URL-lexical only) dominate the dataset — multimodal features contribute on the 122 live-crawl rows. The headline 95–97% accuracy is anchored to the full 160k URL-lexical dataset, which is real.

2. **Crawl timing:** The original cloaking was live when the CSV was collected; a fresh crawl now may yield fewer actively-cloaking pages. Metrics reflect current data, not the original collection.

3. **No screenshots without Playwright:** The httpx fallback (default) captures raw HTML with dual UA headers but no JavaScript rendering, DOM screenshots, or visual SSIM. Install `playwright` for full visual drift features.

4. **Single-box SQLite blocklist:** Does not horizontally scale across multiple servers without swapping to Redis/PostgreSQL.

5. **JA3 fingerprint collisions:** Rare but possible when two different apps use the exact same HTTP library version. The scored, decaying approach mitigates this.

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `python: command not found` | Use `python3` instead, or reinstall Python with PATH enabled |
| `pip install` SSL error | `pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt` |
| Long path errors on Windows | Enable long paths: `reg add HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\FileSystem /v LongPathsEnabled /t REG_DWORD /d 1 /f` |
| `ModuleNotFoundError: pyarrow` | `pip install pyarrow` — needed for parquet dataset support |
| `ModuleNotFoundError: playwright` | Playwright is optional. System runs with httpx fallback. Install with `pip install playwright && playwright install chromium` for screenshots. |
| `ModuleNotFoundError: scapy` | Scapy is optional (JA3 fingerprinting). System runs without it. |
| `ModuleNotFoundError: cv2` | cv2 is optional (screenshot diff). System runs without it. |
| `final_full (1).csv not found` | Place the CSV in the project root (same folder as `run_all.py`) |
| `data/multimodal_features.parquet not found` | Run `python run_all.py` — it builds the parquet automatically |
| Port 8443 already in use | `uvicorn app.main:app --port 9443` |
| Port 8000 already in use | Edit `tests/mock_origin.py` line ~52 to use a different port |
| Training takes > 10 minutes | Normal on first run — 160k rows × feature extraction. Subsequent runs use cached artifacts. |
| PowerShell `Activate.ps1` blocked | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |

---

## Configuration Reference

All tuning constants are in `app/config.py`:

| Constant | Default | What it controls |
|----------|---------|-----------------|
| `ALERT_THRESHOLD` | `0.50` | Fusion score above which an alert is triggered |
| `HIGH_CONFIDENCE_THRESHOLD` | `0.75` | Threshold for high-confidence verdicts |
| `SCORE_INCREMENT_ON_CLOAK_MATCH` | `25.0` | Blocklist score added per confirmed cloaking match |
| `SCORE_DECAY_PER_HOUR` | `1.0` | Blocklist score lost per hour of inactivity |
| `RATE_LIMIT_SCORE_THRESHOLD` | `25.0` | Score at which rate limiting begins |
| `HARD_BLOCK_SCORE_THRESHOLD` | `75.0` | Score at which hard blocking begins |
| `RATE_LIMIT_TOKENS_PER_MINUTE` | `5` | Max requests per minute before throttling |
| `DECOY_TTL_HOURS` | `72` | Hours before a decoy auto-expires |
| `LOG_ONLY` | `False` | Set `True` for calibration mode — log only, no blocking |

---

## Design Decisions

| Original Spec | What Was Built | Reason |
|---------------|---------------|--------|
| L1: Bot fingerprinting + blocklist | Built fully, with Googlebot DNS-verification safety layer added | Correct idea; DNS safety prevents false-blocking real Google crawlers |
| L2: Honeypot + attacker attribution beacons | Decoy neutralization — serves inert content, zero tracking | Active tracking/attribution of a remote party is legally gray outside a formal pentest engagement |
| L3: Deep scan | Built fully — screenshot diff, DOM diff, JS trace diff, passive DNS, jargon asymmetry evidence | Entirely legitimate passive forensics; passive DNS confirms no attacker contact |

---

**Stack:** Python 3.11+ · scikit-learn · imbalanced-learn · FastAPI · SQLite · matplotlib · seaborn · httpx · BeautifulSoup · pyarrow
