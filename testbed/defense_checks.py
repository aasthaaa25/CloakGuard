"""
Owner-side checks on local state.

Injected-verdict checks do not measure detector accuracy.
DNS checks use a stubbed resolver and are not a live Googlebot test.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
TMP = Path(tempfile.mkdtemp(prefix="cloakguard-defense-"))
os.environ["BLOCKLIST_DB_PATH"] = str(TMP / "blocklist.db")
os.environ["DECOY_DB_PATH"] = str(TMP / "decoy.db")
os.environ["FORENSICS_OUTPUT_DIR"] = str(TMP / "forensics")
sys.path.insert(0, str(RESULTS))

from app.decoy.decoy_store import arm_decoy, disarm_decoy, get_decoy_if_armed
from app.fingerprint.blocklist import get_fingerprint_status, register_cloak_match
from app.fingerprint.crawler_verify import verify_crawler
from app.fingerprint import crawler_verify
from app.forensics.deep_scan import _write_forensic_report


def check(name: str, ok: bool, detail: str, category: str) -> dict:
    return {"name": name, "passed": ok, "detail": detail, "category": category}


def injected_verdict_checks() -> list[dict]:
    rows = []
    benign = get_fingerprint_status("ja3-benign-never-scored")
    rows.append(check(
        "benign_fingerprint_unchanged",
        benign["action"] == "ALLOW" and benign["score"] == 0.0,
        str(benign),
        "injected_verdict",
    ))
    register_cloak_match("ja3-trigger", "http://127.0.0.1/page")
    triggered = get_fingerprint_status("ja3-trigger")
    rows.append(check(
        "one_injected_match_rate_limits",
        triggered["action"] == "RATE_LIMIT" and triggered["score"] >= 25,
        str(triggered),
        "injected_verdict",
    ))
    register_cloak_match("ja3-block", "http://127.0.0.1/page")
    register_cloak_match("ja3-block", "http://127.0.0.1/page")
    register_cloak_match("ja3-block", "http://127.0.0.1/page")
    blocked = get_fingerprint_status("ja3-block")
    rows.append(check(
        "three_injected_matches_block",
        blocked["action"] == "BLOCK",
        str(blocked),
        "injected_verdict",
    ))
    url = "http://127.0.0.1/decoy-page"
    arm_decoy(url, "<html><body><p>Inert decoy</p></body></html>")
    served = get_decoy_if_armed(url) or ""
    rows.append(check(
        "decoy_served_while_armed",
        "Inert decoy" in served and "casino" not in served.lower(),
        "served=" + served[:80],
        "injected_verdict",
    ))
    import sqlite3
    from app.config import DECOY_DB_PATH, DECOY_TTL_HOURS
    with sqlite3.connect(DECOY_DB_PATH) as conn:
        conn.execute(
            "UPDATE decoy_state SET armed_at=? WHERE url=?",
            (time.time() - (DECOY_TTL_HOURS * 3600) - 10, url),
        )
    expired = get_decoy_if_armed(url)
    rows.append(check(
        "decoy_expires",
        expired is None,
        f"after_ttl={expired}",
        "injected_verdict",
    ))
    arm_decoy(url, "<html><body><p>Inert decoy</p></body></html>")
    disarm_decoy(url)
    rows.append(check(
        "rollback_disarms_decoy",
        get_decoy_if_armed(url) is None,
        "disarm then fetch",
        "injected_verdict",
    ))
    report = _write_forensic_report(
        "http://127.0.0.1/evidence",
        "evidence1",
        {"final_risk_score": 0.8, "alert": True, "scoring_path": "fixed_weight_heuristic", "flagged_vectors": []},
        {"drift_score": 0.2},
        {"promo_score": 0.1},
        None,
        None,
        None,
        [],
    )
    text = Path(report).read_text(encoding="utf-8")
    rows.append(check(
        "missing_screenshot_is_recorded",
        "Screenshots not available" in text and "HEURISTIC ALERT" in text,
        Path(report).name,
        "injected_verdict",
    ))
    return rows


async def concurrent_checks() -> list[dict]:
    from app.fingerprint.rate_limiter import check_rate_limit
    allowed = await asyncio.gather(*[check_rate_limit("ja3-concurrent") for _ in range(12)])
    true_count = sum(1 for item in allowed if item)
    return [check(
        "concurrent_bucket_rejects_some_requests",
        true_count < 12 and true_count > 0,
        f"allowed {true_count} of 12",
        "injected_verdict",
    )]


def dns_checks() -> list[dict]:
    rows = []
    rejected = verify_crawler("192.0.2.1", "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)")
    rows.append(check(
        "dns_rejection_fail_closed",
        rejected["verified"] is False and rejected.get("fail_closed") is True,
        rejected["reason"],
        "stub_or_live_dns",
    ))

    def fake_reverse(ip):
        if ip == "203.0.113.10":
            return ("crawl-a.googlebot.com", [], [ip])
        raise socket.timeout("timed out")

    def fake_forward(host):
        return (host, [], ["203.0.113.10"])

    original_reverse = socket.gethostbyaddr
    original_forward = socket.gethostbyname_ex
    try:
        socket.gethostbyaddr = fake_reverse
        socket.gethostbyname_ex = fake_forward
        crawler_verify.socket.gethostbyaddr = fake_reverse
        crawler_verify.socket.gethostbyname_ex = fake_forward
        ok = verify_crawler("203.0.113.10", "Mozilla/5.0 (compatible; Googlebot/2.1)")
        rows.append(check(
            "stubbed_dns_success",
            ok["verified"] is True and ok.get("hostname") == "crawl-a.googlebot.com",
            ok["reason"] + "; stubbed resolver, not a live Google address",
            "stubbed_dns",
        ))
        timed = verify_crawler("203.0.113.99", "Mozilla/5.0 (compatible; Googlebot/2.1)")
        rows.append(check(
            "stubbed_dns_timeout_fail_closed",
            timed["verified"] is False and timed["reason"] == "reverse_dns_failed",
            timed["reason"],
            "stubbed_dns",
        ))
    finally:
        socket.gethostbyaddr = original_reverse
        socket.gethostbyname_ex = original_forward
        crawler_verify.socket.gethostbyaddr = original_reverse
        crawler_verify.socket.gethostbyname_ex = original_forward
    return rows


def main() -> None:
    rows = injected_verdict_checks()
    rows.extend(asyncio.run(concurrent_checks()))
    rows.extend(dns_checks())
    dest = ROOT / "testbed" / "results" / "defense_checks.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({
        "note": "Injected-verdict and stubbed-DNS checks. They do not measure end-to-end detector accuracy.",
        "checks": rows,
        "passed": sum(1 for row in rows if row["passed"]),
        "failed": sum(1 for row in rows if not row["passed"]),
    }, indent=2), encoding="utf-8")
    print(f"passed {sum(1 for row in rows if row['passed'])} failed {sum(1 for row in rows if not row['passed'])}")
    for row in rows:
        if not row["passed"]:
            print("FAIL", row["name"], row["detail"])
    if any(not row["passed"] for row in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
