"""
URL Feature Engineering — shared by training pipeline and live detection runtime.

Every feature produced here must be used identically at training time and inference
time so the model sees the same representation in both contexts.

LEAKAGE GUARD: The following columns from the raw CSV are EXCLUDED — they either
encode the label or are derived from empty content columns:
  crawl_status, fusion_score, drift_score,
  text_len, html_len, text_word_count, text_unique_word_count,
  text_avg_word_len, text_digit_count, text_special_count, text_upper_ratio,
  title_len, title_word_count, title_digit_count, title_special_count, title_upper_ratio,
  title_missing, text_missing, html_missing
"""

import re
import math
from urllib.parse import urlparse, parse_qs
from typing import Union
import numpy as np
import pandas as pd

# ── SUSPICIOUS KEYWORD LIST (promo/malicious tokens common in cloaked URLs) ──
SUSPICIOUS_KEYWORDS = {
    "login", "signin", "secure", "account", "verify", "confirm", "update",
    "free", "bonus", "casino", "poker", "slots", "bet", "gambling", "lottery",
    "prize", "winner", "claim", "reward", "offer", "discount", "cheap", "buy",
    "pharmacy", "pills", "viagra", "cialis", "drugs", "meds", "rx",
    "porn", "xxx", "adult", "nude", "sexy",
    "hack", "crack", "keygen", "warez", "torrent", "pirate",
    "phishing", "malware", "virus", "trojan",
    "click", "redirect", "tracking", "affiliate",
}

# ── TLDs commonly abused in cloaking campaigns ─────────────────────────────
SUSPICIOUS_TLDS = {".tk", ".ml", ".ga", ".cf", ".gq", ".pw", ".cc", ".to",
                   ".link", ".click", ".download", ".stream", ".zip"}

# ── Original 16 lexical columns from the CSV that ARE real features ─────────
ORIGINAL_LEXICAL_COLS = [
    "url_len", "host_len", "path_len", "query_len",
    "num_path_slashes", "num_dots", "num_hyphens", "num_digits",
    "num_underscores", "num_at", "num_percent",
    "has_query", "has_https", "has_ip_host",
    "suspicious_token_count", "token_count",
]


def _shannon_entropy(s: str) -> float:
    """Shannon entropy of a string — high entropy suggests obfuscated/random tokens."""
    if not s:
        return 0.0
    counts = {}
    for c in s:
        counts[c] = counts.get(c, 0) + 1
    n = len(s)
    return -sum((v / n) * math.log2(v / n) for v in counts.values())


def _max_consecutive_digits(s: str) -> int:
    """Longest run of consecutive digits — long runs = IP-like or random IDs."""
    groups = re.findall(r"\d+", s)
    return max((len(g) for g in groups), default=0)


def _subdomain_count(hostname: str) -> int:
    """Number of subdomains (dots in hostname minus 1, floored at 0)."""
    parts = hostname.strip(".").split(".")
    return max(0, len(parts) - 2)


def _tld(hostname: str) -> str:
    parts = hostname.strip(".").split(".")
    return ("." + parts[-1]) if parts else ""


def _query_param_count(query_str: str) -> int:
    if not query_str:
        return 0
    return len(parse_qs(query_str, keep_blank_values=True))


