# src/api/routers/channel_router.py
"""
Channel Router - Channel management API endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, asc, or_
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

from src.app.database import db_manager
from src.app.models.channel import Channel
from src.app.models.video import Video

router = APIRouter(prefix="/api/v1/channels", tags=["Channels"])


# ============================================================================
# Pydantic Schemas
# ============================================================================

class ChannelResponse(BaseModel):
    id: int
    channel_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    custom_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    banner_url: Optional[str] = None
    subscriber_count: Optional[int] = None
    video_count: Optional[int] = None
    view_count: Optional[int] = None
    country: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    scraped_video_count: int = 0

    class Config:
        from_attributes = True


class ChannelListResponse(BaseModel):
    items: List[ChannelResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ChannelStatsResponse(BaseModel):
    total_channels: int
    total_subscribers: int
    total_videos: int
    channels_this_week: int
    avg_subscribers: float
    top_country: Optional[str] = None


# ============================================================================
# Channel List & Search
# ============================================================================

@router.get("", response_model=ChannelListResponse)
async def list_channels(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: str = Query("-subscriber_count"),
    search: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    min_subscribers: Optional[int] = Query(None),
):
    """
    Get paginated list of channels
    """
    async with db_manager.session() as session:
        query = select(Channel)
        count_query = select(func.count(Channel.id))

        # Apply filters
        if search:
            search_filter = or_(
                Channel.title.ilike(f"%{search}%"),
                Channel.description.ilike(f"%{search}%"),
                Channel.custom_url.ilike(f"%{search}%")
            )
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        if country:
            query = query.where(Channel.country == country)
            count_query = count_query.where(Channel.country == country)

        if min_subscribers:
            query = query.where(Channel.subscriber_count >= min_subscribers)
            count_query = count_query.where(Channel.subscriber_count >= min_subscribers)

        # Get total
        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0

        # Apply sorting
        sort_desc = sort.startswith("-")
        sort_field = sort.lstrip("-")

        sort_mapping = {
            "subscriber_count": Channel.subscriber_count,
            "video_count": Channel.video_count,
            "view_count": Channel.view_count,
            "title": Channel.title,
            "created_at": Channel.created_at,
        }

        sort_column = sort_mapping.get(sort_field, Channel.subscriber_count)
        if sort_desc:
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(asc(sort_column))

        # Pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        result = await session.execute(query)
        channels = result.scalars().all()

        total_pages = (total + page_size - 1) // page_size

        # Get scraped video counts
        items = []
        for channel in channels:
            video_count_result = await session.execute(
                select(func.count(Video.id)).where(Video.channel_id == channel.channel_id)
            )
            scraped_count = video_count_result.scalar() or 0

            items.append(ChannelResponse(
                id=channel.id,
                channel_id=channel.channel_id,
                title=channel.title,
                description=channel.description,
                custom_url=channel.custom_url,
                thumbnail_url=channel.thumbnail_url,
                banner_url=channel.banner_url,
                subscriber_count=channel.subscriber_count,
                video_count=channel.video_count,
                view_count=channel.view_count,
                country=channel.country,
                created_at=channel.created_at,
                updated_at=channel.updated_at,
                scraped_video_count=scraped_count,
            ))

        return ChannelListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )


@router.get("/stats", response_model=ChannelStatsResponse)
async def get_channel_stats():
    """
    Get aggregate statistics for channels
    """
    async with db_manager.session() as session:
        stats_result = await session.execute(
            select(
                func.count(Channel.id).label("total"),
                func.coalesce(func.sum(Channel.subscriber_count), 0).label("total_subs"),
                func.coalesce(func.sum(Channel.video_count), 0).label("total_videos"),
                func.coalesce(func.avg(Channel.subscriber_count), 0).label("avg_subs"),
            )
        )
        stats = stats_result.first()

        # Get most common country
        country_result = await session.execute(
            select(Channel.country, func.count(Channel.id).label("count"))
            .where(Channel.country.isnot(None))
            .group_by(Channel.country)
            .order_by(desc("count"))
            .limit(1)
        )
        top_country_row = country_result.first()
        top_country = top_country_row[0] if top_country_row else None

        # Channels this week
        from datetime import timedelta
        week_ago = datetime.utcnow() - timedelta(days=7)
        week_result = await session.execute(
            select(func.count(Channel.id)).where(Channel.created_at >= week_ago)
        )
        channels_this_week = week_result.scalar() or 0

        return ChannelStatsResponse(
            total_channels=stats.total or 0,
            total_subscribers=int(stats.total_subs or 0),
            total_videos=int(stats.total_videos or 0),
            channels_this_week=channels_this_week,
            avg_subscribers=float(stats.avg_subs or 0),
            top_country=top_country,
        )


@router.get("/{channel_id}", response_model=ChannelResponse)
async def get_channel(channel_id: str):
    """
    Get a single channel by ID
    """
    async with db_manager.session() as session:
        result = await session.execute(
            select(Channel).where(
                or_(
                    Channel.channel_id == channel_id,
                    Channel.id == int(channel_id) if channel_id.isdigit() else -1
                )
            )
        )
        channel = result.scalar_one_or_none()

        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")

        # Get scraped video count
        video_count_result = await session.execute(
            select(func.count(Video.id)).where(Video.channel_id == channel.channel_id)
        )
        scraped_count = video_count_result.scalar() or 0

        return ChannelResponse(
            id=channel.id,
            channel_id=channel.channel_id,
            title=channel.title,
            description=channel.description,
            custom_url=channel.custom_url,
            thumbnail_url=channel.thumbnail_url,
            banner_url=channel.banner_url,
            subscriber_count=channel.subscriber_count,
            video_count=channel.video_count,
            view_count=channel.view_count,
            country=channel.country,
            created_at=channel.created_at,
            updated_at=channel.updated_at,
            scraped_video_count=scraped_count,
        )


@router.delete("/{channel_id}")
async def delete_channel(channel_id: str, delete_videos: bool = Query(False)):
    """
    Delete a channel (optionally with all its videos)
    """
    async with db_manager.session() as session:
        result = await session.execute(
            select(Channel).where(Channel.channel_id == channel_id)
        )
        channel = result.scalar_one_or_none()

        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")

        deleted_videos = 0
        if delete_videos:
            # Delete all videos from this channel
            video_result = await session.execute(
                select(Video).where(Video.channel_id == channel_id)
            )
            videos = video_result.scalars().all()
            for video in videos:
                await session.delete(video)
                deleted_videos += 1

        await session.delete(channel)
        await session.commit()

        return {
            "message": "Channel deleted successfully",
            "channel_id": channel_id,
            "videos_deleted": deleted_videos
        }


@router.get("/top/subscribers")
async def get_top_channels_by_subscribers(limit: int = Query(10, ge=1, le=50)):
    """
    Get top channels by subscriber count
    """
    response = await list_channels(page=1, page_size=limit, sort="-subscriber_count")
    return response.items


@router.get("/top/videos")
async def get_top_channels_by_videos(limit: int = Query(10, ge=1, le=50)):
    """
    Get top channels by video count
    """
    response = await list_channels(page=1, page_size=limit, sort="-video_count")
    return response.items
