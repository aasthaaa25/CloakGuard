"""
Passive DNS Lookup
Queries public passive-DNS APIs about bot-only domains found by
the JS trace diff — entirely passive, no contact with the domain itself.
Uses a free/public-tier API as an example; swap in your preferred
provider (SecurityTrails, VirusTotal, etc.) by changing the request URL.
"""

import requests as _requests
from app.config import PASSIVE_DNS_API_KEY


def passive_dns_lookup(domain: str) -> dict:
    """
    Returns historical DNS resolution data for a domain WITHOUT
    ever contacting that domain. Example uses a generic passive-DNS
    REST API shape — adapt the endpoint/auth to your chosen provider.
    """
    if not PASSIVE_DNS_API_KEY:
        return {
            "domain": domain,
            "error":  "no_api_key_configured",
            "records": [],
        }

    try:
        resp = _requests.get(
            f"https://api.your-passive-dns-provider.com/v1/pdns/{domain}",
            headers={"Authorization": f"Bearer {PASSIVE_DNS_API_KEY}"},
            timeout=10,
        )
        data = resp.json()
        return {
            "domain":          domain,
            "first_seen":      data.get("first_seen"),
            "last_seen":       data.get("last_seen"),
            "resolved_ips":    data.get("resolved_ips", []),
            "related_domains": data.get("related_domains", []),
            "error":           None,
        }
    except Exception as e:
        return {"domain": domain, "error": str(e), "records": []}


def lookup_all_bot_only_domains(domains: list) -> list:
    return [passive_dns_lookup(d) for d in domains]
