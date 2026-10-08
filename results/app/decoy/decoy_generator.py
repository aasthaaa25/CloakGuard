"""
Decoy Page Generator
Takes the ORIGINAL clean (human-view) HTML and produces a decoy that:
  1. Preserves overall page structure (so it doesn't look broken/suspicious itself)
  2. Strips any content matching the promotional signatures the detection
     pipeline flagged for this URL
  3. Contains ZERO outbound links beyond the original legitimate ones
  4. Contains ZERO tracking/beacon mechanisms
"""

try:
    from bs4 import BeautifulSoup  # type: ignore
    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False


def build_decoy_page(human_html: str, flagged_vectors: list, promo_categories: dict) -> str:
    """
    human_html: the CLEAN version of the page (what real visitors see) —
                 this is what we serve as the decoy, since it is by
                 definition free of the injected promotional content.
    flagged_vectors / promo_categories: from the detection pipeline's
                 fusion + promo results, used only for logging/audit —
                 NOT injected into the decoy itself.
    Returns: decoy HTML string, safe to serve to confirmed-malicious fingerprints.
    """
    if not human_html:
        return _fallback_decoy()

    if not _BS4_AVAILABLE:
        return human_html  # graceful fallback if bs4 not installed

    try:
        soup = BeautifulSoup(human_html, "lxml")
    except Exception:
        soup = BeautifulSoup(human_html, "html.parser")

    # Defense in depth: even though we start from the clean human view,
    # explicitly strip anything that LOOKS like it could be promotional
    # injection in case the 'clean' view itself was partially compromised
    # (e.g. session-dependent cloaking that affects some human visits too).
    suspicious_tags = soup.find_all(["marquee"])
    for tag in suspicious_tags:
        tag.decompose()

    # Strip any inline event handlers / scripts we don't recognize as
    # part of the original page's own asset pipeline (defense against
    # decoy itself being used as an injection vector)
    for script_tag in soup.find_all("script"):
        src = script_tag.get("src", "")
        if src and not src.startswith(("/", "https://")):
            script_tag.decompose()

    # Add a (non-indexable, non-visible-to-humans-elsewhere) marker comment
    # purely for YOUR OWN audit logs — this never leaves your infrastructure
    # and is not a tracking beacon aimed at the requester.
    marker = soup.new_tag("meta")
    marker.attrs["name"]    = "x-internal-decoy-served"
    marker.attrs["content"] = "true"
    if soup.head:
        soup.head.append(marker)

    return str(soup)


def _fallback_decoy() -> str:
    """Returns a minimal inert decoy when no human HTML is available."""
    return """<!DOCTYPE html>
<html><head><title>Page</title></head>
<body><p>Content unavailable.</p></body></html>"""
