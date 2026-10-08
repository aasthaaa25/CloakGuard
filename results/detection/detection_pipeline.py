"""
Detection Pipeline — Public API Contract.

This module exposes the exact interface that app/pipeline_bridge/adapter.py and
app/forensics/deep_scan.py import:

    from detection_pipeline import (
        VIEW_PROFILES, dual_view_crawl, extract_dual_artifacts,
        compute_cross_view_drift, compute_promotional_score, fuse_risk_scores,
    )

Phase 2: All implementations now delegate to the real detection.pipeline package
(detection/pipeline/*.py) which runs the full multimodal pipeline.
Playwright is optional — httpx/requests fallback is used automatically.
"""

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT))

# ── Real pipeline implementations ─────────────────────────────────────────────
from detection.pipeline.crawl     import dual_view_crawl, VIEW_PROFILES
from detection.pipeline.artifacts import extract_dual_artifacts
from detection.pipeline.drift     import compute_cross_view_drift
from detection.pipeline.promotion import compute_promotional_score
from detection.pipeline.jargon    import compute_jargon_asymmetry
from detection.pipeline.fusion    import fuse_risk_scores

# Alert threshold (importable by deep_scan.py etc.)
_ALERT_THRESHOLD = 0.50
try:
    from app.config import ALERT_THRESHOLD as _ALERT_THRESHOLD
except Exception:
    pass

__all__ = [
    "VIEW_PROFILES",
    "dual_view_crawl",
    "extract_dual_artifacts",
    "compute_cross_view_drift",
    "compute_promotional_score",
    "compute_jargon_asymmetry",
    "fuse_risk_scores",
    "_ALERT_THRESHOLD",
]

if __name__ == "__main__":
    print("Testing detection_pipeline.py (real multimodal pipeline) …")
    test_urls = [
        "https://www.google.com/",
        "https://free-casino-bonus.tk/redirect?goto=http://pills.cc",
    ]
    for url in test_urls:
        record  = dual_view_crawl(url)
        arts    = extract_dual_artifacts(record)
        drift   = compute_cross_view_drift(arts, record)
        promo   = compute_promotional_score(arts, record)
        jargon  = compute_jargon_asymmetry(arts, record)
        fusion  = fuse_risk_scores(drift, promo, url=url, jargon=jargon)
        print(f"\nURL: {url[:60]}")
        print(f"  model_prob={fusion['model_probability']:.3f} "
              f" final_risk={fusion['final_risk_score']:.3f} "
              f" alert={fusion['alert']}")
