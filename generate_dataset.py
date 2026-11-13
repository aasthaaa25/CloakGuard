"""Generate reproducible synthetic URL-risk fixtures for training demonstrations.

These reserved .test URLs are constructed locally. Labels describe the generated
scenario and are independent of detector outputs. They are not incident labels.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parent


def generate_dataset(output: Path, rows: int = 160000, seed: int = 42):
    if rows < 80 or rows % 2:
        raise ValueError("rows must be an even integer of at least 80")
    rng = random.Random(seed)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["url", "label", "provenance"])
        writer.writeheader()
        for index in range(rows):
            label = index % 2
            host = f"site-{rng.getrandbits(48):012x}-{index}.test"
            if label:
                path = rng.choice(["login/verify", "account/confirm", "bonus/claim", "download/update"])
                url = f"http://{host}/{path}?redirect={rng.getrandbits(64):016x}&session={index}"
            else:
                path = rng.choice(["about", "news", "products", "contact", "help", "blog"])
                url = f"https://{host}/{path}/{index}"
            writer.writerow({"url": url, "label": label, "provenance": "synthetic_url_risk_fixture"})
    manifest = {
        "dataset_kind": "synthetic_url_risk_fixture",
        "label_source": "Constructed URL scenario, independent of detector scores",
        "scope": "Training and presentation smoke test. External detection performance unmeasured.",
        "rows": rows, "seed": seed,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "generator": "generate_dataset.py", "network_requests": 0,
    }
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "final_full (1).csv")
    parser.add_argument("--rows", type=int, default=160000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"Output already exists: {args.output}. Choose a new --output path.")
    print(json.dumps(generate_dataset(args.output, args.rows, args.seed), indent=2))


if __name__ == "__main__":
    main()
