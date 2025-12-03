# src/app/models/__init__.py
"""
Database Models
ORM models for YouTube automation and analytics
"""

# Import Base for model registration
from src.infrastructure.database.connection import Base

# Import all models
from .video import Video, VideoStatus
from .channel import Channel
from .comment import Comment
from .video_analytics import VideoAnalytics
from .playlist import Playlist, playlist_videos
from .task_execution import TaskExecution, TaskStatus
from .caption import Caption, CaptionSegment, CaptionFormat, CaptionType
from .vqa import (
    VideoFrame,
    FrameAnalysis,
    VQASession,
    VQAQuestion,
    VideoFrameExtraction,
    FrameExtractionStatus,
    VQAModelType,
)
from .chat import (
    ChatSession,
    ChatMessage,
    ChatTemplate,
    ChatRole,
    ChatModelType,
)
from .rag import (
    DocumentChunk,
    ChunkEmbedding,
    RAGIndex,
    RAGQuery,
    VideoEmbeddingStatus,
    EmbeddingModelType,
    ChunkType,
)

__all__ = [
    # Base
    "Base",
    # Models
    "Video",
    "VideoStatus",
    "Channel",
    "Comment",
    "VideoAnalytics",
    "Playlist",
    "playlist_videos",
    "TaskExecution",
    "TaskStatus",
    # Caption models
    "Caption",
    "CaptionSegment",
    "CaptionFormat",
    "CaptionType",
    # VQA models
    "VideoFrame",
    "FrameAnalysis",
    "VQASession",
    "VQAQuestion",
    "VideoFrameExtraction",
    "FrameExtractionStatus",
    "VQAModelType",
    # Chat models
    "ChatSession",
    "ChatMessage",
    "ChatTemplate",
    "ChatRole",
    "ChatModelType",
    # RAG models
    "DocumentChunk",
    "ChunkEmbedding",
    "RAGIndex",
    "RAGQuery",
    "VideoEmbeddingStatus",
    "EmbeddingModelType",
    "ChunkType",
]
