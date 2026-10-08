"""
JS Execution Trace Capture + Diff
Extends the dual-view crawler (re-uses the same Playwright contexts)
to record every network request fired and console message logged
during page load, for comparison across views.
"""


def capture_js_trace(url: str, view_profile: dict, timeout_ms: int = 20000) -> dict:
    """
    Loads a URL under the given view profile (human or bot — same
    VIEW_PROFILES dict from the detection pipeline's Day 1 config)
    while recording every outgoing network request and console event.
    """
    requests_fired = []
    console_events = []

    try:
        from playwright.sync_api import sync_playwright  # type: ignore  # optional dep
    except ImportError:
        return {
            "requests": [], "console": [],
            "error": "playwright not installed — run: pip install playwright && playwright install chromium",
        }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=view_profile["user_agent"],
            viewport=view_profile["viewport"],
            extra_http_headers=view_profile["extra_http_headers"],
        )
        page = context.new_page()

        page.on("request", lambda req: requests_fired.append({
            "url":           req.url,
            "method":        req.method,
            "resource_type": req.resource_type,
        }))
        page.on("console", lambda msg: console_events.append({
            "type": msg.type,
            "text": msg.text[:200],
        }))

        try:
            page.goto(url, timeout=timeout_ms, wait_until="networkidle")
            page.wait_for_timeout(1500)
        except Exception as e:
            console_events.append({"type": "error", "text": str(e)})

        context.close()
        browser.close()

    return {"requests": requests_fired, "console": console_events}


def diff_js_traces(human_trace: dict, bot_trace: dict) -> dict:
    """
    Identifies network requests that fired ONLY in the bot view —
    these often point directly at the spam-delivery infrastructure,
    since promotional content is frequently lazy-loaded via a
    separate script/XHR call rather than baked into initial HTML.
    """
    human_urls = {r["url"] for r in human_trace.get("requests", [])}
    bot_urls   = {r["url"] for r in bot_trace.get("requests", [])}

    bot_only_requests   = [r for r in bot_trace.get("requests", [])   if r["url"] not in human_urls]
    human_only_requests = [r for r in human_trace.get("requests", []) if r["url"] not in bot_urls]

    from urllib.parse import urlparse
    bot_only_domains = sorted(set(
        urlparse(r["url"]).netloc
        for r in bot_only_requests
        if urlparse(r["url"]).netloc
    ))

    return {
        "bot_only_requests":    bot_only_requests,
        "human_only_requests":  human_only_requests,
        "bot_only_domains":     bot_only_domains,    # <-- feeds passive DNS lookup next
        "bot_only_request_count": len(bot_only_requests),
    }
