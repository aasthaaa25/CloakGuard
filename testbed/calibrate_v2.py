"""
Score new template families and apply testbed/THRESHOLD_RULE.md.

Calibration scores are reduced to a threshold before reserved scores are labeled.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "results"))
sys.path.insert(0, str(REPO / "testbed"))

from detection.pipeline.artifacts import extract_dual_artifacts
from detection.pipeline.crawl import VIEW_PROFILES, _fetch_httpx
from detection.pipeline.drift import compute_cross_view_drift
from detection.pipeline.fusion import fuse_risk_scores
from detection.pipeline.jargon import compute_jargon_asymmetry
from detection.pipeline.promotion import compute_promotional_score
from v2_pages import APP_VERSION, CALIBRATION, RESERVED, ROLES, SCENARIOS, pages_for

PORT = 8766
ORDER = ("H1", "B1", "H2", "B2")
STATE = {"token": 0}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parts = [part for part in self.path.split("?")[0].split("/") if part]
        if len(parts) != 2 or parts[1] not in ROLES:
            body, status = "missing", 404
        else:
            STATE["token"] += 1
            profile = "bot" if "Googlebot" in self.headers.get("User-Agent", "") else "human"
            body = pages_for(parts[0], profile, parts[1], str(STATE["token"]))
            status = 200
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-App-Version", APP_VERSION)
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        return


def capture(families) -> list[dict]:
    rows = []
    for family in families:
        split = "calibration" if family in CALIBRATION else "reserved"
        for scenario in SCENARIOS:
            url = f"http://127.0.0.1:{PORT}/{family}/{scenario}"
            for view in ORDER:
                profile = "human" if view.startswith("H") else "bot"
                fetched_at = datetime.now(timezone.utc).isoformat()
                fetched = _fetch_httpx(url, VIEW_PROFILES[profile])
                html = fetched.get("html") or ""
                digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
                path = REPO / "testbed" / "v2_captures" / family / f"{scenario}_{view}.html"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(html, encoding="utf-8")
                meta = {
                    "template_family": family,
                    "scenario_family": scenario,
                    "scenario_id": f"{family}:{scenario}",
                    "split": split,
                    "role": ROLES[scenario],
                    "view_id": view,
                    "profile": profile,
                    "application_version": APP_VERSION,
                    "fetched_at_utc": fetched_at,
                    "requested_url": url,
                    "final_url": fetched.get("final_url", ""),
                    "redirect_chain": fetched.get("redirect_chain", []),
                    "status": fetched.get("status", 0),
                    "response_headers": fetched.get("response_headers", {}),
                    "artifact_sha256": digest,
                    "artifact": str(path.relative_to(REPO)).replace("\\", "/"),
                    "capture_success": fetched.get("status") == 200 and bool(html.strip()),
                    "hostname_group": "127.0.0.1",
                    "registrable_domain_group": "",
                    "screenshot": "unsupported_in_this_phase",
                }
                path.with_suffix(".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
                rows.append(meta)
    return rows


def score_pair(left: dict, right: dict) -> dict:
    record = {
        "url": left["requested_url"],
        "url_id": "v2",
        "human": {"html": (REPO / left["artifact"]).read_text(encoding="utf-8"), "screenshot_path": None},
        "bot": {"html": (REPO / right["artifact"]).read_text(encoding="utf-8"), "screenshot_path": None},
    }
    arts = extract_dual_artifacts(record)
    drift = compute_cross_view_drift(arts, record)
    promo = compute_promotional_score(arts, record)
    jargon = compute_jargon_asymmetry(arts, record)
    fusion = fuse_risk_scores(drift, promo, url="", jargon=jargon)
    return {
        "scoring_path": fusion["scoring_path"],
        "raw_score": fusion["final_risk_score"],
        "drift_score": drift["drift_score"],
        "promo_score": promo["promo_score"],
        "jargon_score": jargon["jargon_asymmetry_score"],
        "signed_jargon_gap": jargon["jargon_signed_density_delta"],
        "v1_threshold": fusion["alert_threshold"],
        "v1_verdict": "alert" if fusion["alert"] else "no_alert",
    }


def pairs(captures: list[dict], split: str) -> list[dict]:
    index = {(row["template_family"], row["scenario_family"], row["view_id"]): row for row in captures}
    families = CALIBRATION if split == "calibration" else RESERVED
    out = []
    for family in families:
        for scenario in SCENARIOS:
            for comparison, left, right in (
                ("cross_profile", "H1", "B1"),
                ("cross_profile", "H2", "B2"),
                ("within_human", "H1", "H2"),
                ("within_bot", "B1", "B2"),
            ):
                scored = score_pair(index[(family, scenario, left)], index[(family, scenario, right)])
                out.append({
                    "template_family": family,
                    "scenario_family": scenario,
                    "split": split,
                    "role": ROLES[scenario],
                    "comparison": comparison,
                    "sets_threshold": comparison == "cross_profile" and left == "H1" and split == "calibration",
                    **scored,
                })
    return out


def choose_threshold(calibration_rows: list[dict]) -> dict:
    primary = [row for row in calibration_rows if row["sets_threshold"]]
    negatives = [row["raw_score"] for row in primary if row["role"] == "negative"]
    positives = [row["raw_score"] for row in primary if row["role"] in {"positive", "positive_substantial"}]
    substantial = [row["raw_score"] for row in primary if row["role"] == "positive_substantial"]
    result = {
        "max_negative": max(negatives),
        "min_positive": min(positives),
        "min_substantial": min(substantial),
    }
    if min(positives) > max(negatives):
        result.update({
            "scope_used": "bot_directed_including_few_terms_and_hidden_in_list_links",
            "review_threshold": (min(positives) + max(negatives)) / 2,
        })
    elif min(substantial) > max(negatives):
        result.update({
            "scope_used": "substantial_bot_directed_injection_only",
            "review_threshold": (min(substantial) + max(negatives)) / 2,
        })
    else:
        result.update({"scope_used": "unseparated", "review_threshold": None})
    return result


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        captures = capture(CALIBRATION + RESERVED)
        calibration = pairs(captures, "calibration")
        decision = choose_threshold(calibration)
        frozen = {
            "heuristic_version": 2,
            "weights": {"drift": 0.40, "jargon": 0.35, "promo": 0.25},
            "keyword_lists": "detection/pipeline/promotion.py PROMO_CATEGORIES",
            "v1_threshold_unchanged": 0.50,
            "decision": decision,
            "objective": "review alert for bot-directed promotional cloaking; not a block",
        }
        out = REPO / "testbed" / "results"
        out.mkdir(parents=True, exist_ok=True)
        (out / "frozen_detector_v2.json").write_text(json.dumps(frozen, indent=2), encoding="utf-8")
        reserved = pairs(captures, "reserved")
        threshold = decision["review_threshold"]
        for row in calibration + reserved:
            if threshold is None:
                row["review_verdict"] = "no_threshold"
            else:
                row["review_verdict"] = "alert" if row["raw_score"] >= threshold else "no_alert"
            row["review_threshold"] = threshold if threshold is not None else ""
        rows = calibration + reserved
        with (out / "v2_scores.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        with (out / "v2_captures.csv").open("w", newline="", encoding="utf-8") as handle:
            flat = []
            for row in captures:
                item = dict(row)
                item["redirect_chain"] = " ".join(item["redirect_chain"])
                item["response_headers"] = json.dumps(item["response_headers"])
                flat.append(item)
            writer = csv.DictWriter(handle, fieldnames=list(flat[0].keys()))
            writer.writeheader()
            writer.writerows(flat)
    finally:
        server.shutdown()
        server.server_close()
    print(json.dumps(decision, indent=2))


if __name__ == "__main__":
    main()
