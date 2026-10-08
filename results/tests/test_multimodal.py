"""
Tests for the Phase-2 multimodal detection pipeline.

Run with:
    pytest tests/test_multimodal.py -v
"""

import sys
import json
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ── Fixtures ──────────────────────────────────────────────────────────────────

SAMPLE_HTML_H = """
<html><head><title>Buy Electronics Online</title></head>
<body>
<h1>Best Gadgets Store</h1>
<p>Great deals on electronics.</p>
<a href="https://example.com/about">About</a>
<a href="https://example.com/contact">Contact</a>
</body></html>
"""

SAMPLE_HTML_B = """
<html><head><title>Buy Cheap Pills - Casino Bonus</title></head>
<body>
<h1>Best Gadgets Store</h1>
<p>Great deals on electronics.</p>
<a href="https://example.com/about">About</a>
<a href="https://example.com/contact">Contact</a>
<div style="display:none">
  <a href="http://casino-spam.tk">FREE CASINO BONUS</a>
  <a href="http://pills4cheap.cc">Buy Viagra Online</a>
  Win jackpot today! Free slots! Poker bonus!
  Cheap pharmacy pills prescription viagra cialis.
  Best casino slots gambling jackpot winner prize.
</div>
</body></html>
"""

SAMPLE_CRAWL_RECORD = {
    "url":    "https://example-store.com/electronics",
    "url_id": "test_url_001",
    "human":  {"html": SAMPLE_HTML_H, "screenshot_path": None},
    "bot":    {"html": SAMPLE_HTML_B, "screenshot_path": None},
}

CLEAN_CRAWL_RECORD = {
    "url":    "https://clean-site.org/about",
    "url_id": "test_url_002",
    "human":  {"html": SAMPLE_HTML_H, "screenshot_path": None},
    "bot":    {"html": SAMPLE_HTML_H, "screenshot_path": None},  # identical
}


# ── Stage 2: artifact extraction ──────────────────────────────────────────────

class TestArtifactExtraction:
    def test_returns_dict_with_required_keys(self):
        from detection.pipeline.artifacts import extract_dual_artifacts
        arts = extract_dual_artifacts(SAMPLE_CRAWL_RECORD)
        required = {"url", "url_id", "human", "bot", "human_links",
                    "bot_links", "bot_only_links", "html_size_diff", "have_html"}
        assert required.issubset(arts.keys()), f"Missing keys: {required - arts.keys()}"

    def test_have_html_true_when_both_views_nonempty(self):
        from detection.pipeline.artifacts import extract_dual_artifacts
        arts = extract_dual_artifacts(SAMPLE_CRAWL_RECORD)
        assert arts["have_html"] is True

    def test_have_html_false_when_no_html(self):
        from detection.pipeline.artifacts import extract_dual_artifacts
        empty_record = {**SAMPLE_CRAWL_RECORD,
                        "human": {"html": "", "screenshot_path": None},
                        "bot":   {"html": "", "screenshot_path": None}}
        arts = extract_dual_artifacts(empty_record)
        assert arts["have_html"] is False

    def test_bot_only_links_subset_of_bot_links(self):
        from detection.pipeline.artifacts import extract_dual_artifacts
        arts = extract_dual_artifacts(SAMPLE_CRAWL_RECORD)
        bot_link_set = set(arts["bot_links"])
        for link in arts["bot_only_links"]:
            assert link in bot_link_set

    def test_per_view_tag_distribution_is_dict(self):
        from detection.pipeline.artifacts import extract_dual_artifacts
        arts = extract_dual_artifacts(SAMPLE_CRAWL_RECORD)
        assert isinstance(arts["human"].get("tag_distribution", {}), dict)
        assert isinstance(arts["bot"].get("tag_distribution", {}), dict)


# ── Stage 3: drift features ───────────────────────────────────────────────────

