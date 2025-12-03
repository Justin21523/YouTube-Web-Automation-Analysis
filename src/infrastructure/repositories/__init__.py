# src/infrastructure/repositories/__init__.py
"""
Repository Layer
Data access patterns for all entities
"""

from .base import BaseRepository
from .video_repository import VideoRepository
from .channel_repository import ChannelRepository
from .comment_repository import CommentRepository
from .analytics_repository import AnalyticsRepository
from .task_execution_repository import TaskExecutionRepository
from .caption_repository import CaptionRepository, CaptionSegmentRepository
from .vqa_repository import (
    VideoFrameRepository,
    FrameAnalysisRepository,
    VQASessionRepository,
    VQAQuestionRepository,
    VideoFrameExtractionRepository,
)
from .chat_repository import (
    ChatSessionRepository,
    ChatMessageRepository,
    ChatTemplateRepository,
)
from .rag_repository import (
    DocumentChunkRepository,
    ChunkEmbeddingRepository,
    RAGIndexRepository,
    RAGQueryRepository,
    VideoEmbeddingStatusRepository,
)

__all__ = [
    "BaseRepository",
    "VideoRepository",
    "ChannelRepository",
    "CommentRepository",
    "AnalyticsRepository",
    "TaskExecutionRepository",
    "CaptionRepository",
    "CaptionSegmentRepository",
    "VideoFrameRepository",
    "FrameAnalysisRepository",
    "VQASessionRepository",
    "VQAQuestionRepository",
    "VideoFrameExtractionRepository",
    "ChatSessionRepository",
    "ChatMessageRepository",
    "ChatTemplateRepository",
    "DocumentChunkRepository",
    "ChunkEmbeddingRepository",
    "RAGIndexRepository",
    "RAGQueryRepository",
    "VideoEmbeddingStatusRepository",
]
