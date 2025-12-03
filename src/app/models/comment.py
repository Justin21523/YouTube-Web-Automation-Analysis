# src/app/models/comment.py
"""
Comment Model
Represents a YouTube comment with sentiment analysis and threading support
"""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Text,
    Boolean,
    Float,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import relationship

from src.infrastructure.database.connection import Base

if TYPE_CHECKING:
    from .video import Video


class Comment(Base):
    """
    YouTube Comment entity

    Stores comment content, author info, sentiment analysis, and reply threading
    """

    __tablename__ = "comments"
    __table_args__ = {"extend_existing": True}

    # Primary Key
    id = Column(String(100), primary_key=True, comment="YouTube comment ID")

    # Foreign Keys
    video_id = Column(
        String(50),
        ForeignKey("videos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to video",
    )
    parent_id = Column(
        String(100),
        ForeignKey("comments.id", ondelete="CASCADE"),
        index=True,
        comment="Parent comment ID for replies",
    )

    # Author Info
    author_name = Column(String(255), nullable=False, comment="Author display name")
    author_channel_id = Column(
        String(50), index=True, comment="Author's channel ID"
    )
    author_profile_image = Column(String(500), comment="Author profile image URL")

    # Comment Content
    text = Column(Text, nullable=False, comment="Raw comment text")
    text_display = Column(Text, comment="HTML-formatted comment text")

    # Engagement
    like_count = Column(Integer, default=0, index=True, comment="Number of likes")
    reply_count = Column(Integer, default=0, comment="Number of replies")

    # Timestamps
    published_at = Column(
        DateTime, nullable=False, index=True, comment="Comment publish date"
    )
    updated_at = Column(DateTime, comment="Last edit timestamp")
    scraped_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="Scrape timestamp",
    )

    # Status Flags
    is_public = Column(Boolean, default=True, comment="Public visibility")
    is_pinned = Column(Boolean, default=False, comment="Pinned by creator")
    is_heart = Column(Boolean, default=False, comment="Hearted by creator")

    # Sentiment Analysis
    sentiment_score = Column(
        Float, comment="Sentiment score (-1.0 to 1.0)"
    )
    sentiment_label = Column(
        String(20), index=True, comment="positive/negative/neutral"
    )
    sentiment_confidence = Column(Float, comment="Sentiment confidence (0-1)")
    analyzed_at = Column(DateTime, comment="Sentiment analysis timestamp")

    # Language Detection
    language = Column(String(10), index=True, comment="Detected language code")
    language_confidence = Column(Float, comment="Language detection confidence")

    # Relationships
    video = relationship("Video", back_populates="comments")
    replies = relationship(
        "Comment",
        backref="parent",
        remote_side=[id],
        cascade="all, delete-orphan",
        single_parent=True,
    )

    def __repr__(self):
        return f"<Comment(id={self.id}, author={self.author_name})>"

    def to_dict(self) -> dict:
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "video_id": self.video_id,
            "parent_id": self.parent_id,
            "author_name": self.author_name,
            "author_channel_id": self.author_channel_id,
            "text": self.text,
            "like_count": self.like_count,
            "reply_count": self.reply_count,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "is_pinned": self.is_pinned,
            "is_heart": self.is_heart,
            "sentiment_label": self.sentiment_label,
            "sentiment_score": self.sentiment_score,
            "language": self.language,
        }

    @property
    def is_reply(self) -> bool:
        """Check if this comment is a reply"""
        return self.parent_id is not None

    @property
    def is_analyzed(self) -> bool:
        """Check if sentiment analysis has been performed"""
        return self.sentiment_label is not None


# Indexes for common queries
Index("idx_comment_video_sentiment", Comment.video_id, Comment.sentiment_label)
Index("idx_comment_video_likes", Comment.video_id, Comment.like_count.desc())
Index("idx_comment_author", Comment.author_channel_id, Comment.published_at.desc())
