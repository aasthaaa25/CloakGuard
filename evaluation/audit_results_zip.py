"""Compare the user-supplied ZIP's stored experiment evidence against this repository."""

import argparse
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = (
    "data/multimodal_features.parquet",
    "detection/artifacts/metrics.json",
    "detection/artifacts/multimodal_metrics.json",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with ZipFile(args.archive) as archive:
        names = archive.namelist()
        checks = {}
        for path in ARTIFACTS:
            matches = [name for name in names if name.endswith("/" + path)]
            if len(matches) != 1:
                raise ValueError(f"Expected one archive entry for {path}")
            archived = archive.read(matches[0])
            current = (ROOT / "results" / path).read_bytes()
            check = {"sha256": hashlib.sha256(archived).hexdigest(), "byte_identical": archived == current}
            if path.endswith(".json"):
                check["parsed_json_equal"] = json.loads(archived) == json.loads(current)
            else:
                table = pd.read_parquet(io.BytesIO(archived), columns=["provenance", "label", "url"])
                check["row_counts"] = {
                    source: {"rows": len(rows), "distinct_urls": rows["url"].nunique(),
                             "label_counts": {str(k): int(v) for k, v in rows["label"].value_counts().items()}}
                    for source, rows in table.groupby("provenance")
                }
            checks[path] = check
        result = {
            "archive_name": args.archive.name,
            "csv_files": sorted(name for name in names if name.lower().endswith(".csv")),
            "artifacts": checks,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
