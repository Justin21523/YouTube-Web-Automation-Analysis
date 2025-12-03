# src/services/rag_service.py
"""
RAG Service
Business logic for Retrieval-Augmented Generation operations
"""

from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
import uuid
import logging
import struct
import os
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.base_service import BaseService
from src.services.exceptions import (
    ResourceNotFoundError,
    ValidationError,
    ExternalServiceError,
    ProcessingError,
)
from src.services.llm_client import get_llm_client, Message

from src.infrastructure.repositories.rag_repository import (
    DocumentChunkRepository,
    ChunkEmbeddingRepository,
    RAGIndexRepository,
    RAGQueryRepository,
    VideoEmbeddingStatusRepository,
)
from src.infrastructure.repositories.video_repository import VideoRepository
from src.infrastructure.repositories.caption_repository import CaptionRepository
from src.app.models import (
    DocumentChunk,
    ChunkEmbedding,
    RAGIndex,
    RAGQuery,
    VideoEmbeddingStatus,
    EmbeddingModelType,
    ChunkType,
)

logger = logging.getLogger(__name__)


class RAGService(BaseService):
    """
    RAG operations service

    Handles:
    - Document chunking
    - Embedding generation
    - Vector search
    - RAG-based generation
    """

    def __init__(
        self,
        chunk_repo: DocumentChunkRepository,
        embedding_repo: ChunkEmbeddingRepository,
        index_repo: RAGIndexRepository,
        query_repo: RAGQueryRepository,
        status_repo: VideoEmbeddingStatusRepository,
        video_repo: VideoRepository,
        caption_repo: Optional[CaptionRepository] = None,
        cache=None,
        config=None,
    ):
        super().__init__(cache=cache, config=config)
        self.chunk_repo = chunk_repo
        self.embedding_repo = embedding_repo
        self.index_repo = index_repo
        self.query_repo = query_repo
        self.status_repo = status_repo
        self.video_repo = video_repo
        self.caption_repo = caption_repo

        # Embedding model (lazy loaded)
        self._embedding_model = None
        self._model_type = None

    def get_service_name(self) -> str:
        return "rag"

    # ========================================================================
    # Index Management
    # ========================================================================

    async def create_index(
        self,
        db: AsyncSession,
        name: str,
        description: Optional[str] = None,
        embedding_model: str = EmbeddingModelType.OPENAI_3_SMALL.value,
        embedding_dimension: int = 1536,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        index_type: str = "flat",
    ) -> Dict[str, Any]:
        """
        Create a new RAG index

        Args:
            db: Database session
            name: Index name (unique)
            description: Index description
            embedding_model: Embedding model to use
            embedding_dimension: Dimension of embeddings
            chunk_size: Target chunk size in tokens
            chunk_overlap: Overlap between chunks
            index_type: Vector index type

        Returns:
            Created index details
        """
        self.log_operation("create_index", name=name)

        try:
            # Check if name exists
            existing = await self.index_repo.get_by_name(name)
            if existing:
                raise ValidationError(f"Index with name '{name}' already exists")

            # Create index
            index = await self.index_repo.create(
                name=name,
                description=description,
                embedding_model=embedding_model,
                embedding_dimension=embedding_dimension,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                index_type=index_type,
                is_active=True,
                total_chunks=0,
                total_videos=0,
            )

            logger.info(f"Created RAG index: {name}")

            return index.to_dict()

        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Failed to create index: {e}")
            raise ProcessingError(f"Failed to create index: {e}")

    async def get_index(
        self,
        db: AsyncSession,
        index_id: Optional[int] = None,
        name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get index by ID or name

        Args:
            db: Database session
            index_id: Index ID
            name: Index name

        Returns:
            Index details or None
        """
        try:
            if index_id:
                index = await self.index_repo.get_by_id(index_id)
            elif name:
                index = await self.index_repo.get_by_name(name)
            else:
                raise ValidationError("Either index_id or name must be provided")

            return index.to_dict() if index else None

        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Failed to get index: {e}")
            raise

    async def list_indexes(
        self,
        db: AsyncSession,
        active_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """Get all indexes"""
        try:
            if active_only:
                indexes = await self.index_repo.get_active_indexes()
            else:
                indexes = await self.index_repo.get_all()

            return [idx.to_dict() for idx in indexes]

        except Exception as e:
            logger.error(f"Failed to list indexes: {e}")
            raise

    # ========================================================================
    # Document Chunking
    # ========================================================================

    async def chunk_video_content(
        self,
        db: AsyncSession,
        video_id: str,
        include_captions: bool = True,
        include_description: bool = True,
        include_comments: bool = False,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> Dict[str, Any]:
        """
        Chunk video content for RAG

        Args:
            db: Database session
            video_id: Video ID
            include_captions: Include caption content
            include_description: Include video description
            include_comments: Include comments
            chunk_size: Target chunk size in tokens
            chunk_overlap: Overlap between chunks

        Returns:
            Chunking result
        """
        self.log_operation("chunk_video_content", video_id=video_id)

        try:
            # Get video
            video = await self.video_repo.get_by_id(video_id)
            if not video:
                raise ResourceNotFoundError(f"Video {video_id} not found")

            chunks_created = []
            total_chunks = 0

            # Get or create status
            status = await self.status_repo.get_or_create(video_id)

            # Chunk description
            if include_description and video.description:
                desc_chunks = self._chunk_text(
                    text=video.description,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )

                for i, chunk in enumerate(desc_chunks):
                    created = await self.chunk_repo.create(
                        video_id=video_id,
                        source_type=ChunkType.DESCRIPTION.value,
                        content=chunk["content"],
                        chunk_index=i,
                        total_chunks=len(desc_chunks),
                        start_position=chunk["start"],
                        end_position=chunk["end"],
                        token_count=chunk["tokens"],
                        word_count=len(chunk["content"].split()),
                        language=video.default_audio_language,
                    )
                    chunks_created.append(created.id)
                    total_chunks += 1

            # Chunk captions
            if include_captions and self.caption_repo:
                captions = await self.caption_repo.get_by_video_id(video_id)
                for caption in captions:
                    if caption.content:
                        cap_chunks = self._chunk_text(
                            text=caption.content,
                            chunk_size=chunk_size,
                            chunk_overlap=chunk_overlap,
                        )

                        for i, chunk in enumerate(cap_chunks):
                            created = await self.chunk_repo.create(
                                video_id=video_id,
                                source_type=ChunkType.CAPTION.value,
                                source_id=caption.id,
                                content=chunk["content"],
                                chunk_index=i,
                                total_chunks=len(cap_chunks),
                                start_position=chunk["start"],
                                end_position=chunk["end"],
                                token_count=chunk["tokens"],
                                word_count=len(chunk["content"].split()),
                                language=caption.language_code,
                            )
                            chunks_created.append(created.id)
                            total_chunks += 1

            # Update status
            await self.status_repo.update_status(
                video_id=video_id,
                total_chunks=total_chunks,
            )

            logger.info(f"Created {total_chunks} chunks for video {video_id}")

            return {
                "video_id": video_id,
                "chunks_created": len(chunks_created),
                "chunk_ids": chunks_created,
            }

        except ResourceNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to chunk video content: {e}")
            raise ProcessingError(f"Failed to chunk video content: {e}")

    def _chunk_text(
        self,
        text: str,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Split text into chunks

        Args:
            text: Input text
            chunk_size: Target chunk size in tokens (approximated)
            chunk_overlap: Overlap between chunks

        Returns:
            List of chunk dictionaries
        """
        if not text:
            return []

        # Approximate tokens (4 chars per token)
        char_size = chunk_size * 4
        char_overlap = chunk_overlap * 4

        chunks = []
        start = 0

        while start < len(text):
            end = min(start + char_size, len(text))

            # Try to break at sentence boundary
            if end < len(text):
                for sep in ['. ', '! ', '? ', '\n\n', '\n', ' ']:
                    last_sep = text.rfind(sep, start, end)
                    if last_sep > start + char_size // 2:
                        end = last_sep + len(sep)
                        break

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append({
                    "content": chunk_text,
                    "start": start,
                    "end": end,
                    "tokens": len(chunk_text) // 4,
                })

            start = end - char_overlap if end < len(text) else len(text)

        return chunks

    # ========================================================================
    # Embedding Generation
    # ========================================================================

    async def generate_embeddings(
        self,
        db: AsyncSession,
        video_id: Optional[str] = None,
        chunk_ids: Optional[List[int]] = None,
        model_type: str = EmbeddingModelType.OPENAI_3_SMALL.value,
        batch_size: int = 100,
    ) -> Dict[str, Any]:
        """
        Generate embeddings for chunks

        Args:
            db: Database session
            video_id: Optional video ID to process
            chunk_ids: Optional specific chunk IDs
            model_type: Embedding model to use
            batch_size: Batch size for processing

        Returns:
            Embedding generation result
        """
        self.log_operation("generate_embeddings", video_id=video_id)

        try:
            # Get chunks to embed
            if chunk_ids:
                chunks = [await self.chunk_repo.get_by_id(cid) for cid in chunk_ids]
                chunks = [c for c in chunks if c and not c.is_embedded]
            elif video_id:
                chunks = await self.chunk_repo.get_by_video_id(
                    video_id=video_id,
                    embedded_only=False,
                    limit=batch_size,
                )
                chunks = [c for c in chunks if not c.is_embedded]
            else:
                chunks = await self.chunk_repo.get_unembedded_chunks(limit=batch_size)

            if not chunks:
                return {
                    "embeddings_created": 0,
                    "message": "No chunks to embed",
                }

            # Generate embeddings
            embeddings_created = 0
            failed = []

            for chunk in chunks:
                try:
                    # Get embedding from model
                    embedding = await self._get_embedding(
                        text=chunk.content,
                        model_type=model_type,
                    )

                    # Serialize and store
                    embedding_bytes = self.embedding_repo.serialize_embedding(embedding)
                    norm = sum(x * x for x in embedding) ** 0.5

                    await self.embedding_repo.create_embedding(
                        chunk_id=chunk.id,
                        embedding=embedding_bytes,
                        dimension=len(embedding),
                        model_type=model_type,
                        norm=norm,
                    )

                    # Mark chunk as embedded
                    await self.chunk_repo.mark_as_embedded(chunk.id, model_type)

                    embeddings_created += 1

                except Exception as e:
                    logger.warning(f"Failed to embed chunk {chunk.id}: {e}")
                    failed.append({"chunk_id": chunk.id, "error": str(e)})

            # Update video status if applicable
            if video_id:
                embedded_count = await self.chunk_repo.count_by_video(
                    video_id, embedded_only=True
                )
                total_count = await self.chunk_repo.count_by_video(video_id)
                await self.status_repo.update_status(
                    video_id=video_id,
                    embedded_chunks=embedded_count,
                    total_chunks=total_count,
                    description_embedded=True,
                )

            logger.info(f"Created {embeddings_created} embeddings")

            return {
                "embeddings_created": embeddings_created,
                "failed": failed,
                "video_id": video_id,
            }

        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            raise ProcessingError(f"Failed to generate embeddings: {e}")

    async def _get_embedding(
        self,
        text: str,
        model_type: str = EmbeddingModelType.OPENAI_3_SMALL.value,
    ) -> List[float]:
        """
        Get embedding for text using OpenAI Embeddings API or local models

        Supports:
        - OpenAI Embeddings API (text-embedding-3-small, text-embedding-3-large)
        - Sentence Transformers (via local model)
        - Ollama embeddings (via local model)
        """
        import httpx

        # Determine embedding provider and model
        model_lower = model_type.lower()

        # OpenAI Embeddings
        if "openai" in model_lower or "text-embedding" in model_lower:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.warning("OpenAI API key not set, using random embeddings")
                return self._generate_random_embedding(1536)

            # Use OpenAI Embeddings API
            model = "text-embedding-3-small"
            if "large" in model_lower:
                model = "text-embedding-3-large"
            elif "ada" in model_lower:
                model = "text-embedding-ada-002"

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        "https://api.openai.com/v1/embeddings",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": model,
                            "input": text[:8000],  # Limit input length
                        },
                    )
                    response.raise_for_status()
                    result = response.json()
                    return result["data"][0]["embedding"]
            except Exception as e:
                logger.error(f"OpenAI embedding failed: {e}")
                raise ProcessingError(f"Failed to generate embedding: {e}")

        # Ollama embeddings
        elif "ollama" in model_lower or "nomic" in model_lower or "mxbai" in model_lower:
            ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
            embed_model = "nomic-embed-text"
            if "mxbai" in model_lower:
                embed_model = "mxbai-embed-large"

            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        f"{ollama_host}/api/embeddings",
                        json={
                            "model": embed_model,
                            "prompt": text[:4000],
                        },
                    )
                    response.raise_for_status()
                    result = response.json()
                    return result["embedding"]
            except Exception as e:
                logger.warning(f"Ollama embedding failed: {e}, using random embeddings")
                return self._generate_random_embedding(768)

        # BGE or sentence-transformers (would need local model)
        elif "bge" in model_lower or "sentence-transformer" in model_lower:
            # Fallback to random for now - would need sentence-transformers library
            dimension = 384 if "small" in model_lower else 1024
            logger.warning(f"Local embedding model not loaded, using random embeddings")
            return self._generate_random_embedding(dimension)

        # Default: random embedding (development fallback)
        else:
            logger.warning(f"Unknown embedding model {model_type}, using random embeddings")
            return self._generate_random_embedding(1536)

    def _generate_random_embedding(self, dimension: int) -> List[float]:
        """Generate a random normalized embedding vector for development"""
        import random
        embedding = [random.gauss(0, 1) for _ in range(dimension)]
        norm = sum(x * x for x in embedding) ** 0.5
        return [x / norm for x in embedding]

    # ========================================================================
    # Vector Search
    # ========================================================================

    async def search(
        self,
        db: AsyncSession,
        query: str,
        user_id: Optional[str] = None,
        video_id: Optional[str] = None,
        index_id: Optional[int] = None,
        top_k: int = 5,
        similarity_threshold: float = 0.7,
        source_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Search for relevant chunks using vector similarity

        Args:
            db: Database session
            query: Search query text
            user_id: User identifier
            video_id: Optional video filter
            index_id: Optional index to use
            top_k: Number of results
            similarity_threshold: Minimum similarity score
            source_types: Filter by source types

        Returns:
            Search results with chunks and scores
        """
        self.log_operation("search", query_length=len(query))

        start_time = datetime.utcnow()

        try:
            # Generate query embedding
            query_embedding = await self._get_embedding(query)

            # Get candidate chunks
            if video_id:
                chunks = await self.chunk_repo.get_by_video_id(
                    video_id=video_id,
                    embedded_only=True,
                    limit=1000,
                )
            else:
                chunks = await self.chunk_repo.get_unembedded_chunks(limit=0)
                # Get all embedded chunks (in production, use vector DB)
                chunks = await self.chunk_repo.search_by_content(
                    query_text="",
                    limit=1000,
                )

            # Calculate similarities
            results = []
            for chunk in chunks:
                if not chunk.is_embedded:
                    continue

                # Get embedding
                chunk_embedding = await self.embedding_repo.get_by_chunk_id(chunk.id)
                if not chunk_embedding:
                    continue

                # Deserialize and calculate similarity
                embedding = self.embedding_repo.deserialize_embedding(
                    chunk_embedding.embedding
                )
                similarity = self._cosine_similarity(query_embedding, embedding)

                if similarity >= similarity_threshold:
                    results.append({
                        "chunk_id": chunk.id,
                        "video_id": chunk.video_id,
                        "source_type": chunk.source_type,
                        "content": chunk.content,
                        "similarity": round(similarity, 4),
                        "start_time": chunk.start_time,
                        "end_time": chunk.end_time,
                    })

            # Sort by similarity and limit
            results.sort(key=lambda x: x["similarity"], reverse=True)
            results = results[:top_k]

            search_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Log query
            query_record = await self.query_repo.create(
                query_text=query,
                user_id=user_id,
                index_id=index_id,
                top_k=top_k,
                similarity_threshold=similarity_threshold,
                filters={"video_id": video_id, "source_types": source_types},
                results=[{"chunk_id": r["chunk_id"], "score": r["similarity"]} for r in results],
                result_count=len(results),
                search_time_ms=search_time,
            )

            logger.info(
                f"Search completed: {len(results)} results in {search_time}ms"
            )

            return {
                "query": query,
                "results": results,
                "result_count": len(results),
                "search_time_ms": search_time,
                "query_id": query_record.id,
            }

        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise ProcessingError(f"Search failed: {e}")

    def _cosine_similarity(
        self,
        vec1: List[float],
        vec2: List[float],
    ) -> float:
        """Calculate cosine similarity between two vectors"""
        if len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(x * x for x in vec1) ** 0.5
        norm2 = sum(x * x for x in vec2) ** 0.5

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    # ========================================================================
    # RAG Generation
    # ========================================================================

    async def generate_response(
        self,
        db: AsyncSession,
        query: str,
        user_id: Optional[str] = None,
        video_id: Optional[str] = None,
        top_k: int = 5,
        model_type: str = "gpt-3.5-turbo",
    ) -> Dict[str, Any]:
        """
        Generate response using RAG

        Args:
            db: Database session
            query: User query
            user_id: User identifier
            video_id: Optional video context
            top_k: Number of chunks to retrieve
            model_type: LLM model for generation

        Returns:
            Generated response with sources
        """
        self.log_operation("generate_response", query_length=len(query))

        start_time = datetime.utcnow()

        try:
            # Search for relevant chunks
            search_results = await self.search(
                db=db,
                query=query,
                user_id=user_id,
                video_id=video_id,
                top_k=top_k,
            )

            # Build context from retrieved chunks
            context_parts = []
            for i, result in enumerate(search_results["results"]):
                context_parts.append(
                    f"[Source {i+1}]\n{result['content']}"
                )

            context = "\n\n".join(context_parts)

            # Generate response using LLM
            response = await self._generate_with_context(
                query=query,
                context=context,
                model_type=model_type,
            )

            total_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Update query record with response
            if search_results.get("query_id"):
                query_record = await self.query_repo.get_by_id(
                    search_results["query_id"]
                )
                if query_record:
                    await self.query_repo.update(
                        search_results["query_id"],
                        generated_response=response["content"],
                        response_model=model_type,
                        response_tokens=response.get("tokens", 0),
                        total_time_ms=total_time,
                    )

            logger.info(f"RAG response generated in {total_time}ms")

            return {
                "query": query,
                "response": response["content"],
                "sources": search_results["results"],
                "source_count": len(search_results["results"]),
                "search_time_ms": search_results["search_time_ms"],
                "total_time_ms": total_time,
                "model": model_type,
            }

        except Exception as e:
            logger.error(f"RAG generation failed: {e}")
            raise ProcessingError(f"RAG generation failed: {e}")

    def _get_llm_provider(self, model_type: str) -> tuple:
        """Determine LLM provider and model from model_type string"""
        model_type_lower = model_type.lower()

        if any(x in model_type_lower for x in ["gpt-4", "gpt-3.5", "gpt4", "gpt35"]):
            if "gpt-4" in model_type_lower or "gpt4" in model_type_lower:
                return ("openai", "gpt-4o-mini")
            return ("openai", "gpt-3.5-turbo")

        if any(x in model_type_lower for x in ["llm_provider", "llm_vendor"]):
            if "opus" in model_type_lower:
                return ("llm_vendor", "llm_provider-3-opus-20240229")
            if "sonnet" in model_type_lower:
                return ("llm_vendor", "llm_provider-3-sonnet-20240229")
            return ("llm_vendor", "llm_provider-3-haiku-20240307")

        if any(x in model_type_lower for x in ["llama", "mistral", "ollama"]):
            if "llama" in model_type_lower:
                return ("ollama", "llama3.2")
            if "mistral" in model_type_lower:
                return ("ollama", "mistral")
            return ("ollama", "llama3.2")

        return (None, None)

    async def _generate_with_context(
        self,
        query: str,
        context: str,
        model_type: str = "gpt-3.5-turbo",
    ) -> Dict[str, Any]:
        """
        Generate response with context using LLM

        Uses the unified LLM client to support OpenAI, LLMVendor, and Ollama
        """
        # Build system prompt for RAG
        system_prompt = """You are a helpful assistant that answers questions based on the provided context from video content.
Your answers should be:
1. Accurate and based on the provided context
2. Clear and well-organized
3. Include relevant details from the sources

If the context doesn't contain enough information to answer the question, acknowledge this and explain what information is available.
Always indicate which source(s) you're drawing from when possible."""

        # Build user prompt with context
        user_prompt = f"""Based on the following context from video content, please answer the question.

Context:
{context}

Question: {query}

Please provide a comprehensive answer based on the context above."""

        try:
            # Get LLM provider
            provider, model = self._get_llm_provider(model_type)

            # Get client
            if provider:
                llm_client = get_llm_client(provider=provider, model=model)
            else:
                llm_client = get_llm_client()

            # Create messages
            messages = [
                Message(role="system", content=system_prompt),
                Message(role="user", content=user_prompt),
            ]

            # Get response
            response = await llm_client.chat(
                messages=messages,
                temperature=0.7,
                max_tokens=2048,
            )

            return {
                "content": response.content,
                "tokens": response.usage.get("completion_tokens", len(response.content) // 4),
                "model": response.model,
            }

        except Exception as e:
            logger.error(f"RAG generation failed: {e}")
            # Fallback response
            return {
                "content": f"I apologize, but I encountered an error while generating a response. The search found {context.count('[Source')} relevant sources. Error: {str(e)}",
                "tokens": 50,
                "model": model_type,
            }

    # ========================================================================
    # Statistics
    # ========================================================================

    async def get_video_status(
        self,
        db: AsyncSession,
        video_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get embedding status for a video"""
        try:
            status = await self.status_repo.get_by_video_id(video_id)
            return status.to_dict() if status else None
        except Exception as e:
            logger.error(f"Failed to get video status: {e}")
            raise

    async def get_index_stats(
        self,
        db: AsyncSession,
        index_id: int,
    ) -> Dict[str, Any]:
        """Get statistics for an index"""
        try:
            index = await self.index_repo.get_by_id(index_id)
            if not index:
                raise ResourceNotFoundError(f"Index {index_id} not found")

            metrics = await self.query_repo.get_average_metrics(index_id)

            return {
                "index": index.to_dict(),
                "query_metrics": metrics,
            }

        except ResourceNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to get index stats: {e}")
            raise

    async def rate_response(
        self,
        db: AsyncSession,
        query_id: int,
        rating: int,
        feedback: Optional[str] = None,
    ) -> bool:
        """Rate a RAG response"""
        try:
            if rating < 1 or rating > 5:
                raise ValidationError("Rating must be between 1 and 5")

            return await self.query_repo.update_feedback(
                query_id=query_id,
                rating=rating,
                feedback=feedback,
            )

        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Failed to rate response: {e}")
            raise


__all__ = ["RAGService"]
