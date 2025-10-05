# src/infrastructure/repositories/analytics_repository.py
"""
Analytics Repository
Handles time-series data for video performance tracking
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import select, func, and_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]  # project root
sys.path.append(str(ROOT_DIR))

from src.infrastructure.repositories.base import BaseRepository
from src.app.models import VideoAnalytics, Video, Channel, VideoStatus

logger = logging.getLogger(__name__)


async def _ensure_demo_video(
    session, *, video_id: str, channel_id: str = "demo-channel"
) -> None:
    # Ensure Channel exists
    ch = await session.get(Channel, channel_id)
    if ch is None:
        ch = Channel(
            id=channel_id,
            # Channel fields (Channel has 'name', not 'title')
            name="Demo Channel",
            handle="demo",
            custom_url="demo",
            country=None,
            description=None,
            published_at=datetime.utcnow(),
            # optional flags/metrics with safe defaults
            subscriber_count=0,
            video_count=0,
            view_count=0,
            is_verified=False,
            is_active=True,
        )
        session.add(ch)
    # Ensure Video exists
    v = await session.get(Video, video_id)
    if v is None:
        v = Video(
            id=video_id,
            channel_id=channel_id,
            title="Demo Video",
            description=None,
            published_at=datetime.utcnow(),  # NOT NULL on your model
            duration_seconds=0,
            view_count=0,
            like_count=0,
            comment_count=0,
            category_id=None,
            # IMPORTANT: use the Enum, not a raw string
            status=VideoStatus.PENDING,
            has_transcript=False,
            transcript_language=None,
        )
        session.add(v)

    # Flush to guarantee PKs exist before inserting analytics rows
    await session.flush()


# MINIMAL HELPERS (for type-safe numeric/datetime normalization)
# These avoid Pylance "ColumnElement" complaints while keeping runtime logic.
# ---------------------------------------------------------------------------
def _as_int(value: Any) -> int:
    try:
        return int(value) if value is not None else 0
    except Exception:
        return 0


def _as_float(value: Any) -> float:
    try:
        return float(value) if value is not None else 0.0
    except Exception:
        return 0.0


class AnalyticsRepository(BaseRepository[VideoAnalytics]):
    """
    Repository for VideoAnalytics operations
    Provides time-series queries and growth tracking
    """

    def __init__(self, session: AsyncSession):
        """Initialize analytics repository"""
        super().__init__(session, VideoAnalytics)

    # ========================================================================
    # Snapshot Creation & Management
    # ========================================================================

    async def create_snapshot(
        self, video_id: str, metrics: Dict[str, Any]
    ) -> VideoAnalytics:
        """
        Create analytics snapshot for a video

        Args:
            video_id: YouTube video ID
            metrics: Dictionary with metric values

        Returns:
            Created analytics snapshot
        """
        try:
            snapshot_data = {
                "video_id": video_id,
                "scraped_at": datetime.utcnow(),
                **metrics,
            }

            snapshot = await self.create(**snapshot_data)
            logger.info(f"✅ Created analytics snapshot for video: {video_id}")
            return snapshot
        except Exception as e:
            logger.error(f"❌ Failed to create snapshot: {e}")
            raise

    async def create_snapshot_from_video(
        self, video_id: str
    ) -> Optional[VideoAnalytics]:
        """
        Create snapshot using current video metrics

        Args:
            video_id: YouTube video ID

        Returns:
            Created snapshot or None if video not found
        """
        try:
            # Get video
            video_result = await self.session.execute(
                select(Video).where(Video.id == video_id)
            )
            video = video_result.scalar_one_or_none()

            if not video:
                logger.warning(f"⚠️ Video not found: {video_id}")
                return None

            # Normalize current metrics to plain numbers for safe math
            v_views = _as_int(getattr(video, "view_count", 0))
            v_likes = _as_int(getattr(video, "like_count", 0))
            v_comments = _as_int(getattr(video, "comment_count", 0))

            # Get previous snapshot for growth calculation
            previous = await self.get_latest_snapshot(video_id)

            # Calculate growth deltas
            view_growth = 0
            like_growth = 0
            comment_growth = 0
            if previous:
                p_views = _as_int(getattr(previous, "view_count", 0))
                p_likes = _as_int(getattr(previous, "like_count", 0))
                p_comments = _as_int(getattr(previous, "comment_count", 0))
                view_growth = v_views - p_views
                like_growth = v_likes - p_likes
                comment_growth = v_comments - p_comments

            # Calculate engagement rate
            engagement_rate = 0.0
            if v_views > 0:
                engagement_rate = ((v_likes + v_comments) / float(v_views)) * 100.0

            # Calculate views per hour since publish
            views_per_hour = 0.0
            published_at = getattr(video, "published_at", None)
            if published_at is not None:
                hours_since_publish = (
                    datetime.utcnow() - published_at
                ).total_seconds() / 3600.0
                if hours_since_publish > 0:
                    views_per_hour = v_views / hours_since_publish

            # Create snapshot
            snapshot = await self.create(
                video_id=video_id,
                scraped_at=datetime.utcnow(),
                view_count=video.view_count,
                like_count=video.like_count,
                comment_count=video.comment_count,
                views_per_hour=views_per_hour,
                engagement_rate=engagement_rate,
                view_growth=view_growth,
                like_growth=like_growth,
                comment_growth=comment_growth,
            )

            logger.info(f"✅ Created snapshot from video: {video_id}")
            return snapshot
        except Exception as e:
            logger.error(f"❌ Failed to create snapshot from video: {e}")
            raise

    # ========================================================================
    # Snapshot Retrieval
    # ========================================================================

    async def get_by_video(
        self, video_id: str, skip: int = 0, limit: int = 100
    ) -> List[VideoAnalytics]:
        """
        Get all snapshots for a video

        Args:
            video_id: YouTube video ID
            skip: Pagination offset
            limit: Max results

        Returns:
            List of analytics snapshots
        """
        try:
            result = await self.session.execute(
                select(VideoAnalytics)
                .where(VideoAnalytics.video_id == video_id)
                .order_by(desc(VideoAnalytics.scraped_at))
                .offset(skip)
                .limit(limit)
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get analytics by video: {e}")
            raise

    async def get_latest_snapshot(self, video_id: str) -> Optional[VideoAnalytics]:
        """
        Get most recent snapshot for a video

        Args:
            video_id: YouTube video ID

        Returns:
            Latest snapshot or None
        """
        try:
            result = await self.session.execute(
                select(VideoAnalytics)
                .where(VideoAnalytics.video_id == video_id)
                .order_by(desc(VideoAnalytics.scraped_at))
                .limit(1)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"❌ Failed to get latest snapshot: {e}")
            raise

    async def get_snapshots_in_range(
        self, video_id: str, start_date: datetime, end_date: datetime
    ) -> List[VideoAnalytics]:
        """
        Get snapshots within date range

        Args:
            video_id: YouTube video ID
            start_date: Start of range
            end_date: End of range

        Returns:
            List of snapshots in range
        """
        try:
            result = await self.session.execute(
                select(VideoAnalytics)
                .where(
                    and_(
                        VideoAnalytics.video_id == video_id,
                        VideoAnalytics.scraped_at >= start_date,
                        VideoAnalytics.scraped_at <= end_date,
                    )
                )
                .order_by(asc(VideoAnalytics.scraped_at))
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get snapshots in range: {e}")
            raise

    # ========================================================================
    # Growth Tracking
    # ========================================================================

    async def get_growth_trend(
        self, video_id: str, days: int = 30
    ) -> List[VideoAnalytics]:
        """
        Get growth trend over time period

        Args:
            video_id: YouTube video ID
            days: Number of days to analyze

        Returns:
            List of snapshots showing growth
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            result = await self.session.execute(
                select(VideoAnalytics)
                .where(
                    and_(
                        VideoAnalytics.video_id == video_id,
                        VideoAnalytics.scraped_at >= cutoff_date,
                    )
                )
                .order_by(asc(VideoAnalytics.scraped_at))
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get growth trend: {e}")
            raise

    async def calculate_growth_rate(
        self, video_id: str, days: int = 7
    ) -> Dict[str, Any]:
        """
        Calculate growth rate over period

        Args:
            video_id: YouTube video ID
            days: Period to calculate growth

        Returns:
            Growth rate metrics
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            # Get first and last snapshots in period
            result = await self.session.execute(
                select(VideoAnalytics)
                .where(
                    and_(
                        VideoAnalytics.video_id == video_id,
                        VideoAnalytics.scraped_at >= cutoff_date,
                    )
                )
                .order_by(asc(VideoAnalytics.scraped_at))
            )

            snapshots = list(result.scalars().all())

            if len(snapshots) < 2:
                return {
                    "video_id": video_id,
                    "period_days": days,
                    "insufficient_data": True,
                }

            first_snapshot = snapshots[0]
            last_snapshot = snapshots[-1]

            # Normalize numeric fields
            f_views = _as_int(getattr(first_snapshot, "view_count", 0))
            f_likes = _as_int(getattr(first_snapshot, "like_count", 0))
            f_comments = _as_int(getattr(first_snapshot, "comment_count", 0))
            l_views = _as_int(getattr(last_snapshot, "view_count", 0))
            l_likes = _as_int(getattr(last_snapshot, "like_count", 0))
            l_comments = _as_int(getattr(last_snapshot, "comment_count", 0))

            # Calculate absolute growth
            view_growth = l_views - f_views
            like_growth = l_likes - f_likes
            comment_growth = l_comments - f_comments

            # Calculate percentage growth (use float math)
            view_growth_pct = 0.0
            like_growth_pct = 0.0
            comment_growth_pct = 0.0
            if f_views > 0:
                view_growth_pct = (view_growth / float(f_views)) * 100.0
            if f_likes > 0:
                like_growth_pct = (like_growth / float(f_likes)) * 100.0
            if f_comments > 0:
                comment_growth_pct = (comment_growth / float(f_comments)) * 100.0

            # Calculate daily averages
            days_elapsed = (last_snapshot.scraped_at - first_snapshot.scraped_at).days
            days_elapsed = max(days_elapsed, 1)  # Avoid division by zero

            return {
                "video_id": video_id,
                "period_days": days,
                "snapshots_analyzed": len(snapshots),
                "start_date": first_snapshot.scraped_at.isoformat(),
                "end_date": last_snapshot.scraped_at.isoformat(),
                "view_growth": view_growth,
                "view_growth_percentage": round(view_growth_pct, 2),
                "views_per_day": round(view_growth / days_elapsed, 2),
                "like_growth": like_growth,
                "like_growth_percentage": round(like_growth_pct, 2),
                "likes_per_day": round(like_growth / days_elapsed, 2),
                "comment_growth": comment_growth,
                "comment_growth_percentage": round(comment_growth_pct, 2),
                "comments_per_day": round(comment_growth / days_elapsed, 2),
            }
        except Exception as e:
            logger.error(f"❌ Failed to calculate growth rate: {e}")
            raise

    async def get_peak_performance(self, video_id: str) -> Dict[str, Any]:
        """
        Get peak performance metrics

        Args:
            video_id: YouTube video ID

        Returns:
            Peak metrics and when they occurred
        """
        try:
            # Get snapshot with highest view growth
            max_view_growth = await self.session.execute(
                select(VideoAnalytics)
                .where(VideoAnalytics.video_id == video_id)
                .order_by(desc(VideoAnalytics.view_growth))
                .limit(1)
            )
            peak_views = max_view_growth.scalar_one_or_none()

            # Get snapshot with highest engagement rate
            max_engagement = await self.session.execute(
                select(VideoAnalytics)
                .where(VideoAnalytics.video_id == video_id)
                .order_by(desc(VideoAnalytics.engagement_rate))
                .limit(1)
            )
            peak_engagement = max_engagement.scalar_one_or_none()

            # Get snapshot with highest views per hour
            max_velocity = await self.session.execute(
                select(VideoAnalytics)
                .where(VideoAnalytics.video_id == video_id)
                .order_by(desc(VideoAnalytics.views_per_hour))
                .limit(1)
            )
            peak_velocity = max_velocity.scalar_one_or_none()

            return {
                "video_id": video_id,
                "peak_view_growth": {
                    "views": peak_views.view_growth if peak_views else 0,
                    "date": peak_views.scraped_at.isoformat() if peak_views else None,
                },
                "peak_engagement": {
                    "rate": peak_engagement.engagement_rate if peak_engagement else 0,
                    "date": (
                        peak_engagement.scraped_at.isoformat()
                        if peak_engagement
                        else None
                    ),
                },
                "peak_velocity": {
                    "views_per_hour": (
                        peak_velocity.views_per_hour if peak_velocity else 0
                    ),
                    "date": (
                        peak_velocity.scraped_at.isoformat() if peak_velocity else None
                    ),
                },
            }
        except Exception as e:
            logger.error(f"❌ Failed to get peak performance: {e}")
            raise

    # ========================================================================
    # Comparative Analysis
    # ========================================================================

    async def compare_videos_performance(
        self, video_ids: List[str], days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Compare performance of multiple videos

        Args:
            video_ids: List of video IDs to compare
            days: Period to analyze

        Returns:
            List of performance comparisons
        """
        try:
            comparisons = []

            for video_id in video_ids:
                growth = await self.calculate_growth_rate(video_id, days)
                latest = await self.get_latest_snapshot(video_id)

                if latest:
                    comparisons.append(
                        {
                            "video_id": video_id,
                            "current_views": latest.view_count,
                            "current_engagement_rate": latest.engagement_rate,
                            "view_growth": growth.get("view_growth", 0),
                            "views_per_day": growth.get("views_per_day", 0),
                            "growth_percentage": growth.get(
                                "view_growth_percentage", 0
                            ),
                        }
                    )

            # Sort by current views
            comparisons.sort(key=lambda x: x["current_views"], reverse=True)

            return comparisons
        except Exception as e:
            logger.error(f"❌ Failed to compare videos: {e}")
            raise

    # ========================================================================
    # Statistical Analysis
    # ========================================================================

    async def get_average_metrics(
        self, video_id: str, days: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get average metrics over period

        Args:
            video_id: YouTube video ID
            days: Period to analyze (None = all time)

        Returns:
            Average metrics
        """
        try:
            query = select(
                func.avg(VideoAnalytics.view_count).label("avg_views"),
                func.avg(VideoAnalytics.like_count).label("avg_likes"),
                func.avg(VideoAnalytics.comment_count).label("avg_comments"),
                func.avg(VideoAnalytics.engagement_rate).label("avg_engagement"),
                func.avg(VideoAnalytics.views_per_hour).label("avg_velocity"),
            ).where(VideoAnalytics.video_id == video_id)

            if days:
                cutoff_date = datetime.utcnow() - timedelta(days=days)
                query = query.where(VideoAnalytics.scraped_at >= cutoff_date)

            result = await self.session.execute(query)
            row = result.first()

            if not row:
                # No data yet; return zeros
                return {
                    "video_id": video_id,
                    "period_days": days,
                    "avg_views": 0.0,
                    "avg_likes": 0.0,
                    "avg_comments": 0.0,
                    "avg_engagement_rate": 0.0,
                    "avg_views_per_hour": 0.0,
                }

            m = row._mapping  # safer for static typing
            return {
                "video_id": video_id,
                "period_days": days,
                "avg_views": float(m.get("avg_views") or 0.0),
                "avg_likes": float(m.get("avg_likes") or 0.0),
                "avg_comments": float(m.get("avg_comments") or 0.0),
                "avg_engagement_rate": float(m.get("avg_engagement") or 0.0),
                "avg_views_per_hour": float(m.get("avg_velocity") or 0.0),
            }

        except Exception as e:
            logger.error(f"❌ Failed to get average metrics: {e}")
            raise

    async def get_performance_forecast(
        self, video_id: str, forecast_days: int = 7
    ) -> Dict[str, Any]:
        """
        Simple linear forecast based on recent trend

        Args:
            video_id: YouTube video ID
            forecast_days: Days to forecast ahead

        Returns:
            Forecasted metrics
        """
        try:
            # Get recent growth rate (last 7 days)
            growth = await self.calculate_growth_rate(video_id, days=7)

            if growth.get("insufficient_data"):
                return {
                    "video_id": video_id,
                    "forecast_days": forecast_days,
                    "insufficient_data": True,
                }

            # Get latest snapshot
            latest = await self.get_latest_snapshot(video_id)

            if not latest:
                return {
                    "video_id": video_id,
                    "forecast_days": forecast_days,
                    "no_data": True,
                }

            # Simple linear projection
            views_per_day = growth.get("views_per_day", 0)
            likes_per_day = growth.get("likes_per_day", 0)
            comments_per_day = growth.get("comments_per_day", 0)

            forecasted_views = latest.view_count + (views_per_day * forecast_days)
            forecasted_likes = latest.like_count + (likes_per_day * forecast_days)
            forecasted_comments = latest.comment_count + (
                comments_per_day * forecast_days
            )

            return {
                "video_id": video_id,
                "forecast_date": (
                    datetime.utcnow() + timedelta(days=forecast_days)
                ).isoformat(),
                "current_views": latest.view_count,
                "forecasted_views": int(forecasted_views),
                "forecasted_view_gain": int(views_per_day * forecast_days),
                "current_likes": latest.like_count,
                "forecasted_likes": int(forecasted_likes),
                "current_comments": latest.comment_count,
                "forecasted_comments": int(forecasted_comments),
                "confidence": "low",  # Simple linear model = low confidence
                "based_on_days": 7,
            }
        except Exception as e:
            logger.error(f"❌ Failed to forecast performance: {e}")
            raise

    # ========================================================================
    # Time-Series Data Export
    # ========================================================================

    async def get_timeseries_data(
        self, video_id: str, metrics: List[str], days: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get time-series data for charting

        Args:
            video_id: YouTube video ID
            metrics: List of metric names to include
            days: Period to retrieve (None = all)

        Returns:
            Time-series data ready for visualization
        """
        try:
            query = select(VideoAnalytics).where(VideoAnalytics.video_id == video_id)

            if days:
                cutoff_date = datetime.utcnow() - timedelta(days=days)
                query = query.where(VideoAnalytics.scraped_at >= cutoff_date)

            query = query.order_by(asc(VideoAnalytics.scraped_at))

            result = await self.session.execute(query)
            snapshots = list(result.scalars().all())

            # Build time-series data
            timestamps = []
            data = {metric: [] for metric in metrics}

            for snapshot in snapshots:
                timestamps.append(snapshot.scraped_at.isoformat())

                for metric in metrics:
                    value = getattr(snapshot, metric, 0)
                    data[metric].append(value)

            return {
                "video_id": video_id,
                "timestamps": timestamps,
                "data": data,
                "data_points": len(timestamps),
            }
        except Exception as e:
            logger.error(f"❌ Failed to get timeseries data: {e}")
            raise

    # ========================================================================
    # Cleanup Operations
    # ========================================================================

    async def delete_old_snapshots(self, days: int = 90) -> int:
        """
        Delete snapshots older than specified days

        Args:
            days: Age threshold in days

        Returns:
            Number of snapshots deleted
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            # Get IDs to delete
            result = await self.session.execute(
                select(VideoAnalytics.id).where(VideoAnalytics.scraped_at < cutoff_date)
            )

            ids_to_delete = [row[0] for row in result.all()]

            if ids_to_delete:
                deleted_count = await self.delete_many(ids_to_delete)
                logger.info(f"✅ Deleted {deleted_count} old snapshots (>{days} days)")
                return deleted_count

            return 0
        except Exception as e:
            logger.error(f"❌ Failed to delete old snapshots: {e}")
            raise

    async def get_snapshot_count(self, video_id: Optional[str] = None) -> int:
        """
        Get total snapshot count

        Args:
            video_id: Filter by video (optional)

        Returns:
            Snapshot count
        """
        try:
            if video_id:
                return await self.count(video_id=video_id)
            else:
                return await self.count()
        except Exception as e:
            logger.error(f"❌ Failed to get snapshot count: {e}")
            raise


# ============================================================================
# Export
# ============================================================================

__all__ = ["AnalyticsRepository"]

# ============================================================================
# Local demo / smoke test
# ============================================================================

if __name__ == "__main__":
    """
    Minimal async smoke test for AnalyticsRepository.

    Usage (from repo root):
        python -m src.infrastructure.repositories.analytics_repository
    """
    import asyncio
    import logging
    from src.infrastructure.database.connection import db_manager

    logging.basicConfig(level=logging.INFO)

    async def _run_demo() -> None:
        video_id = (
            "VIDEO_DEMO_001"  # <-- replace with a real ID in your DB if available
        )

        async with db_manager.session() as session:
            repo = AnalyticsRepository(session)

            # 1) Create a dummy snapshot (0s) just to exercise the write path.
            #    If you already have snapshots, you can comment this out.
            # Ensure FK parents exist
            await _ensure_demo_video(session, video_id=video_id)

            try:
                await repo.create_snapshot(
                    video_id=video_id,
                    metrics={
                        "view_count": 0,
                        "like_count": 0,
                        "comment_count": 0,
                        "views_per_hour": 0.0,
                        "engagement_rate": 0.0,
                        "view_growth": 0,
                        "like_growth": 0,
                        "comment_growth": 0,
                    },
                )
                print("✅ created initial snapshot")
            except Exception as e:
                print(
                    f"⚠️ skipped create_snapshot (likely duplicate/missing video): {e}"
                )

            # 2) Calculate growth rate over the default period
            try:
                rates = await repo.calculate_growth_rate(video_id, days=30)
                print("📈 growth rates:", rates)
            except Exception as e:
                print(f"❌ calculate_growth_rate failed: {e}")

            # 3) Pull average metrics over the same window
            try:
                avg = await repo.get_average_metrics(video_id, days=30)
                print("📊 average metrics:", avg)
            except Exception as e:
                print(f"❌ get_average_metrics failed: {e}")

            # 4) Count snapshots (optionally filtered by video)
            try:
                total = await repo.get_snapshot_count(video_id=video_id)
                print(f"🧮 snapshot count (video): {total}")
            except Exception as e:
                print(f"❌ get_snapshot_count failed: {e}")

    asyncio.run(_run_demo())