def build_url_features(url: str) -> dict:
    """
    Parse a single URL string and return a flat dict of all engineered features.
    Used at inference time (one URL at a time) and vectorized over the CSV at
    training time via transform(df).
    """
    features = {}

    # ── Parse URL structure ──────────────────────────────────────────────────
    try:
        parsed = urlparse(url if url.startswith("http") else "http://" + url)
    except Exception:
        parsed = urlparse("")

    scheme   = parsed.scheme or ""
    hostname = parsed.hostname or parsed.netloc or ""
    path     = parsed.path or ""
    query    = parsed.query or ""
    full_url = url or ""

    # ── Lengths ──────────────────────────────────────────────────────────────
    features["url_len"]   = len(full_url)
    features["host_len"]  = len(hostname)
    features["path_len"]  = len(path)
    features["query_len"] = len(query)

    # ── Count-based URL structure ────────────────────────────────────────────
    features["num_path_slashes"] = path.count("/")
    features["num_dots"]         = full_url.count(".")
    features["num_hyphens"]      = full_url.count("-")
    features["num_digits"]       = sum(c.isdigit() for c in full_url)
    features["num_underscores"]  = full_url.count("_")
    features["num_at"]           = full_url.count("@")
    features["num_percent"]      = full_url.count("%")

    # ── Boolean flags ────────────────────────────────────────────────────────
    features["has_query"]   = int(bool(query))
    features["has_https"]   = int(scheme == "https")
    features["has_ip_host"] = int(bool(re.match(r"^\d{1,3}(\.\d{1,3}){3}$", hostname)))

    # ── Token-based ───────────────────────────────────────────────────────────
    tokens = re.split(r"[/\-_.?=&%+#@!~]", full_url.lower())
    tokens = [t for t in tokens if t]
    features["token_count"] = len(tokens)
    features["suspicious_token_count"] = sum(
        1 for t in tokens if t in SUSPICIOUS_KEYWORDS
    )

    # ════ AUGMENTED FEATURES (engineered on top of the raw dataset) ══════════

    # ── Entropy ──────────────────────────────────────────────────────────────
    features["url_entropy"]  = _shannon_entropy(full_url)
    features["path_entropy"] = _shannon_entropy(path)
    features["host_entropy"] = _shannon_entropy(hostname)

    # ── Character composition ratios ─────────────────────────────────────────
    n = max(len(full_url), 1)
    features["digit_ratio"]   = sum(c.isdigit() for c in full_url) / n
    features["letter_ratio"]  = sum(c.isalpha() for c in full_url) / n
    features["special_ratio"] = sum(not c.isalnum() and c not in ":/._-@" for c in full_url) / n
    vowels = set("aeiouAEIOU")
    features["vowel_ratio"]   = sum(c in vowels for c in full_url) / n

    # ── Structural enrichments ────────────────────────────────────────────────
    features["subdomain_count"]     = _subdomain_count(hostname)
    features["path_depth"]          = path.count("/")  # alias for clarity
    features["query_param_count"]   = _query_param_count(query)
    features["max_consecutive_digits"] = _max_consecutive_digits(full_url)

    # ── Token-length statistics ────────────────────────────────────────────────
    token_lens = [len(t) for t in tokens] if tokens else [0]
    features["longest_token_len"] = max(token_lens)
    features["mean_token_len"]    = float(np.mean(token_lens))

    # ── Suspicious structural flags ───────────────────────────────────────────
    features["is_punycode"]       = int("xn--" in hostname.lower())
    features["is_ipfs_host"]      = int(any(
        s in hostname.lower() for s in ["ipfs", "fleek", "cf-ipfs", "dweb.link"]
    ))
    features["is_hex_host"]       = int(bool(re.match(r"^[0-9a-f]{32,}$", hostname.lower())))
    features["has_suspicious_tld"] = int(_tld(hostname) in SUSPICIOUS_TLDS)
    features["has_double_slash"]  = int("//" in path)
    features["has_at_in_path"]    = int("@" in path)
    features["has_redirect_token"] = int(any(t in full_url.lower() for t in
                                             ["redirect", "redir", "url=", "goto=", "forward="]))
    features["has_encoded_chars"] = int("%" in full_url)
    features["num_query_params"]  = features["query_param_count"]  # duplicate for compat

    # ── Suspicious keyword in different URL regions ────────────────────────────
    features["suspicious_in_host"]  = int(any(kw in hostname.lower() for kw in SUSPICIOUS_KEYWORDS))
    features["suspicious_in_path"]  = int(any(kw in path.lower() for kw in SUSPICIOUS_KEYWORDS))
    features["suspicious_in_query"] = int(any(kw in query.lower() for kw in SUSPICIOUS_KEYWORDS))

    return features


# ── VECTORIZED TRANSFORM for DataFrame (used in training) ─────────────────────

def transform(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply build_url_features() to a DataFrame that has a 'url' column.
    Returns a new DataFrame of features only (no label, no leakage columns).
    """
    feature_rows = df["url"].apply(build_url_features)
    return pd.DataFrame(list(feature_rows))


def get_feature_names() -> list:
    """Return the ordered list of feature column names (matches build_url_features keys)."""
    dummy = build_url_features("https://example.com/path/to/page?q=test&v=1")
    return list(dummy.keys())


FEATURE_NAMES = get_feature_names()
N_FEATURES = len(FEATURE_NAMES)


if __name__ == "__main__":
    test_urls = [
        "https://bafybeidzso4mumpjqm2d4ehwtdtsylrd4kskmpdrrgyyrew7rl3slvzjau.ipfs.cf-ipfs.com/",
        "https://sansebastianshops.com/el-que-tiene-tienda-que-se-atienda-work-cafe/",
        "https://www.cafepress.com/+sparkling_cardinal_shot_glass,1073567754",
        "https://free-casino-bonus-slots.tk/redirect?url=http://spam.cc/pills",
    ]
    for url in test_urls:
        feats = build_url_features(url)
        print(f"\nURL: {url[:70]}")
        print(f"  entropy={feats['url_entropy']:.3f}  path_depth={feats['path_depth']}"
              f"  suspicious_tokens={feats['suspicious_token_count']}"
              f"  digit_ratio={feats['digit_ratio']:.3f}")
    print(f"\nTotal features: {N_FEATURES}")
