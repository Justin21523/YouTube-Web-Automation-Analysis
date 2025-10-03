# tests/unit/test_youtube_api.py
"""
Unit Tests for YouTube API Client
Tests quota tracking, rate limiting, and API interactions
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(ROOT_DIR))

from src.infrastructure.clients.youtube_api import (
    YouTubeAPIClient,
    QuotaTracker,
    VideoResponse,
    ChannelResponse,
    CommentResponse,
)
from src.infrastructure.clients.rate_limiter import (
    RateLimiter,
    TokenBucket,
    rate_limit,
    AdaptiveRateLimiter,
)


# ============================================================================
# Quota Tracker Tests
# ============================================================================


class TestQuotaTracker:
    """Test quota management functionality"""

    def test_quota_initialization(self):
        """Test quota tracker initializes correctly"""
        tracker = QuotaTracker(daily_limit=1000)

        assert tracker.daily_limit == 1000
        assert tracker.used_quota == 0
        assert tracker.reset_time > datetime.now()

    def test_quota_check(self):
        """Test quota availability checking"""
        tracker = QuotaTracker(daily_limit=1000)

        # Should have quota available
        assert tracker.check_quota("videos", count=1) is True
        assert tracker.check_quota("search", count=5) is True

        # Consume most quota
        tracker.used_quota = 950

        # Should not have enough for expensive search
        assert tracker.check_quota("search", count=1) is False

        # Should still have enough for cheap videos call
        assert tracker.check_quota("videos", count=10) is True

    def test_quota_consumption(self):
        """Test quota consumption tracking"""
        tracker = QuotaTracker(daily_limit=1000)

        # Consume videos quota (1 unit each)
        tracker.consume_quota("videos", count=5)
        assert tracker.used_quota == 5

        # Consume search quota (100 units each)
        tracker.consume_quota("search", count=2)
        assert tracker.used_quota == 205

    def test_quota_reset(self):
        """Test quota resets after 24 hours"""
        tracker = QuotaTracker(daily_limit=1000)
        tracker.used_quota = 500

        # Simulate time passing
        tracker.reset_time = datetime.now() - timedelta(hours=1)

        # Trigger reset check
        tracker._reset_if_needed()

        assert tracker.used_quota == 0
        assert tracker.reset_time > datetime.now()

    def test_quota_status(self):
        """Test quota status reporting"""
        tracker = QuotaTracker(daily_limit=1000)
        tracker.used_quota = 300

        status = tracker.get_status()

        assert status["used"] == 300
        assert status["limit"] == 1000
        assert status["remaining"] == 700
        assert status["percentage_used"] == 30.0


# ============================================================================
# Rate Limiter Tests
# ============================================================================


class TestTokenBucket:
    """Test token bucket algorithm"""

    def test_token_bucket_initialization(self):
        """Test token bucket initializes with full capacity"""
        bucket = TokenBucket(
            capacity=10.0, refill_rate=5.0, tokens=10.0, last_refill=time.time()
        )

        assert bucket.capacity == 10.0
        assert bucket.tokens == 10.0
        assert bucket.refill_rate == 5.0

    def test_token_consumption(self):
        """Test consuming tokens"""
        bucket = TokenBucket(
            capacity=10.0, refill_rate=5.0, tokens=10.0, last_refill=time.time()
        )

        # Should consume successfully
        assert bucket.consume(3.0) is True
        assert bucket.tokens == 7.0

        # Should fail when insufficient
        assert bucket.consume(8.0) is False
        assert bucket.tokens == 7.0

    def test_token_refill(self):
        """Test tokens refill over time"""
        bucket = TokenBucket(
            capacity=10.0,
            refill_rate=5.0,  # 5 tokens/second
            tokens=0.0,
            last_refill=time.time(),
        )

        # Wait for refill
        time.sleep(1.1)  # Should refill ~5.5 tokens

        bucket._refill()
        assert bucket.tokens >= 5.0
        assert bucket.tokens <= 10.0


class TestRateLimiter:
    """Test rate limiter functionality"""

    def test_rate_limiter_initialization(self):
        """Test rate limiter initializes correctly"""
        limiter = RateLimiter(calls_per_second=10)

        assert limiter.calls_per_second == 10
        assert limiter.burst_capacity == 20
        assert limiter.bucket.capacity == 20.0

    def test_acquire_permits(self):
        """Test acquiring rate limit permits"""
        limiter = RateLimiter(calls_per_second=100, burst_capacity=10)

        # Should acquire immediately
        for _ in range(10):
            assert limiter.acquire(timeout=0.1) is True

        # Should block (but we use short timeout)
        start = time.time()
        result = limiter.acquire(timeout=0.1)
        elapsed = time.time() - start

        # Either acquired after waiting or timed out
        assert elapsed >= 0.05  # Some wait occurred

    def test_rate_limit_decorator(self):
        """Test rate limit decorator"""
        call_times = []

        @rate_limit(calls_per_second=5, burst_capacity=5)
        def test_function():
            call_times.append(time.time())
            return "success"

        # Make 10 calls
        for _ in range(10):
            result = test_function()
            assert result == "success"

        # Verify rate limiting occurred
        total_time = call_times[-1] - call_times[0]
        assert total_time >= 1.0  # 10 calls at 5/sec = 2sec minimum


class TestAdaptiveRateLimiter:
    """Test adaptive rate limiting"""

    def test_adaptive_backoff_on_error(self):
        """Test rate reduces on 429 errors"""
        limiter = AdaptiveRateLimiter(
            initial_calls_per_second=10.0, min_calls_per_second=1.0, backoff_factor=0.5
        )

        initial_rate = limiter.current_rate

        # Report error
        limiter.report_error(429)

        # Rate should decrease
        assert limiter.current_rate < initial_rate
        assert limiter.current_rate >= limiter.min_rate

    def test_adaptive_recovery_on_success(self):
        """Test rate recovers after successful calls"""
        limiter = AdaptiveRateLimiter(
            initial_calls_per_second=10.0, recovery_factor=1.1
        )

        # Reduce rate first
        limiter.report_error(429)
        reduced_rate = limiter.current_rate

        # Report 10 successes to trigger recovery
        for _ in range(10):
            limiter.report_success()

        # Rate should increase
        assert limiter.current_rate > reduced_rate


# ============================================================================
# YouTube API Client Tests
# ============================================================================


class TestYouTubeAPIClient:
    """Test YouTube API client"""

    @pytest.fixture
    def mock_client(self):
        """Create mock YouTube API client"""
        with patch.dict("os.environ", {"YOUTUBE_API_KEY": "test_api_key"}):
            with patch("httpx.Client"):
                client = YouTubeAPIClient(api_key="test_api_key")
                return client

    def test_client_initialization(self, mock_client):
        """Test client initializes correctly"""
        assert mock_client.api_key == "test_api_key"
        assert mock_client.max_retries == 3
        assert mock_client.quota_tracker is not None

    @patch("httpx.Client.get")
    def test_get_video(self, mock_get, mock_client):
        """Test fetching single video"""
        # Mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {
                    "id": "test_video_id",
                    "snippet": {
                        "title": "Test Video",
                        "description": "Test Description",
                        "publishedAt": "2024-01-01T00:00:00Z",
                        "channelId": "test_channel",
                        "channelTitle": "Test Channel",
                        "thumbnails": {},
                        "categoryId": "10",
                    },
                    "statistics": {
                        "viewCount": "1000",
                        "likeCount": "100",
                        "commentCount": "10",
                    },
                    "contentDetails": {
                        "duration": "PT5M30S",
                        "definition": "hd",
                        "caption": "false",
                        "licensedContent": True,
                    },
                }
            ]
        }
        mock_get.return_value = mock_response

        # Test video fetch
        video = mock_client.get_video("test_video_id")

        assert isinstance(video, VideoResponse)
        assert video.id == "test_video_id"
        assert video.snippet.title == "Test Video"
        assert video.statistics.view_count == 1000

    @patch("httpx.Client.get")
    def test_search_videos(self, mock_get, mock_client):
        """Test video search"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {"id": {"videoId": "video1"}},
                {"id": {"videoId": "video2"}},
                {"id": {"videoId": "video3"}},
            ]
        }
        mock_get.return_value = mock_response

        video_ids = mock_client.search_videos("test query", max_results=3)

        assert len(video_ids) == 3
        assert video_ids[0] == "video1"

    @patch("httpx.Client.get")
    def test_quota_exceeded_error(self, mock_get, mock_client):
        """Test handling quota exceeded error"""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.text = "Quota exceeded"
        mock_response.raise_for_status.side_effect = Exception("403 error")
        mock_get.return_value = mock_response

        # Should raise quota error
        with pytest.raises(ValueError, match="quota"):
            mock_client.get_video("test_id")

    def test_context_manager(self):
        """Test client can be used as context manager"""
        with patch.dict("os.environ", {"YOUTUBE_API_KEY": "test_key"}):
            with patch("httpx.Client"):
                with YouTubeAPIClient(api_key="test_key") as client:
                    assert client is not None


# ============================================================================
# Integration Test Markers
# ============================================================================


@pytest.mark.integration
class TestYouTubeAPIIntegration:
    """Integration tests (require real API key)"""

    @pytest.fixture
    def real_client(self):
        """Create real client (skips if no API key)"""
        import os

        api_key = os.getenv("YOUTUBE_API_KEY")
        if not api_key:
            pytest.skip("YOUTUBE_API_KEY not set")
        return YouTubeAPIClient(api_key=api_key)

    def test_real_video_fetch(self, real_client):
        """Test fetching real video"""
        # Rick Astley - Never Gonna Give You Up
        video = real_client.get_video("dQw4w9WgXcQ")

        assert video.id == "dQw4w9WgXcQ"
        assert "Never Gonna Give You Up" in video.snippet.title
        assert video.statistics.view_count > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
