"""Evaluate URL-lexical proxies on domain-disjoint folds of the archived subset."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

import pandas as pd
import sklearn
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
import tldextract

from benchmark_controlled_ml import ROOT, summarize

sys.path.insert(0, str(ROOT / "results"))
from detection.features import FEATURE_NAMES, build_url_features


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evaluation" / "outputs")
    args = parser.parse_args()
    path = ROOT / "results" / "data" / "multimodal_features.parquet"
    archived = pd.read_parquet(path, columns=["provenance", "url", "label"])
    urls = archived.loc[archived["provenance"].eq("csv_backbone"), ["url", "label"]].reset_index(drop=True)
    if urls["url"].isna().any() or urls["url"].duplicated().any() or set(urls["label"]) != {0, 1}:
        raise ValueError("Expected distinct URL strings with two complete proxy classes")

    suffixes = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None, include_psl_private_domains=True)
    groups = []
    for url in urls["url"]:
        host = urlsplit(url if "://" in url else "//" + url).hostname
        if not host:
            raise ValueError("Backbone row has no hostname")
        extracted = suffixes(host)
        groups.append(extracted.top_domain_under_public_suffix or host.lower().rstrip("."))
    features = pd.DataFrame([build_url_features(url) for url in urls["url"]])[FEATURE_NAMES]
    labels = urls["label"].astype(int)
    models = {
        "prior": DummyClassifier(strategy="prior"),
        "logistic": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)),
        "hist_gradient_boosting": HistGradientBoostingClassifier(random_state=42),
    }
    predictions = pd.DataFrame({"label": labels})
    fold_metrics = []
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)
    for fold, (fit, test) in enumerate(splitter.split(features, labels, groups), start=1):
        if {groups[i] for i in fit} & {groups[i] for i in test}:
            raise RuntimeError("Domain overlap across fold")
        if labels.iloc[test].nunique() != 2 or labels.iloc[fit].nunique() != 2:
            raise RuntimeError("Group split produced a single-class partition")
        predictions.loc[test, "fold"] = fold
        result = {"fold": fold, "rows": len(test), "positive": int(labels.iloc[test].sum()),
                  "groups": len({groups[i] for i in test}), "models": {}}
        for name, model in models.items():
            model.fit(features.iloc[fit], labels.iloc[fit])
            scores = model.predict_proba(features.iloc[test])[:, 1]
            predictions.loc[test, name] = scores
            result["models"][name] = summarize(labels.iloc[test], scores, 0.5)
        fold_metrics.append(result)
    if predictions.isna().any().any():
        raise RuntimeError("Some URLs have missing out-of-fold predictions")
    predictions["fold"] = predictions["fold"].astype(int)
    results = {name: summarize(labels, predictions[name], 0.5) for name in models}
    for name, result in results.items():
        result["mean_fold_roc_auc"] = float(pd.Series([f["models"][name]["roc_auc"] for f in fold_metrics]).mean())
        result["mean_fold_average_precision"] = float(pd.Series([f["models"][name]["average_precision"] for f in fold_metrics]).mean())
    payload = {
        "scope": "Archived 5,000-URL subset; prediction of unverified historical proxy labels, not cloaking validation",
        "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "sklearn_version": sklearn.__version__,
        "rows": len(labels), "positive": int(labels.sum()), "negative": int(labels.eq(0).sum()),
        "registrable_domain_groups": len(set(groups)),
        "feature_count": len(FEATURE_NAMES),
        "models": results, "folds": fold_metrics,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = json.dumps(payload, indent=2) + "\n"
    (args.output_dir / "url_proxy_metrics.json").write_text(report, encoding="utf-8")
    predictions.to_csv(args.output_dir / "url_proxy_predictions.csv", index_label="row_id")
    print(report, end="")


if __name__ == "__main__":
    main()
