"""Calibration and reserved pages. North Market and Harbor Books are not included."""

SHORT = {
    "cedar_clinic": "Cedar Clinic",
    "quartz_supply": "Quartz Supply",
}
LONG = {
    "maple_archive": "Maple Archive",
    "linen_press": "Linen Press",
}
CALIBRATION = ("cedar_clinic", "maple_archive")
RESERVED = ("quartz_supply", "linen_press")

FEW = "casino poker"
MANY = "casino poker slots jackpot betting viagra cialis pharmacy replica lottery"
FILLER = {
    "cedar_clinic": "The clinic posts its weekday hours.",
    "maple_archive": "The archive describes a local collection and its reading room.",
    "quartz_supply": "The workshop lists finished stone samples and pickup times.",
    "linen_press": "The press describes paper stock, ink, and binding appointments.",
}


def _body(family: str, core: str, long_page: bool) -> str:
    text = core
    if long_page:
        text += " " + " ".join([FILLER[family]] * 40)
    return text


def render(family: str, title: str, core: str, extra_html: str = "") -> str:
    long_page = family in LONG
    name = SHORT.get(family) or LONG[family]
    body = _body(family, core, long_page)
    return (
        f"<html><head><title>{title or name}</title></head>"
        f"<body><h1>{name}</h1><p>{body}</p>{extra_html}</body></html>"
    )


def pages_for(family: str, profile: str, scenario: str, token: str) -> str:
    name = SHORT.get(family) or LONG[family]
    filler = FILLER[family]
    if scenario == "clean":
        return render(family, name, filler)
    if scenario == "both_in_list":
        return render(family, name, filler + " " + MANY)
    if scenario == "both_out_of_list":
        return render(family, name, "A lawful discount for every visitor.")
    if scenario == "bot_few":
        core = filler + (" " + FEW if profile == "bot" else "")
        return render(family, name, core)
    if scenario == "bot_substantial":
        core = filler + (" " + MANY if profile == "bot" else "")
        return render(family, name, core)
    if scenario == "human_only":
        core = filler + (" " + MANY if profile == "human" else "")
        return render(family, name, core)
    if scenario == "counter":
        return render(family, name, f"Ordinary counter {token}")
    if scenario == "cookie":
        extra = " This page also shows a cookie notice." if profile == "bot" else ""
        return render(family, name, filler + extra)
    if scenario == "nav_change":
        link = '<a href="/hours">Hours</a>' if profile == "bot" else '<a href="/about">About</a>'
        return render(family, name, filler, link)
    if scenario == "rotating_post":
        line = "The notice board lists a concert." if profile == "bot" else "The notice board lists a lecture."
        return render(family, name, line)
    if scenario == "challenge":
        if profile == "bot":
            return "<html><head><title>Just a moment</title></head><body><h1>Verify you are human</h1><p>Access denied</p></body></html>"
        return render(family, name, filler)
    if scenario == "neutral_hidden_link":
        link = '<a href="/archive" style="display:none">archive</a>' if profile == "bot" else ""
        return render(family, name, filler, link)
    if scenario == "hidden_in_vocab_link":
        link = '<a href="http://spam.example/casino" style="display:none">casino poker</a>' if profile == "bot" else ""
        return render(family, name, filler, link)
    if scenario == "identical_defacement":
        return "<html><head><title>Replaced</title></head><body><h1>This page was replaced</h1></body></html>"
    if scenario == "redirect_stub":
        return "<html><head><title>Page Redirection</title></head><body><p>Follow the link.</p></body></html>"
    if scenario == "error_page":
        return "<html><head><title>Not found</title></head><body><p>Nothing is here.</p></body></html>"
    raise KeyError(scenario)


ROLES = {
    "clean": "negative",
    "both_in_list": "negative",
    "both_out_of_list": "negative",
    "bot_few": "positive",
    "bot_substantial": "positive_substantial",
    "human_only": "negative",
    "counter": "negative",
    "cookie": "negative",
    "nav_change": "negative",
    "rotating_post": "negative",
    "challenge": "negative",
    "neutral_hidden_link": "negative",
    "hidden_in_vocab_link": "positive",
    "identical_defacement": "negative",
    "redirect_stub": "negative",
    "error_page": "negative",
}
SCENARIOS = tuple(ROLES)
APP_VERSION = "local-v2"
