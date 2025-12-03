# src/infrastructure/repositories/rag_repository.py
"""
RAG Repository
Database operations for RAG entities (chunks, embeddings, indexes)
"""

from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, delete, update
from sqlalchemy.orm import selectinload
import logging
import struct
import numpy as np

from src.infrastructure.repositories.base import BaseRepository
from src.app.models import (
    DocumentChunk,
    ChunkEmbedding,
    RAGIndex,
    RAGQuery,
    VideoEmbeddingStatus,
)

logger = logging.getLogger(__name__)


class DocumentChunkRepository(BaseRepository[DocumentChunk]):
    """Repository for DocumentChunk operations"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, DocumentChunk)

    async def get_by_video_id(
        self,
        video_id: str,
        source_type: Optional[str] = None,
        embedded_only: bool = False,
        skip: int = 0,
        limit: int = 100,
    ) -> List[DocumentChunk]:
        """
        Get chunks for a video

        Args:
            video_id: Video ID
            source_type: Filter by source type
            embedded_only: Only return embedded chunks
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of document chunks
        """
        try:
            query = select(DocumentChunk).where(DocumentChunk.video_id == video_id)

            if source_type:
                query = query.where(DocumentChunk.source_type == source_type)

            if embedded_only:
                query = query.where(DocumentChunk.is_embedded == True)

            query = query.order_by(DocumentChunk.chunk_index)
            query = query.offset(skip).limit(limit)

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get chunks for video {video_id}: {e}")
            raise

    async def get_unembedded_chunks(
        self,
        limit: int = 100,
        source_type: Optional[str] = None,
    ) -> List[DocumentChunk]:
        """
        Get chunks without embeddings

        Args:
            limit: Maximum chunks to return
            source_type: Optional filter by source type

        Returns:
            List of unembedded chunks
        """
        try:
            query = select(DocumentChunk).where(DocumentChunk.is_embedded == False)

            if source_type:
                query = query.where(DocumentChunk.source_type == source_type)

            query = query.order_by(DocumentChunk.created_at)
            query = query.limit(limit)

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get unembedded chunks: {e}")
            raise

    async def mark_as_embedded(
        self,
        chunk_id: int,
        model_type: str,
    ) -> bool:
        """
        Mark a chunk as embedded

        Args:
            chunk_id: Chunk ID
            model_type: Embedding model used

        Returns:
            True if updated
        """
        try:
            stmt = (
                update(DocumentChunk)
                .where(DocumentChunk.id == chunk_id)
                .values(
                    is_embedded=True,
                    embedding_model=model_type,
                    updated_at=datetime.utcnow(),
                )
            )
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount > 0
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to mark chunk {chunk_id} as embedded: {e}")
            raise

    async def search_by_content(
        self,
        query_text: str,
        video_id: Optional[str] = None,
        source_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[DocumentChunk]:
        """
        Search chunks by content text

        Args:
            query_text: Search text
            video_id: Optional video filter
            source_type: Optional source type filter
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of matching chunks
        """
        try:
            query = select(DocumentChunk).where(
                DocumentChunk.content.ilike(f"%{query_text}%")
            )

            if video_id:
                query = query.where(DocumentChunk.video_id == video_id)

            if source_type:
                query = query.where(DocumentChunk.source_type == source_type)

            query = query.offset(skip).limit(limit)

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to search chunks: {e}")
            raise

    async def count_by_video(
        self,
        video_id: str,
        embedded_only: bool = False,
    ) -> int:
        """Count chunks for a video"""
        try:
            query = (
                select(func.count())
                .select_from(DocumentChunk)
                .where(DocumentChunk.video_id == video_id)
            )

            if embedded_only:
                query = query.where(DocumentChunk.is_embedded == True)

            result = await self.session.execute(query)
            return int(result.scalar_one_or_none() or 0)
        except Exception as e:
            logger.error(f"Failed to count chunks for video {video_id}: {e}")
            raise

    async def delete_by_video(self, video_id: str) -> int:
        """Delete all chunks for a video"""
        try:
            stmt = delete(DocumentChunk).where(DocumentChunk.video_id == video_id)
            result = await self.session.execute(stmt)
            await self.session.commit()
            deleted_count = result.rowcount or 0
            logger.info(f"Deleted {deleted_count} chunks for video {video_id}")
            return deleted_count
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to delete chunks for video {video_id}: {e}")
            raise

    async def bulk_create_chunks(
        self,
        chunks: List[Dict[str, Any]],
    ) -> List[DocumentChunk]:
        """
        Bulk create document chunks

        Args:
            chunks: List of chunk data

        Returns:
            List of created chunks
        """
        try:
            return await self.bulk_create(chunks)
        except Exception as e:
            logger.error(f"Failed to bulk create chunks: {e}")
            raise


class ChunkEmbeddingRepository(BaseRepository[ChunkEmbedding]):
    """Repository for ChunkEmbedding operations"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, ChunkEmbedding)

    async def get_by_chunk_id(self, chunk_id: int) -> Optional[ChunkEmbedding]:
        """Get embedding for a chunk"""
        try:
            query = select(ChunkEmbedding).where(ChunkEmbedding.chunk_id == chunk_id)
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to get embedding for chunk {chunk_id}: {e}")
            raise

    async def get_embeddings_for_video(
        self,
        video_id: str,
        limit: int = 1000,
    ) -> List[Tuple[int, bytes]]:
        """
        Get all embeddings for a video

        Args:
            video_id: Video ID
            limit: Maximum embeddings

        Returns:
            List of (chunk_id, embedding) tuples
        """
        try:
            query = (
                select(ChunkEmbedding.chunk_id, ChunkEmbedding.embedding)
                .join(DocumentChunk)
                .where(DocumentChunk.video_id == video_id)
                .limit(limit)
            )

            result = await self.session.execute(query)
            return [(row.chunk_id, row.embedding) for row in result.all()]
        except Exception as e:
            logger.error(f"Failed to get embeddings for video {video_id}: {e}")
            raise

    async def create_embedding(
        self,
        chunk_id: int,
        embedding: bytes,
        dimension: int,
        model_type: str,
        model_version: Optional[str] = None,
        norm: Optional[float] = None,
    ) -> ChunkEmbedding:
        """
        Create an embedding for a chunk

        Args:
            chunk_id: Chunk ID
            embedding: Serialized embedding bytes
            dimension: Embedding dimension
            model_type: Embedding model type
            model_version: Optional model version
            norm: Optional L2 norm

        Returns:
            Created embedding
        """
        try:
            return await self.create(
                chunk_id=chunk_id,
                embedding=embedding,
                embedding_dimension=dimension,
                model_type=model_type,
                model_version=model_version,
                norm=norm,
            )
        except Exception as e:
            logger.error(f"Failed to create embedding for chunk {chunk_id}: {e}")
            raise

    async def delete_by_chunk_id(self, chunk_id: int) -> bool:
        """Delete embedding for a chunk"""
        try:
            stmt = delete(ChunkEmbedding).where(ChunkEmbedding.chunk_id == chunk_id)
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount > 0
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to delete embedding for chunk {chunk_id}: {e}")
            raise

    @staticmethod
    def serialize_embedding(embedding: List[float]) -> bytes:
        """Serialize embedding vector to bytes"""
        return struct.pack(f"{len(embedding)}f", *embedding)

    @staticmethod
    def deserialize_embedding(data: bytes) -> List[float]:
        """Deserialize bytes to embedding vector"""
        count = len(data) // 4  # 4 bytes per float
        return list(struct.unpack(f"{count}f", data))


