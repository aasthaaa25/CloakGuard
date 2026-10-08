"""
Full integration test — §2.9 from the doc.
Simulates a complete attack lifecycle:
  Step 1: First crawl triggers detection pipeline (async)
  Step 2: Repeat attacker request → should be rate-limited/decoy-served
  Step 3: Verify forensic report was generated

Tests the three-layer defense logic directly (without needing a live server).

Run: pytest tests/test_full_integration.py -v
"""

import sys
import os
import time
import asyncio
import tempfile
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Use isolated temp DBs
_TMP_DIR = Path(tempfile.mkdtemp())
os.environ["BLOCKLIST_DB_PATH"]    = str(_TMP_DIR / "integ_blocklist.db")
os.environ["DECOY_DB_PATH"]        = str(_TMP_DIR / "integ_decoy.db")
os.environ["FORENSICS_OUTPUT_DIR"] = str(_TMP_DIR / "forensics")


def attacker_verification_crawl():
    """Simulates the attacker's own tooling re-checking their defacement is live."""
    return {
        "user_agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        "source_ip":  "192.0.2.1",
        "url":        "http://victim-site.example.com/cloaked-test-page",
    }


class TestFullIntegration:

    def test_step1_detection_pipeline_runs(self):
        """Step 1: running detection pipeline on a URL produces a fusion verdict."""
        from detection.detection_pipeline import (
            dual_view_crawl, extract_dual_artifacts,
            compute_cross_view_drift, compute_promotional_score, fuse_risk_scores,
        )
        url = "https://free-casino-slots.tk/redirect?goto=spam"
        record = dual_view_crawl(url)
        arts   = extract_dual_artifacts(record)
        drift  = compute_cross_view_drift(arts, record)
        promo  = compute_promotional_score(arts, record)
        fusion = fuse_risk_scores(drift, promo, url=url)

        assert "alert" in fusion
        assert "final_risk_score" in fusion
        assert "flagged_vectors" in fusion
        print(f"\n  Step 1 ✓ — fusion verdict: alert={fusion['alert']} "
              f"score={fusion['final_risk_score']:.3f}")

    def test_step2_fingerprint_scored_after_alert(self):
        """Step 2: fingerprint is scored after a confirmed cloaking verdict."""
        from app.fingerprint.blocklist import register_cloak_match, get_fingerprint_status
        ja3 = "integration_test_ja3_hash_0011"
        url = "http://victim-site.example.com/cloaked-test-page"

        # Simulate the pipeline reporting a cloaking match for this fingerprint
        register_cloak_match(ja3, url)
        status = get_fingerprint_status(ja3)

        assert status["action"] in ("RATE_LIMIT", "BLOCK")
        assert status["score"] >= 25.0
        print(f"\n  Step 2 ✓ — fingerprint scored: action={status['action']}"
              f"  score={status['score']}")

    def test_step2b_decoy_armed_after_alert(self):
        """Step 2b: decoy is armed for a URL with a confirmed cloaking verdict."""
        from app.decoy.decoy_store import arm_decoy, get_decoy_if_armed
        url = "http://victim-site.example.com/decoy-test"
        human_html = "<html><head></head><body><h1>Legitimate Site</h1></body></html>"
        arm_decoy(url, human_html)
        served = get_decoy_if_armed(url)
        assert served is not None
        # The injected payload would NOT be in the decoy
        assert "casino" not in served.lower()
        print(f"\n  Step 2b ✓ — decoy armed, serving clean content")

    def test_step2c_second_request_gets_decoy(self):
        """After decoy is armed, the same fingerprint requesting same URL gets decoy."""
        from app.decoy.decoy_store import arm_decoy, get_decoy_if_armed
        from app.fingerprint.blocklist import register_cloak_match, get_fingerprint_status

        url = "http://victim-site.example.com/page-with-decoy"
        ja3 = "integration_ja3_decoy_test_aaaa"
        clean_html = "<html><body><p>Clean page content</p></body></html>"

        # 1. Pipeline confirms cloaking → arm decoy
        arm_decoy(url, clean_html)
        register_cloak_match(ja3, url)

        # 2. Same fingerprint makes a second request
        status = get_fingerprint_status(ja3)
        decoy = get_decoy_if_armed(url)

        # Should be rate-limited/blocked AND decoy should be there
        assert status["action"] in ("RATE_LIMIT", "BLOCK")
        assert decoy is not None
        print(f"\n  Step 2c ✓ — second request: action={status['action']}, decoy_served=True")

    def test_step3_forensic_report_generated(self):
        """Step 3: forensic report is written to FORENSICS_OUTPUT_DIR."""
        import asyncio

        async def _run():
            from app.forensics.deep_scan import _write_forensic_report
            from app.forensics.dom_diff import compute_dom_diff
            from app.forensics.js_trace_diff import diff_js_traces

            url    = "http://victim-site.example.com/forensic-test"
            url_id = "testid001"

            fusion = {
                "final_risk_score": 0.87,
                "alert": True,
                "flagged_vectors": [{"type": "url_lexical_risk", "score": 0.87, "detail": "test"}],
                "model_probability": 0.87,
            }
            drift = {"drift_score": 0.65, "html_size_drift": 0.3}
            promo = {"promo_score": 0.45, "keyword_categories_found": {"gambling": ["casino"]}}

            dom_diff = compute_dom_diff(
                "<html><body><p>clean</p></body></html>",
                "<html><body><p>clean</p><a href='spam.tk'>casino</a></body></html>",
            )
            js_diff = diff_js_traces({"requests": [], "console": []},
                                      {"requests": [{"url": "https://spam.tk/track.js",
                                                      "method": "GET", "resource_type": "script"}],
                                       "console": []})

            report_path = _write_forensic_report(
                url, url_id, fusion, drift, promo,
                None, dom_diff, js_diff, [],
            )
            return report_path

        report_path = asyncio.run(_run())
        assert Path(report_path).exists()
        content = Path(report_path).read_text()
        assert "CLOAKING CONFIRMED" in content
        assert "0.87" in content
        print(f"\n  Step 3 ✓ — forensic report: {report_path}")

    def test_impersonation_detection_deterministic(self):
        """§2.10: impersonation detection rate — DNS verification is deterministic."""
        from app.fingerprint.crawler_verify import verify_crawler
        # A non-Googlebot IP claiming to be Googlebot must always be flagged
        for ip in ["192.0.2.1", "10.0.0.1", "172.16.0.1"]:
            result = verify_crawler(
                ip, "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
            )
            assert result["verified"] is False, f"Expected unverified for {ip}"
            assert result["claimed_bot"] == "googlebot"


print("\n=== Full Integration Test ===")
print("Step 1: First crawl → detection pipeline runs → fusion verdict")
print("Step 2: Repeat request → fingerprint scored, decoy armed")
print("Step 3: Forensic report auto-generated in logs/forensics/")
print("\nExpected: payload absent in second response, report generated.\n")
