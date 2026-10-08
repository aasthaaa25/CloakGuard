"""
Stage 1 — Dual-View Crawler
Fetches each URL twice: once as a real human browser (Chrome UA, desktop viewport)
and once as Googlebot, capturing HTML, rendered DOM structure, and (optionally)
screenshots via Playwright.  Falls back gracefully to httpx UA-only when
Playwright / Chromium is not installed.

Usage (bake a sample):
    python -m detection.pipeline.crawl --sample 300 --out data/crawl_sample
    python -m detection.pipeline.crawl --url https://example.com
"""

import sys
import json
import hashlib
import time
import asyncio
from pathlib import Path
from typing import Optional

import httpx

# ── optional heavy deps ────────────────────────────────────────────────────────
try:
    from playwright.async_api import async_playwright
    _PLAYWRIGHT = True
except ImportError:
    _PLAYWRIGHT = False

try:
    from PIL import Image
    import io as _io
    _PIL = True
except ImportError:
    _PIL = False

ROOT = Path(__file__).resolve().parents[3]

VIEW_PROFILES = {
    "human": {
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "viewport": {"width": 1280, "height": 720},
        "extra_http_headers": {
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    },
    "bot": {
        "user_agent": (
            "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
        ),
        "viewport": {"width": 1280, "height": 720},
        "extra_http_headers": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "From": "googlebot(at)googlebot.com",
        },
    },
}

_TIMEOUT = 12  # seconds


