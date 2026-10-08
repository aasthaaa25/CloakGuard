"""
Multimodal Detection Model Training
Trains the full multimodal ensemble on URL-lexical + drift + promotion +
jargon features, with per-modality ablation study.

Run: python detection/train_multimodal.py
Output:
  detection/artifacts/multimodal_model.joblib
  detection/artifacts/multimodal_metrics.json
  detection/artifacts/graphs/15_modality_ablation.png
  detection/artifacts/graphs/16_jargon_asymmetry_dist.png
  detection/artifacts/graphs/17_drift_feature_dists.png
  detection/artifacts/graphs/18_screenshot_diff_examples.png (if visual data)
  detection/artifacts/graphs/19_dom_diff_example.png
  detection/artifacts/graphs/20_fusion_contribution.png
  detection/artifacts/graphs/21_crawl_funnel.png
"""

import sys
import json
import warnings
warnings.filterwarnings("ignore")

from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
from matplotlib.gridspec import GridSpec

from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import (
    RandomForestClassifier, HistGradientBoostingClassifier, VotingClassifier
)
from sklearn.pipeline import Pipeline
from sklearn.metrics import (
    accuracy_score, f1_score, roc_auc_score, average_precision_score,
    precision_score, recall_score, confusion_matrix, roc_curve
)
from imblearn.over_sampling import SMOTE
import joblib

# ── Styling ───────────────────────────────────────────────────────────────────
PALETTE = ["#1F3864", "#2E75B6", "#ED7D31", "#70AD47", "#A5A5A5", "#FFC000"]
DPI     = 160
sns.set_theme(style="whitegrid", font_scale=1.0)
plt.rcParams.update({
    "figure.dpi": DPI,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "font.family": "DejaVu Sans",
})

ARTIFACT_DIR = ROOT / "detection" / "artifacts"
GRAPHS_DIR   = ARTIFACT_DIR / "graphs"
GRAPHS_DIR.mkdir(parents=True, exist_ok=True)

# ── Modality feature groups ───────────────────────────────────────────────────
from detection.features import FEATURE_NAMES as URL_FEAT_NAMES
from detection.pipeline.dataset import MULTIMODAL_FEAT_NAMES

MODALITY_GROUPS = {
    "url_lexical": list(URL_FEAT_NAMES),
    "drift":  ["drift_score", "html_size_drift", "dom_drift",
               "link_drift", "text_drift", "title_drift",
               "bot_only_link_count", "visual_ssim", "visual_pixel_delta"],
    "promo":  ["promo_score", "promo_asymmetry", "category_count",
               "total_bot_promo_hits", "total_human_promo_hits", "bot_excess_promo_hits"],
    "jargon": ["jargon_asymmetry_score", "jargon_mass_bot", "jargon_mass_human",
               "jargon_mass_delta", "jargon_jsd"],
    "fused":  list(URL_FEAT_NAMES) + MULTIMODAL_FEAT_NAMES,
}


def _save(fig, name: str):
    path = GRAPHS_DIR / f"{name}.png"
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  [graph] {path.name}")


def _eval(name, clf, X_tr, X_te, y_tr, y_te):
    clf.fit(X_tr, y_tr)
    proba = clf.predict_proba(X_te)[:, 1]
    pred  = (proba >= 0.5).astype(int)
    return {
        "name":      name,
        "accuracy":  float(accuracy_score(y_te, pred)),
        "precision": float(precision_score(y_te, pred, zero_division=0)),
        "recall":    float(recall_score(y_te, pred, zero_division=0)),
        "f1":        float(f1_score(y_te, pred, zero_division=0)),
        "roc_auc":   float(roc_auc_score(y_te, proba)) if len(np.unique(y_te)) > 1 else 0.5,
        "pr_auc":    float(average_precision_score(y_te, proba)) if len(np.unique(y_te)) > 1 else 0.5,
        "proba":     proba,
        "pred":      pred,
        "clf":       clf,
    }


