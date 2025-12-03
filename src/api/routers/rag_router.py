# src/api/routers/rag_router.py
"""
RAG API Router
REST endpoints for Retrieval-Augmented Generation operations
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Path, Depends, Body
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.dependencies import get_db
from src.app.models import EmbeddingModelType, ChunkType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/rag", tags=["RAG"])


# ============================================================================
# Request/Response Models
# ============================================================================


class CreateIndexRequest(BaseModel):
    """Request to create a RAG index"""

    name: str = Field(..., min_length=1, max_length=100, description="Index name")
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Index description",
    )
    embedding_model: str = Field(
        default=EmbeddingModelType.OPENAI_3_SMALL.value,
        description="Embedding model to use",
    )
    embedding_dimension: int = Field(
        default=1536,
        ge=128,
        le=4096,
        description="Embedding dimension",
    )
    chunk_size: int = Field(
        default=500,
        ge=100,
        le=2000,
        description="Target chunk size in tokens",
    )
    chunk_overlap: int = Field(
        default=50,
        ge=0,
        le=500,
        description="Overlap between chunks",
    )
    index_type: str = Field(
        default="flat",
        description="Vector index type (flat, ivf, hnsw)",
    )


class ChunkVideoRequest(BaseModel):
    """Request to chunk video content"""

    video_id: str = Field(..., min_length=11, max_length=11, description="Video ID")
    include_captions: bool = Field(default=True, description="Include captions")
    include_description: bool = Field(default=True, description="Include description")
    include_comments: bool = Field(default=False, description="Include comments")
    chunk_size: int = Field(default=500, ge=100, le=2000)
    chunk_overlap: int = Field(default=50, ge=0, le=500)


class GenerateEmbeddingsRequest(BaseModel):
    """Request to generate embeddings"""

    video_id: Optional[str] = Field(
        default=None,
        min_length=11,
        max_length=11,
        description="Video ID to process",
    )
    chunk_ids: Optional[List[int]] = Field(
        default=None,
        description="Specific chunk IDs to embed",
    )
    model_type: str = Field(
        default=EmbeddingModelType.OPENAI_3_SMALL.value,
        description="Embedding model",
    )
    batch_size: int = Field(
        default=100,
        ge=1,
        le=500,
        description="Batch size",
    )


class SearchRequest(BaseModel):
    """Request to search RAG index"""

    query: str = Field(..., min_length=1, max_length=1000, description="Search query")
    video_id: Optional[str] = Field(
        default=None,
        description="Filter by video",
    )
    index_id: Optional[int] = Field(
        default=None,
        description="Index to search",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Number of results",
    )
    similarity_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score",
    )
    source_types: Optional[List[str]] = Field(
        default=None,
        description="Filter by source types",
    )


class GenerateRequest(BaseModel):
    """Request to generate RAG response"""

    query: str = Field(..., min_length=1, max_length=2000, description="User query")
    video_id: Optional[str] = Field(
        default=None,
        description="Video context",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of sources",
    )
    model_type: str = Field(
        default="gpt-3.5-turbo",
        description="LLM model for generation",
    )


class RateResponseRequest(BaseModel):
    """Request to rate a RAG response"""

    rating: int = Field(..., ge=1, le=5, description="Rating 1-5")
    feedback: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional feedback",
    )


class IndexResponse(BaseModel):
    """RAG index response"""

    id: int
    name: str
    description: Optional[str] = None
    embedding_model: str
    embedding_dimension: int
    chunk_size: int
    chunk_overlap: int
    index_type: str
    total_chunks: int = 0
    total_videos: int = 0
    is_active: bool = True
    last_updated: Optional[str] = None
    created_at: Optional[str] = None


class ChunkResponse(BaseModel):
    """Document chunk response"""

    id: int
    video_id: Optional[str] = None
    source_type: str
    content: str
    chunk_index: int
    token_count: Optional[int] = None
    is_embedded: bool = False
    created_at: Optional[str] = None


class SearchResultResponse(BaseModel):
    """Search result response"""

    query: str
    results: List[dict]
    result_count: int
    search_time_ms: int
    query_id: Optional[int] = None


class GenerateResponseModel(BaseModel):
    """RAG generation response"""

    query: str
    response: str
    sources: List[dict]
    source_count: int
    search_time_ms: int
    total_time_ms: int
    model: str


# ============================================================================
# Dependency Injection
# ============================================================================


async def get_rag_service(db: AsyncSession = Depends(get_db)):
    """Get RAG service instance"""
    from src.infrastructure.repositories import (
        DocumentChunkRepository,
        ChunkEmbeddingRepository,
        RAGIndexRepository,
        RAGQueryRepository,
        VideoEmbeddingStatusRepository,
        VideoRepository,
        CaptionRepository,
    )
    from src.services import RAGService

    chunk_repo = DocumentChunkRepository(db)
    embedding_repo = ChunkEmbeddingRepository(db)
    index_repo = RAGIndexRepository(db)
    query_repo = RAGQueryRepository(db)
    status_repo = VideoEmbeddingStatusRepository(db)
    video_repo = VideoRepository(db)
    caption_repo = CaptionRepository(db)

    return RAGService(
        chunk_repo=chunk_repo,
        embedding_repo=embedding_repo,
        index_repo=index_repo,
        query_repo=query_repo,
        status_repo=status_repo,
        video_repo=video_repo,
        caption_repo=caption_repo,
    )


# ============================================================================
# Index Endpoints
# ============================================================================


@router.post(
    "/indexes",
    response_model=dict,
    summary="Create RAG Index",
    description="Create a new RAG index for vector search",
)
async def create_index(
    request: CreateIndexRequest,
    db: AsyncSession = Depends(get_db),
    rag_service=Depends(get_rag_service),
):
    """Create a new RAG index"""
    try:
        result = await rag_service.create_index(
            db=db,
            name=request.name,
            description=request.description,
            embedding_model=request.embedding_model,
            embedding_dimension=request.embedding_dimension,
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap,
            index_type=request.index_type,
        )

        return result

    except Exception as e:
        if "already exists" in str(e).lower():
            raise HTTPException(status_code=409, detail=str(e))
        logger.error(f"Failed to create index: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/indexes",
    response_model=List[dict],
    summary="List RAG Indexes",
    description="Get all RAG indexes",
)
async def list_indexes(
    active_only: bool = Query(True, description="Only return active indexes"),
    db: AsyncSession = Depends(get_db),
    rag_service=Depends(get_rag_service),
):
    """List all RAG indexes"""
    try:
        results = await rag_service.list_indexes(db=db, active_only=active_only)
        return results

    except Exception as e:
        logger.error(f"Failed to list indexes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/indexes/{index_id}",
    response_model=dict,
    summary="Get RAG Index",
    description="Get a specific RAG index by ID",
)
async def get_index(
    index_id: int = Path(..., description="Index ID"),
    db: AsyncSession = Depends(get_db),
    rag_service=Depends(get_rag_service),
):
    """Get a specific index"""
    try:
        result = await rag_service.get_index(db=db, index_id=index_id)

        if not result:
            raise HTTPException(status_code=404, detail="Index not found")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get index: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/indexes/{index_id}/stats",
    response_model=dict,
    summary="Get Index Statistics",
    description="Get statistics for a RAG index",
)
async def get_index_stats(
    index_id: int = Path(..., description="Index ID"),
    db: AsyncSession = Depends(get_db),
    rag_service=Depends(get_rag_service),
):
    """Get index statistics"""
    try:
        result = await rag_service.get_index_stats(db=db, index_id=index_id)
        return result

    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Index not found")
        logger.error(f"Failed to get index stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Chunking Endpoints
# ============================================================================


@router.post(
    "/chunk",
    response_model=dict,
    summary="Chunk Video Content",
    description="Split video content into chunks for RAG",
)
async def chunk_video(
    request: ChunkVideoRequest,
    db: AsyncSession = Depends(get_db),
    rag_service=Depends(get_rag_service),
):
    """Chunk video content"""
    try:
        result = await rag_service.chunk_video_content(
            db=db,
            video_id=request.video_id,
            include_captions=request.include_captions,
            include_description=request.include_description,
            include_comments=request.include_comments,
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap,
        )

        return result

    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Video not found")
        logger.error(f"Failed to chunk video: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Embedding Endpoints
# ============================================================================


@router.post(
    "/embed",
    response_model=dict,
    summary="Generate Embeddings",
    description="Generate embeddings for document chunks",
)
async def generate_embeddings(
    request: GenerateEmbeddingsRequest,
    db: AsyncSession = Depends(get_db),
    rag_service=Depends(get_rag_service),
):
    """Generate embeddings for chunks"""
    try:
        result = await rag_service.generate_embeddings(
            db=db,
            video_id=request.video_id,
            chunk_ids=request.chunk_ids,
            model_type=request.model_type,
            batch_size=request.batch_size,
        )

        return result

    except Exception as e:
        logger.error(f"Failed to generate embeddings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/videos/{video_id}/status",
    response_model=dict,
    summary="Get Video Embedding Status",
    description="Get embedding status for a video",
)
async def get_video_status(
    video_id: str = Path(..., min_length=11, max_length=11, description="Video ID"),
    db: AsyncSession = Depends(get_db),
    rag_service=Depends(get_rag_service),
):
    """Get embedding status for a video"""
    try:
        result = await rag_service.get_video_status(db=db, video_id=video_id)

        if not result:
            return {
                "video_id": video_id,
                "status": "not_processed",
                "message": "Video has not been processed for RAG",
            }

        return result

    except Exception as e:
        logger.error(f"Failed to get video status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Search Endpoints
# ============================================================================


@router.post(
    "/search",
    response_model=SearchResultResponse,
    summary="Search RAG Index",
    description="Search for relevant content using vector similarity",
)
async def search(
    request: SearchRequest,
    user_id: Optional[str] = Query(None, description="User identifier"),
    db: AsyncSession = Depends(get_db),
    rag_service=Depends(get_rag_service),
):
    """Search for relevant chunks"""
    try:
        result = await rag_service.search(
            db=db,
            query=request.query,
            user_id=user_id,
            video_id=request.video_id,
            index_id=request.index_id,
            top_k=request.top_k,
            similarity_threshold=request.similarity_threshold,
            source_types=request.source_types,
        )

        return SearchResultResponse(**result)

    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Generation Endpoints
# ============================================================================


@router.post(
    "/generate",
    response_model=GenerateResponseModel,
    summary="Generate RAG Response",
    description="Generate a response using retrieved context",
)
async def generate_response(
    request: GenerateRequest,
    user_id: Optional[str] = Query(None, description="User identifier"),
    db: AsyncSession = Depends(get_db),
    rag_service=Depends(get_rag_service),
):
    """Generate RAG response"""
    try:
        result = await rag_service.generate_response(
            db=db,
            query=request.query,
            user_id=user_id,
            video_id=request.video_id,
            top_k=request.top_k,
            model_type=request.model_type,
        )

        return GenerateResponseModel(**result)

    except Exception as e:
        logger.error(f"Generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/queries/{query_id}/rate",
    summary="Rate RAG Response",
    description="Rate a RAG response for feedback",
)
async def rate_response(
    query_id: int = Path(..., description="Query ID"),
    request: RateResponseRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    rag_service=Depends(get_rag_service),
):
    """Rate a RAG response"""
    try:
        result = await rag_service.rate_response(
            db=db,
            query_id=query_id,
            rating=request.rating,
            feedback=request.feedback,
        )

        if not result:
            raise HTTPException(status_code=404, detail="Query not found")

        return {
            "message": "Rating submitted successfully",
            "query_id": query_id,
            "rating": request.rating,
        }

    except HTTPException:
        raise
    except Exception as e:
        if "between" in str(e).lower():
            raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")
        logger.error(f"Failed to rate response: {e}")
        raise HTTPException(status_code=500, detail=str(e))


__all__ = ["router"]
