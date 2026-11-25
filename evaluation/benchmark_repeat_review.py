"""Compare one-pair and repeat-gated review on the saved controlled captures."""

import argparse
import csv
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "results"))
from app.pipeline_bridge.repeat_review import review_repeats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation/outputs/repeat_review.json")
    args = parser.parse_args()
    manifest = ROOT / "testbed/results/v2_captures.csv"
    groups = {}
    with manifest.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            sample = groups.setdefault(row["scenario_id"], {
                "role": row["role"], "url": row["requested_url"], "views": {},
            })
            if row["view_id"] in sample["views"] or sample["role"] != row["role"]:
                raise ValueError(f"Inconsistent capture manifest for {row['scenario_id']}")
            html = (ROOT / row["artifact"]).read_text(encoding="utf-8")
            if sha256(html.encode("utf-8")).hexdigest() != row["artifact_sha256"]:
                raise ValueError(f"Capture hash mismatch for {row['artifact']}")
            sample["views"][row["view_id"]] = {
                "html": html, "status": int(row["status"]), "final_url": row["final_url"],
                "content_type": json.loads(row["response_headers"]).get("content-type", ""),
            }

    rows = []
    counts = {"first_pair": Counter(), "repeat_review": Counter()}
    for name, sample in groups.items():
        if sample["role"] not in {"negative", "positive", "positive_substantial"}:
            raise ValueError(f"Unexpected fixture role for {name}")
        positive = sample["role"] != "negative"
        result = review_repeats(sample["url"], sample["views"])
        if result["verdict"] == "incomplete":
            raise ValueError(f"Incomplete fixture for {name}")
        first = result.pop("first_pair")[3]["alert"]
        for method, alert in (("first_pair", first), ("repeat_review", result["alert"])):
            counts[method][("t" if alert == positive else "f") + ("p" if alert else "n")] += 1
        rows.append({
            "scenario_id": name, "positive": positive, "first_pair_alert": first,
            "repeat_alert": result["alert"], "verdict": result["verdict"],
            "cross_profile_scores": result["cross_profile_scores"],
            "same_profile_scores": result["same_profile_scores"],
        })
    report = {
        "scope": "Retrospective review on scripted captured cases",
        "capture_manifest_sha256": sha256(manifest.read_bytes()).hexdigest(),
        "threshold": result["threshold"],
        "counts": {method: {key: values[key] for key in ("tp", "fp", "tn", "fn")}
                   for method, values in counts.items()},
        "cases": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["counts"], indent=2))


if __name__ == "__main__":
    main()
