"""Bound work per process; the deployment defaults to one process and replica."""

from threading import BoundedSemaphore, Lock
from time import monotonic
from fastapi import HTTPException


class RequestLimits:
    def __init__(self, per_minute: int, concurrent: int, total_per_minute: int = 60):
        self.per_minute = per_minute
        self.total_per_minute = total_per_minute
        self.total_window = (0.0, 0)
        self.slots = BoundedSemaphore(concurrent)
        self.lock = Lock()
        self.windows = {}
        self.last_cleanup = 0.0

    def check_user(self, subject: str):
        now = monotonic()
        with self.lock:
            total_expires, total_count = self.total_window
            if total_expires <= now:
                total_expires, total_count = now + 60, 0
            if total_count >= self.total_per_minute:
                raise HTTPException(
                    429,
                    "The service request limit has been reached.",
                    headers={"Retry-After": str(max(1, int(total_expires - now)))},
                )
            if now - self.last_cleanup >= 60:
                self.windows = {
                    key: row for key, row in self.windows.items() if row[0] > now
                }
                self.last_cleanup = now
            expires, count = self.windows.get(subject, (now + 60, 0))
            if expires <= now:
                expires, count = now + 60, 0
            if count >= self.per_minute or (
                subject not in self.windows and len(self.windows) >= 10000
            ):
                raise HTTPException(
                    429,
                    "Request limit reached. Please try again later.",
                    headers={"Retry-After": str(max(1, int(expires - now)))},
                )
            self.windows[subject] = (expires, count + 1)
            self.total_window = (total_expires, total_count + 1)
