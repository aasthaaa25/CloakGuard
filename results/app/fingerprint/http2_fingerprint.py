"""
HTTP/2 SETTINGS frame fingerprinting — a secondary, complementary
signal to JA3. Real browsers send a highly characteristic SETTINGS
frame (specific header table size, max concurrent streams, etc.)
immediately after the TLS handshake completes. Most scraping/cloaking
backends built on simple HTTP libraries either don't speak HTTP/2 at
all, or send a generic, differently-ordered SETTINGS frame.
"""

import hashlib

# Standard HTTP/2 SETTINGS parameter IDs we fingerprint on
SETTINGS_IDS = {
    0x1: "HEADER_TABLE_SIZE",
    0x2: "ENABLE_PUSH",
    0x3: "MAX_CONCURRENT_STREAMS",
    0x4: "INITIAL_WINDOW_SIZE",
    0x5: "MAX_FRAME_SIZE",
    0x6: "MAX_HEADER_LIST_SIZE",
}


def compute_http2_fingerprint(settings_frame: dict, window_update: int = None) -> str:
    """
    settings_frame: dict of {setting_id: value} as received in the
                     connection-level SETTINGS frame.
    Returns a stable hash representing this client's HTTP/2 'shape'.
    """
    ordered_items = sorted(settings_frame.items())
    fp_string = ",".join(f"{k}:{v}" for k, v in ordered_items)
    if window_update is not None:
        fp_string += f"|wu:{window_update}"
    return hashlib.md5(fp_string.encode()).hexdigest()


# Reference fingerprints for well-known LEGITIMATE crawlers, so we
# never accidentally rate-limit real Googlebot/Bingbot — see §1.7
KNOWN_LEGITIMATE_BOT_HTTP2_FINGERPRINTS: dict = {
    # Populate empirically: run this fingerprinter against verified
    # Googlebot/Bingbot requests (verified via reverse-DNS + forward-DNS
    # confirmation, the official method Google documents) and record
    # their actual fingerprints here before going live.
}
