"""AI Quota and Duplicate-Call Protection Guard.

Prevents duplicate and runaway LLM API requests:
- Idempotency / deterministic context hashing (fingerprint caching with configurable TTL).
- Rate-limiting guardrail (sliding-window rate limiter per minute and per hour).
- Request coalescing (single-flight in-flight deduplication).
- Circuit breaker for rate limits (HTTP 429), quota errors, or repeated network failures.
- Non-blocking fail-closed fallback to prevent crashing the deterministic trading engine.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import os
import threading
import time
from typing import Any, Callable, Coroutine



@dataclass
class QuotaMetrics:
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    network_calls: int = 0
    rate_limits_encountered: int = 0
    quota_exceeded_count: int = 0
    circuit_breaker_trips: int = 0
    last_call_at: str | None = None


class AIQuotaGuard:
    """Manages AI request deduplication, rate limits, and circuit breaking."""

    def __init__(
        self,
        max_calls_per_minute: int | None = None,
        max_calls_per_hour: int | None = None,
        cache_ttl_seconds: float | None = None,
        circuit_cooldown_seconds: float | None = None,
    ) -> None:
        self.max_calls_per_minute = max_calls_per_minute or int(
            os.getenv("NATGAS_AI_MAX_CALLS_PER_MINUTE", "10")
        )
        self.max_calls_per_hour = max_calls_per_hour or int(
            os.getenv("NATGAS_AI_MAX_CALLS_PER_HOUR", "60")
        )
        self.cache_ttl_seconds = (
            cache_ttl_seconds
            if cache_ttl_seconds is not None
            else float(os.getenv("NATGAS_AI_CACHE_TTL_SECONDS", "300"))
        )
        self.circuit_cooldown_seconds = (
            circuit_cooldown_seconds
            if circuit_cooldown_seconds is not None
            else float(os.getenv("NATGAS_AI_CIRCUIT_COOLDOWN_SECONDS", "60"))
        )

        self._cache: dict[str, tuple[float, Any]] = {}  # key -> (timestamp, result)
        self._call_history: list[float] = []
        self._circuit_open_until: float = 0.0
        self._in_flight: dict[str, asyncio.Future] = {}
        self._sync_lock = threading.Lock()
        self.metrics = QuotaMetrics()

    def compute_cache_key(
        self,
        side: str,
        model: str,
        prompt: str,
        sources_digest: str = "",
    ) -> str:
        """Create a deterministic SHA-256 fingerprint for a research request."""
        hasher = hashlib.sha256()
        hasher.update(side.strip().lower().encode("utf-8"))
        hasher.update(b"|")
        hasher.update(model.strip().encode("utf-8"))
        hasher.update(b"|")
        hasher.update(prompt.strip().encode("utf-8"))
        hasher.update(b"|")
        hasher.update(sources_digest.strip().encode("utf-8"))
        return hasher.hexdigest()

    def is_circuit_open(self) -> bool:
        """Check if the circuit breaker is currently open."""
        with self._sync_lock:
            return time.monotonic() < self._circuit_open_until

    def trip_circuit_breaker(self, cooldown: float | None = None) -> None:
        """Trip circuit breaker to halt outgoing calls during rate limit or outage."""
        cd = cooldown if cooldown is not None else self.circuit_cooldown_seconds
        with self._sync_lock:
            self._circuit_open_until = time.monotonic() + cd
            self.metrics.circuit_breaker_trips += 1

    def reset_circuit_breaker(self) -> None:
        """Reset the circuit breaker."""
        with self._sync_lock:
            self._circuit_open_until = 0.0

    def get_cached(self, key: str) -> Any | None:
        """Retrieve unexpired cached result, or None if expired/absent."""
        with self._sync_lock:
            if key not in self._cache:
                return None
            ts, result = self._cache[key]
            if (time.monotonic() - ts) > self.cache_ttl_seconds:
                del self._cache[key]
                return None
            return result

    def set_cached(self, key: str, result: Any) -> None:
        """Store a research result in cache."""
        with self._sync_lock:
            self._cache[key] = (time.monotonic(), result)

    def _prune_history(self, now: float) -> None:
        """Prune timestamps older than 1 hour (must be called inside lock)."""
        cutoff = now - 3600.0
        self._call_history = [t for t in self._call_history if t > cutoff]

    def check_quota_available(self) -> tuple[bool, str | None]:
        """Verify whether an outgoing call complies with sliding-window quota."""
        with self._sync_lock:
            now = time.monotonic()
            if now < self._circuit_open_until:
                remaining = round(self._circuit_open_until - now, 1)
                return False, f"CIRCUIT_BREAKER_OPEN: active for {remaining}s"

            self._prune_history(now)

            # Check 1-minute window
            minute_cutoff = now - 60.0
            calls_last_minute = sum(1 for t in self._call_history if t > minute_cutoff)
            if calls_last_minute >= self.max_calls_per_minute:
                self.metrics.quota_exceeded_count += 1
                return False, f"RATE_LIMIT: exceeded {self.max_calls_per_minute} calls/min"

            # Check 1-hour window
            if len(self._call_history) >= self.max_calls_per_hour:
                self.metrics.quota_exceeded_count += 1
                return False, f"RATE_LIMIT: exceeded {self.max_calls_per_hour} calls/hour"

            return True, None

    def record_call(self) -> None:
        """Record an outgoing network call."""
        with self._sync_lock:
            now = time.monotonic()
            self._call_history.append(now)
            self.metrics.network_calls += 1
            self.metrics.last_call_at = datetime.now(timezone.utc).isoformat()

    def get_status(self) -> dict[str, Any]:
        """Export current quota guard health and telemetry."""
        with self._sync_lock:
            now = time.monotonic()
            self._prune_history(now)
            minute_cutoff = now - 60.0
            calls_last_minute = sum(1 for t in self._call_history if t > minute_cutoff)
            circuit_open = now < self._circuit_open_until
            remaining_cooldown = max(0.0, round(self._circuit_open_until - now, 1)) if circuit_open else 0.0
            return {
                "circuit_breaker_open": circuit_open,
                "circuit_cooldown_remaining_seconds": remaining_cooldown,
                "calls_last_minute": calls_last_minute,
                "max_calls_per_minute": self.max_calls_per_minute,
                "calls_last_hour": len(self._call_history),
                "max_calls_per_hour": self.max_calls_per_hour,
                "cache_entries": len(self._cache),
                "cache_ttl_seconds": self.cache_ttl_seconds,
                "metrics": {
                    "total_requests": self.metrics.total_requests,
                    "cache_hits": self.metrics.cache_hits,
                    "cache_misses": self.metrics.cache_misses,
                    "network_calls": self.metrics.network_calls,
                    "rate_limits_encountered": self.metrics.rate_limits_encountered,
                    "quota_exceeded_count": self.metrics.quota_exceeded_count,
                    "circuit_breaker_trips": self.metrics.circuit_breaker_trips,
                    "last_call_at": self.metrics.last_call_at,
                },
            }

    def clear(self) -> None:
        """Clear cache, history and circuit breaker for clean state."""
        with self._sync_lock:
            self._cache.clear()
            self._call_history.clear()
            self._circuit_open_until = 0.0
            self._in_flight.clear()
            self.metrics = QuotaMetrics()



# Global singleton instance for the NATGAS AI process
global_quota_guard = AIQuotaGuard()
