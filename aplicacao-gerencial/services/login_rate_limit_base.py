from __future__ import annotations

import threading
import time


class LoginRateLimiter:
    def __init__(self, max_attempts: int = 5, window_seconds: int = 300, block_seconds: int = 300) -> None:
        self.max_attempts = max(1, max_attempts)
        self.window_seconds = max(1, window_seconds)
        self.block_seconds = max(1, block_seconds)
        self._lock = threading.Lock()
        self._failures: dict[str, list[float]] = {}
        self._blocked_until: dict[str, float] = {}

    def retry_after(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            blocked_until = self._blocked_until.get(key, 0)
            if blocked_until <= now:
                self._blocked_until.pop(key, None)
                return 0
            return max(1, int(blocked_until - now))

    def failure(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            recent = [stamp for stamp in self._failures.get(key, []) if now - stamp <= self.window_seconds]
            recent.append(now)
            self._failures[key] = recent
            if len(recent) >= self.max_attempts:
                self._blocked_until[key] = now + self.block_seconds
                self._failures.pop(key, None)
                return self.block_seconds
            return 0

    def success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._blocked_until.pop(key, None)
