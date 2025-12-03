# src/api/schemas.py
"""
API Request/Response Schemas
Pydantic models for API validation and serialization
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


# ============================================================================
# Enums
# ============================================================================


class VideoStatusEnum(str, Enum):
    """Video processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class SortOrder(str, Enum):
    """Sort order"""
    ASC = "asc"
    DESC = "desc"


class VideoSortField(str, Enum):
    """Video sort fields"""
    PUBLISHED_AT = "published_at"
    VIEW_COUNT = "view_count"
    LIKE_COUNT = "like_count"
    COMMENT_COUNT = "comment_count"
    CREATED_AT = "created_at"


# ============================================================================
# Video Schemas
# ============================================================================


class VideoCreateRequest(BaseModel):
    """Request to create/fetch a video"""
    video_id: str = Field(..., min_length=11, max_length=11, description="YouTube video ID")
    fetch_comments: bool = Field(default=False, description="Also fetch comments")
    priority: int = Field(default=0, ge=0, le=10, description="Processing priority")


class VideoUpdateRequest(BaseModel):
    """Request to update video metadata"""
    title: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None
    tags: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[VideoStatusEnum] = None


class VideoSearchRequest(BaseModel):
    """Video search parameters"""
    query: Optional[str] = Field(None, description="Search query for title/description")
    channel_id: Optional[str] = Field(None, description="Filter by channel")
    status: Optional[VideoStatusEnum] = Field(None, description="Filter by status")
    min_views: Optional[int] = Field(None, ge=0, description="Minimum view count")
    max_views: Optional[int] = Field(None, description="Maximum view count")
    published_after: Optional[datetime] = Field(None, description="Published after date")
    published_before: Optional[datetime] = Field(None, description="Published before date")
    sort_by: VideoSortField = Field(
        default=VideoSortField.PUBLISHED_AT, description="Sort field"
    )
    sort_order: SortOrder = Field(default=SortOrder.DESC, description="Sort order")
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")


class VideoResponse(BaseModel):
    """Full video response"""
    id: str
    channel_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    published_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    category_id: Optional[str] = None
    tags: Optional[str] = None
    thumbnail_high: Optional[str] = None
    status: str = "pending"
    first_scraped_at: Optional[datetime] = None
    last_updated_at: Optional[datetime] = None
    scrape_count: int = 0

    class Config:
        from_attributes = True


class VideoSummary(BaseModel):
    """Video summary for lists"""
    id: str
    title: str
    channel_id: Optional[str] = None
    published_at: Optional[datetime] = None
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    thumbnail_high: Optional[str] = None
    status: str = "pending"

    class Config:
        from_attributes = True


class VideoStatsResponse(BaseModel):
    """Video statistics response"""
    video_id: str
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    engagement_rate: float = 0.0
    views_per_day: float = 0.0
    days_since_published: int = 0
    last_updated_at: Optional[datetime] = None


class VideoTrendResponse(BaseModel):
    """Trending video response with metrics"""
    video_id: str
    title: str
    channel_id: Optional[str] = None
    published_at: Optional[datetime] = None
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    views_per_day: float = 0.0
    engagement_rate: float = 0.0
    trending_score: float = 0.0


# ============================================================================
# Channel Schemas
# ============================================================================


class ChannelResponse(BaseModel):
    """Channel response"""
    id: str
    name: str
    description: Optional[str] = None
    subscriber_count: Optional[int] = None
    video_count: Optional[int] = None
    view_count: Optional[int] = None
    thumbnail_url: Optional[str] = None
    created_at: Optional[datetime] = None
    last_updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChannelSummary(BaseModel):
    """Channel summary for lists"""
    id: str
    name: str
    subscriber_count: Optional[int] = None
    video_count: Optional[int] = None
    thumbnail_url: Optional[str] = None

    class Config:
        from_attributes = True


# ============================================================================
# Comment Schemas
# ============================================================================


class CommentResponse(BaseModel):
    """Comment response"""
    id: str
    video_id: str
    author_name: str
    text: str
    like_count: int = 0
    published_at: Optional[datetime] = None
    is_reply: bool = False
    parent_id: Optional[str] = None
    sentiment_score: Optional[float] = None
    sentiment_label: Optional[str] = None

    class Config:
        from_attributes = True


# ============================================================================
# Pagination
# ============================================================================


class PaginatedResponse(BaseModel):
    """Generic paginated response"""
    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


class VideoPaginatedResponse(PaginatedResponse):
    """Paginated video response"""
    items: List[VideoSummary]


# ============================================================================
# Converter Functions
# ============================================================================


def video_model_to_response(video) -> VideoResponse:
    """Convert Video model to VideoResponse"""
    return VideoResponse(
        id=video.id,
        channel_id=video.channel_id,
        title=video.title,
        description=video.description,
        published_at=video.published_at,
        duration_seconds=video.duration_seconds,
        view_count=video.view_count or 0,
        like_count=video.like_count or 0,
        comment_count=video.comment_count or 0,
        category_id=video.category_id,
        tags=video.tags,
        thumbnail_high=video.thumbnail_high,
        status=video.status.value if hasattr(video.status, 'value') else str(video.status),
        first_scraped_at=video.first_scraped_at,
        last_updated_at=video.last_updated_at,
        scrape_count=video.scrape_count or 0,
    )


def video_model_to_summary(video) -> VideoSummary:
    """Convert Video model to VideoSummary"""
    return VideoSummary(
        id=video.id,
        title=video.title,
        channel_id=video.channel_id,
        published_at=video.published_at,
        view_count=video.view_count or 0,
        like_count=video.like_count or 0,
        comment_count=video.comment_count or 0,
        thumbnail_high=video.thumbnail_high,
        status=video.status.value if hasattr(video.status, 'value') else str(video.status),
    )


def channel_model_to_response(channel) -> ChannelResponse:
    """Convert Channel model to ChannelResponse"""
    return ChannelResponse(
        id=channel.id,
        name=channel.name,
        description=channel.description,
        subscriber_count=channel.subscriber_count,
        video_count=channel.video_count,
        view_count=channel.view_count,
        thumbnail_url=channel.thumbnail_url,
        created_at=channel.created_at,
        last_updated_at=channel.last_updated_at,
    )


# ============================================================================
# Export
# ============================================================================

__all__ = [
    # Enums
    "VideoStatusEnum",
    "SortOrder",
    "VideoSortField",
    # Video
    "VideoCreateRequest",
    "VideoUpdateRequest",
    "VideoSearchRequest",
    "VideoResponse",
    "VideoSummary",
    "VideoStatsResponse",
    "VideoTrendResponse",
    # Channel
    "ChannelResponse",
    "ChannelSummary",
    # Comment
    "CommentResponse",
    # Pagination
    "PaginatedResponse",
    "VideoPaginatedResponse",
    # Converters
    "video_model_to_response",
    "video_model_to_summary",
    "channel_model_to_response",
]
