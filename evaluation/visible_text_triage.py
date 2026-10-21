"""Count complete pairs whose visible text differs. No detector scores."""

import csv
import hashlib
import json
from pathlib import Path

from bs4 import BeautifulSoup

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "results" / "data" / "crawl_sample"


def visible(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())


def main() -> None:
    rows = list(csv.DictReader((REPO / "data" / "manifests" / "capture_inventory.csv").open(encoding="utf-8")))
    complete = [r for r in rows if r["pair_complete"] == "yes"]
    equal_hash = 0
    equal_text = 0
    differ = []
    for row in complete:
        human_path = REPO / row["human_html_path"]
        bot_path = REPO / row["bot_html_path"]
        h_hash = hashlib.sha256(human_path.read_bytes()).hexdigest()
        b_hash = hashlib.sha256(bot_path.read_bytes()).hexdigest()
        if h_hash == b_hash:
            equal_hash += 1
            equal_text += 1
            continue
        human = visible(human_path.read_text(encoding="utf-8", errors="replace"))
        bot = visible(bot_path.read_text(encoding="utf-8", errors="replace"))
        if human == bot:
            equal_text += 1
            continue
        limit = min(len(human), len(bot))
        index = next((i for i in range(limit) if human[i] != bot[i]), limit)
        differ.append({
            "capture_id": row["capture_id"],
            "site_group": row["site_group"],
            "requested_url": row["requested_url"],
            "human_text_chars": len(human),
            "bot_text_chars": len(bot),
            "first_diff": index,
            "human_window": human[max(0, index - 80): index + 120],
            "bot_window": bot[max(0, index - 80): index + 120],
        })
    report = {
        "complete_pairs": len(complete),
        "byte_identical": equal_hash,
        "visible_text_identical": equal_text,
        "visible_text_differs": len(differ),
        "note": "Triage only. These rows are not annotated and are not cloaking labels.",
    }
    out = REPO / "data" / "annotation" / "visible_text_triage.json"
    out.write_text(json.dumps({"summary": report, "differences": differ}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
