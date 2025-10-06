# src/domain/__init__.py
"""
Lightweight compatibility layer (Claude-style).

This package exposes domain-facing interfaces and model re-exports so that
existing service modules can keep importing:

    from domain.interfaces import ICommentRepository, IVideoRepository, ...
    from domain.models import Comment, Video, Channel, CommentAnalysis

The actual ORM classes live in src.infrastructure.database.models.
Repositories live in src.infrastructure.repositories.
"""
from .interfaces import (  # re-export for convenience
    ICommentRepository,
    IVideoRepository,
    IChannelRepository,
    YouTubeAPIClientProtocol,
)
from .models import Comment, Video, Channel, CommentAnalysis

__all__ = [
    "ICommentRepository",
    "IVideoRepository",
    "IChannelRepository",
    "YouTubeAPIClientProtocol",
    "Comment",
    "Video",
    "Channel",
    "CommentAnalysis",
]