def _quick_lr(X_tr, X_te, y_tr, y_te, name):
    pipe = Pipeline([("sc", StandardScaler()), ("lr", LogisticRegression(max_iter=500, random_state=42))])
    return _eval(name, pipe, X_tr, X_te, y_tr, y_te)


# ════════════════════════════════════════════════════════════════════════════════
def step1_load_data():
    print("\n" + "=" * 60)
    print("STEP 1: Loading multimodal dataset …")
    print("=" * 60)
    from detection.pipeline.dataset import build_dataset
    df = build_dataset()

    y = df["label"].astype(int).values
    print(f"  Dataset: {df.shape}  label={np.bincount(y)}")

    live_mask   = df["provenance"] == "live_crawl"
    n_live      = live_mask.sum()
    n_backbone  = (~live_mask).sum()
    print(f"  Live-crawl rows: {n_live}   Backbone rows: {n_backbone}")
    return df, y


def step2_build_feature_matrices(df, y):
    print("\n" + "=" * 60)
    print("STEP 2: Building per-modality feature matrices …")
    print("=" * 60)

    matrices = {}
    for mod, cols in MODALITY_GROUPS.items():
        avail = [c for c in cols if c in df.columns]
        X = df[avail].fillna(0).values
        matrices[mod] = (X, avail)
        print(f"  {mod:<15}: {X.shape[1]} features")

    return matrices


def step3_ablation_study(matrices, y):
    print("\n" + "=" * 60)
    print("STEP 3: Per-modality ablation study …")
    print("=" * 60)

    # Use SMOTE if imbalanced
    unique, counts = np.unique(y, return_counts=True)
    min_ratio = counts.min() / counts.max()

    X_fused, _ = matrices["fused"]

    ablation_results = []

    for mod, (X, feat_names) in matrices.items():
        if X.shape[1] == 0:
            continue
        X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, stratify=y, random_state=42)

        if min_ratio < 0.40 and X_tr.shape[0] > 20:
            try:
                X_tr, y_tr = SMOTE(random_state=42, k_neighbors=min(5, counts.min()-1)).fit_resample(X_tr, y_tr)
            except Exception:
                pass

        r = _quick_lr(X_tr, X_te, y_tr, y_te, mod)
        ablation_results.append(r)
        print(f"  {mod:<15}: acc={r['accuracy']:.4f}  f1={r['f1']:.4f}  auc={r['roc_auc']:.4f}")

    return ablation_results, y


def step4_full_multimodal_ensemble(matrices, y):
    print("\n" + "=" * 60)
    print("STEP 4: Training full multimodal ensemble …")
    print("=" * 60)

    X, feat_names = matrices["fused"]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, stratify=y, random_state=42)

    unique, counts = np.unique(y_tr, return_counts=True)
    if counts.min() / counts.max() < 0.40:
        try:
            X_tr, y_tr = SMOTE(random_state=42, k_neighbors=min(5, counts.min()-1)).fit_resample(X_tr, y_tr)
        except Exception:
            pass

    lr_pipe = Pipeline([("sc", StandardScaler()), ("lr", LogisticRegression(max_iter=1000, random_state=42))])
    rf  = RandomForestClassifier(n_estimators=200, max_depth=20, n_jobs=-1, random_state=42)
    hgb = HistGradientBoostingClassifier(max_iter=300, random_state=42)
    ens = VotingClassifier([("lr", lr_pipe), ("rf", rf), ("hgb", hgb)], voting="soft")

    results = []
    for name, clf in [("LR_multimodal", lr_pipe), ("RF_multimodal", rf),
                       ("HGB_multimodal", hgb), ("Ensemble_multimodal", ens)]:
        r = _eval(name, clf, X_tr, X_te, y_tr, y_te)
        results.append(r)
        print(f"  {name:<22}: acc={r['accuracy']:.4f}  f1={r['f1']:.4f}  auc={r['roc_auc']:.4f}")

    return results, X_tr, X_te, y_tr, y_te, feat_names


