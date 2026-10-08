"""
Simple async token-bucket rate limiter, keyed by JA3 hash rather
than IP — so a distributed botnet sharing one fingerprint (a common
real-world pattern for unsophisticated scraping tooling deployed
across many machines) is still rate-limited as a single entity.
"""

import time
import asyncio
from collections import defaultdict
from app.config import RATE_LIMIT_TOKENS_PER_MINUTE, RATE_LIMIT_BUCKET_SIZE


class TokenBucket:
    def __init__(self, capacity: int, refill_per_minute: int):
        self.capacity    = capacity
        self.refill_rate = refill_per_minute / 60.0  # tokens per second
        self.tokens      = capacity
        self.last_refill = time.time()
        self._lock       = asyncio.Lock()

    async def consume(self, n: int = 1) -> bool:
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now
            if self.tokens >= n:
                self.tokens -= n
                return True
            return False


_buckets: defaultdict = defaultdict(
    lambda: TokenBucket(RATE_LIMIT_BUCKET_SIZE, RATE_LIMIT_TOKENS_PER_MINUTE)
)


async def check_rate_limit(ja3_hash: str) -> bool:
    """Returns True if this request is ALLOWED under the rate limit."""
    bucket = _buckets[ja3_hash]
    return await bucket.consume(1)
