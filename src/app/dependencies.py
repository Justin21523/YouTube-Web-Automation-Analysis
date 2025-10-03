"""
Service Dependency Injection
FastAPI dependency providers for services
"""

from typing import Generator
from functools import lru_cache

from src.services import VideoService
from src.infrastructure.clients.youtube_api import create_youtube_client
from src.infrastructure.repositories import VideoRepository, ChannelRepository
from src.app.shared_cache import get_shared_cache
from src.app.config import get_config
from src.app.database import get_db


# ============================================================================
# Service Factories
# ============================================================================


@lru_cache()
def get_youtube_client():
    """
    Get or create YouTube API client (Singleton)

    Returns:
        YouTubeAPIClient instance
    """
    return create_youtube_client()


def get_video_service() -> Generator[VideoService, None, None]:
    """
    Dependency provider for VideoService

    Usage in FastAPI:
        @router.get("/videos/{video_id}")
        async def get_video(
            video_id: str,
            service: VideoService = Depends(get_video_service),
            db: AsyncSession = Depends(get_db)
        ):
            return await service.get_video(db, video_id)

    Yields:
        VideoService instance
    """
    # Get dependencies
    youtube_client = get_youtube_client()
    cache = get_shared_cache()
    config = get_config()

    # Create repositories (will use injected DB session)
    video_repo = VideoRepository()
    channel_repo = ChannelRepository()

    # Create service
    service = VideoService(
        youtube_client=youtube_client,
        video_repo=video_repo,
        channel_repo=channel_repo,
        cache=cache,
        config=config,
    )

    try:
        yield service
    finally:
        # Cleanup if needed
        pass


# ============================================================================
# Example FastAPI Router Usage
# ============================================================================


"""
Example router implementation:

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.database import get_db
from src.app.dependencies import get_video_service
from src.services import VideoService, ServiceError, error_to_http_status
from src.api.schemas import (
    VideoCreateRequest,
    VideoResponse,
    VideoSearchRequest,
    PaginatedResponse,
    create_paginated_response,
)

router = APIRouter(prefix="/api/v1/videos", tags=["Videos"])


@router.post("/", response_model=VideoResponse)
async def create_video(
    request: VideoCreateRequest,
    db: AsyncSession = Depends(get_db),
    service: VideoService = Depends(get_video_service)
):
    '''Create new video and fetch metadata from YouTube'''
    try:
        return await service.create_video(db, request)
    except ServiceError as e:
        status_code = error_to_http_status(e)
        raise HTTPException(status_code, detail=e.to_dict())


@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(
    video_id: str,
    db: AsyncSession = Depends(get_db),
    service: VideoService = Depends(get_video_service)
):
    '''Get video by ID'''
    try:
        return await service.get_video(db, video_id)
    except ServiceError as e:
        status_code = error_to_http_status(e)
        raise HTTPException(status_code, detail=e.to_dict())


@router.get("/", response_model=PaginatedResponse[VideoSummary])
async def search_videos(
    params: VideoSearchRequest = Depends(),
    db: AsyncSession = Depends(get_db),
    service: VideoService = Depends(get_video_service)
):
    '''Search videos with filters and pagination'''
    try:
        videos, total = await service.search_videos(db, params)

        return create_paginated_response(
            items=videos,
            total=total,
            page=params.page,
            page_size=params.page_size
        )
    except ServiceError as e:
        status_code = error_to_http_status(e)
        raise HTTPException(status_code, detail=e.to_dict())


@router.get("/trending", response_model=List[VideoTrendResponse])
async def get_trending_videos(
    days: int = 7,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    service: VideoService = Depends(get_video_service)
):
    '''Get trending videos from last N days'''
    try:
        return await service.get_trending_videos(db, days, limit)
    except ServiceError as e:
        status_code = error_to_http_status(e)
        raise HTTPException(status_code, detail=e.to_dict())


@router.post("/{video_id}/refresh", response_model=VideoResponse)
async def refresh_video(
    video_id: str,
    db: AsyncSession = Depends(get_db),
    service: VideoService = Depends(get_video_service)
):
    '''Refresh video metadata from YouTube'''
    try:
        return await service.refresh_video_metadata(db, video_id)
    except ServiceError as e:
        status_code = error_to_http_status(e)
        raise HTTPException(status_code, detail=e.to_dict())


@router.post("/batch", response_model=Dict[str, Any])
async def batch_fetch_videos(
    video_ids: List[str],
    db: AsyncSession = Depends(get_db),
    service: VideoService = Depends(get_video_service)
):
    '''Batch fetch multiple videos from YouTube'''
    try:
        return await service.batch_fetch_videos(db, video_ids)
    except ServiceError as e:
        status_code = error_to_http_status(e)
        raise HTTPException(status_code, detail=e.to_dict())
"""
