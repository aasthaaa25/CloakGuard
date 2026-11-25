"""Stress-test the local review models with both template and scenario exclusions."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import average_precision_score, precision_recall_curve
from sklearn.metrics.pairwise import paired_cosine_distances
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from benchmark_controlled_ml import FEATURES, ROOT, summarize

sys.path.insert(0, str(ROOT / "results"))
from detection.pipeline.artifacts import extract_view_artifacts

KEYS = ["template_family", "scenario_family"]
PROMOTIONAL_TEXT = {"bot_few", "bot_substantial"}


def read_pairs():
    folder = ROOT / "testbed" / "results"
    captures = pd.read_csv(folder / "v2_captures.csv")
    captures["text"] = ""
    for row in captures.itertuples():
        path = ROOT / row.artifact
        html = path.read_text(encoding="utf-8")
        if not row.capture_success or hashlib.sha256(html.encode("utf-8")).hexdigest() != row.artifact_sha256:
            raise ValueError(f"Unsuccessful capture or hash mismatch for {row.artifact}")
        captures.at[row.Index, "text"] = extract_view_artifacts(html)["text"]
    text = captures.pivot(index=KEYS, columns="view_id", values="text").reset_index()
    if text[["H1", "B1", "H2", "B2"]].isna().any().any():
        raise ValueError("Every scenario must have all four capture views")
    snapshots = pd.read_csv(folder / "v2_scores.csv")
    cross = snapshots.loc[snapshots["comparison"].eq("cross_profile")]
    if not cross.groupby(KEYS).size().eq(2).all():
        raise ValueError("Expected precisely two cross-profile scores per scenario")
    # The archived score writer emits H1/B1 first for each scenario.
    pairs = cross.drop_duplicates(KEYS).merge(text, on=KEYS, validate="one_to_one")
    pairs["label"] = pairs["role"].map({"negative": 0, "positive": 1, "positive_substantial": 1})
    pairs["scenario_group"] = pairs["scenario_family"].map(
        lambda scenario: "promotional_text" if scenario in PROMOTIONAL_TEXT else scenario
    )
    if pairs["label"].isna().any() or len(pairs) != len(text):
        raise ValueError("Unexpected label or unmatched capture")
    return pairs


def text_distances(train, test):
    vectorizer = TfidfVectorizer().fit(pd.concat([train["H1"], train["B1"]]))
    def distance(left, right):
        return paired_cosine_distances(vectorizer.transform(left), vectorizer.transform(right))
    cross = distance(test["H1"], test["B1"])
    within = np.maximum(distance(test["H1"], test["H2"]), distance(test["B1"], test["B2"]))
    return pd.DataFrame({"tfidf_distance": cross, "tfidf_excess_over_control": cross - within,
                         "same_profile_tfidf_distance": within}, index=test.index)


def stress_predictions(pairs):
    predictions = []
    for (template, scenario), test in pairs.groupby(["template_family", "scenario_group"]):
        train = pairs.loc[pairs["template_family"].ne(template) & pairs["scenario_group"].ne(scenario)]
        if train["label"].nunique() != 2:
            raise ValueError(f"Training partition lacks both classes for {template}/{scenario}")
        train = train.join(text_distances(train, train))
        test = test.join(text_distances(train, test))
        experiments = {
            "drift_only": ["drift_score"],
            "tfidf_only": ["tfidf_distance"],
            "tfidf_with_control": ["tfidf_distance", "tfidf_excess_over_control"],
            "paired_features": FEATURES,
            "paired_without_jargon": ["drift_score", "promo_score"],
        }
        for name, features in experiments.items():
            model = make_pipeline(StandardScaler(), LogisticRegression())
            model.fit(train[features], train["label"])
            test[name] = model.predict_proba(test[features])[:, 1]
        test["training_rows"] = len(train)
        predictions.append(test)
    return pd.concat(predictions).drop(columns=["H1", "B1", "H2", "B2"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evaluation" / "outputs")
    args = parser.parse_args()
    predictions = stress_predictions(read_pairs())
    labels = predictions["label"]
    methods = ("raw_score", "drift_only", "tfidf_only", "tfidf_with_control",
               "paired_features", "paired_without_jargon")
    curves = []
    report = {}
    for method in methods:
        scores = predictions[method]
        report[method] = summarize(labels, scores, 0.5)
        report[method]["template_f1"] = {
            template: summarize(rows["label"], rows[method], 0.5)["f1"]
            for template, rows in predictions.groupby("template_family")
        }
        precision, recall, thresholds = precision_recall_curve(labels, scores)
        curves.append(pd.DataFrame({"method": method, "precision": precision, "recall": recall,
                                    "threshold": [*thresholds, None]}))
    result = {
        "protocol": "Retrospective controlled stress test. Training excludes all rows sharing either the test template or the test scenario group.",
        "scenario_grouping": "The two visible promotional-text scenarios share a group. Each other scenario forms its own group.",
        "operating_point": "Fixed 0.5 for all methods. Logistic output is uncalibrated. PR curves summarize pooled out-of-fold scores.",
        "rows": len(predictions),
        "positive": int(labels.sum()),
        "negative": int(labels.eq(0).sum()),
        "raw_tfidf_average_precision": float(average_precision_score(labels, predictions["tfidf_distance"])),
        "models": report,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(result, indent=2) + "\n"
    (args.output_dir / "stress_metrics.json").write_text(rendered, encoding="utf-8")
    predictions.to_csv(args.output_dir / "stress_predictions.csv", index=False)
    pd.concat(curves).to_csv(args.output_dir / "stress_pr_curves.csv", index=False)
    print(rendered, end="")


if __name__ == "__main__":
    main()
