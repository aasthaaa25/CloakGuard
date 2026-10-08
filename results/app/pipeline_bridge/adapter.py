"""
Bridges the reverse-proxy middleware to the existing dual-view
detection pipeline (originally built across Day 1-5 of the
detection-side notebook). Exported as detection_pipeline.py.
"""

import sys
import asyncio
from pathlib import Path

# Make detection_pipeline importable whether we're run from project root or app/
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.config import DEEP_SCAN_TRIGGER_THRESHOLD
from app.fingerprint.blocklist import register_cloak_match
from app.decoy.decoy_generator import build_decoy_page
from app.decoy.decoy_store import arm_decoy
from app.forensics.deep_scan import trigger_deep_scan

# Import the detection pipeline (backed by the trained URL model)
from detection.detection_pipeline import (
    dual_view_crawl,
    extract_dual_artifacts,
    compute_cross_view_drift,
    compute_promotional_score,
    fuse_risk_scores,
)


async def run_detection_async(url: str, ja3_hash: str, response_body: bytes):
    """
    Runs the FULL existing detection pipeline on a URL, then acts on
    the verdict by arming L1 (fingerprint scoring), L2 (decoy), and/or
    triggering L3 (deep scan) as appropriate.
    """
    loop = asyncio.get_event_loop()

    # Your existing pipeline is synchronous (Playwright sync API or URL-model path) —
    # run it in a thread pool so it doesn't block the async event loop
    def _run_sync_pipeline():
        crawl_record = dual_view_crawl(url)
        artifacts    = extract_dual_artifacts(crawl_record)
        drift        = compute_cross_view_drift(artifacts, crawl_record)
        promo        = compute_promotional_score(artifacts, crawl_record)
        fusion       = fuse_risk_scores(drift, promo, url=url)
        return crawl_record, artifacts, drift, promo, fusion

    crawl_record, artifacts, drift, promo, fusion = await loop.run_in_executor(
        None, _run_sync_pipeline
    )

    if fusion.get("alert") and ja3_hash:
        # Layer 1: score this fingerprint
        register_cloak_match(ja3_hash, url)

        # Layer 2: arm decoy using the clean human-view HTML
        human_html = crawl_record.get("human", {}).get("html", "")
        if human_html:
            decoy_html = build_decoy_page(
                human_html,
                fusion.get("flagged_vectors", []),
                promo.get("keyword_categories_found", {}),
            )
            arm_decoy(url, decoy_html)

        # Layer 3: trigger deep forensic scan (fire-and-forget)
        if fusion.get("final_risk_score", 0) >= DEEP_SCAN_TRIGGER_THRESHOLD:
            asyncio.create_task(
                trigger_deep_scan(url, crawl_record, artifacts, drift, promo, fusion)
            )
