"""Compare review classifiers on the existing controlled, template-disjoint captures."""

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd
import sklearn
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, confusion_matrix, f1_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ["drift_score", "promo_score", "jargon_score", "signed_jargon_gap"]


def summarize(labels, scores, threshold):
    predictions = scores >= threshold
    tn, fp, fn, tp = confusion_matrix(labels, predictions, labels=[0, 1]).ravel()
    return {
        "threshold": threshold,
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
        "f1": float(f1_score(labels, predictions, zero_division=0)),
        "average_precision": float(average_precision_score(labels, scores)),
        "roc_auc": float(roc_auc_score(labels, scores)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evaluation" / "outputs")
    args = parser.parse_args()
    scores_path = ROOT / "testbed" / "results" / "v2_scores.csv"
    threshold_path = scores_path.with_name("frozen_detector_v2.json")
    rows = pd.read_csv(scores_path)
    # calibrate_v2.pairs writes H1/B1 first, then H2/B2, for each scenario.
    pairs = rows.loc[rows["comparison"].eq("cross_profile")]
    keys = ["template_family", "scenario_family"]
    if not pairs.groupby(keys).size().eq(2).all():
        raise ValueError("Expected two cross-profile comparisons per template and scenario")
    primary = pairs.drop_duplicates(keys).copy()
    primary["label"] = primary["role"].map({"negative": 0, "positive": 1, "positive_substantial": 1})
    if primary["label"].isna().any() or not primary["scoring_path"].eq("fixed_weight_heuristic").all():
        raise ValueError("Expected controlled scenario labels and fixed-weight inputs")
    train = primary.loc[primary["split"].eq("calibration")]
    test = primary.loc[primary["split"].eq("reserved")].copy()
    train_families = sorted(train["template_family"].unique())
    test_families = sorted(test["template_family"].unique())
    if set(train_families) & set(test_families):
        raise ValueError("Template families overlap")
    threshold = json.loads(threshold_path.read_text(encoding="utf-8"))["decision"]["review_threshold"]

    experiments = {
        "always_negative": (DummyClassifier(strategy="most_frequent"), FEATURES),
        "drift_only_logistic": (make_pipeline(StandardScaler(), LogisticRegression()), ["drift_score"]),
        "paired_feature_logistic": (make_pipeline(StandardScaler(), LogisticRegression()), FEATURES),
    }
    results = {"fixed_heuristic": summarize(test["label"], test["raw_score"], threshold)}
    test["fixed_heuristic_alert"] = test["raw_score"].ge(threshold)
    for name, (model, columns) in experiments.items():
        model.fit(train[columns], train["label"])
        test[name + "_score"] = model.predict_proba(test[columns])[:, 1]
        results[name] = summarize(test["label"], test[name + "_score"], 0.5)
        test[name + "_alert"] = test[name + "_score"].ge(0.5)

    report = {
        "scope": "Retrospective controlled benchmark on scripted HTTP pairs, one H1/B1 pair per scenario per template",
        "sklearn_version": sklearn.__version__,
        "input_sha256": hashlib.sha256(scores_path.read_bytes()).hexdigest(),
        "threshold_manifest_sha256": hashlib.sha256(threshold_path.read_bytes()).hexdigest(),
        "fit_families": train_families,
        "reserved_families": test_families,
        "fit_counts": {"negative": int(train["label"].eq(0).sum()), "positive": int(train["label"].eq(1).sum())},
        "reserved_counts": {"negative": int(test["label"].eq(0).sum()), "positive": int(test["label"].eq(1).sum())},
        "paired_features": FEATURES,
        "models": results,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_text = json.dumps(report, indent=2) + "\n"
    (args.output_dir / "controlled_ml_metrics.json").write_text(report_text, encoding="utf-8")
    test.to_csv(args.output_dir / "controlled_ml_predictions.csv", index=False)
    print(report_text, end="")


if __name__ == "__main__":
    main()
