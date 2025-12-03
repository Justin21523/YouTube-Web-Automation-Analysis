# src/api/routers/analytics_router.py
"""
Analytics Router - Data analytics and insights API endpoints
"""

from fastapi import APIRouter, Query
from sqlalchemy import select, func, desc, extract
from typing import Optional, List
from datetime import datetime, timedelta
from pydantic import BaseModel

from src.app.database import db_manager
from src.app.models.video import Video
from src.app.models.channel import Channel
from src.app.models.comment import Comment
from src.app.models.caption import Caption

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


# ============================================================================
# Pydantic Schemas
# ============================================================================

class OverviewStats(BaseModel):
    total_videos: int
    total_channels: int
    total_comments: int
    total_captions: int
    total_views: int
    total_likes: int
    videos_this_week: int
    channels_this_week: int
    avg_views_per_video: float
    avg_likes_per_video: float
    avg_comments_per_video: float
    engagement_rate: float


class TimeSeriesPoint(BaseModel):
    date: str
    count: int
    views: Optional[int] = None
    likes: Optional[int] = None


class CategoryDistribution(BaseModel):
    category: str
    count: int
    percentage: float


class ViewDistribution(BaseModel):
    range: str
    count: int
    percentage: float


class TopItem(BaseModel):
    id: str
    title: str
    value: int
    thumbnail_url: Optional[str] = None
    channel_title: Optional[str] = None


class AnalyticsResponse(BaseModel):
    overview: OverviewStats
    scraping_activity: List[TimeSeriesPoint]
    category_distribution: List[CategoryDistribution]
    view_distribution: List[ViewDistribution]
    engagement_trend: List[TimeSeriesPoint]
    top_videos_by_views: List[TopItem]
    top_videos_by_likes: List[TopItem]
    top_channels: List[TopItem]


# ============================================================================
# Analytics Endpoints
# ============================================================================

@router.get("/overview", response_model=OverviewStats)
async def get_overview_stats():
    """
    Get overview statistics
    """
    async with db_manager.session() as session:
        # Video stats
        video_stats = await session.execute(
            select(
                func.count(Video.id).label("total"),
                func.coalesce(func.sum(Video.view_count), 0).label("views"),
                func.coalesce(func.sum(Video.like_count), 0).label("likes"),
                func.coalesce(func.sum(Video.comment_count), 0).label("comments"),
                func.coalesce(func.avg(Video.view_count), 0).label("avg_views"),
                func.coalesce(func.avg(Video.like_count), 0).label("avg_likes"),
                func.coalesce(func.avg(Video.comment_count), 0).label("avg_comments"),
            )
        )
        vs = video_stats.first()

        # Channel count
        channel_count = await session.execute(select(func.count(Channel.id)))
        total_channels = channel_count.scalar() or 0

        # Comment count (stored)
        comment_count = await session.execute(select(func.count(Comment.id)))
        total_comments = comment_count.scalar() or 0

        # Caption count
        caption_count = await session.execute(select(func.count(Caption.id)))
        total_captions = caption_count.scalar() or 0

        # This week counts
        week_ago = datetime.utcnow() - timedelta(days=7)

        videos_week = await session.execute(
            select(func.count(Video.id)).where(Video.created_at >= week_ago)
        )
        videos_this_week = videos_week.scalar() or 0

        channels_week = await session.execute(
            select(func.count(Channel.id)).where(Channel.created_at >= week_ago)
        )
        channels_this_week = channels_week.scalar() or 0

        # Calculate engagement rate
        total_views = vs.views or 1
        total_likes = vs.likes or 0
        engagement_rate = (total_likes / total_views) * 100 if total_views > 0 else 0

        return OverviewStats(
            total_videos=vs.total or 0,
            total_channels=total_channels,
            total_comments=total_comments,
            total_captions=total_captions,
            total_views=int(vs.views or 0),
            total_likes=int(vs.likes or 0),
            videos_this_week=videos_this_week,
            channels_this_week=channels_this_week,
            avg_views_per_video=round(float(vs.avg_views or 0), 2),
            avg_likes_per_video=round(float(vs.avg_likes or 0), 2),
            avg_comments_per_video=round(float(vs.avg_comments or 0), 2),
            engagement_rate=round(engagement_rate, 2),
        )


