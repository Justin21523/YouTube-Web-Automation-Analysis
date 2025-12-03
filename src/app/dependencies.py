"""
Service Dependency Injection
FastAPI dependency providers for services
"""

from typing import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from src.services import VideoService, CaptionService
from src.infrastructure.clients.youtube_api import create_youtube_client
from src.infrastructure.repositories import (
    VideoRepository,
    ChannelRepository,
    CaptionRepository,
    CaptionSegmentRepository,
)
from src.app.shared_cache import get_shared_cache
from src.app.config import get_config
from src.infrastructure.database import get_session


# ============================================================================
# Database Dependency
# ============================================================================


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI Dependency for database session

    Usage:
        @router.get("/")
        async def endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    async for session in get_session():
        yield session


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


async def get_video_service(
    session: AsyncSession,
) -> VideoService:
    """
    Create VideoService with all dependencies

    This is a factory function, not a FastAPI dependency.
    Use get_video_service_dep() for FastAPI dependency injection.

    Args:
        session: AsyncSession for database operations

    Returns:
        VideoService instance
    """
    youtube_client = get_youtube_client()
    cache = get_shared_cache()
    config = get_config()

    # Create repositories with session
    video_repo = VideoRepository(session)
    channel_repo = ChannelRepository(session)

    # Create and return service
    return VideoService(
        youtube_client=youtube_client,
        video_repo=video_repo,
        channel_repo=channel_repo,
        cache=cache,
        config=config,
    )


async def get_video_service_dep(
    session: AsyncSession = None,  # Will be injected via get_session
) -> AsyncGenerator[VideoService, None]:
    """
    FastAPI Dependency provider for VideoService

    Usage in FastAPI:
        @router.get("/videos/{video_id}")
        async def get_video(
            video_id: str,
            session: AsyncSession = Depends(get_session),
            service: VideoService = Depends(get_video_service_dep)
        ):
            # Note: session must be passed to service methods
            return await service.get_video(video_id)

    Yields:
        VideoService instance with injected session
    """
    # Use get_session to obtain a proper session if not provided
    if session is None:
        async for db_session in get_session():
            service = await get_video_service(db_session)
            yield service
            return

    service = await get_video_service(session)
    yield service


# ============================================================================
# Caption Service Factory
# ============================================================================


async def get_caption_service(
    session: AsyncSession = None,
) -> CaptionService:
    """
    Create CaptionService with all dependencies

    Args:
        session: AsyncSession for database operations

    Returns:
        CaptionService instance
    """
    # Use get_session to obtain a proper session if not provided
    if session is None:
        async for db_session in get_session():
            return await _create_caption_service(db_session)

    return await _create_caption_service(session)


async def _create_caption_service(session: AsyncSession) -> CaptionService:
    """Helper to create CaptionService with session"""
    youtube_client = get_youtube_client()
    cache = get_shared_cache()
    config = get_config()

    # Create repositories with session
    caption_repo = CaptionRepository(session)
    segment_repo = CaptionSegmentRepository(session)
    video_repo = VideoRepository(session)

    # Create and return service
    return CaptionService(
        caption_repo=caption_repo,
        segment_repo=segment_repo,
        video_repo=video_repo,
        youtube_client=youtube_client,
        cache=cache,
        config=config,
    )


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
