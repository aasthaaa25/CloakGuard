"""Run bounded dual-view reviews independently of enforcement."""

import asyncio
import json
import logging
import time
from uuid import uuid4
from pathlib import Path

from app.config import FORENSICS_OUTPUT_DIR

from app.forensics.deep_scan import trigger_deep_scan
from detection.detection_pipeline import (
    dual_view_crawl,
    extract_dual_artifacts,
    compute_cross_view_drift,
    compute_promotional_score,
    compute_jargon_asymmetry,
    fuse_risk_scores,
)

logger = logging.getLogger(__name__)
_active = {}
_recent = {}


def schedule_review(url, fingerprint):
    now = time.monotonic()
    for expired in [key for key, deadline in _recent.items() if deadline <= now]:
        del _recent[expired]
    if url in _active or url in _recent or len(_active) >= 2 or len(_recent) >= 256:
        return
    task = asyncio.create_task(run_detection_async(url, fingerprint, b""))
    _active[url] = task
    _recent[url] = now + 300

    def finished(task):
        _active.pop(url, None)
        if not task.cancelled() and (error := task.exception()):
            logger.error("Dual-view review failed", exc_info=error)

    task.add_done_callback(finished)


async def run_detection_async(url: str, ja3_hash: str | None, response_body: bytes):
    """Collect review evidence without promoting a page alert to enforcement."""
    def run_pipeline():
        record = dual_view_crawl(url)
        artifacts = extract_dual_artifacts(record)
        drift = compute_cross_view_drift(artifacts, record)
        promo = compute_promotional_score(artifacts, record)
        jargon = compute_jargon_asymmetry(artifacts, record)
        fusion = fuse_risk_scores(drift, promo, url=url, jargon=jargon)
        return record, artifacts, drift, promo, fusion

    record, artifacts, drift, promo, fusion = await asyncio.to_thread(run_pipeline)
    if fusion.get("review_alert"):
        review_id = uuid4().hex
        record = {**record, "url_id": review_id}
        fusion = {**fusion, "observed_ja3": ja3_hash}
        directory = Path(FORENSICS_OUTPUT_DIR)
        directory.mkdir(parents=True, exist_ok=True)
        review = directory / f"review_{review_id}.json"
        review.write_text(json.dumps({"url": url, "observed_ja3": ja3_hash}), encoding="utf-8")
        await trigger_deep_scan(url, record, artifacts, drift, promo, fusion)
