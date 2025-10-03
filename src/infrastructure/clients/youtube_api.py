# src/infrastructure/clients/youtube_api.py
"""
YouTube Data API v3 Client
Handles authentication, quota management, retry logic, and structured data fetching.

Features:
- Automatic quota tracking and warnings
- Exponential backoff retry mechanism
- Batch request optimization
- Type-safe response parsing with Pydantic
- Graceful error handling with detailed logging
"""

import logging
import time
from typing import List, Dict, Any, Optional, Literal
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

import httpx
from pydantic import BaseModel, Field, field_validator

# Reuse existing config infrastructure
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(ROOT_DIR))

from src.app.config import get_config
from src.app.shared_cache import get_shared_cache

logger = logging.getLogger(__name__)


# ============================================================================
# Response Models (Type-Safe Data Containers)
# ============================================================================


class VideoSnippet(BaseModel):
    """Video metadata snippet"""

    title: str
    description: str
    published_at: datetime = Field(alias="publishedAt")
    channel_id: str = Field(alias="channelId")
    channel_title: str = Field(alias="channelTitle")
    thumbnails: Dict[str, Dict[str, Any]]
    tags: List[str] = Field(default_factory=list)
    category_id: str = Field(alias="categoryId")

    class Config:
        populate_by_name = True


class VideoStatistics(BaseModel):
    """Video engagement statistics"""

    view_count: int = Field(alias="viewCount", default=0)
    like_count: int = Field(alias="likeCount", default=0)
    comment_count: int = Field(alias="commentCount", default=0)

    class Config:
        populate_by_name = True


class VideoContentDetails(BaseModel):
    """Video content metadata"""

    duration: str
    definition: str
    caption: str
    licensed_content: bool = Field(alias="licensedContent")

    class Config:
        populate_by_name = True


class VideoResponse(BaseModel):
    """Complete video data response"""

    id: str
    snippet: VideoSnippet
    statistics: VideoStatistics
    content_details: VideoContentDetails = Field(alias="contentDetails")

    class Config:
        populate_by_name = True


class ChannelSnippet(BaseModel):
    """Channel metadata snippet"""

    title: str
    description: str
    custom_url: Optional[str] = Field(alias="customUrl", default=None)
    published_at: datetime = Field(alias="publishedAt")
    thumbnails: Dict[str, Dict[str, Any]]
    country: Optional[str] = None

    class Config:
        populate_by_name = True


class ChannelStatistics(BaseModel):
    """Channel statistics"""

    view_count: int = Field(alias="viewCount", default=0)
    subscriber_count: int = Field(alias="subscriberCount", default=0)
    video_count: int = Field(alias="videoCount", default=0)

    class Config:
        populate_by_name = True


class ChannelResponse(BaseModel):
    """Complete channel data response"""

    id: str
    snippet: ChannelSnippet
    statistics: ChannelStatistics

    class Config:
        populate_by_name = True


class CommentSnippet(BaseModel):
    """Comment metadata"""

    text_display: str = Field(alias="textDisplay")
    author_display_name: str = Field(alias="authorDisplayName")
    author_channel_id: Dict[str, str] = Field(alias="authorChannelId")
    like_count: int = Field(alias="likeCount", default=0)
    published_at: datetime = Field(alias="publishedAt")
    updated_at: datetime = Field(alias="updatedAt")

    class Config:
        populate_by_name = True


class CommentResponse(BaseModel):
    """Complete comment data response"""

    id: str
    snippet: CommentSnippet

    class Config:
        populate_by_name = True


# ============================================================================
# Quota Management
# ============================================================================


@dataclass
class QuotaTracker:
    """Tracks API quota usage with daily reset"""

    daily_limit: int = 10000  # YouTube API default quota
    used_quota: int = 0
    reset_time: datetime = field(
        default_factory=lambda: datetime.now() + timedelta(days=1)
    )

    # Quota costs per operation (YouTube API v3 costs)
    COSTS = {
        "search": 100,
        "videos": 1,
        "channels": 1,
        "comments": 1,
        "comment_threads": 1,
        "playlists": 1,
    }

    def check_quota(self, operation: str, count: int = 1) -> bool:
        """Check if sufficient quota available"""
        self._reset_if_needed()
        cost = self.COSTS.get(operation, 1) * count
        return (self.used_quota + cost) <= self.daily_limit

    def consume_quota(self, operation: str, count: int = 1) -> None:
        """Consume quota for an operation"""
        self._reset_if_needed()
        cost = self.COSTS.get(operation, 1) * count
        self.used_quota += cost

        remaining = self.daily_limit - self.used_quota
        if remaining < 1000:
            logger.warning(f"⚠️ Low quota remaining: {remaining} units")

    def _reset_if_needed(self) -> None:
        """Reset quota counter if daily limit expired"""
        if datetime.now() >= self.reset_time:
            logger.info("🔄 Daily quota reset")
            self.used_quota = 0
            self.reset_time = datetime.now() + timedelta(days=1)

    def get_status(self) -> Dict[str, Any]:
        """Get current quota status"""
        self._reset_if_needed()
        return {
            "used": self.used_quota,
            "limit": self.daily_limit,
            "remaining": self.daily_limit - self.used_quota,
            "reset_at": self.reset_time.isoformat(),
            "percentage_used": round((self.used_quota / self.daily_limit) * 100, 2),
        }


