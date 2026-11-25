import sys
from pathlib import Path
from importlib import import_module

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def offline_http_capture(monkeypatch):
    crawl = import_module("detection.pipeline.crawl")
    monkeypatch.setattr(crawl, "_PLAYWRIGHT", False)
    monkeypatch.setattr(crawl, "_fetch_httpx", lambda url, profile: {
        "status": 200, "method": "fixture",
        "html": "<html><body><p>Controlled fixture</p></body></html>",
    })
