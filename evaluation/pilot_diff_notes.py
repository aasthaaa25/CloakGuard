"""Neutral text-diff notes for the annotation pilot. No detector scores."""

import json
from pathlib import Path

from bs4 import BeautifulSoup

REPO = Path(__file__).resolve().parents[1]
rows = json.loads((REPO / "data" / "annotation" / "pilot_30_review_sheet.json").read_text(encoding="utf-8"))
sample = REPO / "results" / "data" / "crawl_sample"
watch = {
    "b08e5e344b41", "68dbce0a7477", "4c9b516a122e", "8061572efed0",
    "000404e03596", "46c3cd998d80", "02ee35902a36", "d4f1e93fdd72",
    "0d8c9ba83679", "2109e63d21b8", "932ae8cf0a7a", "81f9d24dc81d",
    "66e589bae96b", "60e67a49f2a3", "8197fc6716a8", "1e08b84fe6a4",
    "c2d1a3027c50", "018dc28cfc45",
}


def visible(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())


lines = []
for row in rows:
    if row["id"] not in watch:
        continue
    human = (sample / f"{row['id']}_human.html").read_text(encoding="utf-8", errors="replace")
    bot = (sample / f"{row['id']}_bot.html").read_text(encoding="utf-8", errors="replace")
    human_text, bot_text = visible(human), visible(bot)
    limit = min(len(human_text), len(bot_text))
    index = next((i for i in range(limit) if human_text[i] != bot_text[i]), limit)
    lines.append(f"ID {row['id']} {row['site']} identical={row['identical']}")
    lines.append(f"text_len {len(human_text)} {len(bot_text)} first_diff {index}")
    lines.append("human " + human_text[max(0, index - 70): index + 90])
    lines.append("bot   " + bot_text[max(0, index - 70): index + 90])
    lines.append("head  " + human_text[:220])
    lines.append("bot_only " + " | ".join(row["bot_only"][:8]))
    lines.append("human_only " + " | ".join(row["human_only"][:8]))
    lines.append("")

(REPO / "data" / "annotation" / "pilot_diff_notes.txt").write_text("\n".join(lines), encoding="utf-8")
print("wrote", len(lines))
