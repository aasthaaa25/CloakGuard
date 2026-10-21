"""
Verified Crawler Identification — Google's official method:
https://developers.google.com/search/docs/crawling-indexing/verifying-googlebot
1. Reverse DNS lookup on the source IP
2. Confirm the hostname ends in googlebot.com or google.com
3. Forward DNS lookup on that hostname
4. Confirm it resolves back to the original source IP
Both directions must match. Bingbot has an equivalent documented method.
"""

import socket

from app.config import CRAWLER_DNS_FAILURE_POLICY, CRAWLER_DNS_TIMEOUT_SECONDS

VERIFIED_CRAWLER_SUFFIXES = {
    "googlebot": [".googlebot.com", ".google.com"],
    "bingbot":   [".search.msn.com"],
}

CLAIMED_BOT_UA_PATTERNS = {
    "googlebot": ["googlebot"],
    "bingbot":   ["bingbot", "msnbot"],
}


def identify_claimed_bot(user_agent: str):
    ua_lower = (user_agent or "").lower()
    for bot_name, patterns in CLAIMED_BOT_UA_PATTERNS.items():
        if any(p in ua_lower for p in patterns):
            return bot_name
    return None


def verify_crawler(source_ip: str, user_agent: str) -> dict:
    """
    Returns {'verified': bool, 'claimed_bot': str|None, 'reason': str}
    Call this BEFORE any fingerprint scoring logic for every request
    whose User-Agent claims to be a known crawler.
    """
    claimed_bot = identify_claimed_bot(user_agent)
    if claimed_bot is None:
        return {
            "verified": False,
            "claimed_bot": None,
            "reason": "not_claiming_to_be_a_known_crawler",
        }

    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(CRAWLER_DNS_TIMEOUT_SECONDS)
    try:
        try:
            hostname, _, _ = socket.gethostbyaddr(source_ip)
        except (socket.herror, socket.timeout, OSError):
            return {
                "verified": False,
                "claimed_bot": claimed_bot,
                "reason": "reverse_dns_failed",
                "dns_policy": CRAWLER_DNS_FAILURE_POLICY,
                "fail_closed": CRAWLER_DNS_FAILURE_POLICY == "fail_closed",
            }

        valid_suffixes = VERIFIED_CRAWLER_SUFFIXES.get(claimed_bot, [])
        if not any(hostname.endswith(suf) for suf in valid_suffixes):
            return {
                "verified": False,
                "claimed_bot": claimed_bot,
                "hostname": hostname,
                "reason": f"hostname {hostname} not in valid range for {claimed_bot}",
                "dns_policy": CRAWLER_DNS_FAILURE_POLICY,
                "fail_closed": True,
            }

        try:
            forward_ips = socket.gethostbyname_ex(hostname)[2]
        except (socket.gaierror, socket.timeout, OSError):
            return {
                "verified": False,
                "claimed_bot": claimed_bot,
                "hostname": hostname,
                "reason": "forward_dns_failed",
                "dns_policy": CRAWLER_DNS_FAILURE_POLICY,
                "fail_closed": CRAWLER_DNS_FAILURE_POLICY == "fail_closed",
            }

        if source_ip not in forward_ips:
            return {
                "verified": False,
                "claimed_bot": claimed_bot,
                "hostname": hostname,
                "reason": "forward_dns_mismatch",
                "dns_policy": CRAWLER_DNS_FAILURE_POLICY,
                "fail_closed": True,
            }

        return {
            "verified": True,
            "claimed_bot": claimed_bot,
            "hostname": hostname,
            "reason": "dns_verification_passed",
            "dns_policy": CRAWLER_DNS_FAILURE_POLICY,
        }
    finally:
        socket.setdefaulttimeout(old_timeout)
