"""
Freeze-and-audit the CloakGuard repository.

Writes:
  archive/FREEZE_MANIFEST.json
  evaluation/outputs/claim_audit.json
  evaluation/outputs/paired_view_observations.jsonl
  evaluation/outputs/feature_schema.json

This script does not train a model, does not assign cloaking labels, and does
not modify historical metric files.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "results"
sys.path.insert(0, str(RESULTS))

OUT = REPO / "evaluation" / "outputs"
ARCHIVE = REPO / "archive"


def freeze_manifest() -> dict:
    return json.loads((ARCHIVE / "FREEZE_MANIFEST.json").read_text(encoding="utf-8"))


def _domain(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        host = ""
    return host.lower()


def audit_parquet() -> dict:
    path = RESULTS / "data" / "multimodal_features.parquet"
    df = pd.read_parquet(path)
    prov = df["provenance"].value_counts(dropna=False).to_dict() if "provenance" in df.columns else {}
    mm_cols = [
        "drift_score", "html_size_drift", "dom_drift", "link_drift", "text_drift",
        "title_drift", "bot_only_link_count", "visual_ssim", "visual_pixel_delta",
        "promo_score", "promo_asymmetry", "category_count", "total_bot_promo_hits",
        "total_human_promo_hits", "bot_excess_promo_hits", "jargon_asymmetry_score",
        "jargon_mass_bot", "jargon_mass_human", "jargon_mass_delta", "jargon_jsd",
    ]
    present = [c for c in mm_cols if c in df.columns]
    live = df[df["provenance"] == "live_crawl"] if "provenance" in df.columns else df.iloc[0:0]
    back = df[df["provenance"] == "csv_backbone"] if "provenance" in df.columns else df.iloc[0:0]
    zero_live = int((live[present].fillna(0).abs().sum(axis=1) == 0).sum()) if len(live) and present else 0
    zero_back = int((back[present].fillna(0).abs().sum(axis=1) == 0).sum()) if len(back) and present else 0
    leak_cols = [c for c in ("final_risk_score", "model_probability") if c in df.columns]
    fusion_agree = None
    if "label" in live.columns and "final_risk_score" in live.columns and len(live):
        weak = (live["final_risk_score"] >= 0.45).astype(int)
        fusion_agree = float((weak.values == live["label"].astype(int).values).mean())
    return {
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "provenance_counts": {str(k): int(v) for k, v in prov.items()},
        "backbone_rows_with_all_zero_multimodal_features": zero_back,
        "live_rows_with_all_zero_multimodal_features": zero_live,
        "fusion_outputs_stored_as_columns": leak_cols,
        "live_label_agreement_with_fusion_threshold_0_45": fusion_agree,
        "label_counts": {str(k): int(v) for k, v in df["label"].value_counts().to_dict().items()} if "label" in df.columns else {},
        "interpretation": (
            "This table mixes URL-only backbone rows with paired captures and fills "
            "missing multimodal features with zero. It is not a fully observed multimodal benchmark. "
            "Live labels match the fusion threshold, so agreement with those labels is circular."
        ),
    }


def audit_crawl_and_features() -> tuple[dict, list]:
    from detection.features import FEATURE_NAMES
    from detection.pipeline.artifacts import extract_dual_artifacts
    from detection.pipeline.dataset import MULTIMODAL_FEAT_NAMES
    from detection.pipeline.drift import compute_cross_view_drift
    from detection.pipeline.jargon import compute_jargon_asymmetry
    from detection.pipeline.promotion import compute_promotional_score

    sample = RESULTS / "data" / "crawl_sample"
    metas = sorted(sample.glob("*_meta.json"))
    rows = []
    methods = Counter()
    statuses = Counter()
    failures = Counter()
    for mf in metas:
        meta = json.loads(mf.read_text(encoding="utf-8"))
        uid = meta.get("url_id") or mf.name.replace("_meta.json", "")
        url = meta.get("url") or ""
        h_path = sample / f"{uid}_human.html"
        b_path = sample / f"{uid}_bot.html"
        h_html = h_path.read_text(encoding="utf-8", errors="replace") if h_path.exists() else ""
        b_html = b_path.read_text(encoding="utf-8", errors="replace") if b_path.exists() else ""
        h_status = meta.get("human_status")
        b_status = meta.get("bot_status")
        methods[str(meta.get("human_method"))] += 1
        statuses[f"human:{h_status}"] += 1
        statuses[f"bot:{b_status}"] += 1
        reasons = []
        if not h_path.exists():
            reasons.append("missing_human_html")
        elif len(h_html.strip()) == 0:
            reasons.append("empty_human_html")
        if not b_path.exists():
            reasons.append("missing_bot_html")
        elif len(b_html.strip()) == 0:
            reasons.append("empty_bot_html")
        if h_status not in (200, "200"):
            reasons.append(f"human_status_{h_status}")
        if b_status not in (200, "200"):
            reasons.append(f"bot_status_{b_status}")
        if reasons:
            failures["failed_or_incomplete"] += 1
        else:
            failures["both_views_nonempty_http_200"] += 1
        record = {
            "url": url,
            "url_id": uid,
            "human": {"html": h_html, "screenshot_path": str(sample / f"{uid}_human.png") if (sample / f"{uid}_human.png").exists() else None},
            "bot": {"html": b_html, "screenshot_path": str(sample / f"{uid}_bot.png") if (sample / f"{uid}_bot.png").exists() else None},
        }
        obs = {
            "url_id": uid,
            "url": url,
            "domain": _domain(url),
            "human_status": h_status,
            "bot_status": b_status,
            "human_method": meta.get("human_method"),
            "bot_method": meta.get("bot_method"),
            "human_html_bytes": len(h_html.encode("utf-8", errors="replace")),
            "bot_html_bytes": len(b_html.encode("utf-8", errors="replace")),
            "human_png": (sample / f"{uid}_human.png").exists(),
            "bot_png": (sample / f"{uid}_bot.png").exists(),
            "failure_reasons": reasons,
            "capture_ok": not reasons,
            "label": "uncertain",
            "label_reason": "No independent cloaking annotation is stored with this capture.",
        }
        if obs["capture_ok"]:
            arts = extract_dual_artifacts(record)
            drift = compute_cross_view_drift(arts, record)
            promo = compute_promotional_score(arts, record)
            jargon = compute_jargon_asymmetry(arts, record)
            for src in (drift, promo, jargon):
                for key, value in src.items():
                    if isinstance(value, (int, float, np.floating)) and not isinstance(value, bool):
                        obs[key] = float(value)
            obs["visual_extracted"] = bool(drift.get("have_visual", False))
            obs["jargon_log_base"] = jargon.get("jsd_log_base")
            obs["jargon_definition"] = jargon.get("jsd_definition")
        rows.append(obs)

    urls = [r["url"] for r in rows]
    domains = [r["domain"] for r in rows if r["domain"]]
    ok = [r for r in rows if r["capture_ok"]]
    summary = {
        "meta_files": len(metas),
        "unique_urls": len(set(urls)),
        "unique_domains": len(set(domains)),
        "duplicate_url_rows": len(urls) - len(set(urls)),
        "methods": dict(methods),
        "status_counts": dict(statuses),
        "capture_outcomes": dict(failures),
        "screenshot_rows": int(sum(1 for r in rows if r["human_png"] or r["bot_png"])),
        "visual_features_extracted_on_ok_rows": int(sum(1 for r in ok if r.get("visual_extracted"))),
        "renderer": "httpx User-Agent fetch only. No rendered DOM, screenshot, redirect chain, or execution trace is stored in the crawl metadata.",
        "repeated_profile_protocol": "One human fetch and one bot fetch per meta file. H1/B1/H2/B2 repeats are not present.",
        "ok_drift_score_mean": float(np.mean([r["drift_score"] for r in ok])) if ok else None,
        "ok_jargon_score_mean": float(np.mean([r["jargon_asymmetry_score"] for r in ok])) if ok else None,
        "ok_promo_score_mean": float(np.mean([r["promo_score"] for r in ok])) if ok else None,
        "feature_schema": {
            "url_lexical": list(FEATURE_NAMES),
            "url_lexical_count": len(FEATURE_NAMES),
            "multimodal_columns_in_dataset_module": list(MULTIMODAL_FEAT_NAMES),
            "multimodal_column_count_including_fusion_outputs": len(MULTIMODAL_FEAT_NAMES),
            "detector_feature_count_excluding_fusion_outputs": len(FEATURE_NAMES) + 9 + 6 + 5,
            "claimed_63_resolution": (
                "41 URL features + 9 drift + 6 promotional + 5 jargon = 61 detector features. "
                "The extra two columns are final_risk_score and model_probability, which are "
                "fusion outputs and are excluded from the publication feature set."
            ),
            "duplicate_url_features": ["path_depth duplicates num_path_slashes", "num_query_params duplicates query_param_count"],
            "visual_features": {
                "names": ["visual_ssim", "visual_pixel_delta"],
                "used_by_detector_when_screenshots_exist": True,
                "present_in_this_crawl_sample": False,
                "formula": "SSIM and mean absolute pixel difference on 256x192 grayscale screenshots. Default visual_ssim=1 and visual_pixel_delta=0 when screenshots are absent, and have_visual is false so the drift aggregate drops the visual weight.",
            },
        },
    }
    return summary, rows


def historical_metrics() -> dict:
    phase1 = json.loads((RESULTS / "detection" / "artifacts" / "metrics.json").read_text(encoding="utf-8"))
    phase2 = json.loads((RESULTS / "detection" / "artifacts" / "multimodal_metrics.json").read_text(encoding="utf-8"))
    models = phase1["models"]
    best = max(models, key=lambda name: (models[name]["accuracy"], models[name]["roc_auc"]))
    p2 = phase2["models"]
    return {
        "phase1_status": "archived_not_reproduced",
        "phase1_reason": "final_full (1).csv is absent. metrics.json records a prior run whose label column was drift_score. That column is not independent evidence of cloaking.",
        "phase1_best_archived_model_by_accuracy_then_auc": best,
        "phase1_archived": {
            name: {"accuracy": m["accuracy"], "recall": m["recall"], "roc_auc": m["roc_auc"]}
            for name, m in models.items()
        },
        "phase1_wording": (
            f"Archived ensemble ROC-AUC is {models['Ensemble']['roc_auc']}, "
            f"which is not the same number as HistGradientBoosting ROC-AUC {models['HistGradientBoosting']['roc_auc']}. "
            f"{best} is the best archived Phase 1 model by accuracy and ROC-AUC."
        ),
        "phase2_status": "archived_debugging_not_publication_evidence",
        "phase2_reason": "Trained on the mixed 5,122-row table with zero-filled multimodal features and fusion-derived live labels. final_risk_score and model_probability were included as features.",
        "phase2_archived": {
            name: {"accuracy": m["accuracy"], "recall": m["recall"], "roc_auc": m["roc_auc"]}
            for name, m in p2.items()
        },
        "phase2_wording": (
            "On the archived debugging run, Ensemble_multimodal has the highest accuracy and ROC-AUC, "
            "while RF_multimodal has higher recall "
            f"({p2['RF_multimodal']['recall']:.4f} vs {p2['Ensemble_multimodal']['recall']:.4f}). "
            "That comparison is not evidence of cloaking detection."
        ),
        "synthetic_400_status": "unsupported",
        "synthetic_400_reason": "No synthetic corpus, generation script, prediction file, or confusion-matrix artifact for a 400-example evaluation is in the repository.",
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = freeze_manifest()
    parquet_audit = audit_parquet()
    crawl_summary, rows = audit_crawl_and_features()
    history = historical_metrics()
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "freeze": manifest,
        "parquet": parquet_audit,
        "crawl": crawl_summary,
        "historical_results": history,
        "tasks_separated": {
            "url_risk_classification": "Not rerun. Source CSV missing. Archived metrics must not be described as confirmed cloaking detection.",
            "promotional_cloaking_detection": "Not established. Paired captures have no independent cloaking labels.",
            "overt_defacement_detection": "Not evaluated. No defacement ground truth is stored.",
            "controlled_attack_detection": "Only fixture-level unit tests exist. The 400-example synthetic result is unsupported.",
        },
    }
    (OUT / "claim_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (OUT / "paired_view_observations.jsonl").open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    (OUT / "feature_schema.json").write_text(json.dumps(crawl_summary["feature_schema"], indent=2), encoding="utf-8")
    print(json.dumps({
        "meta_files": crawl_summary["meta_files"],
        "unique_urls": crawl_summary["unique_urls"],
        "capture_outcomes": crawl_summary["capture_outcomes"],
        "parquet_rows": parquet_audit["rows"],
        "provenance": parquet_audit["provenance_counts"],
        "fusion_label_agreement": parquet_audit["live_label_agreement_with_fusion_threshold_0_45"],
        "screenshots": crawl_summary["screenshot_rows"],
    }, indent=2))


if __name__ == "__main__":
    main()
