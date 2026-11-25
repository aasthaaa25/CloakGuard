"""
Local walk-through of one authorized fixture.

Does not fetch a remote URL. Writes evaluation/outputs/demo_trace.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "results"))

from app.pipeline_bridge.adapter import score_capture


HUMAN = """
<html><head><title>North Market</title></head>
<body><h1>North Market</h1><p>Today's produce list.</p>
<a href="https://north.example/about">About</a></body></html>
"""

BOT = """
<html><head><title>North Market casino bonus</title></head>
<body><h1>North Market</h1><p>Today's produce list.</p>
<div style="display:none">
free casino jackpot poker slots viagra cialis pharmacy
</div></body></html>
"""


def _run(html_h: str, html_b: str, url: str) -> dict:
    record = {
        "url": url,
        "url_id": "demo-local",
        "human": {"status": 200, "html": html_h, "screenshot_path": None},
        "bot": {"status": 200, "html": html_b, "screenshot_path": None},
        "profile": "local fixture, not a network capture",
    }
    drift, promo, jargon, fusion = score_capture(record)
    return {
        "drift_score": drift["drift_score"],
        "visual_used": drift.get("have_visual", False),
        "promo_score": promo["promo_score"],
        "promo_categories": sorted((promo.get("keyword_categories_found") or {}).keys()),
        "jargon_alternatives": jargon["alternatives"],
        "jsd_definition": jargon["jsd_definition"],
        "jsd_log_base": jargon["jsd_log_base"],
        "final_risk_score": fusion["final_risk_score"],
        "score_is_probability": fusion["score_is_probability"],
        "scoring_path": fusion["scoring_path"],
        "alert_threshold": fusion["alert_threshold"],
        "alert": fusion["alert"],
        "response": "Evidence only. Owner-side controls run separately in the policy harness.",
    }


def main() -> None:
    injected = _run(HUMAN, BOT, "https://north.example/produce")
    same = _run(HUMAN, HUMAN, "https://north.example/produce")
    out = {
        "target": "https://north.example/produce",
        "authorization": "synthetic local HTML only; no remote host was contacted",
        "configuration": "heuristic fusion, threshold 0.50, weights as coded in fusion.py",
        "identical_views": same,
        "bot_injected_keywords": injected,
        "interpretation": (
            "The injected fixture scores higher than the identical-view fixture. "
            "That checks the pipeline. It is not a measurement of real cloaking."
        ),
    }
    dest = REPO / "evaluation" / "outputs" / "demo_trace.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(dest)
    print(json.dumps({
        "identical_score": same["final_risk_score"],
        "injected_score": injected["final_risk_score"],
        "path": injected["scoring_path"],
        "injected_alert": injected["alert"],
    }, indent=2))


if __name__ == "__main__":
    main()
