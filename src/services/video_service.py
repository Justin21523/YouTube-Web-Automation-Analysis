"""
Video Service
Business logic for video operations
"""

from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_

from src.services.base_service import BaseService
from src.services.exceptions import (
    ResourceNotFoundError,
    ResourceAlreadyExistsError,
    ValidationError,
    YouTubeAPIError,
    ProcessingError,
)

from src.infrastructure.clients.youtube_api import YouTubeAPIClient
from src.infrastructure.repositories.video_repository import VideoRepository
from src.infrastructure.repositories.channel_repository import ChannelRepository
from src.infrastructure.database.models import Video, VideoStatus

from src.api.schemas import (
    VideoCreateRequest,
    VideoUpdateRequest,
    VideoSearchRequest,
    VideoResponse,
    VideoSummary,
    VideoStatsResponse,
    VideoTrendResponse,
    video_model_to_response,
    video_model_to_summary,
)


class VideoService(BaseService):
    """
    Video operations service

    Handles:
    - Video CRUD operations
    - YouTube API integration
    - Search and filtering
    - Statistics calculation
    - Caching strategy
    """

    def __init__(
        self,
        youtube_client: YouTubeAPIClient,
        video_repo: VideoRepository,
        channel_repo: ChannelRepository,
        cache=None,
        config=None,
    ):
        super().__init__(cache=cache, config=config)
        self.youtube = youtube_client
        self.video_repo = video_repo
        self.channel_repo = channel_repo

    def get_service_name(self) -> str:
        return "video"

    # ========================================================================
    # CRUD Operations
    # ========================================================================

    async def create_video(
        self, db: AsyncSession, request: VideoCreateRequest
    ) -> VideoResponse:
        """
        Create new video and fetch metadata from YouTube

        Args:
            db: Database session
            request: Video creation request

        Returns:
            Created video response

        Raises:
            ValidationError: Invalid input
            ResourceAlreadyExistsError: Video already exists
            YouTubeAPIError: API fetch failed
        """
        self.log_info(f"Creating video: {request.video_id}")

        # Validate input
        self.validate_required(request.video_id, "video_id")

        # Check if already exists
        existing = await self.video_repo.get_by_id(db, request.video_id)
        if existing:
            raise ResourceAlreadyExistsError("Video", request.video_id)

        try:
            # Fetch metadata from YouTube API
            youtube_video = self.youtube.get_video(request.video_id)

            # Create video record
            video_data = {
                "id": youtube_video.id,
                "channel_id": youtube_video.snippet.channel_id,
                "title": youtube_video.snippet.title,
                "description": youtube_video.snippet.description,
                "published_at": youtube_video.snippet.published_at,
                "duration_seconds": self._parse_duration(
                    youtube_video.content_details.duration
                ),
                "view_count": youtube_video.statistics.view_count,
                "like_count": youtube_video.statistics.like_count,
                "comment_count": youtube_video.statistics.comment_count,
                "category_id": youtube_video.snippet.category_id,
                "tags": (
                    ",".join(youtube_video.snippet.tags)
                    if youtube_video.snippet.tags
                    else None
                ),
                "thumbnail_high": (
                    youtube_video.snippet.thumbnails.high.url
                    if youtube_video.snippet.thumbnails.high
                    else None
                ),
                "status": VideoStatus.COMPLETED,
                "first_scraped_at": datetime.utcnow(),
                "last_updated_at": datetime.utcnow(),
            }

            # Ensure channel exists
            await self._ensure_channel_exists(db, youtube_video.snippet.channel_id)

            # Create in database
            video = await self.video_repo.create(db, video_data)
            await db.commit()

            self.log_info(f"Video created successfully: {request.video_id}")

            # Invalidate cache
            self._invalidate_video_cache(request.video_id)

            return video_model_to_response(video)

        except YouTubeAPIError as e:
            self.log_error(f"YouTube API error for video {request.video_id}", error=e)
            raise

        except Exception as e:
            await db.rollback()
            raise self.handle_error(e, "create_video", {"video_id": request.video_id})

    async def get_video(
        self, db: AsyncSession, video_id: str, use_cache: bool = True
    ) -> VideoResponse:
        """
        Get video by ID with optional caching

        Args:
            db: Database session
            video_id: YouTube video ID
            use_cache: Whether to use cache

        Returns:
            Video response

        Raises:
            ResourceNotFoundError: Video not found
        """
        self.validate_required(video_id, "video_id")

        # Check cache
        if use_cache:
            cache_key = self.get_cache_key("video", video_id)
            cached = self.get_from_cache(cache_key)
            if cached:
                self.log_debug(f"Cache hit for video: {video_id}")
                return cached

        # Fetch from database
        video = await self.video_repo.get_by_id(db, video_id)
        if not video:
            raise ResourceNotFoundError("Video", video_id)

        response = video_model_to_response(video)

        # Cache result
        if use_cache:
            cache_key = self.get_cache_key("video", video_id)
            self.set_in_cache(cache_key, response, ttl_seconds=3600)

        return response

    async def update_video(
        self, db: AsyncSession, video_id: str, request: VideoUpdateRequest
    ) -> VideoResponse:
        """
        Update video metadata

        Args:
            db: Database session
            video_id: YouTube video ID
            request: Update request

        Returns:
            Updated video response
        """
        self.log_info(f"Updating video: {video_id}")

        # Check exists
        video = await self.video_repo.get_by_id(db, video_id)
        if not video:
            raise ResourceNotFoundError("Video", video_id)

        try:
            # Prepare update data
            update_data = request.model_dump(exclude_unset=True)
            update_data["last_updated_at"] = datetime.utcnow()

            # Update in database
            updated_video = await self.video_repo.update(db, video_id, update_data)
            await db.commit()

            self.log_info(f"Video updated successfully: {video_id}")

            # Invalidate cache
            self._invalidate_video_cache(video_id)

            return video_model_to_response(updated_video)

        except Exception as e:
            await db.rollback()
            raise self.handle_error(e, "update_video", {"video_id": video_id})

    async def delete_video(self, db: AsyncSession, video_id: str) -> Dict[str, Any]:
        """
        Delete video and related data

        Args:
            db: Database session
            video_id: YouTube video ID

        Returns:
            Deletion confirmation
        """
        self.log_info(f"Deleting video: {video_id}")

        # Check exists
        video = await self.video_repo.get_by_id(db, video_id)
        if not video:
            raise ResourceNotFoundError("Video", video_id)

        try:
            # Delete video (cascade deletes comments and analytics)
            await self.video_repo.delete(db, video_id)
            await db.commit()

            self.log_info(f"Video deleted successfully: {video_id}")

            # Invalidate cache
            self._invalidate_video_cache(video_id)

            return {
                "success": True,
                "video_id": video_id,
                "message": "Video deleted successfully",
            }

        except Exception as e:
            await db.rollback()
            raise self.handle_error(e, "delete_video", {"video_id": video_id})

    # ========================================================================
    # Search & Filter Operations
    # ========================================================================

    async def search_videos(
        self, db: AsyncSession, params: VideoSearchRequest
    ) -> Tuple[List[VideoSummary], int]:
        """
        Search videos with filters and pagination

        Args:
            db: Database session
            params: Search parameters

        Returns:
            Tuple of (video summaries, total count)
        """
        self.log_info(f"Searching videos with query: {params.query}")

        # Calculate pagination
        skip, limit = self.calculate_pagination(params.page, params.page_size)

        # Build filters
        filters = {}
        if params.channel_id:
            filters["channel_id"] = params.channel_id
        if params.status:
            filters["status"] = params.status
        if params.min_views is not None:
            filters["min_views"] = params.min_views
        if params.max_views is not None:
            filters["max_views"] = params.max_views
        if params.published_after:
            filters["published_after"] = params.published_after
        if params.published_before:
            filters["published_before"] = params.published_before

        # Search videos
        videos = await self.video_repo.search(
            db,
            query=params.query,
            filters=filters,
            skip=skip,
            limit=limit,
            sort_by=params.sort_by,
            sort_order=params.sort_order,
        )

        # Get total count
        total = await self.video_repo.count_search(db, params.query, filters)

        # Convert to summaries
        summaries = [video_model_to_summary(v) for v in videos]

        return summaries, total

    async def get_trending_videos(
        self, db: AsyncSession, days: int = 7, limit: int = 50
    ) -> List[VideoTrendResponse]:
        """
        Get trending videos from last N days

        Args:
            db: Database session
            days: Number of days to look back
            limit: Maximum results

        Returns:
            List of trending videos with metrics
        """
        self.log_info(f"Fetching trending videos for last {days} days")

        self.validate_positive(days, "days")
        self.validate_positive(limit, "limit")

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Get videos published in timeframe
        query = (
            select(Video)
            .where(Video.published_at >= cutoff_date)
            .order_by(Video.view_count.desc())
            .limit(limit)
        )

        result = await db.execute(query)
        videos = result.scalars().all()

        # Convert to trend responses
        trend_responses = []
        for video in videos:
            trend = VideoTrendResponse(
                video_id=video.id,
                title=video.title,
                channel_id=video.channel_id,
                published_at=video.published_at,
                view_count=video.view_count,
                like_count=video.like_count,
                comment_count=video.comment_count,
                views_per_day=self._calculate_views_per_day(video),
                engagement_rate=self._calculate_engagement_rate(video),
                trending_score=self._calculate_trending_score(video, days),
            )
            trend_responses.append(trend)

        return trend_responses

    async def get_videos_by_channel(
        self, db: AsyncSession, channel_id: str, skip: int = 0, limit: int = 20
    ) -> Tuple[List[VideoSummary], int]:
        """
        Get videos for a specific channel

        Args:
            db: Database session
            channel_id: YouTube channel ID
            skip: Pagination offset
            limit: Maximum results

        Returns:
            Tuple of (video summaries, total count)
        """
        self.validate_required(channel_id, "channel_id")

        videos = await self.video_repo.get_by_channel(
            db, channel_id, skip=skip, limit=limit
        )

        total = await self.video_repo.count_by_channel(db, channel_id)

        summaries = [video_model_to_summary(v) for v in videos]

        return summaries, total

    # ========================================================================
    # Statistics Operations
    # ========================================================================

    async def get_video_stats(
        self, db: AsyncSession, video_id: str
    ) -> VideoStatsResponse:
        """
        Get detailed statistics for a video

        Args:
            db: Database session
            video_id: YouTube video ID

        Returns:
            Video statistics
        """
        video = await self.video_repo.get_by_id(db, video_id)
        if not video:
            raise ResourceNotFoundError("Video", video_id)

        # Calculate metrics
        engagement_rate = self._calculate_engagement_rate(video)
        views_per_day = self._calculate_views_per_day(video)

        return VideoStatsResponse(
            video_id=video.id,
            view_count=video.view_count,
            like_count=video.like_count,
            comment_count=video.comment_count,
            engagement_rate=engagement_rate,
            views_per_day=views_per_day,
            days_since_published=self._calculate_days_since_published(video),
            last_updated_at=video.last_updated_at,
        )

    async def get_aggregate_stats(
        self, db: AsyncSession, channel_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get aggregate statistics across videos

        Args:
            db: Database session
            channel_id: Optional channel filter

        Returns:
            Aggregate statistics
        """
        query = select(
            func.count(Video.id).label("total_videos"),
            func.sum(Video.view_count).label("total_views"),
            func.sum(Video.like_count).label("total_likes"),
            func.sum(Video.comment_count).label("total_comments"),
            func.avg(Video.view_count).label("avg_views"),
        )

        if channel_id:
            query = query.where(Video.channel_id == channel_id)

        result = await db.execute(query)
        stats = result.one()

        return {
            "total_videos": stats.total_videos or 0,
            "total_views": stats.total_views or 0,
            "total_likes": stats.total_likes or 0,
            "total_comments": stats.total_comments or 0,
            "avg_views": float(stats.avg_views) if stats.avg_views else 0.0,
        }

    # ========================================================================
    # Orchestration Operations
    # ========================================================================

    async def refresh_video_metadata(
        self, db: AsyncSession, video_id: str
    ) -> VideoResponse:
        """
        Refresh video metadata from YouTube API

        Args:
            db: Database session
            video_id: YouTube video ID

        Returns:
            Updated video response
        """
        self.log_info(f"Refreshing metadata for video: {video_id}")

        # Get existing video
        video = await self.video_repo.get_by_id(db, video_id)
        if not video:
            raise ResourceNotFoundError("Video", video_id)

        try:
            # Fetch fresh data from YouTube
            youtube_video = self.youtube.get_video(video_id)

            # Update fields
            update_data = {
                "title": youtube_video.snippet.title,
                "description": youtube_video.snippet.description,
                "view_count": youtube_video.statistics.view_count,
                "like_count": youtube_video.statistics.like_count,
                "comment_count": youtube_video.statistics.comment_count,
                "last_updated_at": datetime.utcnow(),
                "scrape_count": video.scrape_count + 1,
            }

            # Update in database
            updated_video = await self.video_repo.update(db, video_id, update_data)
            await db.commit()

            self.log_info(f"Metadata refreshed for video: {video_id}")

            # Invalidate cache
            self._invalidate_video_cache(video_id)

            return video_model_to_response(updated_video)

        except Exception as e:
            await db.rollback()
            raise self.handle_error(e, "refresh_video_metadata", {"video_id": video_id})

    async def batch_fetch_videos(
        self, db: AsyncSession, video_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Batch fetch multiple videos from YouTube

        Args:
            db: Database session
            video_ids: List of video IDs

        Returns:
            Batch operation results
        """
        self.log_info(f"Batch fetching {len(video_ids)} videos")

        self.validate_list_not_empty(video_ids, "video_ids")
        self.validate_range(len(video_ids), "video_ids count", 1, 50)

        results = {"success": [], "failed": [], "skipped": []}

        # Use YouTube API batch fetch
        try:
            youtube_videos = self.youtube.get_videos_batch(video_ids)

            for youtube_video in youtube_videos:
                try:
                    # Check if exists
                    existing = await self.video_repo.get_by_id(db, youtube_video.id)
                    if existing:
                        results["skipped"].append(youtube_video.id)
                        continue

                    # Create video data
                    video_data = {
                        "id": youtube_video.id,
                        "channel_id": youtube_video.snippet.channel_id,
                        "title": youtube_video.snippet.title,
                        "description": youtube_video.snippet.description,
                        "published_at": youtube_video.snippet.published_at,
                        "view_count": youtube_video.statistics.view_count,
                        "like_count": youtube_video.statistics.like_count,
                        "comment_count": youtube_video.statistics.comment_count,
                        "status": VideoStatus.COMPLETED,
                        "first_scraped_at": datetime.utcnow(),
                        "last_updated_at": datetime.utcnow(),
                    }

                    # Ensure channel exists
                    await self._ensure_channel_exists(
                        db, youtube_video.snippet.channel_id
                    )

                    # Create video
                    await self.video_repo.create(db, video_data)
                    results["success"].append(youtube_video.id)

                except Exception as e:
                    self.log_error(
                        f"Failed to create video {youtube_video.id}", error=e
                    )
                    results["failed"].append(
                        {"video_id": youtube_video.id, "error": str(e)}
                    )

            await db.commit()

            self.log_info(
                f"Batch fetch complete: "
                f"{len(results['success'])} success, "
                f"{len(results['failed'])} failed, "
                f"{len(results['skipped'])} skipped"
            )

            return results

        except Exception as e:
            await db.rollback()
            raise self.handle_error(e, "batch_fetch_videos", {"count": len(video_ids)})

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _parse_duration(self, iso_duration: str) -> int:
        """Parse ISO 8601 duration to seconds"""
        import re

        pattern = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")
        match = pattern.match(iso_duration)

        if not match:
            return 0

        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)

        return hours * 3600 + minutes * 60 + seconds

    def _calculate_engagement_rate(self, video: Video) -> float:
        """Calculate engagement rate percentage"""
        if video.view_count == 0:
            return 0.0

        engagements = (video.like_count or 0) + (video.comment_count or 0)
        return round((engagements / video.view_count) * 100, 2)

    def _calculate_views_per_day(self, video: Video) -> float:
        """Calculate average views per day since publication"""
        days = self._calculate_days_since_published(video)
        if days == 0:
            return float(video.view_count)

        return round(video.view_count / days, 2)

    def _calculate_days_since_published(self, video: Video) -> int:
        """Calculate days since video was published"""
        delta = datetime.utcnow() - video.published_at
        return max(delta.days, 1)  # At least 1 day

    def _calculate_trending_score(self, video: Video, days: int) -> float:
        """
        Calculate trending score based on multiple factors
        Higher score = more trending
        """
        views_per_day = self._calculate_views_per_day(video)
        engagement_rate = self._calculate_engagement_rate(video)
        recency_factor = (
            1.0 + (days - self._calculate_days_since_published(video)) / days
        )

        # Weighted score
        score = (
            views_per_day * 0.4
            + engagement_rate * 1000 * 0.3
            + recency_factor * 10000 * 0.3
        )

        return round(score, 2)

    async def _ensure_channel_exists(self, db: AsyncSession, channel_id: str) -> None:
        """Ensure channel exists, create placeholder if not"""
        existing = await self.channel_repo.get_by_id(db, channel_id)
        if not existing:
            # Create placeholder channel
            channel_data = {
                "id": channel_id,
                "name": "Unknown Channel",
                "first_scraped_at": datetime.utcnow(),
                "last_updated_at": datetime.utcnow(),
            }
            await self.channel_repo.create(db, channel_data)
            self.log_info(f"Created placeholder channel: {channel_id}")

    def _invalidate_video_cache(self, video_id: str) -> None:
        """Invalidate all cache entries for a video"""
        cache_key = self.get_cache_key("video", video_id)
        self.delete_from_cache(cache_key)