def step5_graphs(ablation_results, ens_results, df, matrices, X_te, y_te, y_full=None):
    print("\n" + "=" * 60)
    print("STEP 5: Generating graphs …")
    print("=" * 60)

    # ── 15: Modality ablation ─────────────────────────────────────────────────
    mods   = [r["name"] for r in ablation_results]
    accs   = [r["accuracy"] for r in ablation_results]
    f1s    = [r["f1"] for r in ablation_results]
    aucs   = [r["roc_auc"] for r in ablation_results]

    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(len(mods))
    w = 0.26
    bars1 = ax.bar(x - w, accs, w, color=PALETTE[0], label="Accuracy")
    bars2 = ax.bar(x,     f1s,  w, color=PALETTE[1], label="F1")
    bars3 = ax.bar(x + w, aucs, w, color=PALETTE[2], label="ROC-AUC")
    for bars in [bars1, bars2, bars3]:
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2, h + 0.005,
                    f"{h:.3f}", ha="center", va="bottom", fontsize=8, rotation=45)
    ax.set_xticks(x)
    ax.set_xticklabels([m.replace("_", "\n") for m in mods], fontsize=10)
    ax.set_ylim(0, 1.12)
    ax.set_title("Per-Modality Ablation Study\n(URL-lexical vs Drift vs Promo vs Jargon vs Fused)",
                 fontweight="bold", fontsize=13)
    ax.axhline(0.90, color="gray", lw=1, linestyle="--", alpha=0.6, label="90% floor")
    ax.legend()
    _save(fig, "15_modality_ablation")

    # ── 16: Jargon asymmetry distribution ─────────────────────────────────────
    if "jargon_asymmetry_score" in df.columns:
        fig, axes = plt.subplots(1, 2, figsize=(13, 5))
        for cls, col, lbl in [(0, PALETTE[0], "Clean (label=0)"), (1, PALETTE[2], "Cloaked (label=1)")]:
            mask = df["label"] == cls
            vals_jas = df.loc[mask, "jargon_asymmetry_score"].fillna(0)
            vals_jmd = df.loc[mask, "jargon_mass_delta"].fillna(0)
            axes[0].hist(vals_jas, bins=40, alpha=0.65, color=col, label=lbl, density=True)
            axes[1].hist(vals_jmd, bins=40, alpha=0.65, color=col, label=lbl, density=True)
        axes[0].set_title("Jargon Asymmetry Score Distribution", fontweight="bold")
        axes[0].set_xlabel("jargon_asymmetry_score")
        axes[0].legend()
        axes[1].set_title("Jargon Mass Delta (bot − human)", fontweight="bold")
        axes[1].set_xlabel("jargon_mass_delta")
        axes[1].legend()
        fig.suptitle("Jargon Asymmetry: Cloaked pages show MORE promotional jargon to bots",
                     fontsize=12, fontweight="bold")
        plt.tight_layout()
        _save(fig, "16_jargon_asymmetry_dist")
    else:
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.text(0.5, 0.5, "Jargon asymmetry requires live-crawl data.\nRun the crawler to populate.",
                ha="center", va="center", transform=ax.transAxes, fontsize=13, color=PALETTE[4])
        ax.set_title("Jargon Asymmetry Distribution", fontweight="bold")
        _save(fig, "16_jargon_asymmetry_dist")

    # ── 17: Drift feature distributions ───────────────────────────────────────
    drift_feats = ["drift_score", "html_size_drift", "dom_drift", "text_drift", "link_drift"]
    drift_avail = [f for f in drift_feats if f in df.columns]

    if drift_avail:
        fig, axes = plt.subplots(1, len(drift_avail), figsize=(4 * len(drift_avail), 5))
        if len(drift_avail) == 1:
            axes = [axes]
        for ax, feat in zip(axes, drift_avail):
            for cls, col, lbl in [(0, PALETTE[0], "Clean"), (1, PALETTE[2], "Cloaked")]:
                mask = df["label"] == cls
                vals = df.loc[mask, feat].fillna(0)
                ax.hist(vals, bins=30, alpha=0.65, color=col, label=lbl, density=True)
            ax.set_title(feat.replace("_", "\n"), fontweight="bold", fontsize=9)
            ax.legend(fontsize=7)
        fig.suptitle("Drift Feature Distributions: Human-view vs Bot-view Divergence by Class",
                     fontsize=12, fontweight="bold")
        plt.tight_layout()
        _save(fig, "17_drift_feature_dists")
    else:
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.text(0.5, 0.5, "Drift features require live-crawl data.\nRun the crawler to populate.",
                ha="center", va="center", transform=ax.transAxes, fontsize=13, color=PALETTE[4])
        ax.set_title("Drift Feature Distributions", fontweight="bold")
        _save(fig, "17_drift_feature_dists")

    # ── 18: Screenshot diff examples (if visual data available) ───────────────
    from pathlib import Path as _P
    crawl_dir = ROOT / "data" / "crawl_sample"
    png_files = list(crawl_dir.glob("*_human.png")) if crawl_dir.exists() else []

    if png_files:
        from PIL import Image
        import io
        pairs = []
        for hf in png_files[:3]:
            bf = _P(str(hf).replace("_human.png", "_bot.png"))
            if bf.exists():
                pairs.append((hf, bf))
        if pairs:
            n_pairs = len(pairs)
            fig, axes = plt.subplots(n_pairs, 3, figsize=(15, 5 * n_pairs))
            if n_pairs == 1:
                axes = [axes]
            for row, (hf, bf) in enumerate(pairs):
                img_h = Image.open(hf).convert("RGB").resize((320, 240))
                img_b = Image.open(bf).convert("RGB").resize((320, 240))
                arr_h = np.array(img_h)
                arr_b = np.array(img_b)
                diff  = np.abs(arr_h.astype(int) - arr_b.astype(int)).astype(np.uint8)
                axes[row][0].imshow(arr_h); axes[row][0].set_title("Human View", fontweight="bold")
                axes[row][1].imshow(arr_b); axes[row][1].set_title("Bot (Googlebot) View", fontweight="bold")
                axes[row][2].imshow(diff, cmap="hot"); axes[row][2].set_title("Pixel Diff Heatmap", fontweight="bold")
                for ax in axes[row]:
                    ax.axis("off")
            fig.suptitle("Screenshot Diff: What humans see vs what bots see",
                         fontsize=14, fontweight="bold")
            plt.tight_layout()
            _save(fig, "18_screenshot_diff_examples")
            goto_19 = True
        else:
            goto_19 = False
    else:
        goto_19 = False

    if not goto_19:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.text(0.5, 0.5,
                "Screenshot diffs require Playwright (browser-based crawl).\n"
                "Install: pip install playwright && playwright install chromium\n"
                "Then re-run: python -m detection.pipeline.crawl --sample 50",
                ha="center", va="center", transform=ax.transAxes, fontsize=12, color=PALETTE[0],
                bbox=dict(boxstyle="round,pad=0.5", facecolor="#EBF3FB", edgecolor=PALETTE[1]))
        ax.set_title("Screenshot Diff Examples (Human vs Bot View)", fontweight="bold")
        ax.axis("off")
        _save(fig, "18_screenshot_diff_examples")

    # ── 19: DOM diff example ───────────────────────────────────────────────────
    _plot_dom_diff_example(df)

    # ── 20: Fusion contribution (feature importance) ───────────────────────────
    _plot_fusion_contribution(matrices, y_full if y_full is not None else y_te)

    # ── 21: Crawl funnel ──────────────────────────────────────────────────────
    _plot_crawl_funnel(df)


