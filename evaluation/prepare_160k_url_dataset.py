"""Prepare and benchmark a balanced URL-only adaptation of UCI dataset 967."""

import argparse
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import parse_qsl, urlsplit
from zipfile import ZipFile

import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
import tldextract

from benchmark_controlled_ml import ROOT, summarize

sys.path.insert(0, str(ROOT / "results"))
from detection.features import FEATURE_NAMES, build_url_features

SOURCE = "https://archive.ics.uci.edu/dataset/967/phiusiil+phishing+url+website+dataset"
CSV_MEMBER = "PhiUSIIL_Phishing_URL_Dataset.csv"
SEED = 42
PER_CLASS = 80_000
SENSITIVE_QUERY_KEYS = {
    "access_token", "api_key", "apikey", "auth_token", "client_secret",
    "id_token", "password", "passwd", "refresh_token", "session_token",
}


def parse_url(url):
    if not isinstance(url, str) or not url or any(char.isspace() for char in url):
        return None
    try:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            return None
        if parts.username is not None or parts.password is not None:
            return None
        if any(key.lower() in SENSITIVE_QUERY_KEYS for key, _ in parse_qsl(parts.query)):
            return None
        host = parts.hostname.rstrip(".").encode("idna").decode("ascii").lower()
        port = parts.port
        default = 80 if parts.scheme == "http" else 443
        normalized_port = "" if port in (None, default) else str(port)
        key = (parts.scheme, host, normalized_port, parts.path or "/", parts.query)
        return key, host
    except (ValueError, UnicodeError):
        return None


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prepare(path):
    with ZipFile(path) as archive, archive.open(CSV_MEMBER) as raw:
        source = pd.read_csv(raw, usecols=["URL", "label"])
    if set(source["label"]) != {0, 1} or source["label"].isna().any():
        raise ValueError("Unexpected UCI labels")
    original_counts = source["label"].value_counts()
    source["url"] = source.pop("URL").str.strip()
    parsed = source["url"].map(parse_url)
    rows = source.loc[parsed.notna()].copy()
    rows["key"] = parsed.dropna().map(lambda item: item[0])
    rows["host"] = parsed.dropna().map(lambda item: item[1])
    conflict = rows.groupby("key")["label"].transform("nunique").gt(1)
    unique = rows.loc[~conflict].drop_duplicates("key")

    # UCI uses 0 for phishing and 1 for legitimate. CloakGuard uses 1 for phishing.
    sampled = pd.concat([
        group.sample(n=PER_CLASS, random_state=SEED) for _, group in unique.groupby("label")
    ]).sample(frac=1, random_state=SEED).reset_index(drop=True)
    sampled["label"] = 1 - sampled["label"]
    extractor = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None, include_psl_private_domains=True)

    @lru_cache(maxsize=None)
    def domain(host):
        return extractor(host).top_domain_under_public_suffix or host

    sampled["domain_group"] = sampled["host"].map(domain)
    fits, tests = next(StratifiedGroupKFold(n_splits=4, shuffle=True, random_state=SEED).split(
        sampled, sampled["label"], sampled["domain_group"]
    ))
    sampled["split"] = "train"
    sampled.loc[tests, "split"] = "test"
    if (set(sampled.loc[fits, "domain_group"]) & set(sampled.loc[tests, "domain_group"])
            or not sampled["label"].value_counts().eq(PER_CLASS).all()
            or sampled["url"].duplicated().any()
            or not sampled.groupby("split")["label"].nunique().eq(2).all()):
        raise RuntimeError("Dataset failed balance, split, or uniqueness validation")

    result = sampled[["url", "label", "domain_group", "split"]]
    stats = {
        "source": SOURCE, "source_archive_sha256": digest(path),
        "attribution": "Arvind Prasad and Shalini Chandra (2024), PhiUSIIL Phishing URL (Website), UCI",
        "license": "CC BY 4.0",
        "label_mapping": {"0": "legitimate", "1": "phishing"},
        "source_counts": {"phishing": int(original_counts[0]), "legitimate": int(original_counts[1])},
        "invalid_or_credential_like_rows_removed": len(source) - len(rows),
        "conflicting_rows_removed": int(conflict.sum()),
        "duplicates_removed": len(rows) - int(conflict.sum()) - len(unique),
        "seed": SEED, "rows": len(result), "domain_groups": result["domain_group"].nunique(),
        "splits": {name: {"rows": len(group), "legitimate": int(group["label"].eq(0).sum()),
                          "phishing": int(group["label"].eq(1).sum()),
                          "domain_groups": group["domain_group"].nunique()}
                   for name, group in result.groupby("split")},
    }
    return result, stats


