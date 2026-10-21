"""Decompose heuristic version 1 scores. Does not change weights or the threshold."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "results"))

from detection.pipeline.artifacts import extract_dual_artifacts
from detection.pipeline.drift import compute_cross_view_drift
from detection.pipeline.fusion import fuse_risk_scores
from detection.pipeline.jargon import (
    _density,
    _distribution,
    _hit_counts,
    _js_divergence,
    _window,
    compute_jargon_asymmetry,
)
from detection.pipeline.promotion import compute_promotional_score

PAIRS = (("H1", "B1", "cross_profile"), ("H2", "B2", "cross_profile"), ("H1", "H2", "within_human"), ("B1", "B2", "within_bot"))
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


def tokens(window: str) -> int:
    return len(window.split()) if window else 0


def main() -> None:
    rows = []
    root = REPO / "testbed" / "live_captures"
    for family in FAMILIES:
        for scenario in SCENARIOS:
            html = {}
            for view in ("H1", "B1", "H2", "B2"):
                html[view] = (root / family / f"{scenario}_{view}.html").read_text(encoding="utf-8")
            for left, right, comparison in PAIRS:
                record = {
                    "url": f"http://127.0.0.1/{family}/{scenario}",
                    "url_id": "audit",
                    "human": {"html": html[left], "screenshot_path": None},
                    "bot": {"html": html[right], "screenshot_path": None},
                }
                arts = extract_dual_artifacts(record)
                drift = compute_cross_view_drift(arts, record)
                promo = compute_promotional_score(arts, record)
                jargon = compute_jargon_asymmetry(arts, record)
                fusion = fuse_risk_scores(drift, promo, url="", jargon=jargon)
                h_window = _window(
                    (arts["human"].get("text") or "") + " " + (arts["human"].get("title") or ""),
                    arts.get("human_links") or set(),
                )
                b_window = _window(
                    (arts["bot"].get("text") or "") + " " + (arts["bot"].get("title") or ""),
                    arts.get("bot_links") or set(),
                )
                h_hits = _hit_counts(h_window)
                b_hits = _hit_counts(b_window)
                jsd = _js_divergence(_distribution(h_hits), _distribution(b_hits))
                reconstructed = (
                    0.40 * drift["drift_score"]
                    + 0.35 * jargon["jargon_asymmetry_score"]
                    + 0.25 * promo["promo_score"]
                )
                rows.append({
                    "scenario_id": scenario,
                    "template_family": family,
                    "comparison_id": f"{family}:{scenario}:{left}-{right}",
                    "comparison": comparison,
                    "scoring_path": fusion["scoring_path"],
                    "model_probability": fusion["model_probability"],
                    "human_token_count": tokens(h_window),
                    "bot_token_count": tokens(b_window),
                    "human_keyword_hits": int(h_hits.sum()),
                    "bot_keyword_hits": int(b_hits.sum()),
                    "human_promo_density": _density(float(h_hits.sum()), h_window),
                    "bot_promo_density": _density(float(b_hits.sum()), b_window),
                    "signed_jargon_gap": jargon["jargon_signed_density_delta"],
                    "jargon_divergence": jsd,
                    "jargon_divergence_is_sqrt": False,
                    "drift_component": fusion["drift_contribution"],
                    "promo_component": fusion["promo_contribution"],
                    "jargon_component": fusion["jargon_contribution"],
                    "drift_score": drift["drift_score"],
                    "promo_score": promo["promo_score"],
                    "jargon_score": jargon["jargon_asymmetry_score"],
                    "final_score": fusion["final_risk_score"],
                    "reconstructed_fallback": reconstructed,
                    "reconstruction_error": abs(reconstructed - fusion["final_risk_score"]),
                    "threshold": fusion["alert_threshold"],
                    "verdict": "alert" if fusion["alert"] else "no_alert",
                    "weights_sum": sum(fusion["weights"].values()),
                })
    dest = REPO / "reports" / "score_path_audit.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    focus = next(row for row in rows if row["comparison_id"].endswith("north_market:selective_promotional_injection:H1-B1") or row["comparison_id"] == "north_market:selective_promotional_injection:H1-B1")
    print(dest)
    print("selective", focus["final_score"], "error", focus["reconstruction_error"], "path", focus["scoring_path"])


if __name__ == "__main__":
    main()
