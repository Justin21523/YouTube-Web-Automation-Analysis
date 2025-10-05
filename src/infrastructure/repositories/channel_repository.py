# src/infrastructure/repositories/channel_repository.py
"""
Channel Repository
Handles all channel-related database operations
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import select, func, and_, or_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import logging

from .base import BaseRepository
from src.app.models import Channel, Video, Playlist, VideoStatus

logger = logging.getLogger(__name__)


class ChannelRepository(BaseRepository[Channel]):
    """
    Repository for Channel operations
    Provides channel-specific queries and analytics
    """

    def __init__(self, session: AsyncSession):
        """Initialize channel repository"""
        super().__init__(session, Channel)

    # ========================================================================
    # Channel Retrieval Methods
    # ========================================================================

    async def get_by_id_with_details(self, channel_id: str) -> Optional[Channel]:
        """
        Get channel with all related data (videos, playlists)

        Args:
            channel_id: YouTube channel ID

        Returns:
            Channel with relationships loaded or None
        """
        try:
            result = await self.session.execute(
                select(Channel)
                .options(selectinload(Channel.videos), selectinload(Channel.playlists))
                .where(Channel.id == channel_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"❌ Failed to get channel with details: {e}")
            raise

    async def get_by_handle(self, handle: str) -> Optional[Channel]:
        """
        Get channel by custom handle (@username)

        Args:
            handle: Channel handle (with or without @)

        Returns:
            Channel or None
        """
        try:
            # Normalize handle (remove @ if present)
            normalized_handle = handle.lstrip("@")

            result = await self.session.execute(
                select(Channel).where(
                    or_(
                        Channel.handle == f"@{normalized_handle}",
                        Channel.handle == normalized_handle,
                    )
                )
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"❌ Failed to get channel by handle: {e}")
            raise

    async def get_by_name(self, name: str, exact_match: bool = False) -> List[Channel]:
        """
        Search channels by name

        Args:
            name: Channel name to search
            exact_match: If True, exact match; otherwise partial match

        Returns:
            List of matching channels
        """
        try:
            if exact_match:
                query = select(Channel).where(Channel.name == name)
            else:
                query = select(Channel).where(Channel.name.ilike(f"%{name}%"))

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to search channels by name: {e}")
            raise

    async def get_active_channels(
        self, skip: int = 0, limit: int = 100
    ) -> List[Channel]:
        """
        Get all active channels

        Args:
            skip: Pagination offset
            limit: Max results

        Returns:
            List of active channels
        """
        try:
            result = await self.session.execute(
                select(Channel)
                .where(Channel.is_active == True)
                .order_by(desc(Channel.subscriber_count))
                .offset(skip)
                .limit(limit)
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get active channels: {e}")
            raise

    async def get_verified_channels(
        self, skip: int = 0, limit: int = 100
    ) -> List[Channel]:
        """
        Get verified channels

        Args:
            skip: Pagination offset
            limit: Max results

        Returns:
            List of verified channels
        """
        try:
            result = await self.session.execute(
                select(Channel)
                .where(Channel.is_verified == True)
                .order_by(desc(Channel.subscriber_count))
                .offset(skip)
                .limit(limit)
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get verified channels: {e}")
            raise

    # ========================================================================
    # Channel Rankings & Sorting
    # ========================================================================

    async def get_top_channels_by_subscribers(
        self, limit: int = 50, country: Optional[str] = None
    ) -> List[Channel]:
        """
        Get top channels by subscriber count

        Args:
            limit: Max results
            country: Filter by country code (optional)

        Returns:
            List of top channels
        """
        try:
            query = (
                select(Channel).order_by(desc(Channel.subscriber_count)).limit(limit)
            )

            if country:
                query = query.where(Channel.country == country)

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get top channels: {e}")
            raise

    async def get_top_channels_by_views(
        self, limit: int = 50, country: Optional[str] = None
    ) -> List[Channel]:
        """
        Get top channels by total view count

        Args:
            limit: Max results
            country: Filter by country code (optional)

        Returns:
            List of top channels by views
        """
        try:
            query = select(Channel).order_by(desc(Channel.view_count)).limit(limit)

            if country:
                query = query.where(Channel.country == country)

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get top channels by views: {e}")
            raise

    async def get_most_active_channels(
        self, days: int = 30, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get most active channels by upload frequency

        Args:
            days: Time period to analyze
            limit: Max results

        Returns:
            List of channels with video count
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            query = (
                select(Channel, func.count(Video.id).label("recent_videos"))
                .join(Video, Channel.id == Video.channel_id)
                .where(Video.published_at >= cutoff_date)
                .group_by(Channel.id)
                .order_by(desc("recent_videos"))
                .limit(limit)
            )

            result = await self.session.execute(query)

            channels_with_counts = []
            for row in result.all():
                channel = row[0]
                video_count = row[1]
                channels_with_counts.append(
                    {
                        "channel": channel,
                        "recent_videos": video_count,
                        "videos_per_day": round(video_count / days, 2),
                    }
                )

            return channels_with_counts
        except Exception as e:
            logger.error(f"❌ Failed to get most active channels: {e}")
            raise

    # ========================================================================
    # Channel Analytics
    # ========================================================================

    async def get_channel_statistics(self, channel_id: str) -> Dict[str, Any]:
        """
        Get comprehensive channel statistics

        Args:
            channel_id: YouTube channel ID

        Returns:
            Dictionary with channel stats
        """
        try:
            channel = await self.get_by_id(channel_id)

            if not channel:
                return {}

            # Get video statistics
            video_stats = await self.session.execute(
                select(
                    func.count(Video.id).label("total_videos"),
                    func.sum(Video.view_count).label("total_video_views"),
                    func.sum(Video.like_count).label("total_likes"),
                    func.sum(Video.comment_count).label("total_comments"),
                    func.avg(Video.view_count).label("avg_views_per_video"),
                    func.max(Video.view_count).label("most_viewed_video_views"),
                ).where(Video.channel_id == channel_id)
            )

            stats_row = video_stats.first()

            # Calculate engagement rate
            total_engagement = (stats_row.total_likes or 0) + (
                stats_row.total_comments or 0
            )
            total_views = stats_row.total_video_views or 1
            engagement_rate = (
                (total_engagement / total_views) * 100 if total_views > 0 else 0
            )

            return {
                "channel_id": channel_id,
                "channel_name": channel.name,
                "handle": channel.handle,
                "subscribers": channel.subscriber_count,
                "total_channel_views": channel.view_count,
                "total_videos": stats_row.total_videos or 0,
                "total_video_views": stats_row.total_video_views or 0,
                "total_likes": stats_row.total_likes or 0,
                "total_comments": stats_row.total_comments or 0,
                "avg_views_per_video": float(stats_row.avg_views_per_video or 0),
                "most_viewed_video_views": stats_row.most_viewed_video_views or 0,
                "engagement_rate": round(engagement_rate, 2),
                "is_verified": channel.is_verified,
                "country": channel.country,
            }
        except Exception as e:
            logger.error(f"❌ Failed to get channel statistics: {e}")
            raise

    async def get_channel_growth(
        self, channel_id: str, days: int = 30
    ) -> Dict[str, Any]:
        """
        Analyze channel growth over time period

        Args:
            channel_id: YouTube channel ID
            days: Analysis period

        Returns:
            Growth metrics
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            # Get videos published in period
            result = await self.session.execute(
                select(
                    func.count(Video.id).label("videos_uploaded"),
                    func.sum(Video.view_count).label("views_gained"),
                    func.sum(Video.like_count).label("likes_gained"),
                ).where(
                    and_(
                        Video.channel_id == channel_id,
                        Video.published_at >= cutoff_date,
                    )
                )
            )

            growth_row = result.first()

            return {
                "channel_id": channel_id,
                "period_days": days,
                "videos_uploaded": growth_row.videos_uploaded or 0,
                "views_gained": growth_row.views_gained or 0,
                "likes_gained": growth_row.likes_gained or 0,
                "upload_frequency": round((growth_row.videos_uploaded or 0) / days, 2),
                "avg_views_per_video": (
                    round(growth_row.views_gained / growth_row.videos_uploaded, 0)
                    if growth_row.videos_uploaded and growth_row.videos_uploaded > 0
                    else 0
                ),
            }
        except Exception as e:
            logger.error(f"❌ Failed to get channel growth: {e}")
            raise

    async def get_channel_performance_summary(self, channel_id: str) -> Dict[str, Any]:
        """
        Get comprehensive performance summary

        Args:
            channel_id: YouTube channel ID

        Returns:
            Performance summary with multiple metrics
        """
        try:
            stats = await self.get_channel_statistics(channel_id)
            growth_30d = await self.get_channel_growth(channel_id, days=30)
            growth_7d = await self.get_channel_growth(channel_id, days=7)

            return {
                "channel_info": {
                    "id": stats.get("channel_id"),
                    "name": stats.get("channel_name"),
                    "handle": stats.get("handle"),
                    "subscribers": stats.get("subscribers"),
                    "is_verified": stats.get("is_verified"),
                    "country": stats.get("country"),
                },
                "overall_stats": {
                    "total_videos": stats.get("total_videos"),
                    "total_views": stats.get("total_video_views"),
                    "avg_views_per_video": stats.get("avg_views_per_video"),
                    "engagement_rate": stats.get("engagement_rate"),
                },
                "recent_growth": {
                    "last_7_days": growth_7d,
                    "last_30_days": growth_30d,
                },
            }
        except Exception as e:
            logger.error(f"❌ Failed to get performance summary: {e}")
            raise

    # ========================================================================
    # Channel Comparison
    # ========================================================================

    async def compare_channels(self, channel_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Compare multiple channels side by side

        Args:
            channel_ids: List of channel IDs to compare

        Returns:
            List of channel statistics for comparison
        """
        try:
            comparisons = []

            for channel_id in channel_ids:
                stats = await self.get_channel_statistics(channel_id)
                if stats:
                    comparisons.append(stats)

            # Sort by subscribers
            comparisons.sort(key=lambda x: x.get("subscribers", 0), reverse=True)

            return comparisons
        except Exception as e:
            logger.error(f"❌ Failed to compare channels: {e}")
            raise

    # ========================================================================
    # Batch Operations
    # ========================================================================

    async def upsert_channel(self, channel_data: Dict[str, Any]) -> Channel:
        """
        Insert or update channel (upsert)

        Args:
            channel_data: Channel attributes dictionary

        Returns:
            Channel instance (created or updated)
        """
        try:
            channel_id = channel_data.get("id")
            existing_channel = await self.get_by_id(channel_id)

            if existing_channel:
                # Update existing channel
                channel_data["last_updated_at"] = datetime.utcnow()
                channel_data["scrape_count"] = existing_channel.scrape_count + 1
                updated_channel = await self.update(channel_id, **channel_data)
                logger.info(f"✅ Updated channel: {channel_id}")
                return updated_channel
            else:
                # Create new channel
                channel_data["first_scraped_at"] = datetime.utcnow()
                channel_data["last_updated_at"] = datetime.utcnow()
                channel_data["scrape_count"] = 1
                new_channel = await self.create(**channel_data)
                logger.info(f"✅ Created new channel: {channel_id}")
                return new_channel
        except Exception as e:
            logger.error(f"❌ Failed to upsert channel: {e}")
            raise

    async def bulk_upsert_channels(
        self, channels_data: List[Dict[str, Any]]
    ) -> tuple[int, int]:
        """
        Bulk insert or update channels

        Args:
            channels_data: List of channel attribute dictionaries

        Returns:
            Tuple of (created_count, updated_count)
        """
        try:
            created_count = 0
            updated_count = 0

            for channel_data in channels_data:
                channel_id = channel_data.get("id")
                existing = await self.exists(channel_id)

                if existing:
                    channel_data["last_updated_at"] = datetime.utcnow()
                    await self.update(channel_id, **channel_data)
                    updated_count += 1
                else:
                    channel_data["first_scraped_at"] = datetime.utcnow()
                    channel_data["last_updated_at"] = datetime.utcnow()
                    channel_data["scrape_count"] = 1
                    await self.create(**channel_data)
                    created_count += 1

            await self.session.commit()
            logger.info(
                f"✅ Bulk upsert complete: {created_count} created, {updated_count} updated"
            )
            return created_count, updated_count
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Failed to bulk upsert channels: {e}")
            raise

    # ========================================================================
    # Channel Status Management
    # ========================================================================

    async def activate_channel(self, channel_id: str) -> bool:
        """
        Activate channel for monitoring

        Args:
            channel_id: YouTube channel ID

        Returns:
            True if activated
        """
        try:
            await self.update(channel_id, is_active=True)
            logger.info(f"✅ Activated channel: {channel_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to activate channel: {e}")
            return False

    async def deactivate_channel(self, channel_id: str) -> bool:
        """
        Deactivate channel monitoring

        Args:
            channel_id: YouTube channel ID

        Returns:
            True if deactivated
        """
        try:
            await self.update(channel_id, is_active=False)
            logger.info(f"✅ Deactivated channel: {channel_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to deactivate channel: {e}")
            return False

    # ========================================================================
    # Filter & Search
    # ========================================================================

    async def filter_by_subscriber_range(
        self,
        min_subscribers: int,
        max_subscribers: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Channel]:
        """
        Filter channels by subscriber count range

        Args:
            min_subscribers: Minimum subscribers
            max_subscribers: Maximum subscribers (optional)
            skip: Pagination offset
            limit: Max results

        Returns:
            List of channels in range
        """
        try:
            query = select(Channel).where(Channel.subscriber_count >= min_subscribers)

            if max_subscribers is not None:
                query = query.where(Channel.subscriber_count <= max_subscribers)

            query = (
                query.order_by(desc(Channel.subscriber_count)).offset(skip).limit(limit)
            )

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to filter by subscriber range: {e}")
            raise

    async def get_channels_by_country(
        self, country: str, skip: int = 0, limit: int = 100
    ) -> List[Channel]:
        """
        Get channels by country

        Args:
            country: Country code (e.g., 'US', 'GB')
            skip: Pagination offset
            limit: Max results

        Returns:
            List of channels from country
        """
        try:
            result = await self.session.execute(
                select(Channel)
                .where(Channel.country == country)
                .order_by(desc(Channel.subscriber_count))
                .offset(skip)
                .limit(limit)
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get channels by country: {e}")
            raise


# ============================================================================
# Export
# ============================================================================

__all__ = ["ChannelRepository"]
