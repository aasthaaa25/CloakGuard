"""Require repeated cross-profile evidence above measured same-profile variation."""

from hashlib import sha256
from math import isfinite

from app.config import ALERT_THRESHOLD
from app.pipeline_bridge.adapter import score_capture

VIEW_IDS = ("H1", "B1", "H2", "B2")


def review_repeats(url, views, *, threshold=ALERT_THRESHOLD):
    """Compare two cross-profile pairs and both directions of each control."""
    if not isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("Review threshold must be finite and in [0, 1]")
    invalid = []
    for name in VIEW_IDS:
        view = views.get(name, {})
        media_type = view.get("content_type", "text/html").split(";", 1)[0].strip().lower()
        if (view.get("status") != 200 or not view.get("html", "").strip()
                or media_type not in {"text/html", "application/xhtml+xml"}
                or view.get("final_url", url) != url):
            invalid.append(name)
    if invalid:
        return {"verdict": "incomplete", "alert": False, "threshold": threshold, "invalid_views": invalid}

    def compare(left, right):
        record = {"url": url, "human": views[left], "bot": views[right]}
        return score_capture(record, use_url_model=False)

    first = compare("H1", "B1")
    second = compare("H2", "B2")
    cross = [first[3]["final_risk_score"], second[3]["final_risk_score"]]
    controls = {
        f"{left}/{right}": max(compare(left, right)[3]["final_risk_score"],
                               compare(right, left)[3]["final_risk_score"])
        for left, right in (("H1", "H2"), ("B1", "B2"))
    }
    cross_floor = min(cross)
    control_ceiling = max(controls.values())
    if max(cross) < threshold:
        verdict = "below_threshold"
    elif cross_floor < threshold:
        verdict = "inconsistent_cross_profile"
    elif cross_floor <= control_ceiling:
        verdict = "variation_explains_signal"
    else:
        verdict = "repeated_profile_difference"

    return {
        "verdict": verdict, "alert": verdict == "repeated_profile_difference",
        "threshold": threshold, "cross_profile_scores": cross, "same_profile_scores": controls,
        "score_excess_over_controls": cross_floor - control_ceiling,
        "captures": {
            name: {"status": views[name]["status"],
                   "sha256_utf8_html": sha256(views[name]["html"].encode("utf-8")).hexdigest()}
            for name in VIEW_IDS
        },
        "score_is_probability": False,
        "first_pair": first,
    }
