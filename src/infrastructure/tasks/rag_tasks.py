# src/infrastructure/tasks/rag_tasks.py
"""
RAG Background Tasks
Celery tasks for Retrieval-Augmented Generation operations
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from src.infrastructure.tasks.celery_app import celery_app
from src.app.database import db_manager
from src.infrastructure.repositories import (
    DocumentChunkRepository,
    ChunkEmbeddingRepository,
    RAGIndexRepository,
    RAGQueryRepository,
    VideoEmbeddingStatusRepository,
    VideoRepository,
    CaptionRepository,
)
from src.services.task_tracking_service import create_task_record, update_task_status

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="tasks.rag.chunk_video_content",
    max_retries=2,
    default_retry_delay=120,
)
def chunk_video_content(
    self,
    video_id: str,
    include_captions: bool = True,
    include_description: bool = True,
    include_comments: bool = False,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Chunk video content for RAG

    Args:
        video_id: Video ID
        include_captions: Include caption content
        include_description: Include video description
        include_comments: Include comments
        chunk_size: Target chunk size in tokens
        chunk_overlap: Overlap between chunks
        user_id: User identifier

    Returns:
        Chunking result
    """
    import asyncio

    async def _chunk():
        await create_task_record(
            task_id=self.request.id,
            task_name="chunk_video_content",
            task_type="rag",
            args=(video_id,),
            kwargs={
                "include_captions": include_captions,
                "include_description": include_description,
                "chunk_size": chunk_size,
            },
            user_id=user_id,
        )

        logger.info(f"📄 Chunking content for video: {video_id}")

        try:
            from src.services.rag_service import RAGService

            async with db_manager.session() as session:
                rag_service = RAGService(
                    chunk_repo=DocumentChunkRepository(session),
                    embedding_repo=ChunkEmbeddingRepository(session),
                    index_repo=RAGIndexRepository(session),
                    query_repo=RAGQueryRepository(session),
                    status_repo=VideoEmbeddingStatusRepository(session),
                    video_repo=VideoRepository(session),
                    caption_repo=CaptionRepository(session),
                )

                await update_task_status(
                    self.request.id, "running", progress=30
                )

                result = await rag_service.chunk_video_content(
                    db=session,
                    video_id=video_id,
                    include_captions=include_captions,
                    include_description=include_description,
                    include_comments=include_comments,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )

                logger.info(
                    f"✅ Created {result.get('chunks_created', 0)} chunks "
                    f"for video {video_id}"
                )

                await update_task_status(
                    self.request.id, "success", progress=100, result=result
                )

                return result

        except Exception as e:
            logger.error(f"Failed to chunk video content for {video_id}: {e}")
            await update_task_status(
                self.request.id, "failed", error_message=str(e)
            )
            raise self.retry(exc=e)

    return asyncio.run(_chunk())


