"""
Scored Fingerprint Blocklist + Rate Limiter
Backed by SQLite for simple, dependency-light persistence on a
single user's server (swap for Redis if scaling beyond one box).
"""

import time
import sqlite3
from contextlib import contextmanager
from app.config import (
    BLOCKLIST_DB_PATH, SCORE_INCREMENT_ON_CLOAK_MATCH,
    SCORE_DECAY_PER_HOUR, RATE_LIMIT_SCORE_THRESHOLD,
    HARD_BLOCK_SCORE_THRESHOLD, GOOGLEBOT_ALLOWLIST_JA3,
)


@contextmanager
def _db():
    conn = sqlite3.connect(BLOCKLIST_DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS fingerprint_scores (
        ja3_hash      TEXT PRIMARY KEY,
        score         REAL NOT NULL DEFAULT 0,
        last_seen     REAL NOT NULL,
        first_seen    REAL NOT NULL,
        hit_count     INTEGER NOT NULL DEFAULT 0,
        sample_urls   TEXT DEFAULT ''
    )""")
    try:
        yield conn
    finally:
        conn.commit()
        conn.close()


def _apply_decay(score: float, last_seen: float, now: float) -> float:
    """Linear decay — a fingerprint that goes quiet for a while gradually
    becomes trusted again, rather than staying permanently blocked from
    one historical incident.
    Minimum interval: 1 minute. Sub-minute gaps are floating-point noise,
    not meaningful decay."""
    hours_elapsed = max(0.0, (now - last_seen) / 3600.0)
    if hours_elapsed < (1 / 60):  # < 1 minute → no decay (avoid FP precision issues)
        return score
    decayed = score - (hours_elapsed * SCORE_DECAY_PER_HOUR)
    return max(decayed, 0.0)


def register_cloak_match(ja3_hash: str, url: str):
    """
    Called when the detection pipeline confirms cloaking was served
    to a request bearing this fingerprint. Increments its score.
    """
    if ja3_hash in GOOGLEBOT_ALLOWLIST_JA3:
        return  # NEVER score legitimate verified crawlers — see §1.7

    now = time.time()
    with _db() as conn:
        row = conn.execute(
            "SELECT score, last_seen, first_seen, hit_count, sample_urls "
            "FROM fingerprint_scores WHERE ja3_hash=?",
            (ja3_hash,)
        ).fetchone()

        if row is None:
            conn.execute(
                "INSERT INTO fingerprint_scores VALUES (?,?,?,?,?,?)",
                (ja3_hash, SCORE_INCREMENT_ON_CLOAK_MATCH, now, now, 1, url[:200])
            )
        else:
            old_score, last_seen, first_seen, hit_count, sample_urls = row
            decayed_score = _apply_decay(old_score, last_seen, now)
            new_score = decayed_score + SCORE_INCREMENT_ON_CLOAK_MATCH
            updated_urls = (sample_urls + ";" + url[:200])[-1000:]  # keep it bounded
            conn.execute(
                "UPDATE fingerprint_scores SET score=?, last_seen=?, hit_count=?, "
                "sample_urls=? WHERE ja3_hash=?",
                (new_score, now, hit_count + 1, updated_urls, ja3_hash)
            )


def get_fingerprint_status(ja3_hash: str) -> dict:
    """
    Returns the current decayed score and recommended action for
    a fingerprint. Called on EVERY inbound request by the middleware.
    """
    if ja3_hash in GOOGLEBOT_ALLOWLIST_JA3:
        return {"score": 0.0, "action": "ALLOW", "reason": "verified_legitimate_crawler"}

    now = time.time()
    with _db() as conn:
        row = conn.execute(
            "SELECT score, last_seen, hit_count FROM fingerprint_scores WHERE ja3_hash=?",
            (ja3_hash,)
        ).fetchone()

    if row is None:
        return {"score": 0.0, "action": "ALLOW", "reason": "no_history"}

    raw_score, last_seen, hit_count = row
    current_score = _apply_decay(raw_score, last_seen, now)

    if current_score >= HARD_BLOCK_SCORE_THRESHOLD:
        action = "BLOCK"
    elif current_score >= RATE_LIMIT_SCORE_THRESHOLD:
        action = "RATE_LIMIT"
    else:
        action = "ALLOW"

    return {
        "score":     round(current_score, 2),
        "action":    action,
        "hit_count": hit_count,
        "reason":    "scored_history",
    }