def _plot_dom_diff_example(df):
    """Show a real DOM diff from the live crawl if available."""
    from pathlib import Path as _P

    crawl_dir = ROOT / "data" / "crawl_sample"
    meta_files = sorted(crawl_dir.glob("*_meta.json")) if crawl_dir.exists() else []

    example_found = False
    if meta_files:
        import json as _json
        from detection.pipeline.artifacts import extract_dual_artifacts
        from detection.pipeline.drift import compute_cross_view_drift
        from app.forensics.dom_diff import compute_dom_diff

        for mf in meta_files[:30]:
            try:
                meta = _json.loads(mf.read_text())
                uid = meta["url_id"]
                hf = crawl_dir / f"{uid}_human.html"
                bf = crawl_dir / f"{uid}_bot.html"
                if not hf.exists() or not bf.exists():
                    continue
                h_html = hf.read_text(encoding="utf-8", errors="replace")
                b_html = bf.read_text(encoding="utf-8", errors="replace")
                if len(h_html) < 500 or len(b_html) < 500:
                    continue
                dom = compute_dom_diff(h_html, b_html)
                if dom.get("injection_node_count", 0) > 0:
                    nodes = dom["nodes_only_in_bot_view"][:8]
                    fig, ax = plt.subplots(figsize=(12, max(4, len(nodes) * 0.7 + 2)))
                    ax.set_title(
                        f"DOM Diff Example — {meta['url'][:60]}\n"
                        f"{dom['injection_node_count']} bot-only injection node(s) found",
                        fontweight="bold",
                    )
                    if nodes:
                        col_labels = ["DOM Path", "Tag", "Bot-only Text"]
                        table_data = [
                            [n.get("path", "")[-50:], n.get("tag", ""), n.get("text", "")[:50]]
                            for n in nodes
                        ]
                        tbl = ax.table(cellText=table_data, colLabels=col_labels,
                                       loc="center", cellLoc="left")
                        tbl.auto_set_font_size(False)
                        tbl.set_fontsize(9)
                        tbl.scale(1, 1.6)
                    ax.axis("off")
                    plt.tight_layout()
                    _save(fig, "19_dom_diff_example")
                    example_found = True
                    break
            except Exception:
                continue

    if not example_found:
        crawl_dir = ROOT / "data" / "crawl_sample"
        meta_files_count = len(list(crawl_dir.glob("*_meta.json"))) if crawl_dir.exists() else 0

        fake_nodes = [
            {"path": "html>body>div[0]>a[3]", "tag": "a",
             "attrs": {"href": "http://casino-spam.tk"}, "text": "FREE CASINO SLOTS"},
            {"path": "html>body>div[0]>span[1]", "tag": "span",
             "attrs": {"style": "display:none"}, "text": "Buy Cheap Pills Online"},
        ]
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.set_title(
            "DOM Diff: Bot-only injection nodes (illustrative example)\n"
            f"[{meta_files_count} crawled URLs available; run more crawls to find live cloaking]",
            fontweight="bold",
        )
        col_labels = ["DOM Path", "Tag", "Bot-only Text (injected content)"]
        table_data = [
            [n["path"], n["tag"], n["text"]]
            for n in fake_nodes
        ]
        tbl = ax.table(cellText=table_data, colLabels=col_labels,
                       loc="center", cellLoc="left")
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(10)
        tbl.scale(1, 2)
        for (r, c), cell in tbl.get_celld().items():
            if r == 0:
                cell.set_facecolor(PALETTE[0])
                cell.set_text_props(color="white", fontweight="bold")
            elif r % 2 == 0:
                cell.set_facecolor("#F0F4FF")
        ax.axis("off")
        plt.tight_layout()
        _save(fig, "19_dom_diff_example")


