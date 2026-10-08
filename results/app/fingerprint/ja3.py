"""
JA3 TLS Fingerprinting
Parses the raw TLS ClientHello (captured at the proxy's TCP layer,
before TLS termination) and computes the JA3 hash.
Reference algorithm: JA3 by Salesforce/John Althouse (open, public spec).
"""

import hashlib

GREASE_VALUES = {
    0x0a0a, 0x1a1a, 0x2a2a, 0x3a3a, 0x4a4a, 0x5a5a, 0x6a6a, 0x7a7a,
    0x8a8a, 0x9a9a, 0xaaaa, 0xbaba, 0xcaca, 0xdada, 0xeaea, 0xfafa,
}


def _filter_grease(values):
    """GREASE values are intentionally-random placeholder values some
    clients insert to test extension-handling robustness. JA3 excludes
    them since they're noise, not a real fingerprint signal."""
    return [v for v in values if v not in GREASE_VALUES]


def compute_ja3(client_hello_bytes: bytes) -> dict:
    """
    Parses a raw TLS ClientHello and returns the JA3 string + MD5 hash.
    Returns None fields gracefully if parsing fails (e.g. non-TLS traffic).
    """
    try:
        from scapy.all import TLS  # type: ignore  # optional dep
    except ImportError:
        return {"ja3": None, "ja3_hash": None, "error": "scapy not installed"}

    try:
        pkt = TLS(client_hello_bytes)
        ch = pkt.msg[0]   # TLSClientHello
    except Exception as e:
        return {"ja3": None, "ja3_hash": None, "error": str(e)}

    tls_version = ch.version
    ciphers     = _filter_grease(ch.ciphers or [])

    extensions      = []
    elliptic_curves = []
    ec_point_formats = []

    for ext in (ch.ext or []):
        ext_type = ext.type
        extensions.append(ext_type)
        if ext_type == 0x0a:   # supported_groups (elliptic curves)
            elliptic_curves = _filter_grease(getattr(ext, "groups", []) or [])
        if ext_type == 0x0b:   # ec_point_formats
            ec_point_formats = list(getattr(ext, "ecpl", []) or [])

    extensions = _filter_grease(extensions)

    ja3_string = "{},{},{},{},{}".format(
        tls_version,
        "-".join(str(c) for c in ciphers),
        "-".join(str(e) for e in extensions),
        "-".join(str(c) for c in elliptic_curves),
        "-".join(str(p) for p in ec_point_formats),
    )
    ja3_hash = hashlib.md5(ja3_string.encode()).hexdigest()

    return {"ja3": ja3_string, "ja3_hash": ja3_hash, "error": None}
