# src/app/models/channel.py
"""
Channel Model
Represents a YouTube channel with metadata and subscriber metrics
"""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import (
    Column,
    String,
    Integer,
    BigInteger,
    DateTime,
    Text,
    Boolean,
    Index,
)
from sqlalchemy.orm import relationship

from src.infrastructure.database.connection import Base

if TYPE_CHECKING:
    from .video import Video


class Channel(Base):
    """
    YouTube Channel entity

    Stores channel metadata, subscriber counts, and activity status
    """

    __tablename__ = "channels"
    __table_args__ = {"extend_existing": True}

    # Primary Key
    id = Column(String(50), primary_key=True, comment="YouTube channel ID")

    # Basic Info
    name = Column(String(255), nullable=False, index=True, comment="Channel name")
    handle = Column(String(100), index=True, comment="Channel handle (@handle)")
    custom_url = Column(String(255), comment="Custom URL path")
    description = Column(Text, comment="Channel description")
    country = Column(String(10), comment="Country code")

    # Timestamps
    published_at = Column(DateTime, comment="Channel creation date")
    created_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, comment="Record creation"
    )
    first_scraped_at = Column(
        DateTime, default=datetime.utcnow, comment="First scrape timestamp"
    )
    last_updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="Last update timestamp",
    )

    # Metrics
    subscriber_count = Column(BigInteger, default=0, index=True, comment="Subscriber count")
    video_count = Column(Integer, default=0, comment="Total videos")
    view_count = Column(BigInteger, default=0, comment="Total channel views")

    # Thumbnails
    thumbnail_default = Column(String(500), comment="Default thumbnail URL")
    thumbnail_medium = Column(String(500), comment="Medium thumbnail URL")
    thumbnail_high = Column(String(500), comment="High-res thumbnail URL")

    # Status Flags
    is_verified = Column(Boolean, default=False, comment="Verified channel flag")
    is_active = Column(Boolean, default=True, index=True, comment="Actively monitored")
    is_hidden_subscriber_count = Column(
        Boolean, default=False, comment="Subscriber count hidden"
    )

    # Tracking
    scrape_count = Column(Integer, default=1, comment="Number of times scraped")

    # Relationships
    videos = relationship(
        "Video", back_populates="channel", cascade="all, delete-orphan"
    )

    @property
    def thumbnail_url(self) -> Optional[str]:
        """Get best available thumbnail URL"""
        return self.thumbnail_high or self.thumbnail_medium or self.thumbnail_default

    def __repr__(self):
        return f"<Channel(id={self.id}, name={self.name})>"

    def to_dict(self) -> dict:
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "name": self.name,
            "handle": self.handle,
            "custom_url": self.custom_url,
            "description": self.description,
            "country": self.country,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "subscriber_count": self.subscriber_count,
            "video_count": self.video_count,
            "view_count": self.view_count,
            "is_verified": self.is_verified,
            "is_active": self.is_active,
            "last_updated_at": self.last_updated_at.isoformat() if self.last_updated_at else None,
        }


# Indexes for common queries
Index("idx_channel_subscribers", Channel.subscriber_count.desc())
Index("idx_channel_active", Channel.is_active, Channel.last_updated_at.desc())
