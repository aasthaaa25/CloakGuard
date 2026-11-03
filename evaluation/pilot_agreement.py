"""Report pilot annotation completeness and agreement without assigning labels."""

import csv
import json
from pathlib import Path

from sklearn.metrics import cohen_kappa_score

ROOT = Path(__file__).resolve().parents[1]
ANNOTATIONS = ROOT / "data" / "annotation"
LABELS = (
    "supported_malicious_cloaking", "benign_profile_dependent_difference",
    "no_suspicious_difference_observed", "bot_challenge_or_access_difference",
    "uncertain", "unusable",
)


def load_sheet(path):
    with path.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    if len({row["capture_id"] for row in rows}) != len(rows):
        raise ValueError(f"Duplicate capture ID in {path}")
    for row in rows:
        label = row["review_label"]
        if label and (label not in LABELS or not row["reviewer_id"] or not row["evidence_reference"]):
            raise ValueError(f"Invalid or unsupported annotation in {path}")
    return {row["capture_id"]: row for row in rows}


def agreement(first, second):
    if not first or first.keys() != second.keys():
        raise ValueError("Reviewer sheets must cover the same nonempty pilot")
    completed = []
    for capture_id, a in first.items():
        b = second[capture_id]
        if not a["review_label"] or not b["review_label"]:
            continue
        if a["reviewer_id"] == b["reviewer_id"]:
            raise ValueError(f"Reviewers must be distinct for {capture_id}")
        completed.append((a["review_label"], b["review_label"]))

    report = {"pilot_pairs": len(first), "double_reviewed_pairs": len(completed)}
    if len(completed) != len(first):
        return {**report, "status": "awaiting_complete_independent_review"}

    def metrics(a, b):
        return {
            "raw_agreement": sum(x == y for x, y in zip(a, b)) / len(a),
            "kappa": float(cohen_kappa_score(a, b)) if len(set(a) | set(b)) > 1 else None,
        }

    a, b = zip(*completed)
    return {
        **report, "status": "complete", "overall": metrics(a, b),
        "by_label": {
            label: metrics([value == label for value in a], [value == label for value in b])
            for label in LABELS
        },
    }


if __name__ == "__main__":
    report = agreement(
        load_sheet(ANNOTATIONS / "pilot_30_reviewer_1.csv"),
        load_sheet(ANNOTATIONS / "pilot_30_reviewer_2_blank.csv"),
    )
    destination = ROOT / "evaluation" / "outputs" / "pilot_agreement.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(destination)
