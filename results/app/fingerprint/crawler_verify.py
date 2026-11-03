"""
Verified Crawler Identification — Google's official method:
https://developers.google.com/search/docs/crawling-indexing/verifying-googlebot
1. Reverse DNS lookup on the source IP
2. Confirm the hostname ends in googlebot.com or google.com
3. Forward DNS lookup on that hostname
4. Confirm it resolves back to the original source IP
Both directions must match. Bingbot has an equivalent documented method.
"""

import ipaddress
import time

import dns.exception
import dns.resolver

from app.config import CRAWLER_DNS_TIMEOUT_SECONDS

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

    ip = ipaddress.ip_address(source_ip)
    deadline = time.monotonic() + CRAWLER_DNS_TIMEOUT_SECONDS
    result = {"verified": False, "claimed_bot": claimed_bot}
    try:
        ptr_records = dns.resolver.resolve_address(str(ip), lifetime=CRAWLER_DNS_TIMEOUT_SECONDS)
        suffixes = VERIFIED_CRAWLER_SUFFIXES[claimed_bot]
        for ptr in ptr_records:
            hostname = str(ptr.target).lower().rstrip(".")
            if not hostname.endswith(tuple(suffixes)):
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return {**result, "reason": "dns_unavailable"}
            try:
                records = dns.resolver.resolve(
                    hostname + ".", "A" if ip.version == 4 else "AAAA", lifetime=remaining,
                )
            except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                continue
            if any(ipaddress.ip_address(record.address) == ip for record in records):
                return {**result, "verified": True, "hostname": hostname,
                        "reason": "dns_verification_passed"}
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return {**result, "reason": "reverse_dns_no_match"}
    except (dns.exception.DNSException, OSError):
        return {**result, "reason": "dns_unavailable"}
    return {**result, "reason": "forward_dns_or_hostname_mismatch"}
