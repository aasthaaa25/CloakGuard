"""
Stage 7 — Label Generation
Derives the binary label for each sample in the training dataset.

For the 160k URL backbone: labels come from crawl_status (0=clean, 1=cloaked).
For fresh-crawled samples:  labels come from the fusion score threshold.

All label provenance is documented so the report can be honest about it.
"""

from typing import Optional
import pandas as pd


FUSION_LABEL_THRESHOLD = 0.45  # fusion_score >= this → cloaked (y=1)


def label_from_csv(row: pd.Series) -> dict:
    """
    Derive label from an existing CSV row (backbone 160k dataset).
    Uses crawl_status as the ground-truth label (1=cloaked, 0=clean).
    drift_score is noted but used as a feature sanity-check, not the primary label.
    """
    y = int(row.get("crawl_status", row.get("drift_score", 0)))
    return {
        "label":      y,
        "provenance": "csv_crawl_status",
        "url":        str(row.get("url", "")),
    }


def label_from_fusion(url: str, fusion_result: dict) -> dict:
    """
    Derive label from a fresh crawl's fusion result.
    Used when building the live-crawled multimodal sample.
    """
    score = fusion_result.get("final_risk_score", 0.0)
    y = 1 if score >= FUSION_LABEL_THRESHOLD else 0
    return {
        "label":          y,
        "provenance":     "fusion_threshold",
        "url":            url,
        "fusion_score":   score,
        "alert":          fusion_result.get("alert", False),
        "high_confidence": fusion_result.get("high_confidence", False),
    }


def build_label_series(
    df_backbone: Optional[pd.DataFrame] = None,
    live_label_rows: Optional[list] = None,
) -> pd.DataFrame:
    """
    Assembles all label rows into a single DataFrame with provenance column.
    """
    rows = []

    if df_backbone is not None:
        for _, row in df_backbone.iterrows():
            r = label_from_csv(row)
            rows.append(r)

    if live_label_rows:
        rows.extend(live_label_rows)

    labels_df = pd.DataFrame(rows)
    if labels_df.empty:
        return labels_df

    print(f"[labels] Total labelled rows: {len(labels_df)}")
    print(f"[labels] Provenance breakdown:\n{labels_df['provenance'].value_counts()}")
    print(f"[labels] Class distribution:\n{labels_df['label'].value_counts()}")
    return labels_df
