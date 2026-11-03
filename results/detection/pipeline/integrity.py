"""Compare one static artifact with a digest approved by the site owner."""

import argparse
import hashlib
import json
import re
from pathlib import Path


def check_integrity(content: bytes, trusted_sha256: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{64}", trusted_sha256):
        raise ValueError("Expected a lowercase SHA-256 digest")
    observed = hashlib.sha256(content).hexdigest()
    return {
        "observed_sha256": observed,
        "trusted_sha256": trusted_sha256,
        "integrity_mismatch": observed != trusted_sha256,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("trusted_sha256")
    args = parser.parse_args()
    result = check_integrity(args.artifact.read_bytes(), args.trusted_sha256)
    print(json.dumps(result))
    raise SystemExit(int(result["integrity_mismatch"]))


if __name__ == "__main__":
    main()
