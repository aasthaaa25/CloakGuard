"""
Tracks which URLs currently have an armed decoy, and serves the
appropriate cached decoy HTML when a matched-fingerprint request
comes in for that URL.
"""

import sqlite3
import time
from contextlib import contextmanager
from app.config import DECOY_DB_PATH, DECOY_TTL_HOURS


@contextmanager
def _db():
    conn = sqlite3.connect(DECOY_DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS decoy_state (
        url          TEXT PRIMARY KEY,
        decoy_html   TEXT NOT NULL,
        armed_at     REAL NOT NULL,
        serve_count  INTEGER NOT NULL DEFAULT 0
    )""")
    try:
        yield conn
    finally:
        conn.commit()
        conn.close()


def arm_decoy(url: str, decoy_html: str):
    with _db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO decoy_state (url, decoy_html, armed_at, serve_count) "
            "VALUES (?, ?, ?, COALESCE((SELECT serve_count FROM decoy_state WHERE url=?), 0))",
            (url, decoy_html, time.time(), url)
        )


def get_decoy_if_armed(url: str):
    """Returns decoy HTML if armed and not expired, else None."""
    with _db() as conn:
        row = conn.execute(
            "SELECT decoy_html, armed_at FROM decoy_state WHERE url=?", (url,)
        ).fetchone()
        if row is None:
            return None
        decoy_html, armed_at = row
        if (time.time() - armed_at) > DECOY_TTL_HOURS * 3600:
            conn.execute("DELETE FROM decoy_state WHERE url=?", (url,))
            return None
        conn.execute(
            "UPDATE decoy_state SET serve_count = serve_count + 1 WHERE url=?", (url,)
        )
        return decoy_html


def disarm_decoy(url: str):
    """Called once the site owner confirms the real page has been cleaned."""
    with _db() as conn:
        conn.execute("DELETE FROM decoy_state WHERE url=?", (url,))
