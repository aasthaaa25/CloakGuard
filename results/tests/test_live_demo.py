"""Exercise the presentation entry point through real TCP/TLS sockets."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("with_url_model", [False, True])
def test_one_command_live_demo(tmp_path, with_url_model):
    arguments = [sys.executable, str(REPO / "demo_live.py"), "--output", str(tmp_path)]
    if with_url_model:
        import joblib
        from sklearn.dummy import DummyClassifier
        from detection.features import FEATURE_NAMES
        import pandas as pd

        features = pd.DataFrame([[0] * len(FEATURE_NAMES)] * 2, columns=FEATURE_NAMES)
        model = DummyClassifier(strategy="prior").fit(features, [0, 1])
        path = tmp_path / "fixture_model.joblib"
        joblib.dump({"pipeline": model, "feature_names": FEATURE_NAMES}, path)
        arguments.extend(["--url-model", str(path)])
    result = subprocess.run(
        arguments,
        cwd=tmp_path, capture_output=True, text=True, timeout=60,
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((tmp_path / "demo_result.json").read_text())
    if with_url_model:
        assert report["url_risk_prediction"]["probability"] == pytest.approx(0.5)
    else:
        assert 0 <= report["url_risk_prediction"]["probability"] <= 1
        assert (tmp_path / "url_model/model_card.json").exists()
    assert report["tls_ja3"]
    assert report["fusion"]["review_alert"] and report["fusion"]["alert"]
    assert report["score_before_confirmation"] == 0
    assert report["score_after_confirmation"] == 25
    assert report["decoy_status"] == 200
    assert report["decoy_inert"]
    assert report["origin_still_injected"]
    assert report["blocked_status"] == 403
    assert report["forensic_report_exists"]
    assert "Controlled fixture confirmation" in result.stdout
