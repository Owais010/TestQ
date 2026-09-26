"""Cooperative cancellation/deadlines. Supported deployment: one API worker."""
import asyncio
import threading
import time


class RunCancelled(Exception):
    pass


class RunDeadlineExceeded(TimeoutError):
    pass


class RunControl:
    def __init__(self, timeout: float):
        self.cancel_event = threading.Event()
        self.deadline = time.monotonic() + timeout
        self.done = asyncio.Event()

    def cancel(self):
        self.cancel_event.set()

    def check(self):
        if self.cancel_event.is_set():
            raise RunCancelled("Cancellation requested")
        if time.monotonic() >= self.deadline:
            raise RunDeadlineExceeded("Whole-run deadline exceeded")

    @property
    def remaining(self):
        self.check()
        return max(0.01, self.deadline - time.monotonic())


controls: dict[str, RunControl] = {}
