"""
Stage 4 — Promotional Feature Extraction
Detects SEO-spam / promotional injection by scanning both views for keyword
categories and measuring the bot-vs-human asymmetry.

Categories: gambling, pharma, adult, replica_luxury, finance_scam, generic_spam.
"""

import re
from typing import Dict, List, Set

# ── Keyword dictionaries per category ─────────────────────────────────────────
PROMO_CATEGORIES: Dict[str, List[str]] = {
    "gambling": [
        "casino", "slot", "poker", "betting", "jackpot", "roulette",
        "blackjack", "baccarat", "lottery", "wager", "gamble", "sportsbook",
        "free spins", "bonus casino", "online casino",
    ],
    "pharma": [
        "viagra", "cialis", "levitra", "pharmacy", "prescription", "pill",
        "medication", "drug", "generic pill", "buy pills", "no prescription",
        "weight loss", "diet pill", "buy xanax", "buy tramadol",
    ],
    "adult": [
        "porn", "xxx", "nude", "naked", "escort", "cam girl", "sex chat",
        "adult dating", "hookup", "milf", "onlyfans promo",
    ],
    "replica_luxury": [
        "replica", "fake rolex", "fake gucci", "cheap louis vuitton",
        "knockoff", "copy watch", "imitation", "aaa quality",
    ],
    "finance_scam": [
        "get rich quick", "make money fast", "passive income", "crypto pump",
        "binary options", "forex signal", "investment scheme", "money flipping",
        "guaranteed profit", "mlm", "ponzi",
    ],
    "generic_spam": [
        "free download", "click here", "limited offer", "act now",
        "winner", "congratulations", "you have been selected",
        "earn money", "work from home", "lose weight fast",
        "enlarge", "male enhancement",
    ],
}

_COMPILED: Dict[str, re.Pattern] = {
    cat: re.compile("|".join(re.escape(kw) for kw in kws), re.IGNORECASE)
    for cat, kws in PROMO_CATEGORIES.items()
}


def _score_text(text: str) -> Dict[str, int]:
    """Return keyword hit count per category for a piece of text."""
    scores = {}
    for cat, pattern in _COMPILED.items():
        hits = pattern.findall(text)
        if hits:
            scores[cat] = len(hits)
    return scores


def _score_view(artifacts_view: dict) -> dict:
    """Score a single view's artifacts."""
    text = (artifacts_view.get("text", "") or "") + " " + (artifacts_view.get("title", "") or "")
    # also scan link hrefs for spam domains / keyword paths
    link_text = " ".join(artifacts_view.get("links", set()) or set())
    combined = text + " " + link_text
    return _score_text(combined)


def compute_promotional_score(artifacts: dict, crawl_record: dict) -> dict:
    """
    Stage 4 entry point.
    Measures promotional content by category in both views, then computes
    the asymmetry: content shown to bot but NOT to human.
    """
    h_scores = _score_view(artifacts.get("human", {}))
    b_scores = _score_view(artifacts.get("bot",   {}))

    all_cats = set(h_scores) | set(b_scores)
    keyword_categories_found: Dict[str, list] = {}

    total_human_hits = sum(h_scores.values())
    total_bot_hits   = sum(b_scores.values())
    bot_excess_hits  = 0

    for cat in all_cats:
        h_n = h_scores.get(cat, 0)
        b_n = b_scores.get(cat, 0)
        excess = max(0, b_n - h_n)
        bot_excess_hits += excess
        if b_n > 0:
            # record which category appeared
            kws_found = []
            pattern = _COMPILED[cat]
            text_b = (artifacts.get("bot", {}).get("text", "") or "")
            for m in pattern.finditer(text_b[:5000]):
                kws_found.append(m.group(0).lower())
            keyword_categories_found[cat] = list(set(kws_found))[:10]

    # Asymmetry: how much MORE promo content does the bot see vs human?
    total_seen = max(total_bot_hits + total_human_hits, 1)
    promo_asymmetry = bot_excess_hits / (total_bot_hits + 1)  # normalized excess
    promo_asymmetry = min(promo_asymmetry, 1.0)

    # Base promo score: presence in bot view + asymmetry weight
    category_count = len(keyword_categories_found)
    promo_score = min(1.0, (
        0.40 * min(total_bot_hits / 20.0, 1.0) +
        0.35 * promo_asymmetry +
        0.25 * min(category_count / 3.0, 1.0)
    ))

    return {
        "promo_score":               promo_score,
        "promo_asymmetry":           promo_asymmetry,
        "keyword_categories_found":  keyword_categories_found,
        "category_count":            category_count,
        "total_bot_promo_hits":      total_bot_hits,
        "total_human_promo_hits":    total_human_hits,
        "bot_excess_promo_hits":     bot_excess_hits,
        "per_category_human":        h_scores,
        "per_category_bot":          b_scores,
    }