class RAGIndexRepository(BaseRepository[RAGIndex]):
    """Repository for RAGIndex operations"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, RAGIndex)

    async def get_by_name(self, name: str) -> Optional[RAGIndex]:
        """Get index by name"""
        try:
            query = select(RAGIndex).where(RAGIndex.name == name)
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to get index by name {name}: {e}")
            raise

    async def get_active_indexes(self) -> List[RAGIndex]:
        """Get all active indexes"""
        try:
            query = (
                select(RAGIndex)
                .where(RAGIndex.is_active == True)
                .order_by(RAGIndex.created_at.desc())
            )
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get active indexes: {e}")
            raise

    async def update_statistics(
        self,
        index_id: int,
        total_chunks: int,
        total_videos: int,
    ) -> bool:
        """
        Update index statistics

        Args:
            index_id: Index ID
            total_chunks: Total chunks count
            total_videos: Total videos count

        Returns:
            True if updated
        """
        try:
            stmt = (
                update(RAGIndex)
                .where(RAGIndex.id == index_id)
                .values(
                    total_chunks=total_chunks,
                    total_videos=total_videos,
                    last_updated=datetime.utcnow(),
                )
            )
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount > 0
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to update statistics for index {index_id}: {e}")
            raise

    async def deactivate_index(self, index_id: int) -> bool:
        """Deactivate an index"""
        try:
            stmt = (
                update(RAGIndex)
                .where(RAGIndex.id == index_id)
                .values(is_active=False)
            )
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount > 0
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to deactivate index {index_id}: {e}")
            raise


class RAGQueryRepository(BaseRepository[RAGQuery]):
    """Repository for RAGQuery operations"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, RAGQuery)

    async def get_by_user_id(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
    ) -> List[RAGQuery]:
        """Get queries for a user"""
        try:
            query = (
                select(RAGQuery)
                .where(RAGQuery.user_id == user_id)
                .order_by(RAGQuery.created_at.desc())
                .offset(skip)
                .limit(limit)
            )
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get queries for user {user_id}: {e}")
            raise

    async def get_recent_queries(
        self,
        hours: int = 24,
        limit: int = 100,
    ) -> List[RAGQuery]:
        """Get recent queries"""
        try:
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            query = (
                select(RAGQuery)
                .where(RAGQuery.created_at >= cutoff)
                .order_by(RAGQuery.created_at.desc())
                .limit(limit)
            )
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get recent queries: {e}")
            raise

    async def update_feedback(
        self,
        query_id: int,
        rating: int,
        feedback: Optional[str] = None,
    ) -> bool:
        """Update feedback for a query"""
        try:
            values = {"user_rating": rating}
            if feedback:
                values["user_feedback"] = feedback

            stmt = (
                update(RAGQuery)
                .where(RAGQuery.id == query_id)
                .values(**values)
            )
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount > 0
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to update feedback for query {query_id}: {e}")
            raise

    async def get_average_metrics(
        self,
        index_id: Optional[int] = None,
    ) -> Dict[str, float]:
        """Get average query metrics"""
        try:
            query = select(
                func.avg(RAGQuery.search_time_ms).label("avg_search_time"),
                func.avg(RAGQuery.total_time_ms).label("avg_total_time"),
                func.avg(RAGQuery.result_count).label("avg_results"),
                func.avg(RAGQuery.user_rating).label("avg_rating"),
            )

            if index_id:
                query = query.where(RAGQuery.index_id == index_id)

            result = await self.session.execute(query)
            row = result.one()

            return {
                "avg_search_time_ms": float(row.avg_search_time or 0),
                "avg_total_time_ms": float(row.avg_total_time or 0),
                "avg_results": float(row.avg_results or 0),
                "avg_rating": float(row.avg_rating or 0),
            }
        except Exception as e:
            logger.error(f"Failed to get average metrics: {e}")
            raise


