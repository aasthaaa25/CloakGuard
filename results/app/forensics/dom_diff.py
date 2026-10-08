"""
DOM tree structural diff — shows the exact nodes added, removed,
or moved between human and bot views, as a readable tree-edit list
rather than just the aggregate tag_distribution_drift score from
the base detection pipeline.
"""

try:
    from bs4 import BeautifulSoup  # type: ignore
    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False


def _node_signature(tag):
    """A signature identifying a node by tag+attrs, ignoring exact text
    content, so we can match structurally-equivalent nodes across views."""
    attrs = tuple(sorted(tag.attrs.items())) if hasattr(tag, "attrs") else ()
    return (tag.name, attrs)


def _flatten_tree(soup, path=""):
    """Returns a list of (path, signature, text_snippet) for every node,
    where path encodes position (e.g. 'html>body>div[2]>a[0]')."""
    nodes = []

    def walk(tag, current_path):
        sig = _node_signature(tag)
        text_snippet = tag.get_text(strip=True)[:60] if hasattr(tag, "get_text") else ""
        nodes.append((current_path, sig, text_snippet))
        child_tags = [c for c in tag.find_all(recursive=False)]
        counts = {}
        for child in child_tags:
            name = child.name
            idx = counts.get(name, 0)
            counts[name] = idx + 1
            walk(child, f"{current_path}>{name}[{idx}]")

    if soup.html:
        walk(soup.html, "html")
    return nodes


def compute_dom_diff(human_html: str, bot_html: str) -> dict:
    """
    Returns a structured diff: nodes present ONLY in the bot view
    (the injection candidates), ONLY in human view, and nodes whose
    text content changed despite structural position matching.
    """
    if not _BS4_AVAILABLE:
        return {
            "nodes_only_in_bot_view": [],
            "nodes_only_in_human_view": [],
            "text_changed_nodes": [],
            "total_human_nodes": 0,
            "total_bot_nodes": 0,
            "injection_node_count": 0,
            "error": "beautifulsoup4 not installed",
        }

    _parser = "lxml"
    try:
        BeautifulSoup("<p/>", "lxml")
    except Exception:
        _parser = "html.parser"
    soup_h = BeautifulSoup(human_html, _parser)
    soup_b = BeautifulSoup(bot_html,   _parser)

    nodes_h = {path: (sig, text) for path, sig, text in _flatten_tree(soup_h)}
    nodes_b = {path: (sig, text) for path, sig, text in _flatten_tree(soup_b)}

    only_in_bot   = []
    only_in_human = []
    text_changed  = []

    for path, (sig, text) in nodes_b.items():
        if path not in nodes_h:
            only_in_bot.append({
                "path": path, "tag": sig[0],
                "attrs": dict(sig[1]), "text": text,
            })
        else:
            h_sig, h_text = nodes_h[path]
            if h_text != text and (h_text or text):
                text_changed.append({
                    "path": path, "tag": sig[0],
                    "human_text": h_text, "bot_text": text,
                })

    for path, (sig, text) in nodes_h.items():
        if path not in nodes_b:
            only_in_human.append({
                "path": path, "tag": sig[0],
                "attrs": dict(sig[1]), "text": text,
            })

    return {
        "nodes_only_in_bot_view":  only_in_bot,      # <-- the injection candidates
        "nodes_only_in_human_view": only_in_human,
        "text_changed_nodes":       text_changed,
        "total_human_nodes":        len(nodes_h),
        "total_bot_nodes":          len(nodes_b),
        "injection_node_count":     len(only_in_bot),
    }
