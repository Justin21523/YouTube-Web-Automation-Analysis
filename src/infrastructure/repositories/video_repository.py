# src/infrastructure/repositories/video_repository.py
"""
Video Repository
Handles all video-related database operations
"""

from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy import select, func, and_, or_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import logging

from .base import BaseRepository
from src.app.models import Video, Channel, Comment, VideoAnalytics

logger = logging.getLogger(__name__)


class VideoRepository(BaseRepository[Video]):
    """
    Repository for Video operations
    Provides video-specific queries and analytics
    """

    def __init__(self, session: AsyncSession):
        """Initialize video repository"""
        super().__init__(session, Video)

    # ========================================================================
    # Video Retrieval Methods
    # ========================================================================

    async def get_by_id_with_details(self, video_id: str) -> Optional[Video]:
        """
        Get video with all related data (channel, comments, analytics)

        Args:
            video_id: YouTube video ID

        Returns:
            Video with relationships loaded or None
        """
        try:
            result = await self.session.execute(
                select(Video)
                .options(
                    selectinload(Video.channel),
                    selectinload(Video.comments),
                    selectinload(Video.analytics),
                )
                .where(Video.id == video_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"❌ Failed to get video with details: {e}")
            raise

    async def get_by_channel(
        self,
        channel_id: str,
        skip: int = 0,
        limit: int = 50,
        order_by: str = "published_at",
    ) -> List[Video]:
        """
        Get all videos from a channel

        Args:
            channel_id: YouTube channel ID
            skip: Pagination offset
            limit: Max results
            order_by: Sort field (published_at, view_count, like_count)

        Returns:
            List of videos
        """
        try:
            query = (
                select(Video)
                .where(Video.channel_id == channel_id)
                .offset(skip)
                .limit(limit)
            )

            # Apply ordering
            if order_by == "published_at":
                query = query.order_by(desc(Video.published_at))
            elif order_by == "view_count":
                query = query.order_by(desc(Video.view_count))
            elif order_by == "like_count":
                query = query.order_by(desc(Video.like_count))
            else:
                query = query.order_by(desc(Video.published_at))

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get videos by channel: {e}")
            raise

    async def get_by_status(
        self, status: str, skip: int = 0, limit: int = 100
    ) -> List[Video]:
        """
        Get videos by processing status

        Args:
            status: pending/processing/completed/failed
            skip: Pagination offset
            limit: Max results

        Returns:
            List of videos with matching status
        """
        try:
            result = await self.session.execute(
                select(Video)
                .where(Video.status == status)
                .order_by(desc(Video.first_scraped_at))
                .offset(skip)
                .limit(limit)
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get videos by status: {e}")
            raise

    # ========================================================================
    # Trending & Popular Videos
    # ========================================================================

    async def get_trending(
        self, days: int = 7, limit: int = 50, min_views: int = 1000
    ) -> List[Video]:
        """
        Get trending videos (recent + high views)

        Args:
            days: Look back period
            limit: Max results
            min_views: Minimum view count threshold

        Returns:
            List of trending videos
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            result = await self.session.execute(
                select(Video)
                .where(
                    and_(
                        Video.published_at >= cutoff_date, Video.view_count >= min_views
                    )
                )
                .order_by(desc(Video.view_count))
                .limit(limit)
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get trending videos: {e}")
            raise

    async def get_most_viewed(
        self, channel_id: Optional[str] = None, limit: int = 50
    ) -> List[Video]:
        """
        Get most viewed videos (all time)

        Args:
            channel_id: Filter by channel (optional)
            limit: Max results

        Returns:
            List of most viewed videos
        """
        try:
            query = select(Video).order_by(desc(Video.view_count)).limit(limit)

            if channel_id:
                query = query.where(Video.channel_id == channel_id)

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get most viewed videos: {e}")
            raise

    async def get_most_engaged(
        self, days: Optional[int] = None, limit: int = 50
    ) -> List[Video]:
        """
        Get videos with highest engagement rate
        Engagement = (likes + comments) / views * 100

        Args:
            days: Optional time period filter
            limit: Max results

        Returns:
            List of videos sorted by engagement
        """
        try:
            query = select(Video).where(Video.view_count > 0)

            # Time filter
            if days:
                cutoff_date = datetime.utcnow() - timedelta(days=days)
                query = query.where(Video.published_at >= cutoff_date)

            # Calculate engagement rate and order
            # Note: SQLAlchemy expression for computed field
            engagement_rate = (
                (Video.like_count + Video.comment_count) / Video.view_count * 100
            )
            query = query.order_by(desc(engagement_rate)).limit(limit)

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get most engaged videos: {e}")
            raise

    # ========================================================================
    # Search & Filtering
    # ========================================================================

    async def search(
        self,
        query: str,
        channel_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Video]:
        """
        Search videos by title or description

        Args:
            query: Search query string
            channel_id: Filter by channel (optional)
            skip: Pagination offset
            limit: Max results

        Returns:
            List of matching videos
        """
        try:
            search_query = select(Video).where(
                or_(
                    Video.title.ilike(f"%{query}%"),
                    Video.description.ilike(f"%{query}%"),
                )
            )

            if channel_id:
                search_query = search_query.where(Video.channel_id == channel_id)

            search_query = (
                search_query.order_by(desc(Video.view_count)).offset(skip).limit(limit)
            )

            result = await self.session.execute(search_query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to search videos: {e}")
            raise

    async def filter_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        channel_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Video]:
        """
        Get videos published within date range

        Args:
            start_date: Start of date range
            end_date: End of date range
            channel_id: Filter by channel (optional)
            skip: Pagination offset
            limit: Max results

        Returns:
            List of videos in date range
        """
        try:
            query = select(Video).where(
                and_(Video.published_at >= start_date, Video.published_at <= end_date)
            )

            if channel_id:
                query = query.where(Video.channel_id == channel_id)

            query = query.order_by(desc(Video.published_at)).offset(skip).limit(limit)

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to filter by date range: {e}")
            raise

    async def filter_by_views(
        self,
        min_views: int,
        max_views: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Video]:
        """
        Filter videos by view count range

        Args:
            min_views: Minimum views
            max_views: Maximum views (optional)
            skip: Pagination offset
            limit: Max results

        Returns:
            List of videos matching criteria
        """
        try:
            query = select(Video).where(Video.view_count >= min_views)

            if max_views is not None:
                query = query.where(Video.view_count <= max_views)

            query = query.order_by(desc(Video.view_count)).offset(skip).limit(limit)

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to filter by views: {e}")
            raise

    # ========================================================================
    # Analytics & Statistics
    # ========================================================================

    async def get_statistics(
        self, channel_id: Optional[str] = None, days: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get aggregated video statistics

        Args:
            channel_id: Filter by channel (optional)
            days: Time period (optional)

        Returns:
            Dictionary with statistics
        """
        try:
            query = select(
                func.count(Video.id).label("total_videos"),
                func.sum(Video.view_count).label("total_views"),
                func.sum(Video.like_count).label("total_likes"),
                func.sum(Video.comment_count).label("total_comments"),
                func.avg(Video.view_count).label("avg_views"),
                func.max(Video.view_count).label("max_views"),
                func.min(Video.view_count).label("min_views"),
            )

            # Apply filters
            if channel_id:
                query = query.where(Video.channel_id == channel_id)

            if days:
                cutoff_date = datetime.utcnow() - timedelta(days=days)
                query = query.where(Video.published_at >= cutoff_date)

            result = await self.session.execute(query)
            row = result.first()

            if row:
                return {
                    "total_videos": row.total_videos or 0,
                    "total_views": row.total_views or 0,
                    "total_likes": row.total_likes or 0,
                    "total_comments": row.total_comments or 0,
                    "avg_views": float(row.avg_views or 0),
                    "max_views": row.max_views or 0,
                    "min_views": row.min_views or 0,
                    "period_days": days,
                    "channel_id": channel_id,
                }
            else:
                return {
                    "total_videos": 0,
                    "total_views": 0,
                    "total_likes": 0,
                    "total_comments": 0,
                    "avg_views": 0.0,
                    "max_views": 0,
                    "min_views": 0,
                }
        except Exception as e:
            logger.error(f"❌ Failed to get statistics: {e}")
            raise

    async def get_upload_frequency(
        self, channel_id: str, days: int = 30
    ) -> Dict[str, Any]:
        """
        Calculate upload frequency for a channel

        Args:
            channel_id: YouTube channel ID
            days: Analysis period

        Returns:
            Upload frequency metrics
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            result = await self.session.execute(
                select(func.count(Video.id)).where(
                    and_(
                        Video.channel_id == channel_id,
                        Video.published_at >= cutoff_date,
                    )
                )
            )

            video_count = result.scalar() or 0
            videos_per_day = video_count / days if days > 0 else 0
            videos_per_week = videos_per_day * 7

            return {
                "channel_id": channel_id,
                "period_days": days,
                "total_videos": video_count,
                "videos_per_day": round(videos_per_day, 2),
                "videos_per_week": round(videos_per_week, 2),
                "videos_per_month": round(videos_per_day * 30, 2),
            }
        except Exception as e:
            logger.error(f"❌ Failed to calculate upload frequency: {e}")
            raise

    async def get_engagement_metrics(self, video_id: str) -> Dict[str, Any]:
        """
        Calculate detailed engagement metrics for a video

        Args:
            video_id: YouTube video ID

        Returns:
            Engagement metrics dictionary
        """
        try:
            video = await self.get_by_id(video_id)

            if not video:
                return {}

            # Calculate metrics
            engagement_rate = 0.0
            like_rate = 0.0
            comment_rate = 0.0

            if video.view_count > 0:
                engagement_rate = (
                    (video.like_count + video.comment_count) / video.view_count * 100
                )
                like_rate = (video.like_count / video.view_count) * 100
                comment_rate = (video.comment_count / video.view_count) * 100

            return {
                "video_id": video_id,
                "view_count": video.view_count,
                "like_count": video.like_count,
                "comment_count": video.comment_count,
                "engagement_rate": round(engagement_rate, 2),
                "like_rate": round(like_rate, 2),
                "comment_rate": round(comment_rate, 2),
                "likes_per_comment": (
                    round(video.like_count / video.comment_count, 2)
                    if video.comment_count > 0
                    else 0
                ),
            }
        except Exception as e:
            logger.error(f"❌ Failed to get engagement metrics: {e}")
            raise

    # ========================================================================
    # Batch Operations
    # ========================================================================

    async def upsert_video(self, video_data: Dict[str, Any]) -> Video:
        """
        Insert or update video (upsert)

        Args:
            video_data: Video attributes dictionary

        Returns:
            Video instance (created or updated)
        """
        try:
            video_id = video_data.get("id")
            existing_video = await self.get_by_id(video_id)

            if existing_video:
                # Update existing video
                video_data["last_updated_at"] = datetime.utcnow()
                video_data["scrape_count"] = existing_video.scrape_count + 1
                updated_video = await self.update(video_id, **video_data)
                logger.info(f"✅ Updated video: {video_id}")
                return updated_video
            else:
                # Create new video
                video_data["first_scraped_at"] = datetime.utcnow()
                video_data["last_updated_at"] = datetime.utcnow()
                video_data["scrape_count"] = 1
                new_video = await self.create(**video_data)
                logger.info(f"✅ Created new video: {video_id}")
                return new_video
        except Exception as e:
            logger.error(f"❌ Failed to upsert video: {e}")
            raise

    async def bulk_upsert_videos(
        self, videos_data: List[Dict[str, Any]]
    ) -> Tuple[int, int]:
        """
        Bulk insert or update videos

        Args:
            videos_data: List of video attribute dictionaries

        Returns:
            Tuple of (created_count, updated_count)
        """
        try:
            created_count = 0
            updated_count = 0

            for video_data in videos_data:
                video_id = video_data.get("id")
                existing = await self.exists(video_id)

                if existing:
                    await self.update(video_id, **video_data)
                    updated_count += 1
                else:
                    video_data["first_scraped_at"] = datetime.utcnow()
                    video_data["last_updated_at"] = datetime.utcnow()
                    video_data["scrape_count"] = 1
                    await self.create(**video_data)
                    created_count += 1

            await self.session.commit()
            logger.info(
                f"✅ Bulk upsert complete: {created_count} created, {updated_count} updated"
            )
            return created_count, updated_count
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Failed to bulk upsert videos: {e}")
            raise

    # ========================================================================
    # Video Status Management
    # ========================================================================

    async def mark_as_processing(self, video_id: str) -> bool:
        """
        Mark video as processing

        Args:
            video_id: YouTube video ID

        Returns:
            True if updated
        """
        try:
            await self.update(video_id, status="processing")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to mark video as processing: {e}")
            return False

    async def mark_as_completed(self, video_id: str) -> bool:
        """
        Mark video as completed

        Args:
            video_id: YouTube video ID

        Returns:
            True if updated
        """
        try:
            await self.update(video_id, status="completed")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to mark video as completed: {e}")
            return False

    async def mark_as_failed(self, video_id: str) -> bool:
        """
        Mark video as failed

        Args:
            video_id: YouTube video ID

        Returns:
            True if updated
        """
        try:
            await self.update(video_id, status="failed")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to mark video as failed: {e}")
            return False

    async def get_pending_videos(self, limit: int = 100) -> List[Video]:
        """
        Get videos pending processing

        Args:
            limit: Max results

        Returns:
            List of pending videos
        """
        try:
            result = await self.session.execute(
                select(Video)
                .where(Video.status == "pending")
                .order_by(asc(Video.first_scraped_at))
                .limit(limit)
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get pending videos: {e}")
            raise


# ============================================================================
# Export
# ============================================================================

__all__ = ["VideoRepository"]