@celery_app.task(
    bind=True,
    name="tasks.rag.generate_embeddings",
    max_retries=3,
    default_retry_delay=60,
)
def generate_embeddings(
    self,
    video_id: Optional[str] = None,
    chunk_ids: Optional[List[int]] = None,
    model_type: str = "text-embedding-3-small",
    batch_size: int = 100,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Generate embeddings for document chunks

    Args:
        video_id: Optional video ID to process
        chunk_ids: Optional specific chunk IDs
        model_type: Embedding model to use
        batch_size: Batch size for processing
        user_id: User identifier

    Returns:
        Embedding generation result
    """
    import asyncio

    async def _embed():
        await create_task_record(
            task_id=self.request.id,
            task_name="generate_embeddings",
            task_type="rag",
            args=(video_id,) if video_id else (),
            kwargs={"model_type": model_type, "batch_size": batch_size},
            user_id=user_id,
        )

        logger.info(f"🔢 Generating embeddings (video={video_id})")

        try:
            from src.services.rag_service import RAGService

            async with db_manager.session() as session:
                rag_service = RAGService(
                    chunk_repo=DocumentChunkRepository(session),
                    embedding_repo=ChunkEmbeddingRepository(session),
                    index_repo=RAGIndexRepository(session),
                    query_repo=RAGQueryRepository(session),
                    status_repo=VideoEmbeddingStatusRepository(session),
                    video_repo=VideoRepository(session),
                    caption_repo=CaptionRepository(session),
                )

                await update_task_status(
                    self.request.id, "running", progress=30
                )

                result = await rag_service.generate_embeddings(
                    db=session,
                    video_id=video_id,
                    chunk_ids=chunk_ids,
                    model_type=model_type,
                    batch_size=batch_size,
                )

                logger.info(
                    f"✅ Generated {result.get('embeddings_created', 0)} embeddings"
                )

                await update_task_status(
                    self.request.id, "success", progress=100, result=result
                )

                return result

        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            await update_task_status(
                self.request.id, "failed", error_message=str(e)
            )
            raise self.retry(exc=e)

    return asyncio.run(_embed())


@celery_app.task(
    bind=True,
    name="tasks.rag.full_video_rag_pipeline",
    max_retries=2,
    default_retry_delay=300,
)
def full_video_rag_pipeline(
    self,
    video_id: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    model_type: str = "text-embedding-3-small",
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Full RAG pipeline: chunk + embed

    Args:
        video_id: Video ID
        chunk_size: Target chunk size in tokens
        chunk_overlap: Overlap between chunks
        model_type: Embedding model to use
        user_id: User identifier

    Returns:
        Pipeline result
    """
    import asyncio

    async def _pipeline():
        await create_task_record(
            task_id=self.request.id,
            task_name="full_video_rag_pipeline",
            task_type="rag",
            args=(video_id,),
            kwargs={
                "chunk_size": chunk_size,
                "model_type": model_type,
            },
            user_id=user_id,
        )

        logger.info(f"🚀 Starting full RAG pipeline for video {video_id}")

        results = {
            "video_id": video_id,
            "chunking": None,
            "embedding": None,
            "started_at": datetime.utcnow().isoformat(),
        }

        try:
            from src.services.rag_service import RAGService

            async with db_manager.session() as session:
                rag_service = RAGService(
                    chunk_repo=DocumentChunkRepository(session),
                    embedding_repo=ChunkEmbeddingRepository(session),
                    index_repo=RAGIndexRepository(session),
                    query_repo=RAGQueryRepository(session),
                    status_repo=VideoEmbeddingStatusRepository(session),
                    video_repo=VideoRepository(session),
                    caption_repo=CaptionRepository(session),
                )

                # Step 1: Chunk content
                await update_task_status(
                    self.request.id, "running", progress=10
                )
                logger.info(f"Step 1: Chunking content for {video_id}")

                chunking_result = await rag_service.chunk_video_content(
                    db=session,
                    video_id=video_id,
                    include_captions=True,
                    include_description=True,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )
                results["chunking"] = chunking_result

                await update_task_status(
                    self.request.id, "running", progress=50
                )

                # Step 2: Generate embeddings
                logger.info(f"Step 2: Generating embeddings for {video_id}")

                embedding_result = await rag_service.generate_embeddings(
                    db=session,
                    video_id=video_id,
                    model_type=model_type,
                    batch_size=100,
                )
                results["embedding"] = embedding_result

                results["completed_at"] = datetime.utcnow().isoformat()

                logger.info(f"✅ Full RAG pipeline complete for {video_id}")

                await update_task_status(
                    self.request.id, "success", progress=100, result=results
                )

                return results

        except Exception as e:
            logger.error(f"RAG pipeline failed for {video_id}: {e}")
            results["error"] = str(e)
            await update_task_status(
                self.request.id, "failed", error_message=str(e)
            )
            raise self.retry(exc=e)

    return asyncio.run(_pipeline())


@celery_app.task(
    bind=True,
    name="tasks.rag.batch_process_videos",
    max_retries=1,
)
def batch_process_videos(
    self,
    video_ids: List[str],
    chunk_size: int = 500,
    model_type: str = "text-embedding-3-small",
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Batch process multiple videos for RAG

    Args:
        video_ids: List of video IDs
        chunk_size: Target chunk size in tokens
        model_type: Embedding model to use
        user_id: User identifier

    Returns:
        Batch processing result
    """
    import asyncio

    async def _batch():
        await create_task_record(
            task_id=self.request.id,
            task_name="batch_process_videos",
            task_type="rag",
            args=(video_ids,),
            kwargs={"chunk_size": chunk_size, "model_type": model_type},
            user_id=user_id,
        )

        logger.info(f"📄 Batch processing {len(video_ids)} videos for RAG")

        results = {
            "total_videos": len(video_ids),
            "success": [],
            "failed": [],
            "started_at": datetime.utcnow().isoformat(),
        }

        try:
            from src.services.rag_service import RAGService

            async with db_manager.session() as session:
                rag_service = RAGService(
                    chunk_repo=DocumentChunkRepository(session),
                    embedding_repo=ChunkEmbeddingRepository(session),
                    index_repo=RAGIndexRepository(session),
                    query_repo=RAGQueryRepository(session),
                    status_repo=VideoEmbeddingStatusRepository(session),
                    video_repo=VideoRepository(session),
                    caption_repo=CaptionRepository(session),
                )

                for i, video_id in enumerate(video_ids):
                    progress = int((i / len(video_ids)) * 90) + 5
                    await update_task_status(
                        self.request.id, "running", progress=progress
                    )

                    try:
                        # Chunk content
                        chunk_result = await rag_service.chunk_video_content(
                            db=session,
                            video_id=video_id,
                            include_captions=True,
                            include_description=True,
                            chunk_size=chunk_size,
                            chunk_overlap=50,
                        )

                        # Generate embeddings
                        embed_result = await rag_service.generate_embeddings(
                            db=session,
                            video_id=video_id,
                            model_type=model_type,
                            batch_size=100,
                        )

                        results["success"].append({
                            "video_id": video_id,
                            "chunks_created": chunk_result.get("chunks_created", 0),
                            "embeddings_created": embed_result.get("embeddings_created", 0),
                        })

                    except Exception as e:
                        logger.warning(
                            f"Failed to process video {video_id}: {e}"
                        )
                        results["failed"].append({
                            "video_id": video_id,
                            "error": str(e),
                        })

            results["completed_at"] = datetime.utcnow().isoformat()

            logger.info(
                f"✅ Batch processing complete: "
                f"{len(results['success'])} success, "
                f"{len(results['failed'])} failed"
            )

            await update_task_status(
                self.request.id, "success", progress=100, result=results
            )

            return results

        except Exception as e:
            logger.error(f"Batch processing failed: {e}")
            results["error"] = str(e)
            await update_task_status(
                self.request.id, "failed", error_message=str(e)
            )
            raise

    return asyncio.run(_batch())


@celery_app.task(
    bind=True,
    name="tasks.rag.update_index_stats",
    max_retries=1,
)
def update_index_stats(
    self,
    index_id: int,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Update statistics for a RAG index

    Args:
        index_id: Index ID
        user_id: User identifier

    Returns:
        Updated stats
    """
    import asyncio

    async def _update():
        await create_task_record(
            task_id=self.request.id,
            task_name="update_index_stats",
            task_type="rag",
            args=(index_id,),
            user_id=user_id,
        )

        logger.info(f"📊 Updating stats for index {index_id}")

        try:
            from sqlalchemy import func, select
            from src.app.models import DocumentChunk

            async with db_manager.session() as session:
                index_repo = RAGIndexRepository(session)
                chunk_repo = DocumentChunkRepository(session)

                # Get index
                index = await index_repo.get_by_id(index_id)
                if not index:
                    raise ValueError(f"Index {index_id} not found")

                # Count total chunks with embeddings
                total_chunks_query = (
                    select(func.count())
                    .select_from(DocumentChunk)
                    .where(DocumentChunk.is_embedded == True)
                )
                result = await session.execute(total_chunks_query)
                total_chunks = result.scalar_one_or_none() or 0

                # Count unique videos
                unique_videos_query = (
                    select(func.count(func.distinct(DocumentChunk.video_id)))
                    .where(DocumentChunk.is_embedded == True)
                )
                result = await session.execute(unique_videos_query)
                total_videos = result.scalar_one_or_none() or 0

                # Update index
                await index_repo.update_statistics(
                    index_id=index_id,
                    total_chunks=total_chunks,
                    total_videos=total_videos,
                )

                result = {
                    "index_id": index_id,
                    "total_chunks": total_chunks,
                    "total_videos": total_videos,
                    "updated_at": datetime.utcnow().isoformat(),
                }

                logger.info(
                    f"✅ Updated index {index_id}: "
                    f"{total_chunks} chunks, {total_videos} videos"
                )

                await update_task_status(
                    self.request.id, "success", progress=100, result=result
                )

                return result

        except Exception as e:
            logger.error(f"Failed to update index stats: {e}")
            await update_task_status(
                self.request.id, "failed", error_message=str(e)
            )
            raise

    return asyncio.run(_update())


@celery_app.task(
    bind=True,
    name="tasks.rag.cleanup_orphan_embeddings",
    max_retries=1,
)
def cleanup_orphan_embeddings(
    self,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Clean up orphaned embeddings

    Args:
        user_id: User identifier

    Returns:
        Cleanup result
    """
    import asyncio
    from sqlalchemy import delete, select

    async def _cleanup():
        await create_task_record(
            task_id=self.request.id,
            task_name="cleanup_orphan_embeddings",
            task_type="rag",
            args=(),
            user_id=user_id,
        )

        logger.info("🧹 Cleaning up orphan embeddings")

        try:
            from src.app.models import ChunkEmbedding, DocumentChunk

            async with db_manager.session() as session:
                # Find embeddings without corresponding chunks
                orphan_query = (
                    select(ChunkEmbedding.id)
                    .outerjoin(DocumentChunk, ChunkEmbedding.chunk_id == DocumentChunk.id)
                    .where(DocumentChunk.id.is_(None))
                )

                result = await session.execute(orphan_query)
                orphan_ids = [row[0] for row in result.all()]

                if orphan_ids:
                    delete_stmt = delete(ChunkEmbedding).where(
                        ChunkEmbedding.id.in_(orphan_ids)
                    )
                    await session.execute(delete_stmt)
                    await session.commit()

                result = {
                    "orphan_embeddings_deleted": len(orphan_ids),
                    "cleaned_at": datetime.utcnow().isoformat(),
                }

                logger.info(f"✅ Cleaned up {len(orphan_ids)} orphan embeddings")

                await update_task_status(
                    self.request.id, "success", progress=100, result=result
                )

                return result

        except Exception as e:
            logger.error(f"Failed to cleanup orphan embeddings: {e}")
            await update_task_status(
                self.request.id, "failed", error_message=str(e)
            )
            raise

    return asyncio.run(_cleanup())


# ============================================================================
# Exported Tasks
# ============================================================================

__all__ = [
    "chunk_video_content",
    "generate_embeddings",
    "full_video_rag_pipeline",
    "batch_process_videos",
    "update_index_stats",
    "cleanup_orphan_embeddings",
]