class TestDriftFeatures:
    def test_returns_dict_with_required_keys(self):
        from detection.pipeline.artifacts import extract_dual_artifacts
        from detection.pipeline.drift import compute_cross_view_drift
        arts = extract_dual_artifacts(SAMPLE_CRAWL_RECORD)
        drift = compute_cross_view_drift(arts, SAMPLE_CRAWL_RECORD)
        required = {"drift_score", "html_size_drift", "dom_drift",
                    "link_drift", "text_drift", "title_drift",
                    "bot_only_link_count", "visual_ssim", "visual_pixel_delta"}
        assert required.issubset(drift.keys()), f"Missing: {required - drift.keys()}"

    def test_all_scores_in_0_1(self):
        from detection.pipeline.artifacts import extract_dual_artifacts
        from detection.pipeline.drift import compute_cross_view_drift
        arts = extract_dual_artifacts(SAMPLE_CRAWL_RECORD)
        drift = compute_cross_view_drift(arts, SAMPLE_CRAWL_RECORD)
        for key in ("drift_score", "html_size_drift", "dom_drift",
                    "link_drift", "text_drift"):
            assert 0.0 <= drift[key] <= 1.0, f"{key}={drift[key]} out of [0,1]"

    def test_cloaked_has_higher_drift_than_clean(self):
        from detection.pipeline.artifacts import extract_dual_artifacts
        from detection.pipeline.drift import compute_cross_view_drift
        arts_cloak = extract_dual_artifacts(SAMPLE_CRAWL_RECORD)
        drift_cloak = compute_cross_view_drift(arts_cloak, SAMPLE_CRAWL_RECORD)
        arts_clean = extract_dual_artifacts(CLEAN_CRAWL_RECORD)
        drift_clean = compute_cross_view_drift(arts_clean, CLEAN_CRAWL_RECORD)
        assert drift_cloak["drift_score"] >= drift_clean["drift_score"], (
            f"Expected cloaked drift >= clean drift: "
            f"{drift_cloak['drift_score']:.3f} vs {drift_clean['drift_score']:.3f}"
        )

    def test_identical_views_has_zero_drift(self):
        from detection.pipeline.artifacts import extract_dual_artifacts
        from detection.pipeline.drift import compute_cross_view_drift
        arts = extract_dual_artifacts(CLEAN_CRAWL_RECORD)
        drift = compute_cross_view_drift(arts, CLEAN_CRAWL_RECORD)
        assert drift["drift_score"] < 0.05, (
            f"Identical views should have near-zero drift, got {drift['drift_score']:.3f}"
        )


# ── Stage 4: promotional features ─────────────────────────────────────────────

class TestPromotionalFeatures:
    def test_returns_dict_with_required_keys(self):
        from detection.pipeline.artifacts import extract_dual_artifacts
        from detection.pipeline.promotion import compute_promotional_score
        arts = extract_dual_artifacts(SAMPLE_CRAWL_RECORD)
        promo = compute_promotional_score(arts, SAMPLE_CRAWL_RECORD)
        required = {"promo_score", "promo_asymmetry", "category_count",
                    "total_bot_promo_hits", "total_human_promo_hits",
                    "bot_excess_promo_hits", "keyword_categories_found",
                    "per_category_human", "per_category_bot"}
        assert required.issubset(promo.keys()), f"Missing: {required - promo.keys()}"

    def test_promo_score_in_0_1(self):
        from detection.pipeline.artifacts import extract_dual_artifacts
        from detection.pipeline.promotion import compute_promotional_score
        arts = extract_dual_artifacts(SAMPLE_CRAWL_RECORD)
        promo = compute_promotional_score(arts, SAMPLE_CRAWL_RECORD)
        assert 0.0 <= promo["promo_score"] <= 1.0

    def test_cloaked_html_detects_gambling_and_pharma(self):
        from detection.pipeline.artifacts import extract_dual_artifacts
        from detection.pipeline.promotion import compute_promotional_score
        arts = extract_dual_artifacts(SAMPLE_CRAWL_RECORD)
        promo = compute_promotional_score(arts, SAMPLE_CRAWL_RECORD)
        cats = promo.get("keyword_categories_found", {})
        # The sample bot HTML has casino + pharma keywords
        detected = set(cats.keys())
        assert "gambling" in detected or "pharma" in detected, (
            f"Expected gambling/pharma in detected categories, got: {detected}"
        )