def benchmark(rows):
    fit = rows["split"].eq("train")
    test = rows["split"].eq("test")
    y_train = rows.loc[fit, "label"]
    y_test = rows.loc[test, "label"]
    # Only features computed from each URL string are used. No source-computed features.
    features = pd.DataFrame([build_url_features(url) for url in rows["url"]], columns=FEATURE_NAMES)
    is_https = rows.loc[test, "url"].str.lower().str.startswith("https:")
    typical_shape = rows.loc[test, "url"].map(urlsplit).map(
        lambda url: url.scheme == "https" and url.hostname.lower().startswith("www.")
        and not url.path and not url.query
    )
    scores = {"scheme_only": (~is_https).astype(float).to_numpy(),
              "shape_only": (~typical_shape).astype(float).to_numpy()}
    for name, model in {
        "logistic": make_pipeline(StandardScaler(), LogisticRegression(max_iter=400, random_state=SEED)),
        "hist_gradient_boosting": HistGradientBoostingClassifier(random_state=SEED),
    }.items():
        model.fit(features.loc[fit], y_train)
        scores[name] = model.predict_proba(features.loc[test])[:, 1]
    held_out = pd.DataFrame({"label": y_test, "https": is_https, "typical_shape": typical_shape, **scores})
    results = {}
    for name in scores:
        slices = {"held_out": held_out, "held_out_https_only": held_out.loc[is_https],
                  "held_out_https_www_empty_path": held_out.loc[typical_shape]}
        results[name] = {}
        for slice_name, subset in slices.items():
            metrics = summarize(subset["label"], subset[name], 0.5)
            metrics["accuracy"] = float(accuracy_score(subset["label"], subset[name].ge(0.5)))
            results[name][slice_name] = metrics
    return held_out, {"model_results": results, "https_only_rows": int(is_https.sum()),
                      "https_www_empty_path_rows": int(typical_shape.sum()),
                      "https_www_empty_path_phishing_rows": int(y_test.loc[typical_shape].sum()),
                      "feature_count": len(FEATURE_NAMES), "sklearn_version": sklearn.__version__}



def write_json(path, content):
    path.write_text(json.dumps(content, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Original UCI ZIP or the prepared CloakGuard CSV")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.source.suffix.lower() == ".csv":
        data = pd.read_csv(args.source)
        if (
            set(data.columns) != {"url", "label", "domain_group", "split"}
            or data.isna().any().any()
            or data["url"].duplicated().any()
            or data["label"].value_counts().to_dict() != {0: PER_CLASS, 1: PER_CLASS}
            or set(data["split"]) != {"train", "test"}
            or not data.groupby("split")["label"].nunique().eq(2).all()
            or data.groupby("domain_group")["split"].nunique().max() != 1
        ):
            raise ValueError("Invalid prepared 160k dataset")
        dataset_hash = digest(args.source)
        print(f"Validated prepared dataset SHA-256: {dataset_hash}", flush=True)
    else:
        data, manifest = prepare(args.source)
        csv_path = args.output_dir / "CloakGuard_160k.csv"
        data.to_csv(csv_path, index=False, lineterminator="\n")
        dataset_hash = digest(csv_path)
        manifest["dataset_sha256"] = dataset_hash
        write_json(args.output_dir / "dataset_manifest.json", manifest)
        print(json.dumps(manifest, indent=2), flush=True)
    if not args.prepare_only:
        predictions, metrics = benchmark(data)
        metrics["dataset_sha256"] = dataset_hash
        predictions.to_csv(args.output_dir / "url_test_predictions.csv", index_label="row_id")
        write_json(args.output_dir / "url_benchmark_metrics.json", metrics)
        print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
