# src/app/models/rag.py
"""
RAG Models
Represents vector embeddings, document chunks, and retrieval components
"""

from datetime import datetime
from typing import Optional, List
from enum import Enum
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    DateTime,
    Text,
    Boolean,
    ForeignKey,
    JSON,
    Index,
    LargeBinary,
)
from sqlalchemy.orm import relationship

from src.infrastructure.database.connection import Base


class EmbeddingModelType(str, Enum):
    """Supported embedding model types"""
    OPENAI_ADA = "text-embedding-ada-002"
    OPENAI_3_SMALL = "text-embedding-3-small"
    OPENAI_3_LARGE = "text-embedding-3-large"
    SENTENCE_TRANSFORMER = "sentence-transformers"
    BGE_SMALL = "bge-small-en"
    BGE_LARGE = "bge-large-en"
    LOCAL = "local"


class ChunkType(str, Enum):
    """Types of content chunks"""
    CAPTION = "caption"
    DESCRIPTION = "description"
    COMMENT = "comment"
    TRANSCRIPT = "transcript"
    FRAME_DESCRIPTION = "frame_description"
    METADATA = "metadata"


class DocumentChunk(Base):
    """
    Document Chunk entity

    Stores text chunks for RAG retrieval
    """

    __tablename__ = "document_chunks"
    __table_args__ = {"extend_existing": True}

    # Primary Key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Source reference
    video_id = Column(
        String(50),
        ForeignKey("videos.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Source video ID",
    )
    source_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment="Type of source content",
    )
    source_id = Column(
        String(100),
        nullable=True,
        comment="ID of specific source (e.g., caption_id, comment_id)",
    )

    # Chunk content
    content = Column(Text, nullable=False, comment="Chunk text content")
    chunk_index = Column(Integer, default=0, comment="Index within source document")
    total_chunks = Column(Integer, default=1, comment="Total chunks from this source")

    # Chunk metadata
    start_position = Column(Integer, comment="Start character position in source")
    end_position = Column(Integer, comment="End character position in source")
    start_time = Column(Float, comment="Start timestamp (for captions/transcripts)")
    end_time = Column(Float, comment="End timestamp (for captions/transcripts)")

    # Token info
    token_count = Column(Integer, comment="Token count for this chunk")
    word_count = Column(Integer, comment="Word count for this chunk")

    # Context metadata
    context = Column(JSON, comment="Additional context metadata")
    language = Column(String(10), comment="Detected language code")

    # Status
    is_embedded = Column(
        Boolean,
        default=False,
        index=True,
        comment="Whether embedding has been generated",
    )
    embedding_model = Column(String(100), comment="Model used for embedding")

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    video = relationship("Video", backref="document_chunks")
    embedding = relationship(
        "ChunkEmbedding",
        back_populates="chunk",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<DocumentChunk(id={self.id}, video_id={self.video_id}, type={self.source_type})>"

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "video_id": self.video_id,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "content": self.content,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "token_count": self.token_count,
            "is_embedded": self.is_embedded,
            "embedding_model": self.embedding_model,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ChunkEmbedding(Base):
    """
    Chunk Embedding entity

    Stores vector embeddings for document chunks
    """

    __tablename__ = "chunk_embeddings"
    __table_args__ = {"extend_existing": True}

    # Primary Key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign Key
    chunk_id = Column(
        Integer,
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        comment="Parent chunk ID",
    )

    # Embedding data
    embedding = Column(LargeBinary, nullable=False, comment="Serialized embedding vector")
    embedding_dimension = Column(Integer, nullable=False, comment="Embedding vector dimension")
    model_type = Column(
        String(100),
        nullable=False,
        default=EmbeddingModelType.OPENAI_3_SMALL.value,
        comment="Model used for embedding",
    )
    model_version = Column(String(50), comment="Model version")

    # Quality metrics
    norm = Column(Float, comment="L2 norm of embedding")

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    chunk = relationship("DocumentChunk", back_populates="embedding")

    def __repr__(self):
        return f"<ChunkEmbedding(id={self.id}, chunk_id={self.chunk_id}, dim={self.embedding_dimension})>"

    def to_dict(self) -> dict:
        """Convert to dictionary (without embedding data)"""
        return {
            "id": self.id,
            "chunk_id": self.chunk_id,
            "embedding_dimension": self.embedding_dimension,
            "model_type": self.model_type,
            "model_version": self.model_version,
            "norm": self.norm,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class RAGIndex(Base):
    """
    RAG Index entity

    Stores index metadata for vector search
    """

    __tablename__ = "rag_indexes"
    __table_args__ = {"extend_existing": True}

    # Primary Key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Index info
    name = Column(String(100), nullable=False, unique=True, comment="Index name")
    description = Column(Text, comment="Index description")

    # Configuration
    embedding_model = Column(
        String(100),
        nullable=False,
        default=EmbeddingModelType.OPENAI_3_SMALL.value,
        comment="Embedding model for this index",
    )
    embedding_dimension = Column(Integer, nullable=False, comment="Embedding dimension")
    chunk_size = Column(Integer, default=500, comment="Target chunk size in tokens")
    chunk_overlap = Column(Integer, default=50, comment="Overlap between chunks in tokens")

    # Index type
    index_type = Column(
        String(50),
        default="flat",
        comment="Vector index type (flat, ivf, hnsw)",
    )
    index_params = Column(JSON, comment="Index-specific parameters")

    # Statistics
    total_chunks = Column(Integer, default=0, comment="Total chunks in index")
    total_videos = Column(Integer, default=0, comment="Total videos indexed")

    # Status
    is_active = Column(Boolean, default=True, comment="Index is active")
    last_updated = Column(DateTime, comment="Last update timestamp")

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"<RAGIndex(id={self.id}, name={self.name})>"

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "embedding_model": self.embedding_model,
            "embedding_dimension": self.embedding_dimension,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "index_type": self.index_type,
            "total_chunks": self.total_chunks,
            "total_videos": self.total_videos,
            "is_active": self.is_active,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class RAGQuery(Base):
    """
    RAG Query entity

    Stores query history and results for analysis
    """

    __tablename__ = "rag_queries"
    __table_args__ = {"extend_existing": True}

    # Primary Key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Query info
    query_text = Column(Text, nullable=False, comment="User query text")
    user_id = Column(String(100), index=True, comment="User identifier")

    # Index reference
    index_id = Column(
        Integer,
        ForeignKey("rag_indexes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="RAG index used",
    )

    # Search parameters
    top_k = Column(Integer, default=5, comment="Number of results requested")
    similarity_threshold = Column(Float, default=0.7, comment="Minimum similarity threshold")
    filters = Column(JSON, comment="Applied filters")

    # Results
    results = Column(JSON, comment="Retrieved chunk IDs and scores")
    result_count = Column(Integer, comment="Number of results returned")

    # Performance metrics
    search_time_ms = Column(Integer, comment="Search time in milliseconds")
    total_time_ms = Column(Integer, comment="Total processing time")

    # Generated response (if RAG used for generation)
    generated_response = Column(Text, comment="LLM-generated response")
    response_model = Column(String(100), comment="Model used for generation")
    response_tokens = Column(Integer, comment="Response token count")

    # Feedback
    user_rating = Column(Integer, comment="User rating (1-5)")
    user_feedback = Column(Text, comment="User feedback text")

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    index = relationship("RAGIndex", backref="queries")

    def __repr__(self):
        return f"<RAGQuery(id={self.id}, user_id={self.user_id})>"

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "query_text": self.query_text,
            "user_id": self.user_id,
            "index_id": self.index_id,
            "top_k": self.top_k,
            "similarity_threshold": self.similarity_threshold,
            "result_count": self.result_count,
            "search_time_ms": self.search_time_ms,
            "total_time_ms": self.total_time_ms,
            "generated_response": self.generated_response,
            "user_rating": self.user_rating,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class VideoEmbeddingStatus(Base):
    """
    Video Embedding Status entity

    Tracks embedding generation status for each video
    """

    __tablename__ = "video_embedding_status"
    __table_args__ = {"extend_existing": True}

    # Primary Key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Video reference
    video_id = Column(
        String(50),
        ForeignKey("videos.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        comment="Video ID",
    )

    # Status for each source type
    caption_embedded = Column(Boolean, default=False, comment="Captions embedded")
    description_embedded = Column(Boolean, default=False, comment="Description embedded")
    comments_embedded = Column(Boolean, default=False, comment="Comments embedded")
    frames_embedded = Column(Boolean, default=False, comment="Frame descriptions embedded")

    # Chunk counts
    total_chunks = Column(Integer, default=0, comment="Total chunks for video")
    embedded_chunks = Column(Integer, default=0, comment="Chunks with embeddings")

    # Processing info
    last_processed = Column(DateTime, comment="Last processing timestamp")
    processing_error = Column(Text, comment="Last error message if any")

    # Index reference
    index_id = Column(
        Integer,
        ForeignKey("rag_indexes.id", ondelete="SET NULL"),
        nullable=True,
        comment="Associated index",
    )

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    video = relationship("Video", backref="embedding_status")
    index = relationship("RAGIndex", backref="video_statuses")

    def __repr__(self):
        return f"<VideoEmbeddingStatus(video_id={self.video_id})>"

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "video_id": self.video_id,
            "caption_embedded": self.caption_embedded,
            "description_embedded": self.description_embedded,
            "comments_embedded": self.comments_embedded,
            "frames_embedded": self.frames_embedded,
            "total_chunks": self.total_chunks,
            "embedded_chunks": self.embedded_chunks,
            "last_processed": self.last_processed.isoformat() if self.last_processed else None,
            "processing_error": self.processing_error,
            "index_id": self.index_id,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# Indexes for common queries
Index("idx_chunk_video_source", DocumentChunk.video_id, DocumentChunk.source_type)
Index("idx_chunk_embedded", DocumentChunk.is_embedded, DocumentChunk.created_at)
Index("idx_query_user", RAGQuery.user_id, RAGQuery.created_at.desc())


__all__ = [
    "DocumentChunk",
    "ChunkEmbedding",
    "RAGIndex",
    "RAGQuery",
    "VideoEmbeddingStatus",
    "EmbeddingModelType",
    "ChunkType",
]
