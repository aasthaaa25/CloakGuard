"""
Stage 5 — Jargon asymmetry.

This module measures promotional-keyword composition in the two captured
views. It is a heuristic signal, not a cloaking label.

Definitions
-----------
Text source: visible text plus the title, truncated to 5,000 characters,
then up to 100 extracted link strings. Tokenization for the keyword counts
is regular-expression search, not a linguistic tokenizer. Matching is
case-insensitive. Keywords that appear in more than one category are counted
in each category whose pattern matches, so categories may overlap.

The six categories are defined in promotion.PROMO_CATEGORIES:
gambling, pharma, adult, replica_luxury, finance_scam, generic_spam.

Hit vector: raw match counts, one bin per category.
Mass: sum of those raw counts. This is promotional quantity, not category
composition. A zero-hit view has mass 0.

Distribution: the hit vector divided by its sum. A zero-hit view is left as
the zero vector and is not turned into a uniform distribution.

Jensen-Shannon divergence: the divergence (not the square-root distance)
between the two distributions, using log base 2, so the value is in [0, 1]
when both views have at least one hit. If both views have zero hits, the
divergence is 0. If only one view has hits, the divergence is 1. No Laplace
smoothing is added, because smoothing a zero-hit view would invent a uniform
vocabulary.

Density: mass divided by the number of whitespace-separated tokens in the
same text window. Zero tokens yield density 0.

Combined heuristic score, fixed before any test-set inspection:
    positive_density_gap = clip((bot_density - human_density) / 0.5, 0, 1)
    jargon_asymmetry_score = clip(0.60 * positive_density_gap + 0.40 * jsd, 0, 1)

The 0.5 scale treats a bot-minus-human density gap of 0.5 as saturation.
The 0.60/0.40 weights are a declared heuristic. They were not selected on a
held-out cloaking test, because this repository does not contain an
independently labeled cloaking test set. Component signals are returned so
a later study can compare them without treating this score as ground truth.
"""

from __future__ import annotations

import math
import re
from typing import Dict

import numpy as np

from .promotion import PROMO_CATEGORIES, _COMPILED


CATEGORY_NAMES = list(PROMO_CATEGORIES.keys())
N_CATEGORIES = len(CATEGORY_NAMES)
JSD_LOG_BASE = 2
DENSITY_SCALE = 0.5
JARGON_WEIGHT = 0.60
JSD_WEIGHT = 0.40
_TOKEN_RE = re.compile(r"\S+")


def _window(text: str, links: set) -> str:
    link_text = " ".join(list(links)[:100]) if links else ""
    return ((text or "")[:5000] + " " + link_text).strip()


def _hit_counts(window: str) -> np.ndarray:
    vec = np.zeros(N_CATEGORIES, dtype=float)
    for i, cat in enumerate(CATEGORY_NAMES):
        vec[i] = len(_COMPILED[cat].findall(window))
    return vec


def _distribution(counts: np.ndarray) -> np.ndarray:
    total = float(counts.sum())
    if total <= 0:
        return np.zeros_like(counts)
    return counts / total


def _js_divergence(p: np.ndarray, q: np.ndarray) -> float:
    """Jensen-Shannon divergence in bits. Not the square-root JS distance."""
    p_mass = float(p.sum())
    q_mass = float(q.sum())
    if p_mass <= 0 and q_mass <= 0:
        return 0.0
    if p_mass <= 0 or q_mass <= 0:
        return 1.0
    m = 0.5 * (p + q)

    def kl(a: np.ndarray, b: np.ndarray) -> float:
        mask = (a > 0) & (b > 0)
        if not np.any(mask):
            return 0.0
        return float(np.sum(a[mask] * (np.log(a[mask] / b[mask]) / math.log(JSD_LOG_BASE))))

    return float(np.clip(0.5 * kl(p, m) + 0.5 * kl(q, m), 0.0, 1.0))


def _density(mass: float, window: str) -> float:
    n_tokens = len(_TOKEN_RE.findall(window))
    if n_tokens == 0:
        return 0.0
    return float(mass) / float(n_tokens)


def compute_jargon_asymmetry(artifacts: dict, crawl_record: dict) -> dict:
    """Return the heuristic jargon score and the component signals."""
    del crawl_record  # views are already in artifacts; kept for call-site compatibility
    h = artifacts.get("human", {})
    b = artifacts.get("bot", {})
    h_window = _window((h.get("text", "") or "") + " " + (h.get("title", "") or ""), artifacts.get("human_links", set()) or set())
    b_window = _window((b.get("text", "") or "") + " " + (b.get("title", "") or ""), artifacts.get("bot_links", set()) or set())

    counts_h = _hit_counts(h_window)
    counts_b = _hit_counts(b_window)
    vec_h = _distribution(counts_h)
    vec_b = _distribution(counts_b)

    mass_h = float(counts_h.sum())
    mass_b = float(counts_b.sum())
    density_h = _density(mass_h, h_window)
    density_b = _density(mass_b, b_window)
    signed_density_delta = density_b - density_h
    absolute_density_delta = abs(signed_density_delta)
    jsd = _js_divergence(vec_h, vec_b)

    positive_gap = max(0.0, min(signed_density_delta / DENSITY_SCALE, 1.0))
    jargon_asymmetry_score = float(np.clip(JARGON_WEIGHT * positive_gap + JSD_WEIGHT * jsd, 0.0, 1.0))

    per_category_asymmetry = {
        cat: float(counts_b[i] - counts_h[i]) for i, cat in enumerate(CATEGORY_NAMES)
    }
    dominant_category = max(per_category_asymmetry, key=per_category_asymmetry.get)

    return {
        "jargon_asymmetry_score": jargon_asymmetry_score,
        "jargon_mass_bot": mass_b,
        "jargon_mass_human": mass_h,
        "jargon_mass_delta": mass_b - mass_h,
        "jargon_density_bot": density_b,
        "jargon_density_human": density_h,
        "jargon_signed_density_delta": signed_density_delta,
        "jargon_absolute_density_delta": absolute_density_delta,
        "jargon_jsd": jsd,
        "jsd_log_base": JSD_LOG_BASE,
        "jsd_definition": "jensen_shannon_divergence_bits",
        "jsd_smoothing": "none; both-empty -> 0; one-empty -> 1",
        "scale_factor": DENSITY_SCALE,
        "heuristic_weights": {"positive_density_gap": JARGON_WEIGHT, "jsd": JSD_WEIGHT},
        "weights_validated_on_held_out_cloaking_test": False,
        "per_category_asymmetry": per_category_asymmetry,
        "dominant_jargon_category": dominant_category if jargon_asymmetry_score > 0.05 else "none",
        "jargon_vector_human": vec_h.tolist(),
        "jargon_vector_bot": vec_b.tolist(),
        "category_names": CATEGORY_NAMES,
        "alternatives": {
            "human_density": density_h,
            "bot_density": density_b,
            "signed_density_delta": signed_density_delta,
            "absolute_density_delta": absolute_density_delta,
            "vocabulary_divergence": jsd,
            "combined_jargon_score": jargon_asymmetry_score,
        },
    }