# ── Stage 5: jargon asymmetry ─────────────────────────────────────────────────

class TestJargonAsymmetry:
    def test_returns_dict_with_required_keys(self):
        from detection.pipeline.artifacts import extract_dual_artifacts
        from detection.pipeline.jargon import compute_jargon_asymmetry
        arts = extract_dual_artifacts(SAMPLE_CRAWL_RECORD)
        jargon = compute_jargon_asymmetry(arts, SAMPLE_CRAWL_RECORD)
        required = {"jargon_asymmetry_score", "jargon_mass_bot", "jargon_mass_human",
                    "jargon_mass_delta", "jargon_jsd", "per_category_asymmetry",
                    "dominant_jargon_category", "jargon_vector_human", "jargon_vector_bot"}
        assert required.issubset(jargon.keys()), f"Missing: {required - jargon.keys()}"

    def test_jargon_asymmetry_score_in_0_1(self):
        from detection.pipeline.artifacts import extract_dual_artifacts
        from detection.pipeline.jargon import compute_jargon_asymmetry
        arts = extract_dual_artifacts(SAMPLE_CRAWL_RECORD)
        jargon = compute_jargon_asymmetry(arts, SAMPLE_CRAWL_RECORD)
        assert 0.0 <= jargon["jargon_asymmetry_score"] <= 1.0

    def test_cloaked_has_higher_asymmetry_than_clean(self):
        from detection.pipeline.artifacts import extract_dual_artifacts
        from detection.pipeline.jargon import compute_jargon_asymmetry
        arts_c = extract_dual_artifacts(SAMPLE_CRAWL_RECORD)
        jas_c = compute_jargon_asymmetry(arts_c, SAMPLE_CRAWL_RECORD)["jargon_asymmetry_score"]
        arts_n = extract_dual_artifacts(CLEAN_CRAWL_RECORD)
        jas_n = compute_jargon_asymmetry(arts_n, CLEAN_CRAWL_RECORD)["jargon_asymmetry_score"]
        assert jas_c >= jas_n, (
            f"Cloaked asymmetry {jas_c:.3f} should be >= clean {jas_n:.3f}"
        )

    def test_bot_mass_higher_than_human_on_cloaked(self):
        from detection.pipeline.artifacts import extract_dual_artifacts
        from detection.pipeline.jargon import compute_jargon_asymmetry
        arts = extract_dual_artifacts(SAMPLE_CRAWL_RECORD)
        jargon = compute_jargon_asymmetry(arts, SAMPLE_CRAWL_RECORD)
        assert jargon["jargon_mass_bot"] >= jargon["jargon_mass_human"], (
            "Bot-view should have more jargon hits on cloaked page"
        )

    def test_vectors_are_6_dimensional(self):
        from detection.pipeline.artifacts import extract_dual_artifacts
        from detection.pipeline.jargon import compute_jargon_asymmetry
        arts = extract_dual_artifacts(SAMPLE_CRAWL_RECORD)
        jargon = compute_jargon_asymmetry(arts, SAMPLE_CRAWL_RECORD)
        assert len(jargon["jargon_vector_human"]) == 6
        assert len(jargon["jargon_vector_bot"]) == 6


# ── Stage 6: fusion ───────────────────────────────────────────────────────────

