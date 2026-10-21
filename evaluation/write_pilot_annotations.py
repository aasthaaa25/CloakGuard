"""Record reviewer 1's pilot labels.

Decisions were made from data/annotation/pilot_30_packet.jsonl and
pilot_diff_notes.txt. This script does not call the detector.
"""

import csv
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ANN = REPO / "data" / "annotation"
packets = [json.loads(line) for line in (ANN / "pilot_30_packet.jsonl").read_text(encoding="utf-8").splitlines()]

EMAIL_TOKEN_SITES = {"68dbce0a7477", "d4f1e93fdd72"}
ROTATING_TEXT = {"46c3cd998d80"}
EMPTY = {"8197fc6716a8"}
REDIRECT_STUB = {"1e08b84fe6a4"}
GAMBLING_BOTH = {"c2d1a3027c50"}
SOFT_404 = {"66e589bae96b", "60e67a49f2a3"}

rows = []
blank = []
for packet in packets:
    capture_id = packet["capture_id"]
    identical = packet["bodies_sha256_equal"]
    promo = capture_id in GAMBLING_BOTH or capture_id in ROTATING_TEXT
    if capture_id in EMPTY:
        label = "unusable"
        reason = "Saved bodies are 114 bytes and contain no visible text."
        confidence = "high"
        recapture = "yes"
        evidence = "human_bytes=114; bot_bytes=114; visible text length 0"
    elif capture_id in REDIRECT_STUB:
        label = "unusable"
        reason = "Both views are the same 416-byte redirect stub. The destination URL was not stored."
        confidence = "high"
        recapture = "yes"
        evidence = "title=Page Redirection; text mentions follow the link to example"
    elif capture_id in ROTATING_TEXT:
        label = "benign_profile_dependent_difference"
        reason = (
            "Visible text matches until a boilerplate paragraph and a set of related links. "
            "Both views keep the same title and the same game-promotion article. "
            "That is consistent with a rotating module. It is not evidence of selective cloaking. "
            "A repeat capture would be needed to see whether the swap follows the profile."
        )
        confidence = "low"
        recapture = "yes"
        evidence = "pilot_diff_notes.txt first_diff=689; related links /banben/*.html differ"
    elif capture_id in EMAIL_TOKEN_SITES:
        label = "benign_profile_dependent_difference"
        reason = (
            "Visible text matches. The link difference is a pair of Cloudflare email-protection tokens. "
            "That has an ordinary explanation and is not selective promotional content."
        )
        confidence = "medium"
        recapture = "no"
        evidence = "links_only_in_bot and links_only_in_human are /cdn-cgi/l/email-protection hashes"
    elif capture_id in SOFT_404:
        label = "no_suspicious_difference_observed"
        reason = "Both views are the same not-found document. Byte hashes differ outside the visible text."
        confidence = "medium"
        recapture = "no"
        evidence = "titles Page Not found or No Results Found; visible text first_diff equals text length"
    elif identical:
        label = "no_suspicious_difference_observed"
        reason = "Human and bot bodies have the same SHA-256. No profile difference is available to review."
        if capture_id in GAMBLING_BOTH:
            reason += " The shared page is an Indonesian lottery promotion, so promotional content is present on both profiles."
        confidence = "high"
        recapture = "no"
        evidence = "bodies_sha256_equal=true"
    else:
        label = "no_suspicious_difference_observed"
        reason = (
            "SHA-256 differs, but the extracted visible text is character-for-character the same "
            "and the saved link sets do not show a content insertion. The byte difference is outside the visible text."
        )
        confidence = "medium"
        recapture = "no"
        evidence = "pilot_diff_notes.txt first_diff equals visible text length"
    profile_diff = "no" if identical else "yes"
    rows.append({
        "capture_id": capture_id,
        "reviewer_id": "pilot_reviewer_1",
        "review_label": label,
        "profile_difference_present": profile_diff,
        "promotional_content_present": "yes" if promo else "no",
        "evidence_reference": evidence,
        "rationale": reason,
        "confidence": confidence,
        "needs_recapture": recapture,
    })
    blank.append({
        "capture_id": capture_id,
        "reviewer_id": "",
        "review_label": "",
        "profile_difference_present": "",
        "promotional_content_present": "",
        "evidence_reference": "",
        "rationale": "",
        "confidence": "",
        "needs_recapture": "",
    })

fields = list(rows[0].keys())
with (ANN / "pilot_30_reviewer_1.csv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
with (ANN / "pilot_30_reviewer_2_blank.csv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    writer.writerows(blank)

from collections import Counter
print(Counter(row["review_label"] for row in rows))
print("rows", len(rows))
