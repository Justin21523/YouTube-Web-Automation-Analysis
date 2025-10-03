# src/app/models/video.py
"""
Video Model
Represents a YouTube video with complete metadata and engagement metrics
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Column,
    String,
    Integer,
    BigInteger,
    DateTime,
    Text,
    Boolean,
    ForeignKey,
    Enum as SQLEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

# Replace with:
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class VideoStatus(str, enum.Enum):
    """Video processing status"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Video(Base):
    """
    YouTube Video entity

    Stores complete video metadata, engagement metrics, and processing status
    """

    __tablename__ = "videos"

    # Add this to prevent redefinition errors
    __table_args__ = {"extend_existing": True}

    # Primary Key
    id = Column(String(50), primary_key=True, comment="YouTube video ID")

    # Foreign Keys
    channel_id = Column(
        String(50),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to channel",
    )

    # Basic Info
    title = Column(String(500), nullable=False, index=True, comment="Video title")
    description = Column(Text, comment="Video description")
    published_at = Column(
        DateTime, nullable=False, index=True, comment="Publication date"
    )

    # Video Properties
    duration_seconds = Column(Integer, comment="Video length in seconds")
    definition = Column(String(10), comment="hd or sd")
    dimension = Column(String(10), comment="2d or 3d")
    caption = Column(Boolean, default=False, comment="Has captions")
    licensed_content = Column(Boolean, default=False, comment="Licensed content flag")

    # Engagement Metrics
    view_count = Column(BigInteger, default=0, index=True, comment="Total views")
    like_count = Column(BigInteger, default=0, comment="Total likes")
    comment_count = Column(Integer, default=0, comment="Total comments")

    # Category & Tags
    category_id = Column(String(20), comment="YouTube category ID")
    tags = Column(Text, comment="Comma-separated tags")
    language = Column(String(10), comment="Video language code")

    # Thumbnails
    thumbnail_default = Column(String(500), comment="Default thumbnail URL")
    thumbnail_medium = Column(String(500), comment="Medium thumbnail URL")
    thumbnail_high = Column(String(500), comment="High-res thumbnail URL")
    thumbnail_maxres = Column(String(500), comment="Max resolution thumbnail")

    # Processing Status
    status = Column(
        SQLEnum(VideoStatus),
        nullable=False,
        default=VideoStatus.PENDING,
        index=True,
        comment="Processing status",
    )
    # Transcript
    has_transcript = Column(Boolean, default=False, comment="Transcript available")
    transcript_language = Column(String(10), comment="Transcript language code")

    # Metadata
    first_scraped_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="Initial scrape timestamp",
    )
    last_updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="Last update timestamp",
    )
    scrape_count = Column(Integer, default=1, comment="Number of times scraped")

    # Relationships
    channel = relationship("Channel", back_populates="videos")
    comments = relationship(
        "Comment", back_populates="video", cascade="all, delete-orphan"
    )
    analytics = relationship(
        "VideoAnalytics", back_populates="video", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Video(id={self.id}, title={self.title[:30]}...)>"

    def to_dict(self) -> dict:
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "channel_id": self.channel_id,
            "title": self.title,
            "description": self.description,
            "published_at": self.published_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "view_count": self.view_count,
            "like_count": self.like_count,
            "comment_count": self.comment_count,
            "status": self.status.value,
            "has_transcript": self.has_transcript,
            "last_updated_at": self.last_updated_at.isoformat(),
        }

    @property
    def engagement_rate(self) -> float:
        """Calculate engagement rate: (likes + comments) / views * 100"""
        if self.view_count > 0:
            return ((self.like_count + self.comment_count) / self.view_count) * 100
        return 0.0

    @property
    def tags_list(self) -> list:
        """Parse tags from comma-separated string"""
        if self.tags:
            return [tag.strip() for tag in self.tags.split(",")]
        return []
