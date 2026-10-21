"""
Apply one reserved detector verdict to the designated test subject.

The URL is not treated as an attacker identity. The harness names the subject.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
TMP = Path(tempfile.mkdtemp(prefix="cloakguard-v2-"))
os.environ["BLOCKLIST_DB_PATH"] = str(TMP / "blocklist.db")
os.environ["DECOY_DB_PATH"] = str(TMP / "decoy.db")
os.environ["FORENSICS_OUTPUT_DIR"] = str(TMP / "forensics")
sys.path.insert(0, str(RESULTS))

from app.decoy.decoy_generator import build_decoy_page
from app.decoy.decoy_store import arm_decoy, disarm_decoy, get_decoy_if_armed
from app.fingerprint.blocklist import get_fingerprint_status, register_cloak_match
from app.fingerprint.crawler_verify import verify_crawler
from app.forensics.deep_scan import _write_forensic_report

SUBJECT = "authorized-test-subject"
OTHER = "unrelated-client"
TARGET = "quartz_supply:bot_substantial"


def main() -> None:
    import csv
    rows = list(csv.DictReader((ROOT / "testbed" / "results" / "v2_scores.csv").open(encoding="utf-8")))
    chosen = next(
        row for row in rows
        if row["split"] == "reserved"
        and row["template_family"] == "quartz_supply"
        and row["scenario_family"] == "bot_substantial"
        and row["comparison"] == "cross_profile"
        and float(row["raw_score"]) >= float(row["review_threshold"])
    )
    human_html = (ROOT / "testbed" / "v2_captures" / "quartz_supply" / "bot_substantial_H1.html").read_text(encoding="utf-8")
    unrelated_before = get_fingerprint_status(OTHER)
    register_cloak_match(SUBJECT, "http://127.0.0.1/quartz_supply/bot_substantial")
    status = get_fingerprint_status(SUBJECT)
    decoy = build_decoy_page(human_html, [], {})
    arm_decoy("http://127.0.0.1/quartz_supply/bot_substantial", decoy)
    served = get_decoy_if_armed("http://127.0.0.1/quartz_supply/bot_substantial")
    report = _write_forensic_report(
        "http://127.0.0.1/quartz_supply/bot_substantial",
        "quartz-substantial",
        {
            "final_risk_score": float(chosen["raw_score"]),
            "alert": True,
            "scoring_path": chosen["scoring_path"],
            "flagged_vectors": [],
        },
        {"drift_score": float(chosen["drift_score"])},
        {"promo_score": float(chosen["promo_score"])},
        None,
        None,
        None,
        [],
    )
    disarm_decoy("http://127.0.0.1/quartz_supply/bot_substantial")
    try:
        live = verify_crawler("8.8.8.8", "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)")
        live_note = "live resolver answered"
    except socket.timeout:
        live = {"verified": False, "reason": "timeout"}
        live_note = "live resolver timed out"
    except OSError as exc:
        live = {"verified": False, "reason": str(exc)}
        live_note = "live resolver failed"
    out = {
        "category": "detector_generated_integration",
        "target": TARGET,
        "raw_score": float(chosen["raw_score"]),
        "review_threshold": float(chosen["review_threshold"]),
        "review_verdict": chosen["review_verdict"],
        "designated_subject": SUBJECT,
        "subject_action": status["action"],
        "unrelated_client_action": unrelated_before["action"],
        "decoy_served": served is not None and "casino" not in (served or "").lower(),
        "rollback_clears_decoy": get_decoy_if_armed("http://127.0.0.1/quartz_supply/bot_substantial") is None,
        "evidence_report": report,
        "attribution": "The harness designated the test subject. The URL was not mapped to a client fingerprint.",
        "live_dns": {"note": live_note, "result": live, "is_live_googlebot_proof": False},
    }
    dest = ROOT / "testbed" / "results" / "detector_integration.json"
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("review_verdict", "subject_action", "decoy_served", "rollback_clears_decoy", "live_dns")}, indent=2))


if __name__ == "__main__":
    main()
