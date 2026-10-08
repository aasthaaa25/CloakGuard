"""
Central configuration. Every threshold lives here so the system
can be tuned without hunting through multiple files — and so
Day 2's validation can report exactly what was tuned and why.
"""

import os

# ── Paths ────────────────────────────────────────────────────
BLOCKLIST_DB_PATH    = os.getenv("BLOCKLIST_DB_PATH",    "data/blocklist.db")
DECOY_DB_PATH        = os.getenv("DECOY_DB_PATH",        "data/decoy_state.db")
FORENSICS_OUTPUT_DIR = os.getenv("FORENSICS_OUTPUT_DIR", "logs/forensics")

# ── Origin server (the real site being protected) ──────────
ORIGIN_SERVER_URL = os.getenv("ORIGIN_SERVER_URL", "http://127.0.0.1:8000")

# ── Fingerprint scoring ──────────────────────────────────────
SCORE_INCREMENT_ON_CLOAK_MATCH = 25.0
SCORE_DECAY_PER_HOUR           = 1.0          # fingerprint trust recovers over time
RATE_LIMIT_SCORE_THRESHOLD     = 25.0         # one confirmed match -> immediate rate limit
HARD_BLOCK_SCORE_THRESHOLD     = 75.0         # repeated matches -> hard block

# Populate via Day 1 calibration run (§1.10) against verified
# Googlebot/Bingbot traffic BEFORE going anywhere near production.
GOOGLEBOT_ALLOWLIST_JA3: set = set()

# ── Rate limiting ─────────────────────────────────────────────
RATE_LIMIT_TOKENS_PER_MINUTE = 5
RATE_LIMIT_BUCKET_SIZE       = 10

# ── Decoy engine ───────────────────────────────────────────────
DECOY_TTL_HOURS = 72   # auto-disarm after 3 days even if not manually cleared

# ── Detection pipeline thresholds (imported from your Day 5 fusion config) ──
ALERT_THRESHOLD            = 0.50
HIGH_CONFIDENCE_THRESHOLD  = 0.75

# ── Forensics (Layer 3) ───────────────────────────────────────
DEEP_SCAN_TRIGGER_THRESHOLD = ALERT_THRESHOLD
PASSIVE_DNS_API_KEY         = os.getenv("PASSIVE_DNS_API_KEY", "")

# ── §1.10 Calibration: log-only mode flag ─────────────────────
# When LOG_ONLY=true the middleware forwards everything and never blocks/decoys
# — used during the initial Googlebot-allowlist calibration run.
LOG_ONLY = os.getenv("LOG_ONLY", "false").lower() in ("true", "1", "yes")
