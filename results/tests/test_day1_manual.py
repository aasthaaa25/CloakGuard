"""
Manual end-to-end test for Day 1 — §1.11 from the doc.
Tests the L1 scored-blocklist, token-bucket rate limiter, L2 decoy engine,
and Googlebot impersonation detection DIRECTLY (no network, no proxy needed).

Run: pytest tests/test_day1_manual.py -v
"""

import sys
import time
import asyncio
import tempfile
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Override DB paths to use temp files for isolated testing
import os
os.environ["BLOCKLIST_DB_PATH"] = str(Path(tempfile.mkdtemp()) / "test_blocklist.db")
os.environ["DECOY_DB_PATH"]     = str(Path(tempfile.mkdtemp()) / "test_decoy.db")


def simulate_attacker_request():
    """Mimics a basic scraping tool — generic UA, no real browser TLS stack"""
    return {"user_agent": "python-requests/2.31", "url": "http://test.example.com/page"}


def simulate_googlebot_impersonator():
    """Claims to be Googlebot but isn't really (wrong IP/no DNS match).
    THIS is what should trigger the strongest, fastest response."""
    return {
        "user_agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        "source_ip":  "192.0.2.1",  # RFC 5737 doc address — never a real Googlebot IP
    }


# ── Tests ────────────────────────────────────────────────────────────────────

class TestScoredBlocklist:
    def test_register_increases_score(self):
        from app.fingerprint.blocklist import register_cloak_match, get_fingerprint_status
        ja3 = "aabbccddeeff00112233445566778899"
        register_cloak_match(ja3, "http://example.com")
        status = get_fingerprint_status(ja3)
        assert status["score"] > 0
        assert status["action"] in ("RATE_LIMIT", "BLOCK")

    def test_score_decay(self):
        from app.fingerprint.blocklist import register_cloak_match, _apply_decay
        score = 25.0
        # After 1 hour, score should decay by SCORE_DECAY_PER_HOUR
        now = time.time()
        old_time = now - 3600
        decayed = _apply_decay(score, old_time, now)
        assert decayed < score

    def test_first_match_triggers_rate_limit(self):
        from app.fingerprint.blocklist import register_cloak_match, get_fingerprint_status
        ja3 = "deadbeef00000000aaaaaaaaaaaaaaaa"
        register_cloak_match(ja3, "http://example.com/evil")
        status = get_fingerprint_status(ja3)
        # One match at score=25.0 >= RATE_LIMIT_SCORE_THRESHOLD=25.0
        assert status["action"] in ("RATE_LIMIT", "BLOCK")

    def test_three_matches_trigger_hard_block(self):
        from app.fingerprint.blocklist import register_cloak_match, get_fingerprint_status
        ja3 = "cafe0000111122223333444455556666"
        for _ in range(3):
            register_cloak_match(ja3, "http://example.com/evil")
        status = get_fingerprint_status(ja3)
        assert status["action"] == "BLOCK"
        assert status["score"] >= 75.0


class TestTokenBucketRateLimiter:
    def test_tokens_consumed(self):
        async def _run():
            from app.fingerprint.rate_limiter import check_rate_limit
            ja3 = "ratelimitertestja3aabbcc001122"
            # First request should be allowed
            result = await check_rate_limit(ja3)
            assert result is True
        asyncio.get_event_loop().run_until_complete(_run())

    def test_bucket_exhausts(self):
        async def _run():
            from app.fingerprint.rate_limiter import TokenBucket
            # Small bucket (capacity=2, refill=1/min = very slow)
            bucket = TokenBucket(capacity=2, refill_per_minute=1)
            r1 = await bucket.consume()
            r2 = await bucket.consume()
            r3 = await bucket.consume()  # should be False
            assert r1 is True
            assert r2 is True
            assert r3 is False
        asyncio.get_event_loop().run_until_complete(_run())


class TestCrawlerVerification:
    def test_non_bot_ua_returns_false(self):
        from app.fingerprint.crawler_verify import verify_crawler
        result = verify_crawler("192.0.2.1", "Mozilla/5.0 Chrome/120")
        assert result["verified"] is False
        assert result["claimed_bot"] is None

    def test_googlebot_impersonation_fails(self):
        from app.fingerprint.crawler_verify import verify_crawler
        # 192.0.2.1 is RFC5737 doc address — reverse DNS won't resolve to googlebot.com
        result = verify_crawler(
            "192.0.2.1",
            "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
        )
        assert result["verified"] is False
        assert result["claimed_bot"] == "googlebot"
        assert "SUSPECTED" in result["reason"] or "failed" in result["reason"]

    def test_identify_claimed_bot(self):
        from app.fingerprint.crawler_verify import identify_claimed_bot
        assert identify_claimed_bot("Googlebot/2.1") == "googlebot"
        assert identify_claimed_bot("Mozilla/5.0 (compatible; bingbot/2.0)") == "bingbot"
        assert identify_claimed_bot("Mozilla/5.0 Chrome/120") is None


class TestDecoyEngine:
    def test_arm_and_serve_decoy(self):
        from app.decoy.decoy_store import arm_decoy, get_decoy_if_armed, disarm_decoy
        url = "http://test.example.com/arm-test"
        html = "<html><body><p>Clean page</p></body></html>"
        arm_decoy(url, html)
        served = get_decoy_if_armed(url)
        assert served == html
        disarm_decoy(url)
        assert get_decoy_if_armed(url) is None

    def test_decoy_expires(self):
        from app.decoy.decoy_store import arm_decoy, get_decoy_if_armed
        import sqlite3
        from app.config import DECOY_DB_PATH
        url = "http://test.example.com/expire-test"
        html = "<html><body>content</body></html>"
        # Force an old armed_at
        arm_decoy(url, html)
        conn = sqlite3.connect(DECOY_DB_PATH)
        conn.execute("UPDATE decoy_state SET armed_at=? WHERE url=?",
                     (0.0, url))  # epoch 0 = very old
        conn.commit()
        conn.close()
        # Should expire on access
        served = get_decoy_if_armed(url)
        assert served is None

    def test_build_decoy_page(self):
        from app.decoy.decoy_generator import build_decoy_page
        human_html = """<html><head></head>
        <body><h1>Hello</h1><marquee>SPAM</marquee></body></html>"""
        result = build_decoy_page(human_html, [], {})
        # marquee should be removed
        assert "marquee" not in result.lower() or "SPAM" not in result
        # marker meta should be present
        assert "x-internal-decoy-served" in result


print("\n=== Day 1 Tests ===")
print("Test 1: Repeated generic scraper requests — score increments, eventually rate-limit/block")
print("Test 2: Googlebot IMPERSONATION — reverse DNS fails → IMPERSONATION SUSPECTED")
print("\nExpected: fingerprint scoring works, decoy arms, impersonation detected.\n")
