import asyncio
import hashlib
from pathlib import Path

from app.pipeline_bridge import adapter
from detection.pipeline import fusion
from detection.pipeline.integrity import check_integrity


def test_bot_only_fixture_opens_review_without_legacy_alert(monkeypatch, tmp_path):
    captures = Path(__file__).resolve().parents[2] / "testbed/v2_captures/linen_press"
    record = {
        view: {"html": (captures / f"bot_substantial_{suffix}.html").read_text()}
        for view, suffix in [("human", "H1"), ("bot", "B1")]
    }
    record["url"] = "https://linen.example/"

    monkeypatch.setattr(adapter, "dual_view_crawl", lambda _: record)
    monkeypatch.setattr(fusion, "_load_model", lambda: None)
    monkeypatch.setattr(fusion, "_REVIEW_THRESHOLD", 0.270)
    monkeypatch.setattr(adapter, "FORENSICS_OUTPUT_DIR", tmp_path)

    async def capture(*args):
        verdict = args[-1]
        assert verdict["review_alert"]
        assert not verdict["alert"]
        assert not verdict["score_is_probability"]
        assert verdict["observed_ja3"] is None

    monkeypatch.setattr(adapter, "trigger_deep_scan", capture)
    asyncio.run(adapter.run_detection_async("https://linen.example/", None, b""))
    assert len(list(tmp_path.glob("review_*.json"))) == 1


def test_single_view_integrity_detects_same_replacement_in_both_profiles():
    approved = b"<h1>Trusted owner page</h1>"
    trusted = hashlib.sha256(approved).hexdigest()
    assert not check_integrity(approved, trusted)["integrity_mismatch"]
    for replacement in (b"<h1>Replaced page</h1>",) * 2:
        assert check_integrity(replacement, trusted)["integrity_mismatch"]
