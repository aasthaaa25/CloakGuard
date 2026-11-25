"""
Layer 3 Orchestrator — triggered automatically the moment a URL's
fusion verdict crosses the alert threshold. Runs every forensic
sub-module and assembles one complete HTML report for the site admin.
"""

import asyncio
import json
import base64
from pathlib import Path
from datetime import datetime
from html import escape

from app.config import FORENSICS_OUTPUT_DIR
from app.forensics.screenshot_diff import generate_diff_heatmap
from app.forensics.dom_diff import compute_dom_diff
from app.forensics.js_trace_diff import capture_js_trace, diff_js_traces
from app.forensics.passive_dns import lookup_all_bot_only_domains

# Re-use the SAME view profiles as the base detection pipeline (Day 1 config)
try:
    import sys
    from pathlib import Path as _P
    sys.path.insert(0, str(_P(__file__).resolve().parents[2]))
    from detection.detection_pipeline import VIEW_PROFILES
except ImportError:
    VIEW_PROFILES = {
        "human": {"user_agent": "Mozilla/5.0", "viewport": {}, "extra_http_headers": {}},
        "bot":   {"user_agent": "Googlebot/2.1", "viewport": {}, "extra_http_headers": {}},
    }


async def trigger_deep_scan(url, crawl_record, artifacts, drift, promo, fusion):
    """
    Fire-and-forget async task. Runs the full forensic suite and
    writes a self-contained HTML report to FORENSICS_OUTPUT_DIR.
    """
    loop = asyncio.get_event_loop()
    url_id = crawl_record.get("url_id", "unknown")

    # ── Screenshot diff (CPU-bound, run in thread pool) ──────────
    human_ss = crawl_record.get("human", {}).get("screenshot_path")
    bot_ss   = crawl_record.get("bot",   {}).get("screenshot_path")
    diff_output_path = f"{FORENSICS_OUTPUT_DIR}/diff_{url_id}.png"
    Path(FORENSICS_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    screenshot_diff_result = None
    if human_ss and bot_ss:
        screenshot_diff_result = await loop.run_in_executor(
            None, generate_diff_heatmap, human_ss, bot_ss, diff_output_path
        )

    # ── DOM diff ───────────────────────────────────────────────────
    human_html = crawl_record.get("human", {}).get("html", "")
    bot_html   = crawl_record.get("bot",   {}).get("html", "")
    dom_diff_result = compute_dom_diff(human_html, bot_html) if human_html and bot_html else None

    # ── JS execution trace diff (re-crawls both views to capture traces) ──
    human_trace = await loop.run_in_executor(
        None, capture_js_trace, url, VIEW_PROFILES["human"]
    )
    bot_trace = await loop.run_in_executor(
        None, capture_js_trace, url, VIEW_PROFILES["bot"]
    )
    js_diff_result = diff_js_traces(human_trace, bot_trace)

    # ── Passive DNS on bot-only domains ────────────────────────────
    dns_results = await loop.run_in_executor(
        None, lookup_all_bot_only_domains, js_diff_result["bot_only_domains"]
    )

    # ── Assemble and write the report ──────────────────────────────
    report_path = await loop.run_in_executor(
        None, _write_forensic_report,
        url, url_id, fusion, drift, promo,
        screenshot_diff_result, dom_diff_result, js_diff_result, dns_results,
    )
    return report_path


def _write_forensic_report(url, url_id, fusion, drift, promo,
                             screenshot_diff, dom_diff, js_diff, dns_results, *, repeat_decision=None):
    timestamp = datetime.now().isoformat()
    safe_url = escape(str(url))
    repeat_section = ""
    if repeat_decision:
        cross = ", ".join(f"{value:.3f}" for value in repeat_decision["cross_profile_scores"])
        controls = ", ".join(f"{key} {value:.3f}"
                             for key, value in repeat_decision["same_profile_scores"].items())
        hashes = "".join(
            f"<tr><td>{escape(view)}</td><td><code>{escape(item['sha256_utf8_html'])}</code></td></tr>"
            for view, item in repeat_decision["captures"].items()
        )
        repeat_section = f"""<div class="section">
<h2>Repeat capture evidence</h2>
<p>Cross-profile scores: {cross}. Same-profile controls: {escape(controls)}.</p>
<p>Both cross-profile scores met cutoff {repeat_decision["threshold"]:.2f} and exceeded the controls.</p>
<table><tr><th>Capture</th><th>SHA-256 of decoded HTML encoded as UTF-8</th></tr>{hashes}</table>
</div>"""

    dom_injection_rows = "".join(
        f"<tr><td>{escape(str(n['path']))}</td><td>{escape(str(n['tag']))}</td><td>{escape(str(n['text'][:60]))}</td></tr>"
        for n in ((dom_diff or {}).get("nodes_only_in_bot_view", [])[:25])
    )

    js_only_rows = "".join(
        f"<tr><td>{escape(str(r['url'][:80]))}</td><td>{escape(str(r['resource_type']))}</td></tr>"
        for r in (js_diff or {}).get("bot_only_requests", [])[:25]
    )

    dns_rows = "".join(
        f"<tr><td>{escape(str(d['domain']))}</td><td>{escape(str(d.get('first_seen','N/A')))}</td>"
        f"<td>{escape(str(d.get('last_seen','N/A')))}</td>"
        f"<td>{escape(str(', '.join(d.get('resolved_ips',[])[:3])))}</td></tr>"
        for d in (dns_results or [])
    )

    diff_img_tag = ""
    if screenshot_diff and screenshot_diff.get("output_path"):
        try:
            with open(screenshot_diff["output_path"], "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            diff_img_tag = (f'<img src="data:image/png;base64,{b64}" '
                             'style="width:100%;border:2px solid #2E75B6;"/>')
        except Exception:
            pass

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Forensic Deep-Scan — {safe_url}</title>
<style>
  body {{ font-family: Arial, sans-serif; max-width: 1200px; margin: 30px auto;
          background: #f4f6fa; color: #222; }}
  h1 {{ color: #1F3864; }}
  h2 {{ color: #2E75B6; border-bottom: 2px solid #2E75B6; padding-bottom: 4px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 12px 0; }}
  td, th {{ padding: 6px 10px; border: 1px solid #ccc; font-size: 13px; }}
  th {{ background: #1F3864; color: white; }}
  .banner {{ background: #c00000; color: white; padding: 16px;
              border-radius: 6px; font-size: 20px; font-weight: bold; }}
  .section {{ margin: 24px 0; background: white; padding: 16px;
               border-radius: 8px; box-shadow: 0 2px 6px rgba(0,0,0,.08); }}
  .metric {{ display: inline-block; background: #1F3864; color: white;
              padding: 8px 18px; border-radius: 4px; margin: 4px;
              font-size: 15px; font-weight: bold; }}
</style>
</head>
<body>

<h1>🔍 Automated Forensic Deep-Scan Report</h1>
<p><b>URL:</b> {safe_url} &nbsp;|&nbsp; <b>Generated:</b> {timestamp}</p>

<div class="banner">HEURISTIC ALERT — uncalibrated score {escape(str(fusion.get('final_risk_score', 'N/A')))} on path {escape(str(fusion.get('scoring_path', 'unspecified')))}. This package does not by itself confirm cloaking or identify an attacker.</div>

{repeat_section}

<div class="section">
<h2>Executive Summary</h2>
<span class="metric">Risk Score: {escape(str(fusion.get('final_risk_score', 'N/A')))}</span>
<span class="metric">Alert: {'YES' if fusion.get('alert') else 'NO'}</span>
<span class="metric">DOM Injections: {escape(str((dom_diff or {}).get('injection_node_count','N/A')))}</span>
<span class="metric">Bot-only Requests: {escape(str((js_diff or {}).get('bot_only_request_count','N/A')))}</span>
</div>

<div class="section">
<h2>1. Visual Diff (Human | Bot | Highlighted Differences)</h2>
{diff_img_tag if diff_img_tag else '<p><em>Screenshots not available (playwright not installed or no screenshot path).</em></p>'}
<p>{escape(str((screenshot_diff or {}).get('flagged_region_count', 0)))} differing regions found,
{escape(str((screenshot_diff or {}).get('diff_percentage', 0)))}% of pixels differ.</p>
</div>

<div class="section">
<h2>2. DOM Nodes Injected ONLY in Bot View</h2>
<table><tr><th>DOM Path</th><th>Tag</th><th>Text Content</th></tr>
{dom_injection_rows if dom_injection_rows else '<tr><td colspan="3">None detected or HTML not available</td></tr>'}
</table>
<p>Total injected nodes: {escape(str((dom_diff or {}).get('injection_node_count', 'N/A')))}</p>
</div>

<div class="section">
<h2>3. Network Requests Fired ONLY in Bot View (JS-Triggered)</h2>
<table><tr><th>Request URL</th><th>Type</th></tr>
{js_only_rows if js_only_rows else '<tr><td colspan="2">None detected or playwright not available</td></tr>'}
</table>
</div>

<div class="section">
<h2>4. Passive DNS — Bot-Only Domains</h2>
<p><em>Passive lookup only — no contact with attacker infrastructure.</em></p>
<table><tr><th>Domain</th><th>First Seen</th><th>Last Seen</th><th>Resolved IPs</th></tr>
{dns_rows if dns_rows else '<tr><td colspan="4">No bot-only domains detected, or no API key configured.</td></tr>'}
</table>
</div>

<div class="section">
<h2>5. Recommended Remediation</h2>
<ol>
<li>Inspect the DOM-injection nodes above to locate the exact injected snippet in your CMS/file system.</li>
<li>Search your codebase/database for the domains listed in Section 4 to find the injection point.</li>
<li>Check file modification times around when bot-only domains first appeared (per passive DNS first_seen).</li>
<li>Review the evidence and verify any suspected modification at the origin before applying a response.</li>
</ol>
</div>

<div class="section">
<h2>6. Detection Pipeline Data</h2>
<table>
<tr><th>Signal</th><th>Value</th></tr>
<tr><td>Drift Score</td><td>{escape(str(drift.get('drift_score','N/A')))}</td></tr>
<tr><td>Promo Score</td><td>{escape(str(promo.get('promo_score','N/A')))}</td></tr>
<tr><td>Model Probability</td><td>{escape(str(fusion.get('model_probability','N/A')))}</td></tr>
<tr><td>Flagged Vectors</td><td>{len(fusion.get('flagged_vectors',[]))}</td></tr>
</table>
</div>

</body></html>"""

    report_path = f"{FORENSICS_OUTPUT_DIR}/forensic_report_{url_id}.html"
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).write_text(html, encoding="utf-8")
    return report_path