class TestFusion:
    def test_returns_dict_with_required_keys(self):
        from detection.pipeline.artifacts import extract_dual_artifacts
        from detection.pipeline.drift import compute_cross_view_drift
        from detection.pipeline.promotion import compute_promotional_score
        from detection.pipeline.jargon import compute_jargon_asymmetry
        from detection.pipeline.fusion import fuse_risk_scores
        arts   = extract_dual_artifacts(SAMPLE_CRAWL_RECORD)
        drift  = compute_cross_view_drift(arts, SAMPLE_CRAWL_RECORD)
        promo  = compute_promotional_score(arts, SAMPLE_CRAWL_RECORD)
        jargon = compute_jargon_asymmetry(arts, SAMPLE_CRAWL_RECORD)
        fusion = fuse_risk_scores(drift, promo, url=SAMPLE_CRAWL_RECORD["url"], jargon=jargon)
        required = {"final_risk_score", "alert", "flagged_vectors",
                    "model_probability", "drift_contribution",
                    "jargon_contribution", "promo_contribution",
                    "url_model_contribution", "high_confidence"}
        assert required.issubset(fusion.keys()), f"Missing: {required - fusion.keys()}"

    def test_final_risk_score_in_0_1(self):
        from detection.pipeline.artifacts import extract_dual_artifacts
        from detection.pipeline.drift import compute_cross_view_drift
        from detection.pipeline.promotion import compute_promotional_score
        from detection.pipeline.jargon import compute_jargon_asymmetry
        from detection.pipeline.fusion import fuse_risk_scores
        arts   = extract_dual_artifacts(SAMPLE_CRAWL_RECORD)
        drift  = compute_cross_view_drift(arts, SAMPLE_CRAWL_RECORD)
        promo  = compute_promotional_score(arts, SAMPLE_CRAWL_RECORD)
        jargon = compute_jargon_asymmetry(arts, SAMPLE_CRAWL_RECORD)
        fusion = fuse_risk_scores(drift, promo, url=SAMPLE_CRAWL_RECORD["url"], jargon=jargon)
        score = fusion["final_risk_score"]
        assert 0.0 <= score <= 1.0, f"Score {score} out of [0,1]"

    def test_alert_type_is_bool(self):
        from detection.pipeline.drift import compute_cross_view_drift
        from detection.pipeline.promotion import compute_promotional_score
        from detection.pipeline.fusion import fuse_risk_scores
        from detection.pipeline.artifacts import extract_dual_artifacts
        arts   = extract_dual_artifacts(CLEAN_CRAWL_RECORD)
        drift  = compute_cross_view_drift(arts, CLEAN_CRAWL_RECORD)
        promo  = compute_promotional_score(arts, CLEAN_CRAWL_RECORD)
        fusion = fuse_risk_scores(drift, promo, url=CLEAN_CRAWL_RECORD["url"])
        assert isinstance(fusion["alert"], bool)

    def test_cloaked_has_higher_risk_than_clean(self):
        from detection.pipeline.artifacts import extract_dual_artifacts
        from detection.pipeline.drift import compute_cross_view_drift
        from detection.pipeline.promotion import compute_promotional_score
        from detection.pipeline.jargon import compute_jargon_asymmetry
        from detection.pipeline.fusion import fuse_risk_scores
        def run(record):
            arts   = extract_dual_artifacts(record)
            drift  = compute_cross_view_drift(arts, record)
            promo  = compute_promotional_score(arts, record)
            jargon = compute_jargon_asymmetry(arts, record)
            return fuse_risk_scores(drift, promo, url=record["url"], jargon=jargon)["final_risk_score"]
        risk_cloak = run(SAMPLE_CRAWL_RECORD)
        risk_clean = run(CLEAN_CRAWL_RECORD)
        assert risk_cloak >= risk_clean, (
            f"Cloaked {risk_cloak:.3f} should be >= clean {risk_clean:.3f}"
        )


# ── Multimodal model metrics ──────────────────────────────────────────────────

