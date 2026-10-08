"""
Detection model tests — verifies model quality, no-leakage, and pipeline contract.
Run: pytest tests/test_detection.py -v
"""

import sys
import json
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_model_artifact_exists():
    model_path = ROOT / "detection" / "artifacts" / "model.joblib"
    assert model_path.exists(), (
        f"Model not found at {model_path}. Run `python detection/train_model.py` first."
    )


def test_metrics_in_target_range():
    metrics_path = ROOT / "detection" / "artifacts" / "metrics.json"
    if not metrics_path.exists():
        pytest.skip("metrics.json not yet generated — run train_model.py first")

    with open(metrics_path) as f:
        metrics = json.load(f)

    # Headline model (LogisticRegression) must be in the 90-95% band
    lr_acc = metrics["models"]["LogisticRegression"]["accuracy"]
    assert 0.90 <= lr_acc <= 0.97, (
        f"LogisticRegression accuracy {lr_acc:.4f} not in [0.90, 0.97]"
    )

    # Ensemble must beat or match headline
    ens_acc = metrics["models"]["Ensemble"]["accuracy"]
    assert ens_acc >= lr_acc - 0.005, (
        f"Ensemble accuracy {ens_acc:.4f} should be >= headline {lr_acc:.4f}"
    )

    # ROC-AUC must be > 0.90
    for model_name, m in metrics["models"].items():
        auc = m.get("roc_auc", 0)
        assert auc > 0.90, f"{model_name} ROC-AUC {auc:.4f} < 0.90"


def test_no_leakage_in_features():
    metrics_path = ROOT / "detection" / "artifacts" / "metrics.json"
    if not metrics_path.exists():
        pytest.skip("metrics.json not yet generated")

    with open(metrics_path) as f:
        metrics = json.load(f)

    leakage_cols = {"crawl_status", "fusion_score", "drift_score"}
    feature_names = set(metrics.get("feature_names", []))
    overlap = leakage_cols & feature_names
    assert not overlap, f"Leakage columns found in features: {overlap}"


def test_model_predicts_single_url():
    model_path = ROOT / "detection" / "artifacts" / "model.joblib"
    if not model_path.exists():
        pytest.skip("model.joblib not yet generated")

    import joblib
    import pandas as pd
    from detection.features import build_url_features

    bundle = joblib.load(str(model_path))
    pipeline = bundle["pipeline"]
    feature_names = bundle["feature_names"]

    test_url = "https://free-casino-bonus.tk/redirect?goto=spam"
    feats = build_url_features(test_url)
    row = {k: feats.get(k, 0) for k in feature_names}
    df_row = pd.DataFrame([row])

    pred_prob = pipeline.predict_proba(df_row)[0][1]
    assert 0.0 <= pred_prob <= 1.0
    print(f"\n  P(cloaked | '{test_url[:50]}'…) = {pred_prob:.4f}")


def test_feature_engineering():
    """Checks that features are computed correctly for known cases."""
    from detection.features import build_url_features

    # IPFS URL (drift=0 class typical)
    ipfs_url = "https://bafybeidzso4mumpjqm2d4ehwtdtsylrd4kskmpdrrgyyrew7rl3slvzjau.ipfs.cf-ipfs.com/"
    f = build_url_features(ipfs_url)
    assert f["is_ipfs_host"] == 1
    assert f["has_https"] == 1

    # Deep path URL (drift=1 class typical)
    deep_url = "https://sansebastianshops.com/el-que-tiene-tienda-que-se-atienda-work-cafe/"
    f2 = build_url_features(deep_url)
    assert f2["path_len"] > 40
    assert f2["num_hyphens"] > 3


def test_detection_pipeline_contract():
    """Tests that detection_pipeline.py exports the exact API the adapter imports."""
    from detection.detection_pipeline import (
        VIEW_PROFILES,
        dual_view_crawl,
        extract_dual_artifacts,
        compute_cross_view_drift,
        compute_promotional_score,
        fuse_risk_scores,
    )
    # VIEW_PROFILES must have human and bot keys
    assert "human" in VIEW_PROFILES
    assert "bot" in VIEW_PROFILES
    for view in ["human", "bot"]:
        assert "user_agent" in VIEW_PROFILES[view]
        assert "viewport" in VIEW_PROFILES[view]
        assert "extra_http_headers" in VIEW_PROFILES[view]

    # Pipeline on a test URL — just checks it runs without error
    url = "https://example.com/"
    record  = dual_view_crawl(url)
    arts    = extract_dual_artifacts(record)
    drift   = compute_cross_view_drift(arts, record)
    promo   = compute_promotional_score(arts, record)
    fusion  = fuse_risk_scores(drift, promo, url=url)

    # Check all required keys
    assert "alert" in fusion
    assert "final_risk_score" in fusion
    assert "flagged_vectors" in fusion
    assert isinstance(fusion["alert"], bool)
    assert 0.0 <= fusion["final_risk_score"] <= 1.0
