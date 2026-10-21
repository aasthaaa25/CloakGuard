"""Arithmetic checks for the fixed-weight heuristic. No threshold is fitted here."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from detection.pipeline.artifacts import extract_dual_artifacts
from detection.pipeline.drift import compute_cross_view_drift
from detection.pipeline.fusion import fuse_risk_scores
from detection.pipeline.jargon import compute_jargon_asymmetry
from detection.pipeline.promotion import compute_promotional_score


def _score(human: str, bot: str) -> dict:
    record = {
        "url": "https://example.test/page",
        "url_id": "arith",
        "human": {"html": human, "screenshot_path": None},
        "bot": {"html": bot, "screenshot_path": None},
    }
    arts = extract_dual_artifacts(record)
    drift = compute_cross_view_drift(arts, record)
    promo = compute_promotional_score(arts, record)
    jargon = compute_jargon_asymmetry(arts, record)
    fusion = fuse_risk_scores(drift, promo, url="", jargon=jargon)
    return {"drift": drift, "promo": promo, "jargon": jargon, "fusion": fusion}


def test_missing_url_uses_fallback_not_zero_filled_assisted_path():
    page = "<html><head><title>North</title></head><body><p>Today's produce list.</p></body></html>"
    fusion = _score(page, page)["fusion"]
    assert fusion["scoring_path"] == "fixed_weight_heuristic"
    assert fusion["model_probability"] == 0.0
    assert fusion["weights"] == {"url_model": 0.0, "drift": 0.40, "jargon": 0.35, "promo": 0.25}
    assert abs(sum(fusion["weights"].values()) - 1.0) < 1e-9


def test_all_zero_components_score_zero():
    page = "<html><head><title>Same</title></head><body><p>Same sentence.</p></body></html>"
    fusion = _score(page, page)["fusion"]
    assert fusion["final_risk_score"] == 0.0
    assert fusion["alert"] is False


def test_reconstruction_matches_fallback_equation():
    human = "<html><head><title>Market</title></head><body><p>Produce list.</p></body></html>"
    bot = "<html><head><title>Market</title></head><body><p>Produce list. casino poker viagra</p></body></html>"
    scored = _score(human, bot)
    fusion = scored["fusion"]
    reconstructed = (
        0.40 * scored["drift"]["drift_score"]
        + 0.35 * scored["jargon"]["jargon_asymmetry_score"]
        + 0.25 * scored["promo"]["promo_score"]
    )
    assert abs(reconstructed - fusion["final_risk_score"]) < 1e-9
    assert fusion["jargon_contribution"] == 0.35 * scored["jargon"]["jargon_asymmetry_score"]


def test_one_component_can_be_nonzero_while_others_are_zero():
    human = "<html><head><title>Clock</title></head><body><p>Counter 1</p></body></html>"
    bot = "<html><head><title>Clock</title></head><body><p>Counter 2</p></body></html>"
    scored = _score(human, bot)
    assert scored["drift"]["drift_score"] > 0
    assert scored["promo"]["promo_score"] == 0
    assert scored["jargon"]["jargon_asymmetry_score"] == 0


def test_empty_one_view_and_both_views():
    page = "<html><head><title>Market</title></head><body><p>casino</p></body></html>"
    one = _score("", page)
    assert one["fusion"]["final_risk_score"] > 0
    both = _score("", "")
    assert both["jargon"]["jargon_jsd"] == 0
    assert both["fusion"]["scoring_path"] == "fixed_weight_heuristic"


def test_reversed_inputs_change_the_signed_gap():
    clean = "<html><head><title>Market</title></head><body><p>Produce list.</p></body></html>"
    injected = "<html><head><title>Market</title></head><body><p>Produce list. casino poker viagra</p></body></html>"
    bot_side = _score(clean, injected)["jargon"]["jargon_signed_density_delta"]
    human_side = _score(injected, clean)["jargon"]["jargon_signed_density_delta"]
    assert bot_side > 0
    assert human_side < 0
    assert abs(bot_side + human_side) < 1e-9


def test_jargon_value_is_divergence_not_square_root():
    clean = "<html><head><title>Market</title></head><body><p>Produce list.</p></body></html>"
    injected = "<html><head><title>Market</title></head><body><p>casino</p></body></html>"
    jargon = _score(clean, injected)["jargon"]
    assert jargon["jsd_definition"] == "jensen_shannon_divergence_bits"
    assert jargon["jargon_jsd"] == 1.0
