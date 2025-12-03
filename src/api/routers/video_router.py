# src/api/routers/video_router.py
"""
Video Router - Video management API endpoints
Provides CRUD operations and search for videos
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, asc, or_
from typing import Optional, List
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

from src.app.database import db_manager
from src.app.models.video import Video
from src.app.models.channel import Channel
from src.app.models.comment import Comment
from src.app.models.caption import Caption

router = APIRouter(prefix="/api/v1/videos", tags=["Videos"])


# ============================================================================
# Pydantic Schemas
# ============================================================================

class VideoBase(BaseModel):
    video_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    channel_id: Optional[str] = None
    channel_title: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    published_at: Optional[datetime] = None
    tags: Optional[List[str]] = None
    category: Optional[str] = None


class VideoResponse(VideoBase):
    id: int
    scraped_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    has_captions: bool = False
    has_comments: bool = False

    class Config:
        from_attributes = True


class VideoListResponse(BaseModel):
    items: List[VideoResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class VideoDetailResponse(VideoResponse):
    channel: Optional[dict] = None
    caption_count: int = 0
    stored_comment_count: int = 0


class CommentResponse(BaseModel):
    id: int
    comment_id: str
    author: Optional[str] = None
    author_channel_id: Optional[str] = None
    text: Optional[str] = None
    like_count: Optional[int] = 0
    reply_count: Optional[int] = 0
    published_at: Optional[datetime] = None
    is_reply: bool = False

    class Config:
        from_attributes = True


class CommentListResponse(BaseModel):
    items: List[CommentResponse]
    total: int
    page: int
    page_size: int


class VideoStatsResponse(BaseModel):
    total_videos: int
    total_views: int
    total_likes: int
    total_comments: int
    videos_this_week: int
    avg_views: float
    avg_likes: float
    avg_engagement_rate: float


# ============================================================================
# Video List & Search Endpoints
# ============================================================================

@router.get("", response_model=VideoListResponse)
async def list_videos(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort: str = Query("-scraped_at", description="Sort field (prefix with - for desc)"),
    search: Optional[str] = Query(None, description="Search in title and description"),
    channel_id: Optional[str] = Query(None, description="Filter by channel ID"),
    min_views: Optional[int] = Query(None, description="Minimum view count"),
    max_views: Optional[int] = Query(None, description="Maximum view count"),
    has_captions: Optional[bool] = Query(None, description="Filter by caption availability"),
    from_date: Optional[datetime] = Query(None, description="Published after this date"),
    to_date: Optional[datetime] = Query(None, description="Published before this date"),
):
    """
    Get paginated list of videos with filtering and sorting
    """
    async with db_manager.session() as session:
        # Base query
        query = select(Video)
        count_query = select(func.count(Video.id))

        # Apply filters
        filters = []

        if search:
            search_filter = or_(
                Video.title.ilike(f"%{search}%"),
                Video.description.ilike(f"%{search}%"),
                Video.channel_title.ilike(f"%{search}%")
            )
            filters.append(search_filter)

        if channel_id:
            filters.append(Video.channel_id == channel_id)

        if min_views is not None:
            filters.append(Video.view_count >= min_views)

        if max_views is not None:
            filters.append(Video.view_count <= max_views)

        if from_date:
            filters.append(Video.published_at >= from_date)

        if to_date:
            filters.append(Video.published_at <= to_date)

        # Apply all filters
        for f in filters:
            query = query.where(f)
            count_query = count_query.where(f)

        # Get total count
        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0

        # Apply sorting
        sort_desc = sort.startswith("-")
        sort_field = sort.lstrip("-")

        sort_mapping = {
            "scraped_at": Video.scraped_at,
            "published_at": Video.published_at,
            "view_count": Video.view_count,
            "like_count": Video.like_count,
            "comment_count": Video.comment_count,
            "title": Video.title,
            "created_at": Video.created_at,
        }

        sort_column = sort_mapping.get(sort_field, Video.scraped_at)
        if sort_desc:
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(asc(sort_column))

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        # Execute query
        result = await session.execute(query)
        videos = result.scalars().all()

        # Calculate total pages
        total_pages = (total + page_size - 1) // page_size

        # Convert to response
        items = []
        for video in videos:
            item = VideoResponse(
                id=video.id,
                video_id=video.video_id,
                title=video.title,
                description=video.description,
                channel_id=video.channel_id,
                channel_title=video.channel_title,
                thumbnail_url=video.thumbnail_url,
                duration_seconds=video.duration_seconds,
                view_count=video.view_count,
                like_count=video.like_count,
                comment_count=video.comment_count,
                published_at=video.published_at,
                tags=video.tags if hasattr(video, 'tags') else None,
                category=video.category if hasattr(video, 'category') else None,
                scraped_at=video.scraped_at if hasattr(video, 'scraped_at') else video.created_at,
                updated_at=video.updated_at,
                has_captions=False,  # Will be updated if needed
                has_comments=False,
            )
            items.append(item)

        return VideoListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )


@router.get("/search")
async def search_videos(
    q: str = Query(..., min_length=1, description="Search query"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    Search videos by title, description, or channel
    """
    return await list_videos(
        page=page,
        page_size=page_size,
        search=q,
        sort="-view_count"
    )