def _plot_fusion_contribution(matrices, y_te):
    """Stacked bar showing each modality's contribution to the final fused score."""
    modalities   = ["url_lexical", "drift", "promo", "jargon"]
    weights_live = [0.35, 0.25, 0.15, 0.25]
    weights_url  = [1.00, 0.00, 0.00, 0.00]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # Left: design-time weights
    bars = axes[0].bar(modalities, weights_live, color=PALETTE[:4])
    for bar in bars:
        h = bar.get_height()
        axes[0].text(bar.get_x() + bar.get_width()/2, h + 0.005,
                     f"{h:.0%}", ha="center", va="bottom", fontweight="bold")
    axes[0].set_title("Fusion Weight per Modality\n(live-crawl mode)", fontweight="bold")
    axes[0].set_ylabel("Weight")
    axes[0].set_ylim(0, 0.55)

    # Right: cumulative per-modality AUC improvement
    mods_r = ["url_lexical", "+ drift", "+ promo", "+ jargon"]
    aucs_r = []
    for ablation_key in ["url_lexical", "drift", "promo", "jargon"]:
        X, _ = matrices[ablation_key]
        if X.shape[1] == 0:
            aucs_r.append(aucs_r[-1] if aucs_r else 0.5)
            continue
        X_tr, X_te, y_tr, y_te2 = train_test_split(X, y_te, test_size=0.25, stratify=y_te, random_state=42)
        if len(np.unique(y_tr)) < 2:
            aucs_r.append(aucs_r[-1] if aucs_r else 0.5)
            continue
        from sklearn.linear_model import LogisticRegression as _LR
        from sklearn.preprocessing import StandardScaler as _SC
        lr = Pipeline([("sc", _SC()), ("lr", _LR(max_iter=500, random_state=42))])
        lr.fit(X_tr, y_tr)
        proba = lr.predict_proba(X_te)[:, 1]
        if len(np.unique(y_te2)) < 2:
            aucs_r.append(aucs_r[-1] if aucs_r else 0.5)
        else:
            aucs_r.append(float(roc_auc_score(y_te2, proba)))

    axes[1].bar(mods_r, aucs_r, color=PALETTE[:4])
    for i, (m, v) in enumerate(zip(mods_r, aucs_r)):
        axes[1].text(i, v + 0.005, f"{v:.3f}", ha="center", va="bottom", fontweight="bold")
    axes[1].set_title("ROC-AUC per Modality (single-modality LR)", fontweight="bold")
    axes[1].set_ylabel("ROC-AUC")
    axes[1].set_ylim(0.4, 1.05)
    axes[1].axhline(0.5, color="gray", lw=1, linestyle="--", alpha=0.7, label="Random")
    axes[1].legend()

    fig.suptitle("Fusion Contribution: Multimodal Signal Analysis", fontsize=13, fontweight="bold")
    plt.tight_layout()
    _save(fig, "20_fusion_contribution")


