"""
Tiny mock origin server for integration testing.
Run standalone:  python tests/mock_origin.py
(starts on port 8000 — the default ORIGIN_SERVER_URL in app/config.py)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse
    import uvicorn
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

if _AVAILABLE:
    app = FastAPI(title="Mock Origin Server")

    CLEAN_PAGE = """<!DOCTYPE html>
    <html><head><title>Test Page</title></head>
    <body>
      <h1>Welcome to the Test Site</h1>
      <p>This is a legitimate page.</p>
      <a href="/about">About us</a>
    </body></html>"""

    CLOAKED_PAGE = """<!DOCTYPE html>
    <html><head><title>Test Page</title></head>
    <body>
      <h1>Welcome to the Test Site</h1>
      <p>This is a legitimate page.</p>
      <!-- INJECTED BY ATTACKER: -->
      <div style="display:none">
        <a href="http://casino-spam.tk/free-slots">FREE CASINO SLOTS</a>
        <a href="http://pharma-pills.cc/viagra">Buy Pills Online</a>
      </div>
    </body></html>"""

    @app.get("/{full_path:path}")
    async def serve(full_path: str, request: Request):
        ua = request.headers.get("user-agent", "")
        is_bot = "googlebot" in ua.lower()
        content = CLOAKED_PAGE if is_bot else CLEAN_PAGE
        return HTMLResponse(content=content)

    if __name__ == "__main__":
        print("[mock_origin] Starting on http://127.0.0.1:8000")
        uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
else:
    print("fastapi/uvicorn not installed; mock origin unavailable.")
