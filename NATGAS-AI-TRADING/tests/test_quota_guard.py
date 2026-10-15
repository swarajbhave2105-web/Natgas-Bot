"""Unit tests for AI Quota Guard, sliding-window rate limiting, and cache deduplication."""

import time
from backend.ai.llm_research import LLMResearchResult
from backend.ai.quota_guard import AIQuotaGuard


def test_quota_guard_cache_deduplication():
    guard = AIQuotaGuard(cache_ttl_seconds=10.0)
    key = guard.compute_cache_key("bull", "auto", "test prompt", "sources_digest")

    # Initial cache miss
    assert guard.get_cached(key) is None

    result = LLMResearchResult(side="bull", model="auto", text="Analysis", source_count=2)
    guard.set_cached(key, result)

    # Cache hit
    cached = guard.get_cached(key)
    assert cached is not None
    assert cached.text == "Analysis"


def test_quota_guard_ttl_expiration():
    guard = AIQuotaGuard(cache_ttl_seconds=0.05)
    key = guard.compute_cache_key("bear", "auto", "test prompt", "")

    result = LLMResearchResult(side="bear", model="auto", text="Bearish", source_count=1)
    guard.set_cached(key, result)
    assert guard.get_cached(key) is not None

    time.sleep(0.06)
    assert guard.get_cached(key) is None


def test_quota_guard_rate_limit_sliding_window():
    # Allow max 2 calls per minute
    guard = AIQuotaGuard(max_calls_per_minute=2, max_calls_per_hour=10)

    # First call allowed
    allowed, reason = guard.check_quota_available()
    assert allowed is True
    guard.record_call()

    # Second call allowed
    allowed, reason = guard.check_quota_available()
    assert allowed is True
    guard.record_call()

    # Third call blocked by rate limit
    allowed, reason = guard.check_quota_available()
    assert allowed is False
    assert "RATE_LIMIT" in reason


def test_quota_guard_circuit_breaker_trip_and_recovery():
    guard = AIQuotaGuard(circuit_cooldown_seconds=0.08)
    assert guard.is_circuit_open() is False

    # Trip breaker
    guard.trip_circuit_breaker()
    assert guard.is_circuit_open() is True

    allowed, reason = guard.check_quota_available()
    assert allowed is False
    assert "CIRCUIT_BREAKER_OPEN" in reason

    # Wait for cooldown
    time.sleep(0.09)
    assert guard.is_circuit_open() is False
    allowed, _ = guard.check_quota_available()
    assert allowed is True


def test_quota_guard_telemetry_reporting():
    guard = AIQuotaGuard(max_calls_per_minute=15, max_calls_per_hour=100)
    guard.metrics.total_requests = 10
    guard.metrics.cache_hits = 6
    guard.metrics.cache_misses = 4
    guard.record_call()

    status = guard.get_status()
    assert status["max_calls_per_minute"] == 15
    assert status["max_calls_per_hour"] == 100
    assert status["calls_last_minute"] == 1
    assert status["metrics"]["cache_hits"] == 6
    assert status["metrics"]["cache_misses"] == 4
    assert status["circuit_breaker_open"] is False


def test_cache_hit_does_not_consume_quota_or_rate_limit():
    guard = AIQuotaGuard(max_calls_per_minute=2, max_calls_per_hour=10, cache_ttl_seconds=60.0)
    key = guard.compute_cache_key("bull", "auto", "same prompt", "")

    # Set up cached item
    result = LLMResearchResult(side="bull", model="auto", text="Cached response", source_count=1)
    guard.set_cached(key, result)

    initial_calls = guard.metrics.network_calls
    assert len(guard._call_history) == 0

    # 10 duplicate queries should hit cache and NOT consume any network call or rate-limit slot
    for _ in range(10):
        cached = guard.get_cached(key)
        assert cached is not None
        assert cached.text == "Cached response"

    assert guard.metrics.network_calls == initial_calls
    assert len(guard._call_history) == 0

    # Because cache hits consumed 0 slots, quota is still completely free
    allowed, _ = guard.check_quota_available()
    assert allowed is True


def test_quota_guard_concurrency_thread_safety():
    import threading
    guard = AIQuotaGuard(max_calls_per_minute=500, max_calls_per_hour=1000)

    def worker(worker_id):
        for i in range(25):
            k = guard.compute_cache_key("bull", "auto", f"prompt_{worker_id}_{i}", "")
            guard.set_cached(k, LLMResearchResult("bull", "auto", "ok", 1))
            guard.get_cached(k)
            allowed, _ = guard.check_quota_available()
            if allowed:
                guard.record_call()

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 4 threads * 25 calls = 100 calls recorded safely
    assert guard.metrics.network_calls == 100
    assert len(guard._call_history) == 100


def test_dashboard_ai_status_polling_does_not_consume_quota():
    from backend.ai.quota_guard import global_quota_guard
    from backend.ai.model_router import get_active_route_name, get_routes

    global_quota_guard.clear()
    initial_network_calls = global_quota_guard.metrics.network_calls
    initial_total_reqs = global_quota_guard.metrics.total_requests

    # Simulate 50 dashboard poll requests to /api/v1/ai/status
    for _ in range(50):
        active = get_active_route_name()
        routes = {name: r.model for name, r in get_routes().items()}
        quota_state = global_quota_guard.get_status()
        assert quota_state["circuit_breaker_open"] is False

    # Confirm 0 quota consumed
    assert global_quota_guard.metrics.network_calls == initial_network_calls
    assert global_quota_guard.metrics.total_requests == initial_total_reqs
    assert len(global_quota_guard._call_history) == 0

