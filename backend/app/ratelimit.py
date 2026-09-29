"""In-memory sliding-window rate limits.

State lives in the process, which is fine for the single uvicorn worker this app runs as
(SQLite rules out several workers anyway). Moving to several processes would need Redis or similar.
"""
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException


class RateLimiter:
    def __init__(self, max_calls: int, per_seconds: int, message: str):
        self.max_calls = max_calls
        self.per_seconds = per_seconds
        self.message = message
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str):
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self.per_seconds:
                hits.popleft()
            if len(hits) >= self.max_calls:
                retry_after = int(hits[0] + self.per_seconds - now) + 1
                raise HTTPException(status_code=429, detail=self.message, headers={"Retry-After": str(retry_after)})
            hits.append(now)
            # drop idle keys now and then so the dict doesn't grow forever
            if len(self._hits) > 10_000:
                for k in [k for k, v in self._hits.items() if not v or v[-1] <= now - self.per_seconds]:
                    del self._hits[k]


login_limiter = RateLimiter(10, 5 * 60, "Too many login attempts — try again in a few minutes")
execution_limiter = RateLimiter(30, 60, "Too many runs — wait a moment and try again")
# sign-ups per email, and in total (the client IP can't be trusted behind Render's proxy), so a script
# can't mass-create accounts
signup_limiter = RateLimiter(5, 60 * 60, "Too many sign-up attempts — try again later")
signup_total_limiter = RateLimiter(100, 60 * 60, "Sign-ups are busy right now — try again in a while")