# ============================================================================
# Main API Client
# ============================================================================


class YouTubeAPIClient:
    """
    YouTube Data API v3 Client

    Handles:
    - Video metadata retrieval
    - Channel information
    - Comment fetching with pagination
    - Search queries
    - Playlist enumeration

    Integrates with existing config and cache infrastructure.
    """

    BASE_URL = "https://www.googleapis.com/youtube/v3"

    def __init__(
        self, api_key: Optional[str] = None, max_retries: int = 3, timeout: int = 30
    ):
        """
        Initialize YouTube API client

        Args:
            api_key: YouTube Data API key (reads from env if not provided)
            max_retries: Maximum retry attempts for failed requests
            timeout: Request timeout in seconds
        """
        self.config = get_config()
        self.cache = get_shared_cache()

        # API Key from parameter or environment
        self.api_key = api_key or self._get_api_key()
        if not self.api_key:
            raise ValueError(
                "YouTube API key not found. Set YOUTUBE_API_KEY in .env or pass to constructor"
            )

        self.max_retries = max_retries
        self.timeout = timeout

        # HTTP client with connection pooling
        self.client = httpx.Client(
            timeout=timeout, limits=httpx.Limits(max_keepalive_connections=5)
        )

        # Quota tracking
        self.quota_tracker = QuotaTracker()

        logger.info("✅ YouTube API client initialized")

    def _get_api_key(self) -> Optional[str]:
        """Load API key from environment or config"""
        import os

        return os.getenv("YOUTUBE_API_KEY") or self.config.get("youtube.api_key")

    def _request(
        self, endpoint: str, params: Dict[str, Any], operation: str = "videos"
    ) -> Dict[str, Any]:
        """
        Make API request with retry logic and quota management

        Args:
            endpoint: API endpoint path (e.g., 'videos', 'search')
            params: Query parameters
            operation: Operation type for quota tracking

        Returns:
            Parsed JSON response

        Raises:
            httpx.HTTPStatusError: For unrecoverable HTTP errors
            ValueError: When quota exceeded
        """
        # Check quota before request
        if not self.quota_tracker.check_quota(operation):
            raise ValueError(
                f"Quota exceeded. Status: {self.quota_tracker.get_status()}"
            )

        url = f"{self.BASE_URL}/{endpoint}"
        params["key"] = self.api_key

        # Exponential backoff retry
        for attempt in range(self.max_retries):
            try:
                response = self.client.get(url, params=params)
                response.raise_for_status()

                # Consume quota on success
                self.quota_tracker.consume_quota(operation)

                return response.json()

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 403:
                    # Quota exceeded or API key invalid
                    logger.error(f"❌ API error 403: {e.response.text}")
                    raise ValueError("API quota exceeded or invalid API key")

                if e.response.status_code >= 500:
                    # Server error - retry with backoff
                    wait_time = 2**attempt
                    logger.warning(
                        f"⚠️ Server error {e.response.status_code}, "
                        f"retrying in {wait_time}s (attempt {attempt + 1}/{self.max_retries})"
                    )
                    time.sleep(wait_time)
                    continue

                # Client error - don't retry
                logger.error(
                    f"❌ Client error {e.response.status_code}: {e.response.text}"
                )
                raise

            except httpx.RequestError as e:
                # Network error - retry
                wait_time = 2**attempt
                logger.warning(
                    f"⚠️ Network error: {e}, "
                    f"retrying in {wait_time}s (attempt {attempt + 1}/{self.max_retries})"
                )
                time.sleep(wait_time)

        raise httpx.RequestError(f"Failed after {self.max_retries} retries")

    # ========================================================================
    # Video Operations
    # ========================================================================

    def get_video(self, video_id: str) -> VideoResponse:
        """
        Fetch complete video information

        Args:
            video_id: YouTube video ID

        Returns:
            VideoResponse with snippet, statistics, and content details
        """
        params = {"part": "snippet,statistics,contentDetails", "id": video_id}

        response = self._request("videos", params, operation="videos")

        if not response.get("items"):
            raise ValueError(f"Video not found: {video_id}")

        video_data = response["items"][0]
        return VideoResponse(**video_data)

    def get_videos_batch(self, video_ids: List[str]) -> List[VideoResponse]:
        """
        Fetch multiple videos in a single request (up to 50 IDs)

        Args:
            video_ids: List of video IDs (max 50 per batch)

        Returns:
            List of VideoResponse objects
        """
        if len(video_ids) > 50:
            raise ValueError("Maximum 50 video IDs per batch request")

        params = {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(video_ids),
        }

        response = self._request("videos", params, operation="videos")

        return [VideoResponse(**item) for item in response.get("items", [])]

    def search_videos(
        self,
        query: str,
        max_results: int = 10,
        order: Literal[
            "date", "rating", "relevance", "title", "viewCount"
        ] = "relevance",
        published_after: Optional[datetime] = None,
    ) -> List[str]:
        """
        Search for videos and return video IDs

        Args:
            query: Search query string
            max_results: Maximum results to return (1-50)
            order: Result ordering method
            published_after: Filter videos published after this date

        Returns:
            List of video IDs

        Note:
            Search costs 100 quota units per request!
        """
        params = {
            "part": "id",
            "q": query,
            "type": "video",
            "maxResults": min(max_results, 50),
            "order": order,
        }

        if published_after:
            params["publishedAfter"] = published_after.isoformat() + "Z"

        response = self._request("search", params, operation="search")

        return [item["id"]["videoId"] for item in response.get("items", [])]

    # ========================================================================
    # Channel Operations
    # ========================================================================

    def get_channel(self, channel_id: str) -> ChannelResponse:
        """
        Fetch complete channel information

        Args:
            channel_id: YouTube channel ID

        Returns:
            ChannelResponse with snippet and statistics
        """
        params = {"part": "snippet,statistics", "id": channel_id}

        response = self._request("channels", params, operation="channels")

        if not response.get("items"):
            raise ValueError(f"Channel not found: {channel_id}")

        channel_data = response["items"][0]
        return ChannelResponse(**channel_data)

    def get_channel_videos(self, channel_id: str, max_results: int = 50) -> List[str]:
        """
        Get video IDs from a channel's uploads playlist

        Args:
            channel_id: YouTube channel ID
            max_results: Maximum videos to fetch

        Returns:
            List of video IDs
        """
        # First, get the channel's uploads playlist ID
        channel = self.get_channel(channel_id)

        # Search for videos from this channel
        params = {
            "part": "id",
            "channelId": channel_id,
            "type": "video",
            "maxResults": min(max_results, 50),
            "order": "date",
        }

        response = self._request("search", params, operation="search")

        return [item["id"]["videoId"] for item in response.get("items", [])]

    # ========================================================================
    # Comment Operations
    # ========================================================================

    def get_video_comments(
        self,
        video_id: str,
        max_results: int = 100,
        order: Literal["time", "relevance"] = "relevance",
    ) -> List[CommentResponse]:
        """
        Fetch comments for a video with pagination

        Args:
            video_id: YouTube video ID
            max_results: Maximum comments to fetch
            order: Comment ordering (time or relevance)

        Returns:
            List of CommentResponse objects
        """
        comments = []
        page_token = None

        while len(comments) < max_results:
            params = {
                "part": "snippet",
                "videoId": video_id,
                "maxResults": min(100, max_results - len(comments)),
                "order": order,
                "textFormat": "plainText",
            }

            if page_token:
                params["pageToken"] = page_token

            try:
                response = self._request(
                    "commentThreads", params, operation="comment_threads"
                )
            except Exception as e:
                logger.warning(
                    f"⚠️ Comments disabled or unavailable for {video_id}: {e}"
                )
                break

            items = response.get("items", [])
            if not items:
                break

            for item in items:
                comment_data = item["snippet"]["topLevelComment"]
                comments.append(CommentResponse(**comment_data))

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return comments[:max_results]

    # ========================================================================
    # Utility Methods
    # ========================================================================

    def get_quota_status(self) -> Dict[str, Any]:
        """Get current quota usage status"""
        return self.quota_tracker.get_status()

    def close(self) -> None:
        """Close HTTP client connection pool"""
        self.client.close()
        logger.info("🔌 YouTube API client closed")

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


# ============================================================================
# Convenience Functions
# ============================================================================


def create_youtube_client(api_key: Optional[str] = None) -> YouTubeAPIClient:
    """
    Factory function to create YouTube API client

    Args:
        api_key: Optional API key (reads from env if not provided)

    Returns:
        Configured YouTubeAPIClient instance
    """
    return YouTubeAPIClient(api_key=api_key)


if __name__ == "__main__":
    # Smoke test
    import os

    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        print("❌ YOUTUBE_API_KEY not set in environment")
        exit(1)

    with create_youtube_client(api_key) as client:
        print("\n📊 Quota Status:")
        print(client.get_quota_status())

        # Test video fetch
        print("\n🎥 Testing video fetch...")
        video = client.get_video("dQw4w9WgXcQ")  # Rick Astley - Never Gonna Give You Up
        print(f"✅ Fetched: {video.snippet.title}")
        print(f"   Views: {video.statistics.view_count:,}")
        print(f"   Likes: {video.statistics.like_count:,}")

        print("\n✅ Smoke test passed!")
