"""
detection.pipeline — Full Multimodal Detection Pipeline

Stages:
  1. crawl.py      — dual_view_crawl() → human + bot HTML/DOM/screenshots
  2. artifacts.py  — extract_dual_artifacts() → structured view artifacts
  3. drift.py      — compute_cross_view_drift() → DOM/text/visual drift features
  4. promotion.py  — compute_promotional_score() → per-category promo features
  5. jargon.py     — compute_jargon_asymmetry() → jargon asymmetry score
  6. fusion.py     — fuse_risk_scores() → final verdict
  7. labels.py     — label generation
  8. dataset.py    — training dataset assembly
"""

from .crawl     import dual_view_crawl, VIEW_PROFILES
from .artifacts import extract_dual_artifacts
from .drift     import compute_cross_view_drift
from .promotion import compute_promotional_score
from .jargon    import compute_jargon_asymmetry
from .fusion    import fuse_risk_scores
from .labels    import label_from_csv, label_from_fusion
from .dataset   import build_dataset

__all__ = [
    "dual_view_crawl",
    "VIEW_PROFILES",
    "extract_dual_artifacts",
    "compute_cross_view_drift",
    "compute_promotional_score",
    "compute_jargon_asymmetry",
    "fuse_risk_scores",
    "label_from_csv",
    "label_from_fusion",
    "build_dataset",
]
