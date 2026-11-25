import pytest

from app.pipeline_bridge import repeat_review


@pytest.mark.parametrize(
    ("cross", "reverse_control", "verdict"),
    [
        ((0.6, 0.7), 0.1, "repeated_profile_difference"),
        ((0.6, 0.1), 0.1, "inconsistent_cross_profile"),
        ((0.6, 0.7), 0.6, "variation_explains_signal"),
        ((0.1, 0.2), 0.1, "below_threshold"),
    ],
)
def test_repeat_gate_uses_both_pairs_and_controls(monkeypatch, cross, reverse_control, verdict):
    def score(capture, *, use_url_model):
        assert not use_url_model
        pair = (capture["human"]["html"], capture["bot"]["html"])
        scores = {("H1", "B1"): cross[0], ("H2", "B2"): cross[1], ("H2", "H1"): reverse_control}
        return None, None, None, {"final_risk_score": scores.get(pair, 0)}

    monkeypatch.setattr(repeat_review, "score_capture", score)
    views = {name: {"html": name, "status": 200} for name in repeat_review.VIEW_IDS}
    result = repeat_review.review_repeats("http://example.test", views)
    assert result["verdict"] == verdict
    assert result["alert"] == (verdict == "repeated_profile_difference")
    assert result["same_profile_scores"]["H1/H2"] == reverse_control
    assert all(len(item["sha256_utf8_html"]) == 64 for item in result["captures"].values())


@pytest.mark.parametrize("invalid_view", [None, {"content_type": "application/json"},
                                          {"final_url": "http://example.test/redirected"}])
def test_incomparable_repeat_abstains_without_scoring(monkeypatch, invalid_view):
    def unexpected(*args, **kwargs):
        pytest.fail("Incomplete views must not be scored")

    monkeypatch.setattr(repeat_review, "score_capture", unexpected)
    views = {name: {"html": "sample", "status": 200} for name in ("H1", "B1", "H2")}
    if invalid_view is not None:
        views["B2"] = {"html": "sample", "status": 200, **invalid_view}
    result = repeat_review.review_repeats("http://example.test", views)
    assert result["verdict"] == "incomplete"
    assert result["invalid_views"] == ["B2"]
    assert result["alert"] is False
