"""
Build the capture inventory and a blinded 30-pair review packet.

This script reads crawl metadata and saved HTML only. It does not import
the fusion scorer, the jargon scorer, the URL model, or any saved prediction.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import tldextract

_TLD = tldextract.TLDExtract(suffix_list_urls=None)

from bs4 import BeautifulSoup

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "results" / "data" / "crawl_sample"
OUT_DIR = REPO / "data" / "manifests"
ANN_DIR = REPO / "data" / "annotation"
PILOT_SEED = 20261021
PILOT_N = 30


def _host(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        host = ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _registrable(host: str) -> str:
    if not host or host.replace(".", "").isdigit():
        return ""
    parsed = _TLD(host)
    if not parsed.domain or not parsed.suffix:
        return host
    return f"{parsed.domain}.{parsed.suffix}"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _visible(html: str) -> tuple[str, str, list[str]]:
    if not html.strip():
        return "", "", []
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    title = title_tag.get_text(" ", strip=True)[:200] if title_tag else ""
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ", strip=True).split())
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href and not href.startswith(("#", "javascript:", "mailto:")):
            links.append(href[:200])
    return title, text, links


def _challenge_markers(text: str, html: str) -> list[str]:
    blob = (text[:4000] + " " + html[:2000]).lower()
    markers = []
    for name, needle in (
        ("cloudflare", "cloudflare"),
        ("captcha", "captcha"),
        ("access_denied", "access denied"),
        ("just_a_moment", "just a moment"),
        ("enable_javascript", "enable javascript"),
        ("bot_check", "verify you are human"),
    ):
        if needle in blob:
            markers.append(name)
    return markers


def inventory_rows() -> list[dict]:
    rows = []
    for meta_path in sorted(SAMPLE.glob("*_meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        capture_id = str(meta.get("url_id") or meta_path.name.replace("_meta.json", ""))
        requested = str(meta.get("url") or "")
        human_path = SAMPLE / f"{capture_id}_human.html"
        bot_path = SAMPLE / f"{capture_id}_bot.html"
        human_png = SAMPLE / f"{capture_id}_human.png"
        bot_png = SAMPLE / f"{capture_id}_bot.png"
        human_exists = human_path.exists()
        bot_exists = bot_path.exists()
        human_bytes = human_path.stat().st_size if human_exists else 0
        bot_bytes = bot_path.stat().st_size if bot_exists else 0
        human_empty = (not human_exists) or human_path.read_text(encoding="utf-8", errors="replace").strip() == ""
        bot_empty = (not bot_exists) or bot_path.read_text(encoding="utf-8", errors="replace").strip() == ""
        h_status = meta.get("human_status")
        b_status = meta.get("bot_status")
        reasons = []
        if not human_exists:
            reasons.append("missing_human_html")
        elif human_empty:
            reasons.append("empty_human_html")
        if not bot_exists:
            reasons.append("missing_bot_html")
        elif bot_empty:
            reasons.append("empty_bot_html")
        if h_status not in (200, "200"):
            reasons.append(f"human_status_{h_status}")
        if b_status not in (200, "200"):
            reasons.append(f"bot_status_{b_status}")
        rel = lambda p: str(p.relative_to(REPO)).replace("\\", "/") if p.exists() else ""
        rows.append({
            "capture_id": capture_id,
            "site_group": _host(requested),
            "hostname_group": _host(requested),
            "registrable_domain_group": _registrable(_host(requested)),
            "requested_url": requested,
            "final_human_url": "",
            "final_bot_url": "",
            "capture_timestamp": "",
            "human_html_path": rel(human_path),
            "bot_html_path": rel(bot_path),
            "human_status": h_status if h_status is not None else "",
            "bot_status": b_status if b_status is not None else "",
            "pair_complete": "yes" if not reasons else "no",
            "failure_reason": "|".join(reasons),
            "human_screenshot_path": rel(human_png),
            "bot_screenshot_path": rel(bot_png),
            "human_method": meta.get("human_method", ""),
            "bot_method": meta.get("bot_method", ""),
            "human_bytes": human_bytes,
            "bot_bytes": bot_bytes,
            "meta_recorded_final_url": "no",
            "meta_recorded_timestamp": "no",
        })
    return rows


def write_inventory(rows: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fields = [
        "capture_id", "site_group", "hostname_group", "registrable_domain_group", "requested_url", "final_human_url", "final_bot_url",
        "capture_timestamp", "human_html_path", "bot_html_path", "human_status", "bot_status",
        "pair_complete", "failure_reason", "human_screenshot_path", "bot_screenshot_path",
        "human_method", "bot_method", "human_bytes", "bot_bytes",
        "meta_recorded_final_url", "meta_recorded_timestamp",
    ]
    path = OUT_DIR / "capture_inventory.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def summary(rows: list[dict]) -> dict:
    complete = [r for r in rows if r["pair_complete"] == "yes"]
    sites = Counter(r["site_group"] for r in rows)
    complete_sites = Counter(r["site_group"] for r in complete)
    urls = [r["requested_url"] for r in rows]
    return {
        "attempted_captures": len(rows),
        "pair_complete_yes": len(complete),
        "pair_complete_no": len(rows) - len(complete),
        "unique_requested_urls": len(set(urls)),
        "duplicate_requested_urls": len(urls) - len(set(urls)),
        "unique_site_groups": len(sites),
        "site_groups_with_more_than_one_capture": sum(1 for n in sites.values() if n > 1),
        "complete_unique_urls": len({r["requested_url"] for r in complete}),
        "complete_unique_site_groups": len(complete_sites),
        "complete_site_groups_with_more_than_one_capture": sum(1 for n in complete_sites.values() if n > 1),
        "screenshot_files_present": sum(1 for r in rows if r["human_screenshot_path"] or r["bot_screenshot_path"]),
        "pair_complete_definition": (
            "Artifact and status check only: both HTML files exist, both are non-empty "
            "after stripping whitespace, and both recorded statuses are HTTP 200. "
            "This is the 204-count. It does not mean the pair is a valid annotation example."
        ),
        "site_group_definition": (
            "Hostname with a leading www. removed. This is not a public-suffix registrable "
            "domain and not a template family. Distinct hostnames are not necessarily independent sites."
        ),
        "attempted_definition": "One row per *_meta.json in results/data/crawl_sample. This is the 300-count.",
        "fields_not_in_source_meta": ["final_human_url", "final_bot_url", "capture_timestamp"],
    }


def build_packet(rows: list[dict]) -> list[str]:
    complete = [r for r in rows if r["pair_complete"] == "yes"]
    rng = random.Random(PILOT_SEED)
    chosen = rng.sample(complete, PILOT_N)
    chosen_ids = [r["capture_id"] for r in chosen]
    ANN_DIR.mkdir(parents=True, exist_ok=True)
    (ANN_DIR / "pilot_30_ids.txt").write_text("\n".join(chosen_ids) + "\n", encoding="utf-8")
    packet_path = ANN_DIR / "pilot_30_packet.jsonl"
    with packet_path.open("w", encoding="utf-8") as out:
        for row in chosen:
            human_file = REPO / row["human_html_path"]
            bot_file = REPO / row["bot_html_path"]
            human_hash = _sha256(human_file)
            bot_hash = _sha256(bot_file)
            identical = human_hash == bot_hash
            h_html = human_file.read_text(encoding="utf-8", errors="replace")
            b_html = "" if identical else bot_file.read_text(encoding="utf-8", errors="replace")
            h_title, h_text, h_links = _visible(h_html)
            if identical:
                b_title, b_text, b_links = h_title, h_text, h_links
            else:
                b_title, b_text, b_links = _visible(b_html)
            h_link_set, b_link_set = set(h_links), set(b_links)
            packet = {
                "capture_id": row["capture_id"],
                "site_group": row["site_group"],
                "requested_url": row["requested_url"],
                "human_status": row["human_status"],
                "bot_status": row["bot_status"],
                "bodies_sha256_equal": identical,
                "human_bytes": row["human_bytes"],
                "bot_bytes": row["bot_bytes"],
                "human_title": h_title,
                "bot_title": b_title,
                "human_text_excerpt": h_text[:1200],
                "bot_text_excerpt": "" if identical else b_text[:1200],
                "human_text_chars": len(h_text),
                "bot_text_chars": len(b_text),
                "human_link_count": len(h_link_set),
                "bot_link_count": len(b_link_set),
                "links_only_in_bot": sorted(b_link_set - h_link_set)[:15],
                "links_only_in_human": sorted(h_link_set - b_link_set)[:15],
                "human_challenge_markers": _challenge_markers(h_text, h_html),
                "bot_challenge_markers": [] if identical else _challenge_markers(b_text, b_html),
                "detector_scores_included": False,
            }
            out.write(json.dumps(packet, ensure_ascii=False) + "\n")
    return chosen_ids


def main() -> None:
    rows = inventory_rows()
    write_inventory(rows)
    info = summary(rows)
    (OUT_DIR / "capture_inventory_summary.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    ids = build_packet(rows)
    print(json.dumps(info, indent=2))
    print("pilot_ids", len(ids))


if __name__ == "__main__":
    main()
