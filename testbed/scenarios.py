"""Local pages with known behavior. Nothing here is a remote capture."""

SCENARIOS = {
    "clean_static": {
        "known_behavior": "same_content_across_profiles",
        "human": "<html><head><title>North Market</title></head><body><h1>North Market</h1><p>Today's produce list.</p></body></html>",
        "bot": "<html><head><title>North Market</title></head><body><h1>North Market</h1><p>Today's produce list.</p></body></html>",
    },
    "legitimate_dynamic": {
        "known_behavior": "ordinary_changing_content",
        "human": None,
        "bot": None,
    },
    "benign_promotional": {
        "known_behavior": "promotional_vocabulary_without_an_attack",
        "human": "<html><head><title>North Market sale</title></head><body><h1>This week: apples</h1><p>A lawful produce discount for every visitor.</p></body></html>",
        "bot": "<html><head><title>North Market sale</title></head><body><h1>This week: apples</h1><p>A lawful produce discount for every visitor.</p></body></html>",
    },
    "selective_promotional_injection": {
        "known_behavior": "controlled_spam_in_bot_profile",
        "human": "<html><head><title>North Market</title></head><body><h1>North Market</h1><p>Today's produce list.</p></body></html>",
        "bot": "<html><head><title>North Market</title></head><body><h1>North Market</h1><p>Today's produce list.</p><div style=\"display:none\">free casino jackpot viagra</div></body></html>",
    },
    "reverse_selective_injection": {
        "known_behavior": "controlled_injection_in_human_profile",
        "human": "<html><head><title>North Market</title></head><body><h1>North Market</h1><p>cheap pills casino bonus</p></body></html>",
        "bot": "<html><head><title>North Market</title></head><body><h1>North Market</h1><p>Today's produce list.</p></body></html>",
    },
    "hidden_link_injection": {
        "known_behavior": "controlled_hidden_link_in_bot_profile",
        "human": "<html><head><title>North Market</title></head><body><h1>North Market</h1><a href=\"/about\">About</a></body></html>",
        "bot": "<html><head><title>North Market</title></head><body><h1>North Market</h1><a href=\"/about\">About</a><a href=\"http://spam.example/offer\" style=\"display:none\">offer</a></body></html>",
    },
    "overt_modification": {
        "known_behavior": "controlled_visible_defacement",
        "human": "<html><head><title>Hacked</title></head><body><h1>This page was replaced</h1></body></html>",
        "bot": "<html><head><title>Hacked</title></head><body><h1>This page was replaced</h1></body></html>",
    },
    "access_challenge": {
        "known_behavior": "profile_dependent_challenge",
        "human": "<html><head><title>North Market</title></head><body><h1>North Market</h1><p>Today's produce list.</p></body></html>",
        "bot": "<html><head><title>Just a moment</title></head><body><h1>Verify you are human</h1><p>Access denied</p></body></html>",
    },
}


def dynamic_page(token: str) -> str:
    return (
        "<html><head><title>North Market clock</title></head><body>"
        f"<h1>North Market</h1><p>Ordinary counter {token}</p></body></html>"
    )
