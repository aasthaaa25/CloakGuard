"""
Stage 6 — Multimodal Fusion
Fuses URL-lexical + drift + promotion + jargon modalities into a single
risk score and alert decision.  Uses the trained model when available;
falls back to a heuristic weighted sum.
"""

import os
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

_REVIEW_THRESHOLD        = float(os.getenv("REVIEW_THRESHOLD", "0.270"))
_ALERT_THRESHOLD         = 0.50
_HIGH_CONFIDENCE_THRESHOLD = 0.75

try:
    from app.config import ALERT_THRESHOLD, HIGH_CONFIDENCE_THRESHOLD, REVIEW_THRESHOLD
    _REVIEW_THRESHOLD         = REVIEW_THRESHOLD
    _ALERT_THRESHOLD          = ALERT_THRESHOLD
    _HIGH_CONFIDENCE_THRESHOLD = HIGH_CONFIDENCE_THRESHOLD
except Exception:
    pass


if not 0 <= _REVIEW_THRESHOLD <= _ALERT_THRESHOLD:
    raise ValueError("REVIEW_THRESHOLD must be between 0 and ALERT_THRESHOLD")


def _load_model():
    try:
        import joblib
        model_path = ROOT / "detection" / "artifacts" / "model.joblib"
        if model_path.exists():
            return joblib.load(str(model_path))
    except Exception:
        pass
    return None


def _url_probability(url: str, model_bundle) -> float:
    """Get the URL-lexical model's probability for a URL."""
    try:
        import pandas as pd
        from detection.features import build_url_features
        feats = build_url_features(url)
        feature_names = model_bundle["feature_names"]
        row = {k: feats.get(k, 0) for k in feature_names}
        return float(model_bundle["pipeline"].predict_proba(
            pd.DataFrame([row])
        )[0][1])
    except Exception:
        return 0.0


def fuse_risk_scores(drift: dict, promo: dict, url: str = "",
                     jargon: Optional[dict] = None) -> dict:
    """
    Stage 6 entry point.
    Combines all modality signals into final_risk_score + alert.

    This function is the operational heuristic scorer. It is not the trained
    multimodal ensemble in detection/train_multimodal.py. Those are different
    scoring paths.

    url_model_assisted_heuristic, used only when a Phase-1 URL model loads
    and returns a positive score:
        url_model  0.35
        drift      0.25
        jargon     0.25
        promo      0.15

    fixed_weight_heuristic, used otherwise:
        drift      0.40
        jargon     0.35
        promo      0.25

    The weights are fixed constants. They were not selected on a held-out
    cloaking test. final_risk_score is an uncalibrated score in [0, 1], not
    a probability. The alert threshold is ALERT_THRESHOLD (default 0.50) on
    this same score. A 0.05 cutoff is not an operating threshold of this path.
    """
    drift_score  = float(drift.get("drift_score",  0.0))
    promo_score  = float(promo.get("promo_score",  0.0))
    jargon_score = float((jargon or {}).get("jargon_asymmetry_score", 0.0))

    model_bundle = _load_model()
    model_prob   = _url_probability(url, model_bundle) if model_bundle and url else 0.0
    assisted = bool(model_bundle and model_prob > 0)

    if assisted:
        scoring_path = "url_model_assisted_heuristic"
        weights = {"url_model": 0.35, "drift": 0.25, "jargon": 0.25, "promo": 0.15}
        final_score = min(1.0, (
            weights["url_model"] * model_prob +
            weights["drift"] * drift_score +
            weights["jargon"] * jargon_score +
            weights["promo"] * promo_score
        ))
    else:
        scoring_path = "fixed_weight_heuristic"
        weights = {"url_model": 0.0, "drift": 0.40, "jargon": 0.35, "promo": 0.25}
        final_score = min(1.0, (
            weights["drift"] * drift_score +
            weights["jargon"] * jargon_score +
            weights["promo"] * promo_score
        ))

    alert = bool(final_score >= _ALERT_THRESHOLD)
    review_threshold = _ALERT_THRESHOLD if assisted else _REVIEW_THRESHOLD

    flagged_vectors = []
    if drift_score > 0.30:
        flagged_vectors.append({
            "type": "content_drift",
            "score": drift_score,
            "detail": (
                f"DOM drift={drift.get('dom_drift',0):.3f} "
                f"text_drift={drift.get('text_drift',0):.3f} "
                f"visual_ssim={drift.get('visual_ssim',1):.3f}"
            ),
        })
    if jargon_score > 0.10:
        flagged_vectors.append({
            "type": "jargon_asymmetry",
            "score": jargon_score,
            "detail": (
                f"bot_mass={jargon.get('jargon_mass_bot',0):.3f} "
                f"human_mass={jargon.get('jargon_mass_human',0):.3f} "
                f"delta={jargon.get('jargon_mass_delta',0):.3f} "
                f"dominant={jargon.get('dominant_jargon_category','none')}"
            ),
        })
    if promo_score > 0.25:
        cats = list((promo.get("keyword_categories_found") or {}).keys())
        flagged_vectors.append({
            "type": "promotional_content",
            "score": promo_score,
            "detail": f"Categories: {cats}",
        })
    if model_prob > 0.50:
        flagged_vectors.append({
            "type": "url_lexical_risk",
            "score": model_prob,
            "detail": f"URL-lexical model probability={model_prob:.3f}",
        })

    return {
        "final_risk_score":          final_score,
        "score_is_probability":      False,
        "scoring_path":              scoring_path,
        "weights":                   weights,
        "alert_threshold":           _ALERT_THRESHOLD,
        "alert":                     alert,
        "review_threshold":          review_threshold,
        "review_alert":              bool(final_score >= review_threshold),
        "flagged_vectors":           flagged_vectors,
        "model_probability":         model_prob,
        "drift_contribution":        weights["drift"] * drift_score,
        "jargon_contribution":       weights["jargon"] * jargon_score,
        "promo_contribution":        weights["promo"] * promo_score,
        "url_model_contribution":    weights["url_model"] * model_prob,
        "high_confidence":           bool(final_score >= _HIGH_CONFIDENCE_THRESHOLD),
        "trained_multimodal_ensemble_used": False,
    }