class VideoEmbeddingStatusRepository(BaseRepository[VideoEmbeddingStatus]):
    """Repository for VideoEmbeddingStatus operations"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, VideoEmbeddingStatus)

    async def get_by_video_id(self, video_id: str) -> Optional[VideoEmbeddingStatus]:
        """Get embedding status for a video"""
        try:
            query = select(VideoEmbeddingStatus).where(
                VideoEmbeddingStatus.video_id == video_id
            )
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to get embedding status for video {video_id}: {e}")
            raise

    async def get_or_create(self, video_id: str) -> VideoEmbeddingStatus:
        """Get or create embedding status for a video"""
        try:
            existing = await self.get_by_video_id(video_id)
            if existing:
                return existing

            return await self.create(video_id=video_id)
        except Exception as e:
            logger.error(f"Failed to get/create status for video {video_id}: {e}")
            raise

    async def update_status(
        self,
        video_id: str,
        caption_embedded: Optional[bool] = None,
        description_embedded: Optional[bool] = None,
        comments_embedded: Optional[bool] = None,
        frames_embedded: Optional[bool] = None,
        total_chunks: Optional[int] = None,
        embedded_chunks: Optional[int] = None,
        processing_error: Optional[str] = None,
    ) -> bool:
        """Update embedding status for a video"""
        try:
            values = {"last_processed": datetime.utcnow()}

            if caption_embedded is not None:
                values["caption_embedded"] = caption_embedded
            if description_embedded is not None:
                values["description_embedded"] = description_embedded
            if comments_embedded is not None:
                values["comments_embedded"] = comments_embedded
            if frames_embedded is not None:
                values["frames_embedded"] = frames_embedded
            if total_chunks is not None:
                values["total_chunks"] = total_chunks
            if embedded_chunks is not None:
                values["embedded_chunks"] = embedded_chunks
            if processing_error is not None:
                values["processing_error"] = processing_error

            stmt = (
                update(VideoEmbeddingStatus)
                .where(VideoEmbeddingStatus.video_id == video_id)
                .values(**values)
            )
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount > 0
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to update status for video {video_id}: {e}")
            raise

    async def get_videos_needing_embedding(
        self,
        limit: int = 100,
    ) -> List[VideoEmbeddingStatus]:
        """Get videos that need embedding processing"""
        try:
            query = (
                select(VideoEmbeddingStatus)
                .where(
                    or_(
                        VideoEmbeddingStatus.caption_embedded == False,
                        VideoEmbeddingStatus.description_embedded == False,
                    )
                )
                .order_by(VideoEmbeddingStatus.created_at)
                .limit(limit)
            )
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get videos needing embedding: {e}")
            raise


__all__ = [
    "DocumentChunkRepository",
    "ChunkEmbeddingRepository",
    "RAGIndexRepository",
    "RAGQueryRepository",
    "VideoEmbeddingStatusRepository",
]
