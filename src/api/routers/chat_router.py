# src/api/routers/chat_router.py
"""
Chat API Router
REST endpoints for conversational AI operations
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Path, Depends, Body
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.dependencies import get_db
from src.app.models import ChatModelType, ChatRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chat", tags=["Chat"])


# ============================================================================
# Request/Response Models
# ============================================================================


class CreateSessionRequest(BaseModel):
    """Request to create a chat session"""

    user_id: str = Field(..., min_length=1, max_length=100, description="User identifier")
    video_id: Optional[str] = Field(
        default=None,
        min_length=11,
        max_length=11,
        description="YouTube video ID for video-specific chat",
    )
    title: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Session title",
    )
    model_type: str = Field(
        default=ChatModelType.GPT35.value,
        description="LLM model type",
    )
    system_prompt: Optional[str] = Field(
        default=None,
        max_length=5000,
        description="Custom system prompt",
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Model temperature",
    )
    max_tokens: int = Field(
        default=2000,
        ge=100,
        le=8000,
        description="Max tokens per response",
    )
    template_id: Optional[int] = Field(
        default=None,
        description="Template ID to use for session",
    )


class SendMessageRequest(BaseModel):
    """Request to send a message"""

    content: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Message content",
    )
    stream: bool = Field(
        default=False,
        description="Enable streaming response",
    )


class RateMessageRequest(BaseModel):
    """Request to rate a message"""

    rating: int = Field(..., ge=1, le=5, description="Rating 1-5")
    is_helpful: Optional[bool] = Field(
        default=None,
        description="Was the response helpful?",
    )


class CreateTemplateRequest(BaseModel):
    """Request to create a chat template"""

    name: str = Field(..., min_length=1, max_length=100, description="Template name")
    system_prompt: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="System prompt template",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Template description",
    )
    category: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Template category",
    )
    example_queries: Optional[List[str]] = Field(
        default=None,
        description="Example user queries",
    )
    default_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    default_max_tokens: int = Field(default=2000, ge=100, le=8000)
    recommended_model: Optional[str] = Field(default=None)


class SessionResponse(BaseModel):
    """Chat session response"""

    session_id: str
    user_id: str
    video_id: Optional[str] = None
    title: Optional[str] = None
    model_type: str
    is_active: bool = True
    message_count: int = 0
    created_at: Optional[str] = None
    last_activity_at: Optional[str] = None


class MessageResponse(BaseModel):
    """Chat message response"""

    id: int
    session_id: str
    role: str
    content: str
    token_count: Optional[int] = None
    model_used: Optional[str] = None
    user_rating: Optional[int] = None
    created_at: Optional[str] = None


class SendMessageResponse(BaseModel):
    """Response after sending a message"""

    user_message: dict
    assistant_message: dict


class TemplateResponse(BaseModel):
    """Chat template response"""

    id: int
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    system_prompt: str
    example_queries: Optional[List[str]] = None
    default_temperature: float
    default_max_tokens: int
    recommended_model: Optional[str] = None
    usage_count: int = 0
    is_active: bool = True


class SessionStatsResponse(BaseModel):
    """Session statistics response"""

    session_id: str
    message_count: int
    total_tokens: int
    average_rating: Optional[float] = None
    model_type: str
    is_active: bool
    created_at: Optional[str] = None
    last_activity: Optional[str] = None


# ============================================================================
# Dependency Injection
# ============================================================================


async def get_chat_service(db: AsyncSession = Depends(get_db)):
    """Get chat service instance"""
    from src.infrastructure.repositories import (
        ChatSessionRepository,
        ChatMessageRepository,
        ChatTemplateRepository,
        VideoRepository,
    )
    from src.services import ChatService

    session_repo = ChatSessionRepository(db)
    message_repo = ChatMessageRepository(db)
    template_repo = ChatTemplateRepository(db)
    video_repo = VideoRepository(db)

    return ChatService(
        session_repo=session_repo,
        message_repo=message_repo,
        template_repo=template_repo,
        video_repo=video_repo,
    )


# ============================================================================
# Session Endpoints
# ============================================================================


@router.post(
    "/sessions",
    response_model=SessionResponse,
    summary="Create Chat Session",
    description="Create a new chat session, optionally linked to a video",
)
async def create_session(
    request: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
    chat_service=Depends(get_chat_service),
):
    """Create a new chat session"""
    try:
        result = await chat_service.create_session(
            db=db,
            user_id=request.user_id,
            video_id=request.video_id,
            title=request.title,
            model_type=request.model_type,
            system_prompt=request.system_prompt,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            template_id=request.template_id,
        )

        return SessionResponse(
            session_id=result["session_id"],
            user_id=result["user_id"],
            video_id=result.get("video_id"),
            title=result.get("title"),
            model_type=result["model_type"],
            created_at=result.get("created_at"),
        )

    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/sessions/{session_id}",
    response_model=dict,
    summary="Get Chat Session",
    description="Get chat session details with optional message history",
)
async def get_session(
    session_id: str = Path(..., description="Session ID"),
    include_messages: bool = Query(False, description="Include message history"),
    db: AsyncSession = Depends(get_db),
    chat_service=Depends(get_chat_service),
):
    """Get chat session details"""
    try:
        result = await chat_service.get_session(
            db=db,
            session_id=session_id,
            include_messages=include_messages,
        )

        if not result:
            raise HTTPException(status_code=404, detail="Session not found")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/users/{user_id}/sessions",
    response_model=List[dict],
    summary="Get User Sessions",
    description="Get all chat sessions for a user",
)
async def get_user_sessions(
    user_id: str = Path(..., description="User identifier"),
    include_inactive: bool = Query(False, description="Include inactive sessions"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    chat_service=Depends(get_chat_service),
):
    """Get chat sessions for a user"""
    try:
        results = await chat_service.get_user_sessions(
            db=db,
            user_id=user_id,
            include_inactive=include_inactive,
            skip=skip,
            limit=limit,
        )

        return results

    except Exception as e:
        logger.error(f"Failed to get user sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/sessions/{session_id}/end",
    summary="End Chat Session",
    description="Deactivate a chat session",
)
async def end_session(
    session_id: str = Path(..., description="Session ID"),
    db: AsyncSession = Depends(get_db),
    chat_service=Depends(get_chat_service),
):
    """End/deactivate a chat session"""
    try:
        result = await chat_service.end_session(db=db, session_id=session_id)

        if not result:
            raise HTTPException(status_code=404, detail="Session not found")

        return {"message": "Session ended successfully", "session_id": session_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to end session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/sessions/{session_id}",
    summary="Delete Chat Session",
    description="Delete a chat session and all its messages",
)
async def delete_session(
    session_id: str = Path(..., description="Session ID"),
    db: AsyncSession = Depends(get_db),
    chat_service=Depends(get_chat_service),
):
    """Delete a chat session"""
    try:
        result = await chat_service.delete_session(db=db, session_id=session_id)

        if not result:
            raise HTTPException(status_code=404, detail="Session not found")

        return {"message": "Session deleted successfully", "session_id": session_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/sessions/{session_id}/stats",
    response_model=SessionStatsResponse,
    summary="Get Session Statistics",
    description="Get statistics for a chat session",
)
async def get_session_stats(
    session_id: str = Path(..., description="Session ID"),
    db: AsyncSession = Depends(get_db),
    chat_service=Depends(get_chat_service),
):
    """Get session statistics"""
    try:
        result = await chat_service.get_session_stats(db=db, session_id=session_id)

        return SessionStatsResponse(**result)

    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Session not found")
        logger.error(f"Failed to get session stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Message Endpoints
# ============================================================================


@router.post(
    "/sessions/{session_id}/messages",
    response_model=SendMessageResponse,
    summary="Send Message",
    description="Send a message and get AI response",
)
async def send_message(
    session_id: str = Path(..., description="Session ID"),
    request: SendMessageRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    chat_service=Depends(get_chat_service),
):
    """Send a message and get AI response"""
    try:
        result = await chat_service.send_message(
            db=db,
            session_id=session_id,
            content=request.content,
            stream=request.stream,
        )

        return SendMessageResponse(**result)

    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Session not found")
        if "inactive" in str(e).lower():
            raise HTTPException(status_code=400, detail="Session is inactive")
        if "empty" in str(e).lower():
            raise HTTPException(status_code=400, detail="Message cannot be empty")
        logger.error(f"Failed to send message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/sessions/{session_id}/messages",
    response_model=List[dict],
    summary="Get Messages",
    description="Get messages for a chat session",
)
async def get_messages(
    session_id: str = Path(..., description="Session ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    chat_service=Depends(get_chat_service),
):
    """Get messages for a session"""
    try:
        results = await chat_service.get_messages(
            db=db,
            session_id=session_id,
            skip=skip,
            limit=limit,
        )

        return results

    except Exception as e:
        logger.error(f"Failed to get messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/messages/{message_id}/rate",
    summary="Rate Message",
    description="Rate an assistant message",
)
async def rate_message(
    message_id: int = Path(..., description="Message ID"),
    request: RateMessageRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    chat_service=Depends(get_chat_service),
):
    """Rate a message"""
    try:
        result = await chat_service.rate_message(
            db=db,
            message_id=message_id,
            rating=request.rating,
            is_helpful=request.is_helpful,
        )

        if not result:
            raise HTTPException(status_code=404, detail="Message not found")

        return {
            "message": "Rating submitted successfully",
            "message_id": message_id,
            "rating": request.rating,
        }

    except HTTPException:
        raise
    except Exception as e:
        if "between" in str(e).lower():
            raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")
        logger.error(f"Failed to rate message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Template Endpoints
# ============================================================================


@router.get(
    "/templates",
    response_model=List[dict],
    summary="Get Templates",
    description="Get available chat templates",
)
async def get_templates(
    category: Optional[str] = Query(None, description="Filter by category"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    chat_service=Depends(get_chat_service),
):
    """Get available chat templates"""
    try:
        results = await chat_service.get_templates(
            db=db,
            category=category,
            skip=skip,
            limit=limit,
        )

        return results

    except Exception as e:
        logger.error(f"Failed to get templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/templates",
    response_model=dict,
    summary="Create Template",
    description="Create a new chat template",
)
async def create_template(
    request: CreateTemplateRequest,
    db: AsyncSession = Depends(get_db),
    chat_service=Depends(get_chat_service),
):
    """Create a new chat template"""
    try:
        result = await chat_service.create_template(
            db=db,
            name=request.name,
            system_prompt=request.system_prompt,
            description=request.description,
            category=request.category,
            example_queries=request.example_queries,
            default_temperature=request.default_temperature,
            default_max_tokens=request.default_max_tokens,
            recommended_model=request.recommended_model,
        )

        return result

    except Exception as e:
        if "already exists" in str(e).lower():
            raise HTTPException(status_code=409, detail=str(e))
        logger.error(f"Failed to create template: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/templates/categories",
    response_model=List[str],
    summary="Get Template Categories",
    description="Get list of available template categories",
)
async def get_template_categories(
    db: AsyncSession = Depends(get_db),
    chat_service=Depends(get_chat_service),
):
    """Get template categories"""
    try:
        results = await chat_service.get_template_categories(db=db)
        return results

    except Exception as e:
        logger.error(f"Failed to get template categories: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# User Statistics Endpoints
# ============================================================================


@router.get(
    "/users/{user_id}/stats",
    response_model=dict,
    summary="Get User Chat Statistics",
    description="Get chat statistics for a user",
)
async def get_user_stats(
    user_id: str = Path(..., description="User identifier"),
    db: AsyncSession = Depends(get_db),
    chat_service=Depends(get_chat_service),
):
    """Get user chat statistics"""
    try:
        result = await chat_service.get_user_stats(db=db, user_id=user_id)
        return result

    except Exception as e:
        logger.error(f"Failed to get user stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Context Management Endpoints
# ============================================================================


@router.post(
    "/sessions/{session_id}/summarize",
    summary="Summarize Context",
    description="Generate a summary of the conversation context",
)
async def summarize_context(
    session_id: str = Path(..., description="Session ID"),
    db: AsyncSession = Depends(get_db),
    chat_service=Depends(get_chat_service),
):
    """Summarize conversation context"""
    try:
        summary = await chat_service.summarize_context(db=db, session_id=session_id)

        return {
            "session_id": session_id,
            "summary": summary,
        }

    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Session not found")
        logger.error(f"Failed to summarize context: {e}")
        raise HTTPException(status_code=500, detail=str(e))


__all__ = ["router"]
