# src/api/routers/vqa_router.py
"""
VQA API Router
REST endpoints for Visual Question Answering operations
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Path, Depends, Body
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.dependencies import get_db
from src.app.models import VQAModelType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/vqa", tags=["VQA"])


# ============================================================================
# Request/Response Models
# ============================================================================


class FrameExtractionRequest(BaseModel):
    """Request to extract frames from a video"""

    video_id: str = Field(..., min_length=11, max_length=11, description="YouTube video ID")
    method: str = Field(
        default="keyframe",
        description="Extraction method: keyframe, interval, scene_change",
    )
    max_frames: int = Field(default=50, ge=1, le=200, description="Maximum frames to extract")
    interval_seconds: Optional[float] = Field(
        default=None,
        ge=1.0,
        description="Interval for interval-based extraction",
    )
    force_reextract: bool = Field(default=False, description="Re-extract even if exists")


class FrameAnalysisRequest(BaseModel):
    """Request to analyze a frame"""

    frame_id: int = Field(..., description="Frame ID to analyze")
    model_type: str = Field(
        default=VQAModelType.BLIP2.value,
        description="VQA model type",
    )


class CreateSessionRequest(BaseModel):
    """Request to create a VQA session"""

    video_id: str = Field(..., min_length=11, max_length=11, description="YouTube video ID")
    user_id: Optional[str] = Field(default=None, description="User identifier")
    model_type: str = Field(
        default=VQAModelType.BLIP2.value,
        description="VQA model type",
    )


class AskQuestionRequest(BaseModel):
    """Request to ask a question"""

    question: str = Field(..., min_length=1, max_length=1000, description="Question text")
    timestamp: Optional[float] = Field(
        default=None,
        ge=0,
        description="Video timestamp for context",
    )
    frame_id: Optional[int] = Field(
        default=None,
        description="Specific frame ID for question",
    )


class RateAnswerRequest(BaseModel):
    """Request to rate an answer"""

    rating: int = Field(..., ge=1, le=5, description="Rating 1-5")
    feedback: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional feedback text",
    )


class FrameSearchRequest(BaseModel):
    """Request to search frames"""

    query: str = Field(..., min_length=1, description="Search query")
    video_id: Optional[str] = Field(default=None, description="Limit to specific video")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)


class FrameResponse(BaseModel):
    """Frame data response"""

    id: int
    video_id: str
    frame_number: int
    timestamp: float
    file_path: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    is_keyframe: bool = True
    created_at: Optional[str] = None


class ExtractionStatusResponse(BaseModel):
    """Frame extraction status response"""

    video_id: str
    status: str
    progress: int = 0
    frames_count: int = 0
    extraction_method: Optional[str] = None
    error_message: Optional[str] = None


class SessionResponse(BaseModel):
    """VQA session response"""

    session_id: str
    video_id: str
    model_type: str
    frame_count: int = 0
    question_count: int = 0
    is_active: bool = True
    created_at: str


class QuestionAnswerResponse(BaseModel):
    """Question and answer response"""

    question_id: int
    question: str
    answer: str
    confidence: Optional[float] = None
    relevant_frames: List[dict] = []
    processing_time_ms: Optional[int] = None


# ============================================================================
# Dependency Injection
# ============================================================================


async def get_vqa_service(db: AsyncSession = Depends(get_db)):
    """Get VQA service with dependencies"""
    from src.services.vqa_service import VQAService
    from src.infrastructure.repositories import (
        VideoFrameRepository,
        FrameAnalysisRepository,
        VQASessionRepository,
        VQAQuestionRepository,
        VideoFrameExtractionRepository,
        VideoRepository,
    )
    from src.app.shared_cache import get_shared_cache
    from src.app.config import get_config

    return VQAService(
        frame_repo=VideoFrameRepository(db),
        analysis_repo=FrameAnalysisRepository(db),
        session_repo=VQASessionRepository(db),
        question_repo=VQAQuestionRepository(db),
        extraction_repo=VideoFrameExtractionRepository(db),
        video_repo=VideoRepository(db),
        cache=get_shared_cache(),
        config=get_config(),
    )


# ============================================================================
# Frame Extraction Endpoints
# ============================================================================


@router.post(
    "/frames/extract",
    response_model=ExtractionStatusResponse,
    summary="Extract frames from a video",
)
async def extract_frames(
    request: FrameExtractionRequest,
    db: AsyncSession = Depends(get_db),
    vqa_service=Depends(get_vqa_service),
):
    """
    Extract frames from a YouTube video for VQA analysis

    - **video_id**: YouTube video ID
    - **method**: keyframe (I-frames), interval, or scene_change
    - **max_frames**: Maximum frames to extract
    - **force_reextract**: Re-extract even if frames exist
    """
    try:
        result = await vqa_service.extract_frames(
            db=db,
            video_id=request.video_id,
            method=request.method,
            max_frames=request.max_frames,
            interval_seconds=request.interval_seconds,
            force_reextract=request.force_reextract,
        )
        return ExtractionStatusResponse(
            video_id=result["video_id"],
            status=result["status"],
            frames_count=result.get("frames_count", 0),
            extraction_method=result.get("extraction_method"),
            progress=100 if result["status"] == "completed" else result.get("progress", 0),
        )
    except Exception as e:
        logger.error(f"Frame extraction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/frames/video/{video_id}",
    summary="Get frames for a video",
)
async def get_video_frames(
    video_id: str = Path(..., min_length=11, max_length=11),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    vqa_service=Depends(get_vqa_service),
):
    """Get extracted frames for a video"""
    try:
        frames, total = await vqa_service.get_video_frames(db, video_id, skip, limit)
        return {
            "frames": frames,
            "total": total,
            "skip": skip,
            "limit": limit,
        }
    except Exception as e:
        logger.error(f"Failed to get frames: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/frames/{frame_id}",
    summary="Get frame with analysis",
)
async def get_frame_details(
    frame_id: int = Path(..., ge=1),
    db: AsyncSession = Depends(get_db),
    vqa_service=Depends(get_vqa_service),
):
    """Get frame details with any existing analyses"""
    try:
        result = await vqa_service.get_frame_with_analysis(db, frame_id)
        return result
    except Exception as e:
        logger.error(f"Failed to get frame: {e}")
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================================
# Frame Analysis Endpoints
# ============================================================================


@router.post(
    "/frames/analyze",
    summary="Analyze a frame",
)
async def analyze_frame(
    request: FrameAnalysisRequest,
    db: AsyncSession = Depends(get_db),
    vqa_service=Depends(get_vqa_service),
):
    """
    Analyze a single frame using VQA model

    Generates caption, description, and detected objects.
    """
    try:
        result = await vqa_service.analyze_frame(
            db=db,
            frame_id=request.frame_id,
            model_type=request.model_type,
        )
        return result
    except Exception as e:
        logger.error(f"Frame analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/frames/analyze/video/{video_id}",
    summary="Analyze multiple frames from a video",
)
async def analyze_video_frames(
    video_id: str = Path(..., min_length=11, max_length=11),
    model_type: str = Query(default=VQAModelType.BLIP2.value),
    max_frames: int = Query(default=20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    vqa_service=Depends(get_vqa_service),
):
    """Analyze keyframes from a video"""
    try:
        result = await vqa_service.analyze_video_frames(
            db=db,
            video_id=video_id,
            model_type=model_type,
            max_frames=max_frames,
        )
        return result
    except Exception as e:
        logger.error(f"Video frame analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/frames/search",
    summary="Search frames by visual content",
)
async def search_frames(
    request: FrameSearchRequest,
    db: AsyncSession = Depends(get_db),
    vqa_service=Depends(get_vqa_service),
):
    """Search frames by caption/description content"""
    try:
        skip = (request.page - 1) * request.page_size
        results = await vqa_service.search_frames(
            db=db,
            query=request.query,
            video_id=request.video_id,
            skip=skip,
            limit=request.page_size,
        )
        return {
            "results": results,
            "page": request.page,
            "page_size": request.page_size,
        }
    except Exception as e:
        logger.error(f"Frame search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# VQA Session Endpoints
# ============================================================================


@router.post(
    "/sessions",
    response_model=SessionResponse,
    summary="Create a VQA session",
)
async def create_session(
    request: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
    vqa_service=Depends(get_vqa_service),
):
    """
    Create a new VQA session for asking questions about a video

    The video must have extracted frames before creating a session.
    """
    try:
        result = await vqa_service.create_session(
            db=db,
            video_id=request.video_id,
            user_id=request.user_id,
            model_type=request.model_type,
        )
        return SessionResponse(
            session_id=result["session_id"],
            video_id=result["video_id"],
            model_type=result["model_type"],
            frame_count=result["frame_count"],
            question_count=0,
            is_active=True,
            created_at=result["created_at"],
        )
    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/sessions/{session_id}",
    summary="Get session details",
)
async def get_session(
    session_id: str = Path(...),
    include_questions: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    vqa_service=Depends(get_vqa_service),
):
    """Get VQA session details with optional question history"""
    try:
        result = await vqa_service.get_session(
            db=db,
            session_id=session_id,
            include_questions=include_questions,
        )
        return result
    except Exception as e:
        logger.error(f"Failed to get session: {e}")
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/sessions/{session_id}/ask",
    response_model=QuestionAnswerResponse,
    summary="Ask a question",
)
async def ask_question(
    session_id: str = Path(...),
    request: AskQuestionRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    vqa_service=Depends(get_vqa_service),
):
    """
    Ask a question about the video in a VQA session

    Optionally specify a timestamp or frame ID for context.
    """
    try:
        result = await vqa_service.ask_question(
            db=db,
            session_id=session_id,
            question=request.question,
            timestamp=request.timestamp,
            frame_id=request.frame_id,
        )
        return QuestionAnswerResponse(
            question_id=result["question_id"],
            question=result["question"],
            answer=result["answer"],
            confidence=result.get("confidence"),
            relevant_frames=result.get("relevant_frames", []),
            processing_time_ms=result.get("processing_time_ms"),
        )
    except Exception as e:
        logger.error(f"Failed to answer question: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/sessions/{session_id}/end",
    summary="End a session",
)
async def end_session(
    session_id: str = Path(...),
    db: AsyncSession = Depends(get_db),
    vqa_service=Depends(get_vqa_service),
):
    """End a VQA session"""
    try:
        result = await vqa_service.end_session(db=db, session_id=session_id)
        return result
    except Exception as e:
        logger.error(f"Failed to end session: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/questions/{question_id}/rate",
    summary="Rate an answer",
)
async def rate_answer(
    question_id: int = Path(..., ge=1),
    request: RateAnswerRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    vqa_service=Depends(get_vqa_service),
):
    """Rate an answer (1-5) with optional feedback"""
    try:
        result = await vqa_service.rate_answer(
            db=db,
            question_id=question_id,
            rating=request.rating,
            feedback=request.feedback,
        )
        return result
    except Exception as e:
        logger.error(f"Failed to rate answer: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# Utility Endpoints
# ============================================================================


@router.get(
    "/models",
    summary="Get available VQA models",
)
async def get_available_models():
    """Get list of available VQA models"""
    return {
        "models": [
            {
                "id": VQAModelType.BLIP2.value,
                "name": "BLIP-2",
                "description": "Salesforce BLIP-2 for image captioning and VQA",
            },
            {
                "id": VQAModelType.LLAVA.value,
                "name": "LLaVA",
                "description": "Large Language and Vision Assistant",
            },
            {
                "id": VQAModelType.COGVLM.value,
                "name": "CogVLM",
                "description": "CogVLM visual language model",
            },
            {
                "id": VQAModelType.QWEN_VL.value,
                "name": "Qwen-VL",
                "description": "Alibaba Qwen vision-language model",
            },
            {
                "id": VQAModelType.GPT4V.value,
                "name": "GPT-4V",
                "description": "OpenAI GPT-4 with vision (requires API key)",
            },
        ],
        "default": VQAModelType.BLIP2.value,
    }


@router.get(
    "/extraction/methods",
    summary="Get available extraction methods",
)
async def get_extraction_methods():
    """Get list of available frame extraction methods"""
    return {
        "methods": [
            {
                "id": "keyframe",
                "name": "Keyframe Extraction",
                "description": "Extract I-frames (keyframes) from video",
            },
            {
                "id": "interval",
                "name": "Interval Extraction",
                "description": "Extract frames at fixed time intervals",
            },
            {
                "id": "scene_change",
                "name": "Scene Change Detection",
                "description": "Extract frames when scene changes detected",
            },
        ],
        "default": "keyframe",
    }


__all__ = ["router"]