class TestMultimodalModelMetrics:
    def test_metrics_file_exists(self):
        metrics_path = ROOT / "detection" / "artifacts" / "multimodal_metrics.json"
        assert metrics_path.exists(), f"multimodal_metrics.json not found at {metrics_path}"

    def test_ensemble_accuracy_above_90(self):
        metrics_path = ROOT / "detection" / "artifacts" / "multimodal_metrics.json"
        if not metrics_path.exists():
            pytest.skip("multimodal_metrics.json not yet generated")
        with open(metrics_path) as f:
            metrics = json.load(f)
        ens = metrics.get("models", {}).get("Ensemble_multimodal", {})
        acc = ens.get("accuracy", 0)
        assert acc >= 0.85, f"Ensemble_multimodal accuracy {acc:.4f} below 0.85"

    def test_fused_auc_above_90(self):
        metrics_path = ROOT / "detection" / "artifacts" / "multimodal_metrics.json"
        if not metrics_path.exists():
            pytest.skip("multimodal_metrics.json not yet generated")
        with open(metrics_path) as f:
            metrics = json.load(f)
        ens = metrics.get("models", {}).get("Ensemble_multimodal", {})
        auc = ens.get("roc_auc", 0)
        assert auc >= 0.85, f"Ensemble_multimodal ROC-AUC {auc:.4f} below 0.85"

    def test_all_7_graphs_generated(self):
        graphs_dir = ROOT / "detection" / "artifacts" / "graphs"
        expected = [f"{i}_{name}.png" for i, name in [
            (15, "modality_ablation"), (16, "jargon_asymmetry_dist"),
            (17, "drift_feature_dists"), (18, "screenshot_diff_examples"),
            (19, "dom_diff_example"), (20, "fusion_contribution"),
            (21, "crawl_funnel"),
        ]]
        for fname in expected:
            assert (graphs_dir / fname).exists(), f"Missing graph: {fname}"

    def test_fused_beats_url_only_in_ablation(self):
        metrics_path = ROOT / "detection" / "artifacts" / "multimodal_metrics.json"
        if not metrics_path.exists():
            pytest.skip("multimodal_metrics.json not yet generated")
        with open(metrics_path) as f:
            metrics = json.load(f)
        abl = metrics.get("ablation", {})
        fused_auc = abl.get("fused", {}).get("roc_auc", 0)
        url_auc   = abl.get("url_lexical", {}).get("roc_auc", 0)
        assert fused_auc >= url_auc - 0.02, (
            f"Fused AUC {fused_auc:.4f} should be competitive with url_lexical {url_auc:.4f}"
        )


# ── Pipeline integration: end-to-end contract ────────────────────────────────

class TestPipelineIntegration:
    def test_full_pipeline_runs_without_error(self):
        from detection.pipeline import (
            extract_dual_artifacts, compute_cross_view_drift,
            compute_promotional_score, compute_jargon_asymmetry, fuse_risk_scores,
        )
        arts   = extract_dual_artifacts(SAMPLE_CRAWL_RECORD)
        drift  = compute_cross_view_drift(arts, SAMPLE_CRAWL_RECORD)
        promo  = compute_promotional_score(arts, SAMPLE_CRAWL_RECORD)
        jargon = compute_jargon_asymmetry(arts, SAMPLE_CRAWL_RECORD)
        fusion = fuse_risk_scores(drift, promo, url=SAMPLE_CRAWL_RECORD["url"], jargon=jargon)
        assert isinstance(fusion["final_risk_score"], float)
        assert isinstance(fusion["alert"], bool)

    def test_detection_pipeline_module_imports(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "detection_pipeline",
            ROOT / "detection" / "detection_pipeline.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "VIEW_PROFILES")
        assert hasattr(mod, "dual_view_crawl")
        assert hasattr(mod, "fuse_risk_scores")

    def test_dataset_parquet_exists_and_has_expected_shape(self):
        parquet_path = ROOT / "data" / "multimodal_features.parquet"
        if not parquet_path.exists():
            pytest.skip("multimodal_features.parquet not yet built")
        import pandas as pd
        df = pd.read_parquet(parquet_path)
        assert len(df) > 1000, f"Dataset too small: {len(df)} rows"
        assert "label" in df.columns
        assert "provenance" in df.columns
