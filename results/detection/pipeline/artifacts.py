"""
Stage 2 — Artifact Extraction
Pulls structured artifacts from raw HTML per view: visible text, link set,
DOM tag-distribution, title, byte sizes.  Input = crawl_record from crawl.py.
"""

import re
from typing import Optional
from collections import Counter

try:
    from bs4 import BeautifulSoup as _BS
    _BS4 = True
except ImportError:
    _BS4 = False


def _parse(html: str):
    if not html or not _BS4:
        return None
    try:
        return _BS(html, "html.parser")
    except Exception:
        return None


def _visible_text(soup) -> str:
    if soup is None:
        return ""
    for tag in soup(["script", "style", "meta", "link", "head"]):
        tag.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())


def _links(soup) -> set:
    if soup is None:
        return set()
    hrefs = set()
    for a in soup.find_all("a", href=True):
        h = a["href"].strip()
        if h and not h.startswith(("#", "javascript:", "mailto:")):
            hrefs.add(h[:200])
    return hrefs


def _tag_distribution(soup) -> dict:
    if soup is None:
        return {}
    tags = [t.name for t in soup.find_all() if t.name]
    return dict(Counter(tags))


def _title(soup) -> str:
    if soup is None:
        return ""
    t = soup.find("title")
    return t.get_text(strip=True)[:200] if t else ""


def _meta_description(soup) -> str:
    if soup is None:
        return ""
    m = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    if m and m.get("content"):
        return m["content"][:300]
    return ""


def _script_srcs(soup) -> list:
    if soup is None:
        return []
    return [s.get("src", "") for s in soup.find_all("script") if s.get("src")]


def extract_view_artifacts(html: str, screenshot_path: Optional[str] = None) -> dict:
    """Extract all artifacts from a single view's HTML."""
    soup = _parse(html)
    text = _visible_text(soup)
    links = _links(soup)
    tags  = _tag_distribution(soup)
    return {
        "html_bytes":      len(html.encode("utf-8", errors="replace")) if html else 0,
        "html":            html or "",
        "text":            text,
        "text_len":        len(text),
        "title":           _title(soup),
        "meta_description": _meta_description(soup),
        "links":           links,
        "link_count":      len(links),
        "tag_distribution": tags,
        "script_srcs":     _script_srcs(soup),
        "screenshot_path": screenshot_path,
        "have_html":       bool(html and len(html) > 50),
    }


def extract_dual_artifacts(crawl_record: dict) -> dict:
    """
    Stage 2 entry point.
    Input:  crawl_record from dual_view_crawl()
    Output: artifacts dict with human/bot views + cross-view derived fields.
    """
    human = extract_view_artifacts(
        crawl_record["human"]["html"],
        crawl_record["human"].get("screenshot_path"),
    )
    bot = extract_view_artifacts(
        crawl_record["bot"]["html"],
        crawl_record["bot"].get("screenshot_path"),
    )

    # Cross-view derived fields used directly by drift/promo/jargon stages
    bot_only_links  = bot["links"] - human["links"]
    human_only_links = human["links"] - bot["links"]

    return {
        "url":             crawl_record["url"],
        "url_id":          crawl_record.get("url_id", ""),
        "human":           human,
        "bot":             bot,
        # top-level mirrors for legacy pipeline compat
        "human_html":      human["html"],
        "bot_html":        bot["html"],
        "human_links":     human["links"],
        "bot_links":       bot["links"],
        "bot_only_links":  bot_only_links,
        "human_only_links": human_only_links,
        "html_size_diff":  abs(human["html_bytes"] - bot["html_bytes"]),
        "have_html":       human["have_html"] or bot["have_html"],
    }
