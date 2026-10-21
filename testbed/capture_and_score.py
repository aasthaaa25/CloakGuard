"""
Capture the local application with the project's httpx fetcher, then score pairs.

north_market is the development family. harbor_books is the held-out family.
This script does not change thresholds and does not train a model.
"""

from __future__ import annotations

import csv
import json
import sys
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "results"))

from detection.pipeline.artifacts import extract_dual_artifacts
from detection.pipeline.crawl import VIEW_PROFILES, _fetch_httpx
from detection.pipeline.drift import compute_cross_view_drift
from detection.pipeline.fusion import fuse_risk_scores
from detection.pipeline.jargon import compute_jargon_asymmetry
from detection.pipeline.promotion import compute_promotional_score
from local_app import serve

PORT = 8765
FEATURE_SCHEMA_VERSION = "url41-drift9-promo6-jargon5-heuristic-0.50"
ORDER = ("H1", "B1", "H2", "B2")
FAMILIES = ("north_market", "harbor_books")
SCENARIOS = (
    "clean_static",
    "benign_promotional",
    "selective_promotional_injection",
    "reverse_selective_injection",
    "legitimate_dynamic",
    "hidden_link_injection",
    "overt_modification",
    "access_challenge",
)
COMPARISONS = (
    ("cross_profile", "H1", "B1"),
    ("cross_profile", "H2", "B2"),
    ("within_human", "H1", "H2"),
    ("within_bot", "B1", "B2"),
)


def capture_family(family: str) -> list[dict]:
    out_dir = REPO / "testbed" / "live_captures" / family
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for scenario in SCENARIOS:
        url = f"http://127.0.0.1:{PORT}/{family}/{scenario}"
        for view in ORDER:
            profile = "human" if view.startswith("H") else "bot"
            fetched = _fetch_httpx(url, VIEW_PROFILES[profile])
            html = fetched.get("html") or ""
            path = out_dir / f"{scenario}_{view}.html"
            path.write_text(html, encoding="utf-8")
            success = fetched.get("status") == 200 and bool(html.strip())
            row = {
                "template_family": family,
                "scenario_id": scenario,
                "view_id": view,
                "profile": profile,
                "requested_url": url,
                "final_url": fetched.get("final_url", ""),
                "status": fetched.get("status", 0),
                "method": fetched.get("method", ""),
                "capture_success": success,
                "error": fetched.get("error", ""),
                "artifact": str(path.relative_to(REPO)).replace("\\", "/"),
                "capture_source": "httpx fetcher from detection/pipeline/crawl.py against testbed/local_app.py",
            }
            rows.append(row)
            (out_dir / f"{scenario}_{view}.json").write_text(json.dumps(row, indent=2), encoding="utf-8")
    return rows


def score_html(url: str, left_html: str, right_html: str) -> dict:
    record = {
        "url": url,
        "url_id": "local",
        "human": {"html": left_html, "screenshot_path": None},
        "bot": {"html": right_html, "screenshot_path": None},
    }
    arts = extract_dual_artifacts(record)
    drift = compute_cross_view_drift(arts, record)
    promo = compute_promotional_score(arts, record)
    jargon = compute_jargon_asymmetry(arts, record)
    fusion = fuse_risk_scores(drift, promo, url="", jargon=jargon)
    return {
        "drift_score": drift.get("drift_score"),
        "bot_only_link_count": drift.get("bot_only_link_count"),
        "text_drift": drift.get("text_drift"),
        "promo_score": promo.get("promo_score"),
        "jargon_asymmetry_score": jargon.get("jargon_asymmetry_score"),
        "jargon_signed_density_delta": jargon.get("jargon_signed_density_delta"),
        "scoring_path": fusion.get("scoring_path"),
        "raw_score": fusion.get("final_risk_score"),
        "threshold": fusion.get("alert_threshold"),
        "predicted_label": "alert" if fusion.get("alert") else "no_alert",
        "score_is_probability": fusion.get("score_is_probability"),
        "visual_used": drift.get("have_visual", False),
    }


def score_saved(capture_rows: list[dict]) -> list[dict]:
    by_key = {(row["template_family"], row["scenario_id"], row["view_id"]): row for row in capture_rows}
    predictions = []
    for family in FAMILIES:
        role = "development" if family == "north_market" else "held_out_controlled_evaluation"
        for scenario in SCENARIOS:
            for comparison, left, right in COMPARISONS:
                left_row = by_key[(family, scenario, left)]
                right_row = by_key[(family, scenario, right)]
                success = bool(left_row["capture_success"] and right_row["capture_success"])
                base = {
                    "scenario_id": scenario,
                    "template_family": family,
                    "evaluation_role": role,
                    "comparison": comparison,
                    "capture_id": f"{family}:{scenario}:{left}-{right}",
                    "capture_success": success,
                    "ground_truth_file": "testbed/expectations.csv",
                    "feature_schema_version": FEATURE_SCHEMA_VERSION,
                    "url_model_used": False,
                    "error_or_limitation": "",
                }
                if not success:
                    base.update({
                        "scoring_path": "",
                        "raw_score": "",
                        "threshold": 0.50,
                        "predicted_label": "",
                        "error_or_limitation": left_row["error"] or right_row["error"] or "capture_failed",
                    })
                    predictions.append(base)
                    continue
                left_html = (REPO / left_row["artifact"]).read_text(encoding="utf-8")
                right_html = (REPO / right_row["artifact"]).read_text(encoding="utf-8")
                scored = score_html(left_row["requested_url"], left_html, right_html)
                base.update(scored)
                if comparison.startswith("within"):
                    base["error_or_limitation"] = (
                        "Within-profile pair is passed through the human/bot feature API. "
                        "The jargon score only counts a positive right-minus-left density gap."
                    )
                predictions.append(base)
    return predictions


def main() -> None:
    server = serve(PORT)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        captures = []
        for family in FAMILIES:
            captures.extend(capture_family(family))
        predictions = score_saved(captures)
    finally:
        server.shutdown()
        server.server_close()
    out = REPO / "testbed" / "results"
    out.mkdir(parents=True, exist_ok=True)
    with (out / "captures.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(captures[0].keys()))
        writer.writeheader()
        writer.writerows(captures)
    pred_fields = []
    for row in predictions:
        for key in row:
            if key not in pred_fields:
                pred_fields.append(key)
    with (out / "predictions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=pred_fields)
        writer.writeheader()
        writer.writerows(predictions)
    print(f"captures {len(captures)} predictions {len(predictions)}")


if __name__ == "__main__":
    main()