async def _fetch_playwright(url: str, profile: dict) -> dict:
    """Full browser fetch with Playwright — captures rendered HTML + screenshot."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=profile["user_agent"],
            viewport=profile["viewport"],
            extra_http_headers=profile.get("extra_http_headers", {}),
        )
        page = await ctx.new_page()
        try:
            resp = await page.goto(url, timeout=_TIMEOUT * 1000, wait_until="domcontentloaded")
            status = resp.status if resp else 0
            html = await page.content()
            shot = await page.screenshot(full_page=False)
            return {
                "html": html,
                "status": status,
                "screenshot_bytes": shot,
                "method": "playwright",
            }
        except Exception as e:
            return {"html": "", "status": 0, "screenshot_bytes": b"", "method": "playwright_fail", "error": str(e)}
        finally:
            await browser.close()


def _fetch_httpx(url: str, profile: dict) -> dict:
    """Lightweight UA-only fetch via httpx — no JS rendering."""
    headers = {"User-Agent": profile["user_agent"]}
    headers.update(profile.get("extra_http_headers", {}))
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=_TIMEOUT,
            headers=headers,
            verify=False,
        ) as client:
            r = client.get(url)
            return {
                "html": r.text,
                "status": r.status_code,
                "screenshot_bytes": b"",
                "method": "httpx",
            }
    except Exception as e:
        return {"html": "", "status": 0, "screenshot_bytes": b"", "method": "httpx_fail", "error": str(e)}


async def _dual_view_async(url: str) -> dict:
    if _PLAYWRIGHT:
        h_task = asyncio.create_task(_fetch_playwright(url, VIEW_PROFILES["human"]))
        b_task = asyncio.create_task(_fetch_playwright(url, VIEW_PROFILES["bot"]))
        human_raw, bot_raw = await asyncio.gather(h_task, b_task)
    else:
        loop = asyncio.get_event_loop()
        human_raw = await loop.run_in_executor(None, _fetch_httpx, url, VIEW_PROFILES["human"])
        bot_raw   = await loop.run_in_executor(None, _fetch_httpx, url, VIEW_PROFILES["bot"])
    return human_raw, bot_raw


def dual_view_crawl(url: str, save_dir: Optional[Path] = None) -> dict:
    """
    Crawl url with both human and bot profiles.
    Returns a crawl_record dict compatible with extract_dual_artifacts().
    Optionally persists raw HTML and screenshots to save_dir.
    """
    url_id = hashlib.md5(url.encode()).hexdigest()[:12]

    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        human_raw, bot_raw = loop.run_until_complete(_dual_view_async(url))
    except RuntimeError:
        human_raw = _fetch_httpx(url, VIEW_PROFILES["human"])
        bot_raw   = _fetch_httpx(url, VIEW_PROFILES["bot"])

    record = {
        "url":    url,
        "url_id": url_id,
        "human": {
            "html":            human_raw["html"],
            "status":          human_raw.get("status", 0),
            "method":          human_raw.get("method", "unknown"),
            "screenshot_path": None,
        },
        "bot": {
            "html":            bot_raw["html"],
            "status":          bot_raw.get("status", 0),
            "method":          bot_raw.get("method", "unknown"),
            "screenshot_path": None,
        },
    }

    if save_dir is not None:
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)

        for view_key, raw in [("human", human_raw), ("bot", bot_raw)]:
            html_path = save_dir / f"{url_id}_{view_key}.html"
            html_path.write_text(raw["html"], encoding="utf-8", errors="replace")

            if raw.get("screenshot_bytes") and _PIL:
                try:
                    img = Image.open(_io.BytesIO(raw["screenshot_bytes"]))
                    img_path = save_dir / f"{url_id}_{view_key}.png"
                    img.save(img_path)
                    record[view_key]["screenshot_path"] = str(img_path)
                except Exception:
                    pass

        meta_path = save_dir / f"{url_id}_meta.json"
        meta = {
            "url": url,
            "url_id": url_id,
            "human_status": record["human"]["status"],
            "bot_status":   record["bot"]["status"],
            "human_html_len": len(record["human"]["html"]),
            "bot_html_len":   len(record["bot"]["html"]),
            "human_method":  record["human"]["method"],
            "bot_method":    record["bot"]["method"],
        }
        meta_path.write_text(json.dumps(meta, indent=2))

    return record


# ── CLI for baking the sample ──────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    import pandas as pd

    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=300, help="Number of URLs to crawl")
    ap.add_argument("--out", default="data/crawl_sample", help="Output directory")
    ap.add_argument("--url", help="Crawl a single URL (ignores --sample)")
    ap.add_argument("--csv", default="final_full (1).csv", help="Source CSV path")
    args = ap.parse_args()

    out_dir = ROOT / args.out

    if args.url:
        print(f"Crawling {args.url} ...")
        rec = dual_view_crawl(args.url, save_dir=out_dir)
        print(json.dumps({
            "url_id": rec["url_id"],
            "human_html_len": len(rec["human"]["html"]),
            "bot_html_len":   len(rec["bot"]["html"]),
        }, indent=2))
        sys.exit(0)

    csv_path = ROOT / args.csv
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}")
        sys.exit(1)

    df = pd.read_csv(csv_path, low_memory=False)
    urls_pos = df[df["drift_score"] == 1]["url"].dropna().sample(
        min(args.sample // 2, len(df[df["drift_score"] == 1])), random_state=42
    ).tolist()
    urls_neg = df[df["drift_score"] == 0]["url"].dropna().sample(
        min(args.sample // 2, len(df[df["drift_score"] == 0])), random_state=42
    ).tolist()
    urls = urls_pos + urls_neg

    print(f"Crawling {len(urls)} URLs → {out_dir}")
    success, fail = 0, 0
    for i, url in enumerate(urls):
        print(f"  [{i+1}/{len(urls)}] {url[:70]}", end=" ")
        t0 = time.time()
        try:
            rec = dual_view_crawl(url, save_dir=out_dir)
            if rec["human"]["html"] or rec["bot"]["html"]:
                success += 1
                print(f"✓ h={len(rec['human']['html'])} b={len(rec['bot']['html'])} ({time.time()-t0:.1f}s)")
            else:
                fail += 1
                print(f"✗ empty ({time.time()-t0:.1f}s)")
        except Exception as e:
            fail += 1
            print(f"✗ ERROR: {e}")

    print(f"\nDone: {success} ok, {fail} failed → {out_dir}")
