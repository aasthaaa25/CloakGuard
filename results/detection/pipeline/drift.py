"""
Stage 3 — Drift Feature Extraction
Computes cross-view drift features comparing human-view vs bot-view artifacts.

Modalities:
  - HTML size drift (byte-level)
  - DOM tag-distribution drift (Jensen-Shannon divergence)
  - Link-set drift (Jaccard distance)
  - Text-content drift (character-level diff ratio)
  - Visual drift (SSIM / pixel-delta, if screenshots available)
"""

import math
import difflib
from typing import Optional

import numpy as np

# optional visual diff
try:
    from skimage.metrics import structural_similarity as _ssim
    from PIL import Image
    import io as _io
    _VISUAL = True
except ImportError:
    _VISUAL = False


def _js_divergence(p_dict: dict, q_dict: dict) -> float:
    """Jensen-Shannon divergence between two tag-distribution dicts."""
    keys = set(p_dict) | set(q_dict)
    p_total = max(sum(p_dict.values()), 1)
    q_total = max(sum(q_dict.values()), 1)
    p = np.array([p_dict.get(k, 0) / p_total for k in keys])
    q = np.array([q_dict.get(k, 0) / q_total for k in keys])
    m = 0.5 * (p + q)

    def kl(a, b):
        mask = (a > 0) & (b > 0)
        return float(np.sum(a[mask] * np.log(a[mask] / b[mask])))

    return float(0.5 * kl(p, m) + 0.5 * kl(q, m))


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return 1.0 - inter / union if union > 0 else 0.0


def _text_diff_ratio(t1: str, t2: str) -> float:
    if not t1 and not t2:
        return 0.0
    if not t1 or not t2:
        return 1.0
    sm = difflib.SequenceMatcher(None, t1[:3000], t2[:3000])
    return 1.0 - sm.ratio()


def _visual_drift(path_human: Optional[str], path_bot: Optional[str]) -> dict:
    """Compute visual drift between two screenshots using SSIM."""
    result = {"visual_ssim": 1.0, "visual_pixel_delta": 0.0, "have_visual": False}
    if not _VISUAL or not path_human or not path_bot:
        return result
    try:
        img_h = Image.open(path_human).convert("L").resize((256, 192))
        img_b = Image.open(path_bot).convert("L").resize((256, 192))
        arr_h = np.array(img_h)
        arr_b = np.array(img_b)
        ssim_val = float(_ssim(arr_h, arr_b, data_range=255))
        pixel_delta = float(np.mean(np.abs(arr_h.astype(float) - arr_b.astype(float)))) / 255.0
        result.update({
            "visual_ssim": ssim_val,
            "visual_pixel_delta": pixel_delta,
            "have_visual": True,
        })
    except Exception:
        pass
    return result


def _clamp(x: float, lo=0.0, hi=1.0) -> float:
    return max(lo, min(hi, x))


def compute_cross_view_drift(artifacts: dict, crawl_record: dict) -> dict:
    """
    Stage 3 entry point.
    Input:  artifacts from extract_dual_artifacts()
    Output: drift dict with drift_score + sub-features.
    """
    h = artifacts.get("human", {})
    b = artifacts.get("bot",   {})

    # 1. HTML size drift
    h_bytes = h.get("html_bytes", 0)
    b_bytes = b.get("html_bytes", 0)
    max_bytes = max(h_bytes, b_bytes, 1)
    html_size_drift = abs(h_bytes - b_bytes) / max_bytes

    # 2. DOM tag-distribution drift (JSD)
    dom_drift = _clamp(_js_divergence(
        h.get("tag_distribution", {}),
        b.get("tag_distribution", {}),
    ))

    # 3. Link-set drift
    link_drift = _jaccard(
        artifacts.get("human_links", set()),
        artifacts.get("bot_links",   set()),
    )

    # 4. Text drift
    text_drift = _text_diff_ratio(h.get("text", ""), b.get("text", ""))

    # 5. Bot-only links count (absolute)
    bot_only_count = len(artifacts.get("bot_only_links", set()))

    # 6. Visual drift
    visual = _visual_drift(
        h.get("screenshot_path"),
        b.get("screenshot_path"),
    )

    # Title drift
    title_h = h.get("title", "").lower().strip()
    title_b = b.get("title", "").lower().strip()
    title_drift = 0.0 if title_h == title_b else _text_diff_ratio(title_h, title_b)

    # Aggregate drift_score: weighted combination
    # Visual gets weight only when available
    if visual["have_visual"]:
        visual_component = 1.0 - visual["visual_ssim"]  # 0=identical, 1=totally different
        drift_score = _clamp(
            0.25 * html_size_drift +
            0.25 * dom_drift +
            0.20 * text_drift +
            0.15 * visual_component +
            0.10 * link_drift +
            0.05 * min(bot_only_count / 10.0, 1.0)
        )
    else:
        drift_score = _clamp(
            0.30 * html_size_drift +
            0.30 * dom_drift +
            0.25 * text_drift +
            0.10 * link_drift +
            0.05 * min(bot_only_count / 10.0, 1.0)
        )

    return {
        "drift_score":       drift_score,
        "html_size_drift":   html_size_drift,
        "dom_drift":         dom_drift,
        "link_drift":        link_drift,
        "text_drift":        text_drift,
        "title_drift":       title_drift,
        "bot_only_link_count": bot_only_count,
        "visual_ssim":       visual["visual_ssim"],
        "visual_pixel_delta": visual["visual_pixel_delta"],
        "have_visual":       visual["have_visual"],
        # sub-feature alias used by train_multimodal.py
        "html_size_diff":    artifacts.get("html_size_diff", 0),
    }
