"""
Simple timing utilities for pipeline profiling.
Usage:
    timer = Timer()
    timer.start("section_name")
    ... code ...
    timer.stop("section_name")
    timer.report()  # print all timings

Or as context manager:
    with timer("section_name"):
        ... code ...
"""

import time
from contextlib import contextmanager


class Timer:
    """Multi-section timer for pipeline profiling."""

    def __init__(self, enabled=True):
        self._enabled = enabled
        self._times = {}

    def start(self, name):
        if self._enabled:
            self._times[name] = time.time()

    def stop(self, name):
        if self._enabled and name in self._times:
            elapsed = time.time() - self._times.pop(name)
            print(f"  [Profile] {name}: {elapsed:.1f}s")
            return elapsed

    def elapsed(self, name):
        """Get elapsed without printing (for total accumulation)."""
        if self._enabled and name in self._times:
            return time.time() - self._times[name]
        return 0

    def report(self):
        if self._times:
            print(f"  [Profile] Remaining unfinished: {list(self._times.keys())}")

    @contextmanager
    def __call__(self, name):
        if not self._enabled:
            yield
            return
        self.start(name)
        try:
            yield
        finally:
            self.stop(name)


# Global singleton for easy import
_timer = Timer(enabled=True)  # 默认启用计时，可通过 disable_timing() 关闭


def enable_timing():
    _timer._enabled = True


def disable_timing():
    _timer._enabled = False


def start(name):
    _timer.start(name)


def stop(name):
    return _timer.stop(name)


def profile(name):
    return _timer(name)
