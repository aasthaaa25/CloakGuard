"""
Stage 8 — Training Dataset Assembly
Assembles the multimodal feature matrix (X) from:
  a) The 160k URL-lexical backbone (from the CSV)
  b) The live-crawled multimodal sample (from data/crawl_sample/)
Persists to data/multimodal_features.parquet for fast re-loading.

Usage:
    python -m detection.pipeline.dataset          # build from existing crawl sample
    python -m detection.pipeline.dataset --rebuild # re-extract features from crawl_sample
"""

import sys
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]   # active_defense_system/
ROOT         = PROJECT_ROOT.parent                   # AA/  (where the CSV lives)
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(ROOT))

CRAWL_SAMPLE_DIR = PROJECT_ROOT / "data" / "crawl_sample"
OUTPUT_PARQUET   = PROJECT_ROOT / "data" / "multimodal_features.parquet"
BACKBONE_CSV     = ROOT / "final_full (1).csv"

from detection.features import transform as _url_transform, FEATURE_NAMES as _URL_FEAT_NAMES

# multimodal feature names (from live crawl)
MULTIMODAL_FEAT_NAMES = [
    # drift modality
    "drift_score", "html_size_drift", "dom_drift",
    "link_drift", "text_drift", "title_drift",
    "bot_only_link_count", "visual_ssim", "visual_pixel_delta",
    # promotion modality
    "promo_score", "promo_asymmetry", "category_count",
    "total_bot_promo_hits", "total_human_promo_hits", "bot_excess_promo_hits",
    # jargon modality
    "jargon_asymmetry_score", "jargon_mass_bot", "jargon_mass_human",
    "jargon_mass_delta", "jargon_jsd",
    # fusion
    "final_risk_score", "model_probability",
]

ALL_FEATURE_NAMES = _URL_FEAT_NAMES + MULTIMODAL_FEAT_NAMES


def _process_crawl_sample(sample_dir: Path) -> pd.DataFrame:
    """
    Walk crawl_sample directory, read meta + HTML files, run the full
    pipeline on each URL, return a DataFrame with all features.
    """
    from detection.pipeline.artifacts import extract_dual_artifacts
    from detection.pipeline.drift     import compute_cross_view_drift
    from detection.pipeline.promotion import compute_promotional_score
    from detection.pipeline.jargon    import compute_jargon_asymmetry
    from detection.pipeline.fusion    import fuse_risk_scores
    from detection.features            import build_url_features

    meta_files = sorted(sample_dir.glob("*_meta.json"))
    if not meta_files:
        print(f"[dataset] No crawl sample found in {sample_dir}")
        return pd.DataFrame()

    rows = []
    for mf in meta_files:
        try:
            meta = json.loads(mf.read_text())
            url    = meta["url"]
            uid    = meta["url_id"]

            h_file = sample_dir / f"{uid}_human.html"
            b_file = sample_dir / f"{uid}_bot.html"

            h_html = h_file.read_text(encoding="utf-8", errors="replace") if h_file.exists() else ""
            b_html = b_file.read_text(encoding="utf-8", errors="replace") if b_file.exists() else ""

            h_shot = sample_dir / f"{uid}_human.png"
            b_shot = sample_dir / f"{uid}_bot.png"

            crawl_record = {
                "url": url, "url_id": uid,
                "human": {
                    "html": h_html,
                    "screenshot_path": str(h_shot) if h_shot.exists() else None,
                },
                "bot": {
                    "html": b_html,
                    "screenshot_path": str(b_shot) if b_shot.exists() else None,
                },
            }

            arts   = extract_dual_artifacts(crawl_record)
            drift  = compute_cross_view_drift(arts, crawl_record)
            promo  = compute_promotional_score(arts, crawl_record)
            jargon = compute_jargon_asymmetry(arts, crawl_record)
            fusion = fuse_risk_scores(drift, promo, url=url, jargon=jargon)
            url_feats = build_url_features(url)

            row = {"url": url, "url_id": uid}
            for fn in _URL_FEAT_NAMES:
                row[fn] = url_feats.get(fn, 0)
            for fn in MULTIMODAL_FEAT_NAMES:
                for d in [drift, promo, jargon, fusion]:
                    if fn in d:
                        row[fn] = d[fn]
                        break
                else:
                    row[fn] = 0.0
            # label from fusion
            row["label"]      = 1 if fusion["final_risk_score"] >= 0.45 else 0
            row["provenance"] = "live_crawl"
            rows.append(row)
        except Exception as e:
            print(f"[dataset] Error processing {mf.name}: {e}")

    df = pd.DataFrame(rows)
    print(f"[dataset] Crawl sample processed: {len(df)} rows")
    return df


def _build_backbone_subset(n: int = 5000) -> pd.DataFrame:
    """
    Build URL-lexical-only rows from the 160k CSV backbone.
    Multimodal features are set to 0 / NaN (provenance = csv_backbone).
    """
    if not BACKBONE_CSV.exists():
        print(f"[dataset] Backbone CSV not found: {BACKBONE_CSV}")
        return pd.DataFrame()

    df_csv = pd.read_csv(BACKBONE_CSV, low_memory=False)
    # Balanced sample
    n_each = n // 2
    pos = df_csv[df_csv["drift_score"] == 1].sample(min(n_each, len(df_csv[df_csv["drift_score"]==1])), random_state=42)
    neg = df_csv[df_csv["drift_score"] == 0].sample(min(n_each, len(df_csv[df_csv["drift_score"]==0])), random_state=42)
    df_sub = pd.concat([pos, neg]).reset_index(drop=True)

    df_x = _url_transform(df_sub)
    df_x["label"]      = df_sub["drift_score"].values
    df_x["url"]        = df_sub["url"].values
    df_x["url_id"]     = ""
    df_x["provenance"] = "csv_backbone"

    for fn in MULTIMODAL_FEAT_NAMES:
        df_x[fn] = 0.0

    print(f"[dataset] Backbone subset: {len(df_x)} rows")
    return df_x


def build_dataset(force_rebuild: bool = False) -> pd.DataFrame:
    """
    Assemble the combined multimodal dataset.
    Returns DataFrame with URL-lexical + multimodal features + label.
    """
    if OUTPUT_PARQUET.exists() and not force_rebuild:
        print(f"[dataset] Loading cached: {OUTPUT_PARQUET}")
        return pd.read_parquet(OUTPUT_PARQUET)

    print("[dataset] Building from scratch...")
    parts = []

    # 1. Live crawl sample (has all multimodal features)
    if CRAWL_SAMPLE_DIR.exists():
        df_live = _process_crawl_sample(CRAWL_SAMPLE_DIR)
        if not df_live.empty:
            parts.append(df_live)

    # 2. CSV backbone (URL-lexical only, multimodal columns = 0)
    df_back = _build_backbone_subset(n=5000)
    if not df_back.empty:
        parts.append(df_back)

    if not parts:
        raise RuntimeError("No data available — run the crawler first.")

    df = pd.concat(parts, ignore_index=True)

    # Ensure all expected columns exist
    for fn in ALL_FEATURE_NAMES:
        if fn not in df.columns:
            df[fn] = 0.0

    df = df.fillna(0.0)
    OUTPUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUTPUT_PARQUET, index=False)
    print(f"[dataset] Saved → {OUTPUT_PARQUET}  ({len(df)} rows)")
    print(f"[dataset] Class balance: {df['label'].value_counts().to_dict()}")
    return df


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()
    df = build_dataset(force_rebuild=args.rebuild)
    print(f"Dataset shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