def _plot_crawl_funnel(df):
    """Show the crawl pipeline funnel: 160k → crawled → live → dual-view → cloaked."""
    total_csv = 160000
    n_total   = len(df)
    n_live    = int((df["provenance"] == "live_crawl").sum()) if "provenance" in df.columns else 0
    n_backbone = n_total - n_live
    n_cloaked  = int((df["label"] == 1).sum())
    n_with_drift = int((df["drift_score"] > 0.05).sum()) if "drift_score" in df.columns else 0
    n_with_jargon = int((df["jargon_asymmetry_score"] > 0.05).sum()) if "jargon_asymmetry_score" in df.columns else 0

    stages = [
        ("160k URLs\n(CSV dataset)", total_csv),
        (f"Backbone sample\n({n_backbone} URL-lexical)", n_backbone),
        (f"Live dual-view\ncrawl ({n_live} URLs)", max(n_live, 1)),
        (f"Non-zero drift\n({n_with_drift} rows)", max(n_with_drift, 1)),
        (f"Jargon signal\n({n_with_jargon} rows)", max(n_with_jargon, 1)),
        (f"Label=Cloaked\n({n_cloaked} rows)", n_cloaked),
    ]

    fig, ax = plt.subplots(figsize=(13, 6))
    colors = [PALETTE[0], PALETTE[1], PALETTE[2], PALETTE[3], PALETTE[5], "#C00000"]
    bar_w = 0.6
    xs = range(len(stages))
    bars = ax.bar(xs, [s[1] for s in stages], color=colors, width=bar_w)
    for bar, (lbl, val) in zip(bars, stages):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 400,
                f"{val:,}", ha="center", va="bottom", fontweight="bold", fontsize=9)
    ax.set_xticks(list(xs))
    ax.set_xticklabels([s[0] for s in stages], fontsize=9)
    ax.set_yscale("log")
    ax.set_ylabel("Count (log scale)")
    ax.set_title(
        "Data Pipeline Funnel: From 160k URLs to Multimodal Training Dataset\n"
        f"(Backbone={n_backbone} URL-lexical rows + Live-crawl={n_live} fully multimodal rows)",
        fontweight="bold",
    )
    # Retention arrows
    for i in range(len(stages) - 1):
        x1, v1 = i, stages[i][1]
        x2, v2 = i + 1, stages[i + 1][1]
        if v1 > 0:
            ret = v2 / v1 * 100
            ax.annotate(f"{ret:.0f}%",
                        xy=(x2, v2), xytext=(x1 + 0.5, max(v1, v2) * 1.5),
                        fontsize=8, color="gray", ha="center")
    plt.tight_layout()
    _save(fig, "21_crawl_funnel")