@router.get("/stats", response_model=VideoStatsResponse)
async def get_video_stats():
    """
    Get aggregate statistics for all videos
    """
    async with db_manager.session() as session:
        # Total counts
        total_result = await session.execute(
            select(
                func.count(Video.id).label("total_videos"),
                func.coalesce(func.sum(Video.view_count), 0).label("total_views"),
                func.coalesce(func.sum(Video.like_count), 0).label("total_likes"),
                func.coalesce(func.sum(Video.comment_count), 0).label("total_comments"),
                func.coalesce(func.avg(Video.view_count), 0).label("avg_views"),
                func.coalesce(func.avg(Video.like_count), 0).label("avg_likes"),
            )
        )
        stats = total_result.first()

        # Videos this week
        week_ago = datetime.utcnow() - timedelta(days=7)
        week_result = await session.execute(
            select(func.count(Video.id)).where(Video.created_at >= week_ago)
        )
        videos_this_week = week_result.scalar() or 0

        # Calculate engagement rate
        total_views = stats.total_views or 1
        total_likes = stats.total_likes or 0
        engagement_rate = (total_likes / total_views) * 100 if total_views > 0 else 0

        return VideoStatsResponse(
            total_videos=stats.total_videos or 0,
            total_views=int(stats.total_views or 0),
            total_likes=int(stats.total_likes or 0),
            total_comments=int(stats.total_comments or 0),
            videos_this_week=videos_this_week,
            avg_views=float(stats.avg_views or 0),
            avg_likes=float(stats.avg_likes or 0),
            avg_engagement_rate=round(engagement_rate, 2)
        )


# ============================================================================
# Single Video Endpoints
# ============================================================================

@router.get("/{video_id}", response_model=VideoDetailResponse)
async def get_video(video_id: str):
    """
    Get detailed information for a single video
    """
    async with db_manager.session() as session:
        # Get video
        result = await session.execute(
            select(Video).where(
                or_(Video.video_id == video_id, Video.id == int(video_id) if video_id.isdigit() else -1)
            )
        )
        video = result.scalar_one_or_none()

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        # Get channel info if available
        channel_info = None
        if video.channel_id:
            channel_result = await session.execute(
                select(Channel).where(Channel.channel_id == video.channel_id)
            )
            channel = channel_result.scalar_one_or_none()
            if channel:
                channel_info = {
                    "channel_id": channel.channel_id,
                    "title": channel.title,
                    "description": channel.description,
                    "subscriber_count": channel.subscriber_count,
                    "video_count": channel.video_count,
                    "thumbnail_url": channel.thumbnail_url,
                }

        # Get caption count
        caption_count_result = await session.execute(
            select(func.count(Caption.id)).where(Caption.video_id == video.video_id)
        )
        caption_count = caption_count_result.scalar() or 0

        # Get stored comment count
        comment_count_result = await session.execute(
            select(func.count(Comment.id)).where(Comment.video_id == video.video_id)
        )
        stored_comment_count = comment_count_result.scalar() or 0

        return VideoDetailResponse(
            id=video.id,
            video_id=video.video_id,
            title=video.title,
            description=video.description,
            channel_id=video.channel_id,
            channel_title=video.channel_title,
            thumbnail_url=video.thumbnail_url,
            duration_seconds=video.duration_seconds,
            view_count=video.view_count,
            like_count=video.like_count,
            comment_count=video.comment_count,
            published_at=video.published_at,
            tags=video.tags if hasattr(video, 'tags') else None,
            category=video.category if hasattr(video, 'category') else None,
            scraped_at=video.scraped_at if hasattr(video, 'scraped_at') else video.created_at,
            updated_at=video.updated_at,
            has_captions=caption_count > 0,
            has_comments=stored_comment_count > 0,
            channel=channel_info,
            caption_count=caption_count,
            stored_comment_count=stored_comment_count,
        )


@router.delete("/{video_id}")
async def delete_video(video_id: str):
    """
    Delete a video and its associated data
    """
    async with db_manager.session() as session:
        # Get video
        result = await session.execute(
            select(Video).where(
                or_(Video.video_id == video_id, Video.id == int(video_id) if video_id.isdigit() else -1)
            )
        )
        video = result.scalar_one_or_none()

        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        # Delete associated comments
        await session.execute(
            Comment.__table__.delete().where(Comment.video_id == video.video_id)
        )

        # Delete associated captions
        await session.execute(
            Caption.__table__.delete().where(Caption.video_id == video.video_id)
        )

        # Delete video
        await session.delete(video)
        await session.commit()

        return {"message": "Video deleted successfully", "video_id": video.video_id}


