"""Owner-only CLI for confirming a review and approving a temporary decoy."""

import argparse
import json
import re
from pathlib import Path

from app.config import DEFENSE_MODE, FORENSICS_OUTPUT_DIR, LOG_ONLY
from app.decoy.decoy_store import STATIC_DECOY, arm_decoy, disarm_decoy
from app.fingerprint.blocklist import register_cloak_match


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    confirm = commands.add_parser("confirm")
    confirm.add_argument("review_id")
    confirm.add_argument("--ja3", required=True)
    confirm.add_argument("--evidence-id", required=True, help="Stable ID for the independently confirmed incident")
    commands.add_parser("arm").add_argument("review_id")
    commands.add_parser("disarm").add_argument("url")
    args = parser.parse_args()
    if DEFENSE_MODE != "owner_authorized" or LOG_ONLY:
        parser.error("Owner-authorized mode is required")
    if args.command == "disarm":
        disarm_decoy(args.url)
        return
    if not re.fullmatch(r"[0-9a-f]{32}", args.review_id):
        parser.error("Invalid review ID")
    try:
        path = Path(FORENSICS_OUTPUT_DIR) / f"review_{args.review_id}.json"
        review = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        parser.error(f"Cannot read review: {error}")
    if args.command == "arm":
        arm_decoy(review["url"], STATIC_DECOY, approved=True)
        return
    if not re.fullmatch(r"[0-9a-f]{32}", args.ja3) or args.ja3 != review["observed_ja3"]:
        parser.error("JA3 must match the fingerprint observed for this review")
    evidence_id = args.evidence_id.strip()
    if not evidence_id or len(evidence_id) > 200:
        parser.error("Evidence ID must contain 1–200 characters")
    applied = register_cloak_match(
        args.ja3, review["url"], evidence_id=evidence_id, review_id=args.review_id,
    )
    print("Confirmation recorded" if applied else "Confirmation already recorded or exempt")


if __name__ == "__main__":
    main()
