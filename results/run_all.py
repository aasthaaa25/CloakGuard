"""
One-click run_all script.
Runs everything in order:
  Phase 1: train URL-lexical model (14 graphs)
  Phase 2: build multimodal dataset + train multimodal ensemble (7 new graphs)
  Phase 3: generate HTML report
  Phase 4: run full test suite (53 tests)

Usage:
  python run_all.py                  # full run (uses baked crawl data)
  python run_all.py --recrawl N      # optional: re-crawl N URLs before training
"""

import sys
import json
import argparse
import subprocess
from pathlib import Path

ROOT   = Path(__file__).resolve().parent
PYTHON = sys.executable


def run(cmd: list, label: str, cwd=None):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, cwd=cwd or ROOT)
    if result.returncode != 0:
        print(f"\n[FAIL] Step '{label}' exited with code {result.returncode}")
        print("Fix the error above and re-run run_all.py")
        sys.exit(result.returncode)
    print(f"  ✓ {label} — done")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recrawl", type=int, default=0,
                    help="Re-crawl N URLs before training (0 = use baked data)")
    args = ap.parse_args()

    print("\n" + "=" * 60)
    print("  Active Defense System — Full Run (Phase 1 + Phase 2)")
    print("  First run: ~3–5 min.  Subsequent runs: ~1–2 min.")
    print("=" * 60)

    # Phase 1: URL-lexical model (14 graphs, ~2 min)
    run([PYTHON, "detection/train_model.py"],
        "Phase 1/4: Training URL-lexical detection model (14 graphs)")

    # Phase 2a: (optional) re-crawl
    if args.recrawl > 0:
        run([PYTHON, "-m", "detection.pipeline.crawl",
             "--sample", str(args.recrawl)],
            f"Phase 2a/4: Live dual-view crawl of {args.recrawl} URLs")

    # Phase 2b: build multimodal dataset
    parquet = ROOT / "data" / "multimodal_features.parquet"
    if not parquet.exists() or args.recrawl > 0:
        run([PYTHON, "-c",
             "from detection.pipeline.dataset import build_dataset; "
             "build_dataset(force_rebuild=True)"],
            "Phase 2b/4: Building multimodal feature dataset")
    else:
        print("\n  [skip] Multimodal dataset already exists — use --recrawl N to rebuild")

    # Phase 2c: multimodal training (7 new graphs)
    run([PYTHON, "detection/train_multimodal.py"],
        "Phase 2c/4: Training multimodal ensemble (7 new graphs)")

    # Phase 3: HTML report
    run([PYTHON, "detection/make_report.py"],
        "Phase 3/4: Building HTML report (21 graphs total)")

    # Phase 4: Test suite
    run([PYTHON, "-m", "pytest", "tests/", "-v", "--tb=short"],
        "Phase 4/4: Running full test suite")

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  ALL STEPS COMPLETE")
    print("=" * 60)

    metrics_path = ROOT / "detection" / "artifacts" / "metrics.json"
    mm_metrics_path = ROOT / "detection" / "artifacts" / "multimodal_metrics.json"

    if metrics_path.exists():
        with open(metrics_path) as f:
            m = json.load(f)
        print(f"\n  ── Phase 1 (URL-lexical, 160k URLs) ──")
        print(f"  Headline   LogisticRegression: "
              f"acc={m['models']['LogisticRegression']['accuracy']:.4f}  "
              f"auc={m['models']['LogisticRegression']['roc_auc']:.4f}")
        print(f"  Best       Ensemble:           "
              f"acc={m['models']['Ensemble']['accuracy']:.4f}  "
              f"auc={m['models']['Ensemble']['roc_auc']:.4f}")

    if mm_metrics_path.exists():
        with open(mm_metrics_path) as f:
            mm = json.load(f)
        ens = mm["models"].get("Ensemble_multimodal", {})
        print(f"\n  ── Phase 2 (Multimodal fusion, live crawl + backbone) ──")
        print(f"  Fused Ensemble: acc={ens.get('accuracy',0):.4f}  "
              f"f1={ens.get('f1',0):.4f}  auc={ens.get('roc_auc',0):.4f}")
        print(f"  Features used:  {mm.get('feature_count', '?')} total "
              f"(41 URL-lexical + 22 multimodal)")

    report_path = ROOT / "report" / "report.html"
    graphs_dir  = ROOT / "detection" / "artifacts" / "graphs"
    n_graphs    = len(list(graphs_dir.glob("*.png"))) if graphs_dir.exists() else 0

    print(f"\n  HTML report:    {report_path}")
    print(f"  Graphs ({n_graphs}):    {graphs_dir}/")
    print(f"  Crawl sample:   {ROOT / 'data' / 'crawl_sample'}/")
    print("\n  Open the report:")
    print("    macOS:   open report/report.html")
    print("    Windows: start report\\report.html")
    print()


if __name__ == "__main__":
    main()
