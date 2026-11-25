"""Score captured pages for review without taking action on client traffic."""

from detection.pipeline.artifacts import extract_dual_artifacts
from detection.pipeline.drift import compute_cross_view_drift
from detection.pipeline.fusion import fuse_risk_scores
from detection.pipeline.jargon import compute_jargon_asymmetry
from detection.pipeline.promotion import compute_promotional_score


def score_capture(capture):
    for profile in ("human", "bot"):
        view = capture[profile]
        if view.get("status") != 200 or not view.get("html", "").strip():
            raise ValueError(f"Missing successful {profile} capture")

    artifacts = extract_dual_artifacts(capture)
    drift = compute_cross_view_drift(artifacts, capture)
    promo = compute_promotional_score(artifacts, capture)
    jargon = compute_jargon_asymmetry(artifacts, capture)
    fusion = fuse_risk_scores(drift, promo, url=capture["url"], jargon=jargon)
    return drift, promo, jargon, fusion
