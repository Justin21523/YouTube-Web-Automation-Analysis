# src/api/routers/caption_router.py
"""
Caption API Router
REST endpoints for caption/subtitle operations
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Path, Depends, Body
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.dependencies import get_db, get_caption_service
from src.services.caption_service import CaptionService
from src.services.exceptions import (
    ResourceNotFoundError,
    ValidationError,
    ExternalServiceError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/captions", tags=["Captions"])


# ============================================================================
# Request/Response Models
# ============================================================================


class CaptionFetchRequest(BaseModel):
    """Request to fetch captions for a video"""

    video_id: str = Field(..., min_length=11, max_length=11, description="YouTube video ID")
    languages: Optional[List[str]] = Field(
        default=None,
        description="Specific languages to fetch (None = all available)",
    )
    include_auto: bool = Field(
        default=True,
        description="Include auto-generated captions",
    )
    force_refresh: bool = Field(
        default=False,
        description="Re-fetch even if exists",
    )


class CaptionSearchRequest(BaseModel):
    """Request to search within captions"""

    query: str = Field(..., min_length=1, description="Search query text")
    video_ids: Optional[List[str]] = Field(
        default=None,
        description="Limit search to specific videos",
    )
    language_code: Optional[str] = Field(
        default=None,
        description="Filter by language",
    )
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Results per page")


class SegmentSearchRequest(BaseModel):
    """Request to search caption segments"""

    query: str = Field(..., min_length=1, description="Search query text")
    video_id: Optional[str] = Field(
        default=None,
        description="Limit search to specific video",
    )
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Results per page")


class CaptionResponse(BaseModel):
    """Caption data response"""

    id: str
    video_id: str
    language_code: str
    language_name: Optional[str] = None
    caption_type: str
    content: Optional[str] = None
    word_count: int = 0
    segment_count: int = 0
    duration_seconds: Optional[float] = None
    is_processed: bool = False
    fetched_at: Optional[str] = None


class CaptionSummaryResponse(BaseModel):
    """Caption summary without full content"""

    id: str
    language_code: str
    language_name: Optional[str] = None
    caption_type: str
    word_count: int = 0
    segment_count: int = 0
    duration_seconds: Optional[float] = None
    is_processed: bool = False
    fetched_at: Optional[str] = None


class LanguageInfo(BaseModel):
    """Available language info"""

    language_code: str
    language_name: Optional[str] = None
    caption_type: str
    word_count: int = 0


class CaptionSearchResult(BaseModel):
    """Caption search result"""

    video_id: str
    language_code: str
    caption_id: str
    word_count: int
    match_preview: str


class SegmentSearchResult(BaseModel):
    """Segment search result with timestamp"""

    video_id: str
    caption_id: str
    segment_id: int
    start_time: float
    end_time: float
    text: str
    timestamp_link: str


class FetchResultResponse(BaseModel):
    """Caption fetch operation result"""

    video_id: str
    success: List[str]
    failed: List[dict]
    skipped: List[dict]
    message: Optional[str] = None


class ProcessSegmentsResponse(BaseModel):
    """Segment processing result"""

    video_id: str
    language_code: str
    segments_created: int


class DeleteCaptionsResponse(BaseModel):
    """Delete captions result"""

    success: bool
    video_id: str
    captions_deleted: int
    segments_deleted: int


# ============================================================================
# Caption CRUD Endpoints
# ============================================================================


@router.get(
    "/video/{video_id}",
    response_model=List[CaptionSummaryResponse],
    summary="Get all captions for a video",
)
async def get_video_captions(
    video_id: str = Path(..., min_length=11, max_length=11, description="YouTube video ID"),
    db: AsyncSession = Depends(get_db),
    caption_service: CaptionService = Depends(get_caption_service),
):
    """
    Get all available captions for a video

    Returns a list of caption summaries without full content.
    """
    try:
        captions = await caption_service.get_video_captions(db, video_id)
        return captions

    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get video captions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/video/{video_id}/languages",
    response_model=List[LanguageInfo],
    summary="Get available languages for a video",
)
async def get_available_languages(
    video_id: str = Path(..., min_length=11, max_length=11, description="YouTube video ID"),
    db: AsyncSession = Depends(get_db),
    caption_service: CaptionService = Depends(get_caption_service),
):
    """
    Get list of available caption languages for a video
    """
    try:
        languages = await caption_service.get_available_languages(db, video_id)
        return languages

    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get available languages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/video/{video_id}/{language_code}",
    response_model=CaptionResponse,
    summary="Get caption in specific language",
)
async def get_caption(
    video_id: str = Path(..., min_length=11, max_length=11, description="YouTube video ID"),
    language_code: str = Path(..., description="Language code (e.g., 'en', 'zh-TW')"),
    db: AsyncSession = Depends(get_db),
    caption_service: CaptionService = Depends(get_caption_service),
):
    """
    Get caption content for a video in a specific language

    Returns the full caption with content.
    """
    try:
        caption = await caption_service.get_caption(db, video_id, language_code)
        return caption

    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get caption: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/video/{video_id}",
    response_model=DeleteCaptionsResponse,
    summary="Delete all captions for a video",
)
async def delete_video_captions(
    video_id: str = Path(..., min_length=11, max_length=11, description="YouTube video ID"),
    db: AsyncSession = Depends(get_db),
    caption_service: CaptionService = Depends(get_caption_service),
):
    """
    Delete all captions and segments for a video
    """
    try:
        result = await caption_service.delete_video_captions(db, video_id)
        return result

    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to delete captions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Caption Fetching Endpoints
# ============================================================================


@router.post(
    "/fetch",
    response_model=FetchResultResponse,
    summary="Fetch captions for a video",
)
async def fetch_captions(
    request: CaptionFetchRequest,
    db: AsyncSession = Depends(get_db),
    caption_service: CaptionService = Depends(get_caption_service),
):
    """
    Fetch and store captions for a video from YouTube

    - **video_id**: YouTube video ID
    - **languages**: Specific languages to fetch (None = all available)
    - **include_auto**: Include auto-generated captions
    - **force_refresh**: Re-fetch even if exists
    """
    try:
        result = await caption_service.fetch_captions(
            db=db,
            video_id=request.video_id,
            languages=request.languages,
            include_auto=request.include_auto,
            force_refresh=request.force_refresh,
        )
        return result

    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ExternalServiceError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to fetch captions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/fetch/batch",
    response_model=List[FetchResultResponse],
    summary="Fetch captions for multiple videos",
)
async def fetch_captions_batch(
    video_ids: List[str] = Body(..., min_items=1, max_items=10, description="List of video IDs"),
    languages: Optional[List[str]] = Body(default=None, description="Languages to fetch"),
    include_auto: bool = Body(default=True, description="Include auto-generated"),
    db: AsyncSession = Depends(get_db),
    caption_service: CaptionService = Depends(get_caption_service),
):
    """
    Batch fetch captions for multiple videos

    Limited to 10 videos per request.
    """
    results = []

    for video_id in video_ids:
        try:
            result = await caption_service.fetch_captions(
                db=db,
                video_id=video_id,
                languages=languages,
                include_auto=include_auto,
                force_refresh=False,
            )
            results.append(result)

        except Exception as e:
            logger.error(f"Failed to fetch captions for {video_id}: {e}")
            results.append({
                "video_id": video_id,
                "success": [],
                "failed": [{"error": str(e)}],
                "skipped": [],
            })

    return results


# ============================================================================
# Caption Search Endpoints
# ============================================================================


@router.post(
    "/search",
    summary="Search within captions",
)
async def search_captions(
    request: CaptionSearchRequest,
    db: AsyncSession = Depends(get_db),
    caption_service: CaptionService = Depends(get_caption_service),
):
    """
    Search for text within caption content

    Returns matching captions with preview text.
    """
    try:
        results, total = await caption_service.search_captions(
            db=db,
            query=request.query,
            video_ids=request.video_ids,
            language_code=request.language_code,
            page=request.page,
            page_size=request.page_size,
        )

        return {
            "results": results,
            "total": total,
            "page": request.page,
            "page_size": request.page_size,
        }

    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to search captions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/search/segments",
    summary="Search caption segments with timestamps",
)
async def search_segments(
    request: SegmentSearchRequest,
    db: AsyncSession = Depends(get_db),
    caption_service: CaptionService = Depends(get_caption_service),
):
    """
    Search within caption segments for precise timestamp matching

    Returns segments with start/end times and clickable timestamp links.
    """
    try:
        results, total = await caption_service.search_segments(
            db=db,
            query=request.query,
            video_id=request.video_id,
            page=request.page,
            page_size=request.page_size,
        )

        return {
            "results": results,
            "total": total,
            "page": request.page,
            "page_size": request.page_size,
        }

    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to search segments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/segment/at-time",
    summary="Get segment at specific timestamp",
)
async def get_segment_at_time(
    video_id: str = Query(..., min_length=11, max_length=11, description="Video ID"),
    timestamp: float = Query(..., ge=0, description="Time in seconds"),
    db: AsyncSession = Depends(get_db),
    caption_service: CaptionService = Depends(get_caption_service),
):
    """
    Get the caption segment at a specific timestamp

    Useful for finding what's being said at a particular moment in the video.
    """
    try:
        segment = await caption_service.get_segment_at_time(db, video_id, timestamp)

        if segment:
            return segment
        else:
            raise HTTPException(
                status_code=404,
                detail=f"No segment found at timestamp {timestamp}",
            )

    except Exception as e:
        logger.error(f"Failed to get segment at time: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Segment Processing Endpoints
# ============================================================================


@router.post(
    "/process-segments/{video_id}/{language_code}",
    response_model=ProcessSegmentsResponse,
    summary="Process caption into segments",
)
async def process_caption_segments(
    video_id: str = Path(..., min_length=11, max_length=11, description="YouTube video ID"),
    language_code: str = Path(..., description="Language code"),
    db: AsyncSession = Depends(get_db),
    caption_service: CaptionService = Depends(get_caption_service),
):
    """
    Process a caption into searchable segments

    Creates individual segment records with timing information for
    precise search and navigation.
    """
    try:
        result = await caption_service.process_caption_segments(
            db, video_id, language_code
        )
        return result

    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to process segments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Utility Endpoints
# ============================================================================


@router.get(
    "/stats/video/{video_id}",
    summary="Get caption statistics for a video",
)
async def get_video_caption_stats(
    video_id: str = Path(..., min_length=11, max_length=11, description="YouTube video ID"),
    db: AsyncSession = Depends(get_db),
    caption_service: CaptionService = Depends(get_caption_service),
):
    """
    Get caption statistics for a video

    Returns counts, languages available, and processing status.
    """
    try:
        captions = await caption_service.get_video_captions(db, video_id)

        total_words = sum(c.get("word_count", 0) for c in captions)
        total_segments = sum(c.get("segment_count", 0) for c in captions)
        languages = [c.get("language_code") for c in captions]
        processed_count = sum(1 for c in captions if c.get("is_processed"))

        return {
            "video_id": video_id,
            "caption_count": len(captions),
            "languages": languages,
            "total_words": total_words,
            "total_segments": total_segments,
            "processed_count": processed_count,
            "all_processed": processed_count == len(captions),
        }

    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get caption stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


__all__ = ["router"]
