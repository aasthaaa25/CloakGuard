"""
Stage 5 — Jargon Asymmetry Analysis
The core cloaking signal: legitimate pages use the same language for humans
and bots. Cloaked pages inject promotional/SEO jargon ONLY for bots.

Jargon asymmetry = how different the two views' domain-jargon fingerprints are.

Computation:
  1. Build a normalized jargon-category vector for each view
     (fraction of promotional-jargon hits in each of 6 categories).
  2. jargon_mass_bot  = total normalized jargon in bot view
     jargon_mass_human = total normalized jargon in human view
  3. jargon_asymmetry_raw = jargon_mass_bot − jargon_mass_human
     (positive = bot sees more jargon than human → cloaking signal)
  4. jargon_jsd = Jensen-Shannon divergence between the two vectors
     (high divergence = different jargon MIX, even if total mass similar)
  5. jargon_asymmetry_score = 0.6 * clamp(raw/0.5) + 0.4 * jsd
     (combined metric in [0, 1], higher = more suspicious)
"""

import math
from typing import Dict

import numpy as np
from .promotion import PROMO_CATEGORIES, _COMPILED


CATEGORY_NAMES = list(PROMO_CATEGORIES.keys())
N_CATEGORIES   = len(CATEGORY_NAMES)


def _jargon_vector(text: str, links: set) -> np.ndarray:
    """
    Returns a normalized L1 vector of promotional-jargon hit counts
    across the 6 categories. Sum = 1 if any jargon present, else all zeros.
    """
    combined = text[:5000] + " " + " ".join(list(links)[:100])
    vec = np.zeros(N_CATEGORIES)
    for i, cat in enumerate(CATEGORY_NAMES):
        hits = len(_COMPILED[cat].findall(combined))
        vec[i] = hits
    total = vec.sum()
    if total > 0:
        vec = vec / total  # normalize to probability distribution
    return vec


def _js_divergence_vec(p: np.ndarray, q: np.ndarray) -> float:
    m = 0.5 * (p + q)
    def kl(a, b):
        mask = (a > 1e-12) & (b > 1e-12)
        return float(np.sum(a[mask] * np.log(a[mask] / b[mask])))
    return float(0.5 * kl(p, m) + 0.5 * kl(q, m))


def compute_jargon_asymmetry(artifacts: dict, crawl_record: dict) -> dict:
    """
    Stage 5 entry point.
    Returns jargon_asymmetry_score + all per-category and vector sub-features.
    """
    h = artifacts.get("human", {})
    b = artifacts.get("bot",   {})

    h_text  = (h.get("text", "") or "") + " " + (h.get("title", "") or "")
    b_text  = (b.get("text", "") or "") + " " + (b.get("title", "") or "")
    h_links = artifacts.get("human_links", set()) or set()
    b_links = artifacts.get("bot_links",   set()) or set()

    vec_h = _jargon_vector(h_text, h_links)
    vec_b = _jargon_vector(b_text, b_links)

    # Raw masses (before normalizing)
    mass_h = float(np.sum(vec_h))
    mass_b = float(np.sum(vec_b))

    # Asymmetry raw = bot − human jargon mass  (range: −1 to +1)
    jargon_mass_delta = mass_b - mass_h  # positive → bot sees more spam

    # JSD between the two normalized vectors
    jsd = _js_divergence_vec(vec_h, vec_b)

    # Per-category asymmetry
    per_category_asymmetry = {
        cat: float(vec_b[i] - vec_h[i])
        for i, cat in enumerate(CATEGORY_NAMES)
    }
    dominant_category = max(per_category_asymmetry, key=per_category_asymmetry.get)

    # Combined score in [0, 1]
    raw_norm = max(0.0, min(jargon_mass_delta / 0.5, 1.0))  # clamp to [0,1]
    jargon_asymmetry_score = float(np.clip(0.60 * raw_norm + 0.40 * jsd, 0.0, 1.0))

    return {
        "jargon_asymmetry_score":  jargon_asymmetry_score,
        "jargon_mass_bot":         mass_b,
        "jargon_mass_human":       mass_h,
        "jargon_mass_delta":       jargon_mass_delta,
        "jargon_jsd":              jsd,
        "per_category_asymmetry":  per_category_asymmetry,
        "dominant_jargon_category": dominant_category if jargon_asymmetry_score > 0.05 else "none",
        "jargon_vector_human":     vec_h.tolist(),
        "jargon_vector_bot":       vec_b.tolist(),
        "category_names":          CATEGORY_NAMES,
    }
