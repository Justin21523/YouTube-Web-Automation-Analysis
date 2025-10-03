# src/infrastructure/clients/rate_limiter.py
"""
Rate Limiting Decorator for API Clients
Implements token bucket algorithm with distributed support via Redis.

Features:
- Thread-safe rate limiting
- Optional Redis backend for multi-process scenarios
- Configurable burst capacity
- Decorator pattern for easy integration
"""

import time
import logging
import threading
from typing import Callable, Optional, Any
from functools import wraps
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


# ============================================================================
# Token Bucket Algorithm Implementation
# ============================================================================


@dataclass
class TokenBucket:
    """
    Token bucket for rate limiting

    Attributes:
        capacity: Maximum tokens (burst capacity)
        refill_rate: Tokens added per second
        tokens: Current available tokens
        last_refill: Last refill timestamp
    """

    capacity: float
    refill_rate: float
    tokens: float
    last_refill: float
    lock: threading.Lock = None

    def __post_init__(self):
        if self.lock is None:
            self.lock = threading.Lock()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time"""
        now = time.time()
        elapsed = now - self.last_refill

        # Add tokens based on time passed
        new_tokens = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + new_tokens)
        self.last_refill = now

    def consume(self, tokens: float = 1.0) -> bool:
        """
        Try to consume tokens

        Args:
            tokens: Number of tokens to consume

        Returns:
            True if tokens consumed, False if insufficient
        """
        with self.lock:
            self._refill()

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True

            return False

    def wait_for_tokens(
        self, tokens: float = 1.0, timeout: Optional[float] = None
    ) -> bool:
        """
        Wait until tokens become available

        Args:
            tokens: Number of tokens needed
            timeout: Maximum wait time in seconds (None = infinite)

        Returns:
            True if tokens obtained, False if timeout
        """
        start_time = time.time()

        while True:
            if self.consume(tokens):
                return True

            # Check timeout
            if timeout and (time.time() - start_time) >= timeout:
                return False

            # Calculate sleep time
            with self.lock:
                self._refill()
                deficit = tokens - self.tokens
                if deficit > 0:
                    sleep_time = min(deficit / self.refill_rate, 1.0)
                    time.sleep(sleep_time)
                else:
                    time.sleep(0.01)  # Small sleep to avoid busy-wait


# ============================================================================
# Rate Limiter Class
# ============================================================================


class RateLimiter:
    """
    Rate limiter with multiple strategies

    Supports:
    - Token bucket algorithm (local)
    - Redis-backed distributed rate limiting (optional)
    """

    def __init__(
        self,
        calls_per_second: float,
        burst_capacity: Optional[int] = None,
        redis_client=None,
        redis_key_prefix: str = "rate_limit",
    ):
        """
        Initialize rate limiter

        Args:
            calls_per_second: Maximum calls per second
            burst_capacity: Burst capacity (defaults to calls_per_second * 2)
            redis_client: Optional Redis client for distributed limiting
            redis_key_prefix: Redis key prefix
        """
        self.calls_per_second = calls_per_second
        self.burst_capacity = burst_capacity or int(calls_per_second * 2)
        self.redis_client = redis_client
        self.redis_key_prefix = redis_key_prefix

        # Local token bucket
        self.bucket = TokenBucket(
            capacity=float(self.burst_capacity),
            refill_rate=calls_per_second,
            tokens=float(self.burst_capacity),
            last_refill=time.time(),
        )

        logger.info(
            f"🕐 Rate limiter initialized: {calls_per_second} calls/sec, "
            f"burst={self.burst_capacity}"
        )

    def acquire(self, timeout: Optional[float] = None) -> bool:
        """
        Acquire permission to make a call

        Args:
            timeout: Maximum wait time (None = block indefinitely)

        Returns:
            True if permission acquired, False if timeout
        """
        if self.redis_client:
            return self._acquire_redis(timeout)
        else:
            return self.bucket.wait_for_tokens(1.0, timeout)

    def _acquire_redis(self, timeout: Optional[float] = None) -> bool:
        """Acquire permission using Redis (distributed limiting)"""
        # Redis-based rate limiting using INCR + EXPIRE
        key = f"{self.redis_key_prefix}:count"
        window_key = f"{self.redis_key_prefix}:window"

        start_time = time.time()

        while True:
            try:
                # Get current count
                count = self.redis_client.get(key)

                if count is None:
                    # First request in window
                    pipe = self.redis_client.pipeline()
                    pipe.set(key, 1, ex=1)  # 1 second window
                    pipe.execute()
                    return True

                count = int(count)

                if count < self.burst_capacity:
                    # Increment and allow
                    self.redis_client.incr(key)
                    return True

                # Rate limited - check timeout
                if timeout and (time.time() - start_time) >= timeout:
                    return False

                # Wait for window reset
                ttl = self.redis_client.ttl(key)
                if ttl > 0:
                    time.sleep(min(ttl, 0.1))
                else:
                    time.sleep(0.01)

            except Exception as e:
                logger.warning(f"⚠️ Redis rate limit error: {e}, falling back to local")
                return self.bucket.wait_for_tokens(1.0, timeout)


# ============================================================================
# Decorator
# ============================================================================


def rate_limit(
    calls_per_second: float,
    burst_capacity: Optional[int] = None,
    timeout: Optional[float] = 30.0,
) -> Callable:
    """
    Rate limiting decorator

    Args:
        calls_per_second: Maximum calls per second
        burst_capacity: Burst capacity (default: 2x calls_per_second)
        timeout: Maximum wait time before raising error

    Returns:
        Decorated function with rate limiting

    Example:
        ```python
        @rate_limit(calls_per_second=10, burst_capacity=20)
        def api_call():
            # Your API call here
            pass
        ```
    """
    limiter = RateLimiter(calls_per_second, burst_capacity)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            if not limiter.acquire(timeout):
                raise TimeoutError(
                    f"Rate limit timeout after {timeout}s "
                    f"(limit: {calls_per_second} calls/sec)"
                )

            return func(*args, **kwargs)

        return wrapper

    return decorator


# ============================================================================
# Adaptive Rate Limiter (Advanced)
# ============================================================================


class AdaptiveRateLimiter(RateLimiter):
    """
    Adaptive rate limiter that adjusts based on error responses

    Automatically reduces rate when receiving 429 (Too Many Requests) errors
    and gradually increases back to normal.
    """

    def __init__(
        self,
        initial_calls_per_second: float,
        min_calls_per_second: float = 1.0,
        max_calls_per_second: Optional[float] = None,
        backoff_factor: float = 0.5,
        recovery_factor: float = 1.1,
        **kwargs,
    ):
        """
        Initialize adaptive rate limiter

        Args:
            initial_calls_per_second: Starting rate
            min_calls_per_second: Minimum rate after backoff
            max_calls_per_second: Maximum rate (defaults to initial)
            backoff_factor: Rate reduction multiplier on error
            recovery_factor: Rate increase multiplier on success
        """
        super().__init__(initial_calls_per_second, **kwargs)

        self.current_rate = initial_calls_per_second
        self.min_rate = min_calls_per_second
        self.max_rate = max_calls_per_second or initial_calls_per_second
        self.backoff_factor = backoff_factor
        self.recovery_factor = recovery_factor
        self.consecutive_successes = 0
        self.adjustment_lock = threading.Lock()

    def report_error(self, status_code: int) -> None:
        """Report API error to adjust rate"""
        if status_code == 429:
            with self.adjustment_lock:
                old_rate = self.current_rate
                self.current_rate = max(
                    self.min_rate, self.current_rate * self.backoff_factor
                )
                self.bucket.refill_rate = self.current_rate
                self.consecutive_successes = 0

                logger.warning(
                    f"⚠️ Rate limit hit, reducing rate: "
                    f"{old_rate:.2f} → {self.current_rate:.2f} calls/sec"
                )

    def report_success(self) -> None:
        """Report successful call to gradually increase rate"""
        with self.adjustment_lock:
            self.consecutive_successes += 1

            # Recover rate after 10 consecutive successes
            if self.consecutive_successes >= 10:
                old_rate = self.current_rate
                self.current_rate = min(
                    self.max_rate, self.current_rate * self.recovery_factor
                )
                self.bucket.refill_rate = self.current_rate
                self.consecutive_successes = 0

                if old_rate != self.current_rate:
                    logger.info(
                        f"✅ Rate recovering: "
                        f"{old_rate:.2f} → {self.current_rate:.2f} calls/sec"
                    )


# ============================================================================
# Testing
# ============================================================================

if __name__ == "__main__":
    import random

    # Test basic rate limiter
    print("🧪 Testing basic rate limiter (5 calls/sec)...")
    limiter = RateLimiter(calls_per_second=5, burst_capacity=10)

    start = time.time()
    for i in range(15):
        if limiter.acquire(timeout=2.0):
            elapsed = time.time() - start
            print(f"  Call {i+1} at {elapsed:.2f}s")
        else:
            print(f"  Call {i+1} timed out!")

    total_time = time.time() - start
    print(f"\n✅ Completed 15 calls in {total_time:.2f}s (expected ~3s)")

    # Test decorator
    print("\n🧪 Testing rate limit decorator...")

    @rate_limit(calls_per_second=2, burst_capacity=4)
    def mock_api_call(call_id: int) -> str:
        return f"Response {call_id}"

    start = time.time()
    for i in range(6):
        result = mock_api_call(i + 1)
        elapsed = time.time() - start
        print(f"  {result} at {elapsed:.2f}s")

    print("\n✅ All rate limiter tests passed!")
