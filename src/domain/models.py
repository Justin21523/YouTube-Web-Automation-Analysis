# src/domain/models.py
"""
Domain model re-exports + lightweight DTOs.

This module re-exports ORM entities from the infrastructure layer so that
existing code can keep using:

    from domain.models import Comment, Video, Channel, CommentAnalysis

We also define a small CommentAnalysis DTO commonly returned by services.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime

# Re-export ORM models from the infrastructure layer.
# We intentionally guard imports to be resilient in tooling / partial environments.
try:
    from src.infrastructure.database.models import Comment, Video, Channel  # type: ignore
except Exception:  # pragma: no cover
    Comment = object  # type: ignore
    Video = object  # type: ignore
    Channel = object  # type: ignore


@dataclass
class KeywordItem:
    text: str
    score: float
    count: int


@dataclass
class CommentAnalysis:
    """
    Lightweight DTO for summarizing comment analytics.

    NOTE: This is not a DB model. Services may return this structure or
    convert it to a Pydantic response model in API routes.
    """

    video_id: str
    total_comments: int = 0
    analyzed_comments: int = 0
    average_sentiment: float = 0.0
    sentiment_breakdown: Dict[str, int] = field(default_factory=dict)
    language_distribution: Dict[str, int] = field(default_factory=dict)
    top_keywords: List[KeywordItem] = field(default_factory=list)
    analyzed_at: datetime = field(default_factory=datetime.utcnow)


__all__ = ["Comment", "Video", "Channel", "CommentAnalysis", "KeywordItem"]
