from __future__ import annotations

import threading
import time
from datetime import datetime, timezone


class ResponseTimer:
    """Thread-safe timer for measuring reminder acknowledgement latency."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started_monotonic: float | None = None
        self._started_at: str | None = None

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    def start(self) -> str:
        with self._lock:
            if self._started_monotonic is not None:
                raise RuntimeError("Response timer is already running.")
            self._started_monotonic = time.monotonic()
            self._started_at = self._utc_now_iso()
            return self._started_at

    def stop(self) -> dict:
        with self._lock:
            if self._started_monotonic is None or self._started_at is None:
                raise RuntimeError("Response timer is not running.")

            elapsed_seconds = time.monotonic() - self._started_monotonic
            acknowledged_at = self._utc_now_iso()
            result = {
                "started_at": self._started_at,
                "acknowledged_at": acknowledged_at,
                "response_time_ms": round(elapsed_seconds * 1000),
            }
            self._started_monotonic = None
            self._started_at = None
            return result

    def reset(self) -> None:
        with self._lock:
            self._started_monotonic = None
            self._started_at = None

    @property
    def running(self) -> bool:
        with self._lock:
            return self._started_monotonic is not None
