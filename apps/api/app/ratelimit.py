"""Small in-process sliding-window rate limiter (swap for Redis when running several replicas)."""
import time
from collections import defaultdict, deque

from fastapi import Request

from app.errors import ApiError


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_s: float = 60.0):
        self.limit, self.window = limit, window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        q = self._hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            retry = int(self.window - (now - q[0])) + 1
            raise ApiError(429, "rate_limited", f"Too many attempts. Try again in {retry} s.", {"retry_after": retry})
        q.append(now)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def auth_rate_limit(request: Request) -> None:
    request.app.state.auth_limiter.check(client_ip(request))


def public_rate_limit(request: Request) -> None:
    request.app.state.public_limiter.check(client_ip(request))