# ════════════════════════════════════════════════════════════════════════════════
def save_artifacts(ens_results, ablation_results, feat_names):
    print("\n" + "=" * 60)
    print("STEP 6: Saving artifacts …")
    print("=" * 60)

    best = max(ens_results, key=lambda r: r["accuracy"])
    model_path = ARTIFACT_DIR / "multimodal_model.joblib"
    joblib.dump({"pipeline": best["clf"], "feature_names": feat_names,
                 "model_name": best["name"]}, str(model_path))
    print(f"  Saved model → {model_path}")

    metrics = {
        "models":    {r["name"]: {k: v for k, v in r.items()
                                  if k not in ("proba", "pred", "clf")}
                     for r in ens_results},
        "ablation":  {r["name"]: {k: v for k, v in r.items()
                                  if k not in ("proba", "pred", "clf")}
                     for r in ablation_results},
        "feature_names": list(feat_names),
        "feature_count": len(feat_names),
        "notes": [
            "Fused multimodal model uses URL-lexical + drift + promotion + jargon features.",
            "Backbone rows have zero multimodal features (url_lexical only).",
            "Live-crawl rows have real drift/promotion/jargon computed from httpx dual-view.",
            "Jargon asymmetry = bot-view jargon mass - human-view jargon mass + JS divergence.",
        ],
    }
    metrics_path = ARTIFACT_DIR / "multimodal_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2, default=float)
    print(f"  Saved metrics → {metrics_path}")


# ════════════════════════════════════════════════════════════════════════════════
def main():
    print("\n╔══════════════════════════════════════════════════════╗")
    print("║  Multimodal Detection Model Training                 ║")
    print("╚══════════════════════════════════════════════════════╝\n")

    df, y        = step1_load_data()
    matrices     = step2_build_feature_matrices(df, y)
    abl, y       = step3_ablation_study(matrices, y)
    ens_r, X_tr, X_te, y_tr, y_te, feat_names = step4_full_multimodal_ensemble(matrices, y)
    step5_graphs(abl, ens_r, df, matrices, X_te, y_te, y_full=y)
    save_artifacts(ens_r, abl, feat_names)

    print("\n" + "=" * 60)
    print("MULTIMODAL TRAINING COMPLETE")
    print("=" * 60)
    best = max(ens_r, key=lambda r: r["accuracy"])
    print(f"  Best model: {best['name']}  acc={best['accuracy']:.4f}  "
          f"f1={best['f1']:.4f}  auc={best['roc_auc']:.4f}")
    print(f"  Graphs saved to: {GRAPHS_DIR}")
    print(f"\n✓ Next: python detection/make_report.py")


if __name__ == "__main__":
    main()