@router.get("/scraping-activity")
async def get_scraping_activity(
    days: int = Query(30, ge=1, le=365)
):
    """
    Get daily scraping activity for the specified period
    """
    async with db_manager.session() as session:
        start_date = datetime.utcnow() - timedelta(days=days)

        # Group by date
        result = await session.execute(
            select(
                func.date(Video.created_at).label("date"),
                func.count(Video.id).label("count"),
                func.coalesce(func.sum(Video.view_count), 0).label("views"),
                func.coalesce(func.sum(Video.like_count), 0).label("likes"),
            )
            .where(Video.created_at >= start_date)
            .group_by(func.date(Video.created_at))
            .order_by(func.date(Video.created_at))
        )

        rows = result.all()

        # Fill in missing dates with zeros
        activity = {}
        for row in rows:
            date_str = row.date.strftime("%Y-%m-%d") if hasattr(row.date, 'strftime') else str(row.date)
            activity[date_str] = TimeSeriesPoint(
                date=date_str,
                count=row.count,
                views=int(row.views),
                likes=int(row.likes),
            )

        # Generate all dates in range
        result_list = []
        current = start_date
        while current <= datetime.utcnow():
            date_str = current.strftime("%Y-%m-%d")
            if date_str in activity:
                result_list.append(activity[date_str])
            else:
                result_list.append(TimeSeriesPoint(date=date_str, count=0, views=0, likes=0))
            current += timedelta(days=1)

        return result_list


@router.get("/category-distribution")
async def get_category_distribution():
    """
    Get distribution of videos by category
    """
    async with db_manager.session() as session:
        result = await session.execute(
            select(
                func.coalesce(Video.category, 'Unknown').label("category"),
                func.count(Video.id).label("count"),
            )
            .group_by(func.coalesce(Video.category, 'Unknown'))
            .order_by(desc("count"))
        )

        rows = result.all()
        total = sum(row.count for row in rows)

        return [
            CategoryDistribution(
                category=row.category,
                count=row.count,
                percentage=round((row.count / total) * 100, 2) if total > 0 else 0,
            )
            for row in rows
        ]


@router.get("/view-distribution")
async def get_view_distribution():
    """
    Get distribution of videos by view count ranges
    """
    async with db_manager.session() as session:
        ranges = [
            ("0-1K", 0, 1000),
            ("1K-10K", 1000, 10000),
            ("10K-100K", 10000, 100000),
            ("100K-1M", 100000, 1000000),
            ("1M+", 1000000, None),
        ]

        total_result = await session.execute(select(func.count(Video.id)))
        total = total_result.scalar() or 1

        distribution = []
        for label, min_val, max_val in ranges:
            query = select(func.count(Video.id)).where(Video.view_count >= min_val)
            if max_val:
                query = query.where(Video.view_count < max_val)

            result = await session.execute(query)
            count = result.scalar() or 0

            distribution.append(ViewDistribution(
                range=label,
                count=count,
                percentage=round((count / total) * 100, 2),
            ))

        return distribution


@router.get("/engagement-trend")
async def get_engagement_trend(days: int = Query(30, ge=1, le=365)):
    """
    Get engagement metrics over time
    """
    async with db_manager.session() as session:
        start_date = datetime.utcnow() - timedelta(days=days)

        result = await session.execute(
            select(
                func.date(Video.created_at).label("date"),
                func.count(Video.id).label("count"),
                func.coalesce(func.sum(Video.like_count), 0).label("likes"),
            )
            .where(Video.created_at >= start_date)
            .group_by(func.date(Video.created_at))
            .order_by(func.date(Video.created_at))
        )

        return [
            TimeSeriesPoint(
                date=row.date.strftime("%Y-%m-%d") if hasattr(row.date, 'strftime') else str(row.date),
                count=row.count,
                likes=int(row.likes),
            )
            for row in result.all()
        ]


@router.get("/top-videos/views")
async def get_top_videos_by_views(limit: int = Query(10, ge=1, le=50)):
    """
    Get top videos by view count
    """
    async with db_manager.session() as session:
        result = await session.execute(
            select(Video)
            .where(Video.view_count.isnot(None))
            .order_by(desc(Video.view_count))
            .limit(limit)
        )

        return [
            TopItem(
                id=v.video_id,
                title=v.title or "Untitled",
                value=v.view_count or 0,
                thumbnail_url=v.thumbnail_url,
                channel_title=v.channel_title,
            )
            for v in result.scalars().all()
        ]