# ============================================================================
# Video Comments Endpoints
# ============================================================================

@router.get("/{video_id}/comments", response_model=CommentListResponse)
async def get_video_comments(
    video_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort: str = Query("-like_count", description="Sort field"),
    replies_only: bool = Query(False, description="Show only replies"),
):
    """
    Get comments for a video
    """
    async with db_manager.session() as session:
        # Verify video exists
        video_result = await session.execute(
            select(Video.id).where(
                or_(Video.video_id == video_id, Video.id == int(video_id) if video_id.isdigit() else -1)
            )
        )
        if not video_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Video not found")

        # Build query
        query = select(Comment).where(Comment.video_id == video_id)
        count_query = select(func.count(Comment.id)).where(Comment.video_id == video_id)

        if replies_only:
            query = query.where(Comment.is_reply == True)
            count_query = count_query.where(Comment.is_reply == True)
        else:
            query = query.where(Comment.is_reply == False)
            count_query = count_query.where(Comment.is_reply == False)

        # Get total
        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0

        # Apply sorting
        sort_desc = sort.startswith("-")
        sort_field = sort.lstrip("-")

        sort_mapping = {
            "like_count": Comment.like_count,
            "published_at": Comment.published_at,
            "reply_count": Comment.reply_count,
        }

        sort_column = sort_mapping.get(sort_field, Comment.like_count)
        if sort_desc:
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(asc(sort_column))

        # Pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        # Execute
        result = await session.execute(query)
        comments = result.scalars().all()

        items = [
            CommentResponse(
                id=c.id,
                comment_id=c.comment_id,
                author=c.author,
                author_channel_id=c.author_channel_id,
                text=c.text,
                like_count=c.like_count or 0,
                reply_count=c.reply_count or 0,
                published_at=c.published_at,
                is_reply=c.is_reply or False,
            )
            for c in comments
        ]

        return CommentListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )


# ============================================================================
# Channel Endpoints
# ============================================================================

@router.get("/channel/{channel_id}/videos")
async def get_channel_videos(
    channel_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: str = Query("-published_at"),
):
    """
    Get all videos from a specific channel
    """
    return await list_videos(
        page=page,
        page_size=page_size,
        channel_id=channel_id,
        sort=sort
    )


# ============================================================================
# Bulk Operations
# ============================================================================

@router.post("/bulk/delete")
async def bulk_delete_videos(video_ids: List[str]):
    """
    Delete multiple videos at once
    """
    async with db_manager.session() as session:
        deleted = 0
        for vid in video_ids:
            result = await session.execute(
                select(Video).where(Video.video_id == vid)
            )
            video = result.scalar_one_or_none()
            if video:
                # Delete comments
                await session.execute(
                    Comment.__table__.delete().where(Comment.video_id == vid)
                )
                # Delete captions
                await session.execute(
                    Caption.__table__.delete().where(Caption.video_id == vid)
                )
                # Delete video
                await session.delete(video)
                deleted += 1

        await session.commit()

        return {
            "message": f"Deleted {deleted} videos",
            "deleted_count": deleted,
            "requested_count": len(video_ids)
        }


# ============================================================================
# Recent/Trending Endpoints
# ============================================================================

@router.get("/recent/scraped")
async def get_recently_scraped(limit: int = Query(10, ge=1, le=50)):
    """
    Get recently scraped videos
    """
    response = await list_videos(page=1, page_size=limit, sort="-scraped_at")
    return response.items


@router.get("/trending/views")
async def get_trending_by_views(limit: int = Query(10, ge=1, le=50)):
    """
    Get videos with highest view counts
    """
    response = await list_videos(page=1, page_size=limit, sort="-view_count")
    return response.items


@router.get("/trending/engagement")
async def get_trending_by_engagement(limit: int = Query(10, ge=1, le=50)):
    """
    Get videos with highest engagement (likes relative to views)
    """
    async with db_manager.session() as session:
        # Calculate engagement rate and sort
        query = select(Video).where(
            Video.view_count > 0
        ).order_by(
            desc(Video.like_count * 1.0 / Video.view_count)
        ).limit(limit)

        result = await session.execute(query)
        videos = result.scalars().all()

        return [
            VideoResponse(
                id=v.id,
                video_id=v.video_id,
                title=v.title,
                description=v.description,
                channel_id=v.channel_id,
                channel_title=v.channel_title,
                thumbnail_url=v.thumbnail_url,
                duration_seconds=v.duration_seconds,
                view_count=v.view_count,
                like_count=v.like_count,
                comment_count=v.comment_count,
                published_at=v.published_at,
                scraped_at=v.scraped_at if hasattr(v, 'scraped_at') else v.created_at,
                updated_at=v.updated_at,
                has_captions=False,
                has_comments=False,
            )
            for v in videos
        ]
