"""Regression tests for the portable training and demo entry points."""
import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from app import config
from detection import train_model
from detection.pipeline import fusion

REPO = Path(__file__).resolve().parents[2]


def generator_module():
    spec = importlib.util.spec_from_file_location("generate_dataset", REPO / "generate_dataset.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_training_csv_is_at_repository_root():
    assert train_model.CSV_PATH == REPO / "final_full (1).csv"


def test_generator_is_reproducible_and_explicitly_synthetic(tmp_path):
    generator = generator_module()
    first, second = tmp_path / "a.csv", tmp_path / "b.csv"
    generator.generate_dataset(first, rows=120, seed=42)
    generator.generate_dataset(second, rows=120, seed=42)
    assert first.read_bytes() == second.read_bytes()
    data = pd.read_csv(first)
    assert len(data) == 120
    assert data.url.nunique() == 120
    assert set(data.label) == {0, 1}
    assert set(data.provenance) == {"synthetic_url_risk_fixture"}
    assert "drift_score" not in data
    assert data.url.str.contains(r"\.test/", regex=True).all()


def test_training_rejects_detector_derived_labels(tmp_path):
    path = tmp_path / "circular.csv"
    pd.DataFrame({"url": ["https://a.test/", "https://b.test/"],
                  "drift_score": [0, 1]}).to_csv(path, index=False)
    with pytest.raises(ValueError, match="label"):
        train_model.read_training_data(path)


def test_requested_alert_and_review_thresholds(monkeypatch):
    assert config.ALERT_THRESHOLD == 0.45
    assert config.REVIEW_THRESHOLD == 0.270
    monkeypatch.setattr(fusion, "_load_model", lambda: None)
    result = fusion.fuse_risk_scores({"drift_score": 0.5}, {"promo_score": 0.56},
                                    jargon={"jargon_asymmetry_score": 0.4})
    assert result["final_risk_score"] == pytest.approx(0.480)
    assert result["alert"] and result["review_alert"]
    assert result["score_is_probability"] is False


def test_generator_rejects_too_few_rows_for_default_smote_demo(tmp_path):
    with pytest.raises(ValueError, match="80"):
        generator_module().generate_dataset(tmp_path / "small.csv", rows=20)