@router.get("/top-videos/likes")
async def get_top_videos_by_likes(limit: int = Query(10, ge=1, le=50)):
    """
    Get top videos by like count
    """
    async with db_manager.session() as session:
        result = await session.execute(
            select(Video)
            .where(Video.like_count.isnot(None))
            .order_by(desc(Video.like_count))
            .limit(limit)
        )

        return [
            TopItem(
                id=v.video_id,
                title=v.title or "Untitled",
                value=v.like_count or 0,
                thumbnail_url=v.thumbnail_url,
                channel_title=v.channel_title,
            )
            for v in result.scalars().all()
        ]


@router.get("/top-videos/engagement")
async def get_top_videos_by_engagement(limit: int = Query(10, ge=1, le=50)):
    """
    Get top videos by engagement rate (likes/views)
    """
    async with db_manager.session() as session:
        result = await session.execute(
            select(Video)
            .where(Video.view_count > 100)  # Min views threshold
            .order_by(desc(Video.like_count * 1.0 / Video.view_count))
            .limit(limit)
        )

        return [
            TopItem(
                id=v.video_id,
                title=v.title or "Untitled",
                value=round((v.like_count / v.view_count) * 100, 2) if v.view_count else 0,
                thumbnail_url=v.thumbnail_url,
                channel_title=v.channel_title,
            )
            for v in result.scalars().all()
        ]


@router.get("/top-channels")
async def get_top_channels(
    limit: int = Query(10, ge=1, le=50),
    by: str = Query("subscribers", regex="^(subscribers|videos|views)$")
):
    """
    Get top channels by specified metric
    """
    async with db_manager.session() as session:
        sort_field = {
            "subscribers": Channel.subscriber_count,
            "videos": Channel.video_count,
            "views": Channel.view_count,
        }.get(by, Channel.subscriber_count)

        result = await session.execute(
            select(Channel)
            .where(sort_field.isnot(None))
            .order_by(desc(sort_field))
            .limit(limit)
        )

        return [
            TopItem(
                id=c.channel_id,
                title=c.title or "Unknown",
                value=getattr(c, f"{by.rstrip('s')}_count", 0) or 0,
                thumbnail_url=c.thumbnail_url,
            )
            for c in result.scalars().all()
        ]


@router.get("/full", response_model=AnalyticsResponse)
async def get_full_analytics(days: int = Query(30, ge=1, le=365)):
    """
    Get comprehensive analytics data
    """
    overview = await get_overview_stats()
    scraping = await get_scraping_activity(days=days)
    categories = await get_category_distribution()
    views = await get_view_distribution()
    engagement = await get_engagement_trend(days=days)
    top_by_views = await get_top_videos_by_views(limit=5)
    top_by_likes = await get_top_videos_by_likes(limit=5)
    top_channels = await get_top_channels(limit=5)

    return AnalyticsResponse(
        overview=overview,
        scraping_activity=scraping,
        category_distribution=categories,
        view_distribution=views,
        engagement_trend=engagement,
        top_videos_by_views=top_by_views,
        top_videos_by_likes=top_by_likes,
        top_channels=top_channels,
    )


@router.get("/export")
async def export_analytics(
    format: str = Query("json", regex="^(json|csv)$"),
    days: int = Query(30, ge=1, le=365),
):
    """
    Export analytics data in specified format
    """
    data = await get_full_analytics(days=days)

    if format == "csv":
        # Return CSV format
        import io
        import csv

        output = io.StringIO()
        writer = csv.writer(output)

        # Overview section
        writer.writerow(["Metric", "Value"])
        writer.writerow(["Total Videos", data.overview.total_videos])
        writer.writerow(["Total Channels", data.overview.total_channels])
        writer.writerow(["Total Views", data.overview.total_views])
        writer.writerow(["Total Likes", data.overview.total_likes])
        writer.writerow(["Engagement Rate", f"{data.overview.engagement_rate}%"])
        writer.writerow([])

        # Activity section
        writer.writerow(["Date", "Videos Scraped", "Views", "Likes"])
        for point in data.scraping_activity:
            writer.writerow([point.date, point.count, point.views, point.likes])

        from fastapi.responses import StreamingResponse
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=analytics.csv"}
        )

    return data
