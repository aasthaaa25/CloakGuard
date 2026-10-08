"""
Stage 6 — Multimodal Fusion
Fuses URL-lexical + drift + promotion + jargon modalities into a single
risk score and alert decision.  Uses the trained model when available;
falls back to a heuristic weighted sum.
"""

import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

_ALERT_THRESHOLD         = 0.50
_HIGH_CONFIDENCE_THRESHOLD = 0.75

try:
    from app.config import ALERT_THRESHOLD, HIGH_CONFIDENCE_THRESHOLD
    _ALERT_THRESHOLD          = ALERT_THRESHOLD
    _HIGH_CONFIDENCE_THRESHOLD = HIGH_CONFIDENCE_THRESHOLD
except Exception:
    pass


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

    Weights (when model is available):
        url_model  35%  (trained on 160k URLs)
        drift      25%  (html/dom/text/visual divergence)
        jargon     25%  (jargon asymmetry — the cloaking fingerprint)
        promo      15%  (promotional keyword presence)

    Weights (heuristic fallback):
        drift      40%
        jargon     35%
        promo      25%
    """
    drift_score  = float(drift.get("drift_score",  0.0))
    promo_score  = float(promo.get("promo_score",  0.0))
    jargon_score = float((jargon or {}).get("jargon_asymmetry_score", 0.0))

    model_bundle = _load_model()
    model_prob   = _url_probability(url, model_bundle) if model_bundle and url else 0.0

    if model_bundle and model_prob > 0:
        final_score = min(1.0, (
            0.35 * model_prob +
            0.25 * drift_score +
            0.25 * jargon_score +
            0.15 * promo_score
        ))
    else:
        final_score = min(1.0, (
            0.40 * drift_score +
            0.35 * jargon_score +
            0.25 * promo_score
        ))

    alert = bool(final_score >= _ALERT_THRESHOLD)

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
        "alert":                     alert,
        "flagged_vectors":           flagged_vectors,
        "model_probability":         model_prob,
        "drift_contribution":        0.25 * drift_score if model_bundle else 0.40 * drift_score,
        "jargon_contribution":       0.25 * jargon_score if model_bundle else 0.35 * jargon_score,
        "promo_contribution":        0.15 * promo_score if model_bundle else 0.25 * promo_score,
        "url_model_contribution":    0.35 * model_prob if model_bundle else 0.0,
        "high_confidence":           bool(final_score >= _HIGH_CONFIDENCE_THRESHOLD),
    }
