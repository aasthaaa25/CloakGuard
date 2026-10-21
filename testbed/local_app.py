"""
Authorized local application. It serves a page that depends on the User-Agent.

This is the origin used by the real httpx fetcher. It is not a remote site.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGES = {
    "north_market": {
        "clean_static": {
            "human": "<html><head><title>North Market</title></head><body><h1>North Market</h1><p>Today's produce list.</p></body></html>",
            "bot": "<html><head><title>North Market</title></head><body><h1>North Market</h1><p>Today's produce list.</p></body></html>",
        },
        "benign_promotional": {
            "human": "<html><head><title>North Market sale</title></head><body><h1>This week: apples</h1><p>A lawful produce discount for every visitor.</p></body></html>",
            "bot": "<html><head><title>North Market sale</title></head><body><h1>This week: apples</h1><p>A lawful produce discount for every visitor.</p></body></html>",
        },
        "selective_promotional_injection": {
            "human": "<html><head><title>North Market</title></head><body><h1>North Market</h1><p>Today's produce list.</p></body></html>",
            "bot": "<html><head><title>North Market</title></head><body><h1>North Market</h1><p>Today's produce list.</p><div style=\"display:none\">free casino jackpot viagra</div></body></html>",
        },
        "reverse_selective_injection": {
            "human": "<html><head><title>North Market</title></head><body><h1>North Market</h1><p>cheap pills casino bonus</p></body></html>",
            "bot": "<html><head><title>North Market</title></head><body><h1>North Market</h1><p>Today's produce list.</p></body></html>",
        },
        "hidden_link_injection": {
            "human": "<html><head><title>North Market</title></head><body><h1>North Market</h1><a href=\"/about\">About</a></body></html>",
            "bot": "<html><head><title>North Market</title></head><body><h1>North Market</h1><a href=\"/about\">About</a><a href=\"http://spam.example/offer\" style=\"display:none\">offer</a></body></html>",
        },
        "overt_modification": {
            "human": "<html><head><title>Hacked</title></head><body><h1>This page was replaced</h1></body></html>",
            "bot": "<html><head><title>Hacked</title></head><body><h1>This page was replaced</h1></body></html>",
        },
        "access_challenge": {
            "human": "<html><head><title>North Market</title></head><body><h1>North Market</h1><p>Today's produce list.</p></body></html>",
            "bot": "<html><head><title>Just a moment</title></head><body><h1>Verify you are human</h1><p>Access denied</p></body></html>",
        },
    },
    "harbor_books": {
        "clean_static": {
            "human": "<html><head><title>Harbor Books</title></head><body><h1>Harbor Books</h1><p>Today's shelf list.</p></body></html>",
            "bot": "<html><head><title>Harbor Books</title></head><body><h1>Harbor Books</h1><p>Today's shelf list.</p></body></html>",
        },
        "benign_promotional": {
            "human": "<html><head><title>Harbor Books sale</title></head><body><h1>This week: novels</h1><p>A lawful book discount for every visitor.</p></body></html>",
            "bot": "<html><head><title>Harbor Books sale</title></head><body><h1>This week: novels</h1><p>A lawful book discount for every visitor.</p></body></html>",
        },
        "selective_promotional_injection": {
            "human": "<html><head><title>Harbor Books</title></head><body><h1>Harbor Books</h1><p>Today's shelf list.</p></body></html>",
            "bot": "<html><head><title>Harbor Books</title></head><body><h1>Harbor Books</h1><p>Today's shelf list.</p><div style=\"display:none\">free casino jackpot viagra</div></body></html>",
        },
        "reverse_selective_injection": {
            "human": "<html><head><title>Harbor Books</title></head><body><h1>Harbor Books</h1><p>cheap pills casino bonus</p></body></html>",
            "bot": "<html><head><title>Harbor Books</title></head><body><h1>Harbor Books</h1><p>Today's shelf list.</p></body></html>",
        },
        "hidden_link_injection": {
            "human": "<html><head><title>Harbor Books</title></head><body><h1>Harbor Books</h1><a href=\"/about\">About</a></body></html>",
            "bot": "<html><head><title>Harbor Books</title></head><body><h1>Harbor Books</h1><a href=\"/about\">About</a><a href=\"http://spam.example/offer\" style=\"display:none\">offer</a></body></html>",
        },
        "overt_modification": {
            "human": "<html><head><title>Replaced</title></head><body><h1>This page was replaced</h1></body></html>",
            "bot": "<html><head><title>Replaced</title></head><body><h1>This page was replaced</h1></body></html>",
        },
        "access_challenge": {
            "human": "<html><head><title>Harbor Books</title></head><body><h1>Harbor Books</h1><p>Today's shelf list.</p></body></html>",
            "bot": "<html><head><title>Just a moment</title></head><body><h1>Verify you are human</h1><p>Access denied</p></body></html>",
        },
    },
}

COUNTERS = {}


def page_for(family: str, scenario: str, profile: str) -> tuple[int, str]:
    if scenario == "legitimate_dynamic":
        key = f"{family}:{scenario}"
        COUNTERS[key] = COUNTERS.get(key, 0) + 1
        title = "North Market clock" if family == "north_market" else "Harbor Books clock"
        name = "North Market" if family == "north_market" else "Harbor Books"
        html = (
            f"<html><head><title>{title}</title></head><body>"
            f"<h1>{name}</h1><p>Ordinary counter {COUNTERS[key]}</p></body></html>"
        )
        return 200, html
    family_pages = PAGES.get(family)
    if family_pages is None or scenario not in family_pages:
        return 404, "<html><head><title>Missing</title></head><body>Unknown scenario</body></html>"
    return 200, family_pages[scenario][profile]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parts = [part for part in self.path.split("/") if part]
        if len(parts) != 2:
            body = "<html><head><title>Missing</title></head><body>Use /family/scenario</body></html>"
            status = 404
        else:
            profile = "bot" if "Googlebot" in self.headers.get("User-Agent", "") else "human"
            status, body = page_for(parts[0], parts[1], profile)
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        return


def serve(port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    return server
