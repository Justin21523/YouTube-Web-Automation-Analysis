# src/app/models/playlist.py
"""
Playlist Model
Represents a YouTube playlist with video collection
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
    ForeignKey,
    Table,
    Index,
)
from sqlalchemy.orm import relationship

from src.infrastructure.database.connection import Base

if TYPE_CHECKING:
    from .channel import Channel
    from .video import Video


# Association table for playlist-video many-to-many relationship
playlist_videos = Table(
    "playlist_videos",
    Base.metadata,
    Column(
        "playlist_id",
        String(100),
        ForeignKey("playlists.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "video_id",
        String(50),
        ForeignKey("videos.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("position", Integer, default=0, comment="Video position in playlist"),
    Column("added_at", DateTime, default=datetime.utcnow, comment="When video was added"),
)


class Playlist(Base):
    """
    YouTube Playlist entity

    Stores playlist metadata and video collection
    """

    __tablename__ = "playlists"
    __table_args__ = {"extend_existing": True}

    # Primary Key
    id = Column(String(100), primary_key=True, comment="YouTube playlist ID")

    # Foreign Key
    channel_id = Column(
        String(50),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to channel",
    )

    # Basic Info
    title = Column(String(500), nullable=False, index=True, comment="Playlist title")
    description = Column(Text, comment="Playlist description")

    # Timestamps
    published_at = Column(DateTime, nullable=False, comment="Playlist creation date")
    created_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, comment="Record creation"
    )
    last_updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="Last update timestamp",
    )

    # Metrics
    video_count = Column(Integer, default=0, comment="Number of videos in playlist")

    # Thumbnails
    thumbnail_default = Column(String(500), comment="Default thumbnail URL")
    thumbnail_medium = Column(String(500), comment="Medium thumbnail URL")
    thumbnail_high = Column(String(500), comment="High-res thumbnail URL")

    # Status
    privacy_status = Column(
        String(20), default="public", comment="public/unlisted/private"
    )
    is_active = Column(Boolean, default=True, comment="Actively monitored")

    # Relationships
    channel = relationship("Channel", backref="playlists")
    videos = relationship(
        "Video",
        secondary=playlist_videos,
        backref="playlists",
    )

    def __repr__(self):
        return f"<Playlist(id={self.id}, title={self.title[:30]}...)>"

    def to_dict(self) -> dict:
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "channel_id": self.channel_id,
            "title": self.title,
            "description": self.description,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "video_count": self.video_count,
            "privacy_status": self.privacy_status,
            "is_active": self.is_active,
            "last_updated_at": self.last_updated_at.isoformat() if self.last_updated_at else None,
        }


# Indexes for common queries
Index("idx_playlist_channel", Playlist.channel_id, Playlist.published_at.desc())
