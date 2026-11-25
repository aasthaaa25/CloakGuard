"""Static fallback page for the isolated owner-policy demonstration."""


def build_decoy_page(human_html: str, flagged_vectors: list, promo_categories: dict) -> str:
    """Return an inert document independent of all captured page data."""
    return """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="x-internal-decoy-served" content="true">
<meta name="robots" content="noindex, nofollow">
<title>Content unavailable</title></head>
<body><p>Content unavailable.</p></body></html>"""
