# src/app/models/video_analytics.py
"""
Video Analytics Model
Time-series performance tracking for videos
"""

from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import (
    Column,
    String,
    Integer,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import relationship

from src.infrastructure.database.connection import Base

if TYPE_CHECKING:
    from .video import Video


class VideoAnalytics(Base):
    """
    Video Analytics Snapshot entity

    Stores time-series data for tracking video performance over time
    """

    __tablename__ = "video_analytics"
    __table_args__ = {"extend_existing": True}

    # Primary Key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign Key
    video_id = Column(
        String(50),
        ForeignKey("videos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to video",
    )

    # Timestamp
    scraped_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
        comment="Snapshot timestamp",
    )

    # Core Metrics (at snapshot time)
    view_count = Column(BigInteger, default=0, comment="View count at snapshot")
    like_count = Column(BigInteger, default=0, comment="Like count at snapshot")
    comment_count = Column(Integer, default=0, comment="Comment count at snapshot")

    # Growth Metrics (since last snapshot)
    view_growth = Column(Integer, default=0, comment="Views gained since last snapshot")
    like_growth = Column(Integer, default=0, comment="Likes gained since last snapshot")
    comment_growth = Column(
        Integer, default=0, comment="Comments gained since last snapshot"
    )

    # Calculated Metrics
    views_per_hour = Column(Float, default=0.0, comment="Views per hour rate")
    engagement_rate = Column(
        Float, default=0.0, comment="Engagement rate ((likes+comments)/views)*100"
    )

    # Performance Indicators
    trending_score = Column(
        Float, default=0.0, comment="Custom trending score calculation"
    )
    velocity_score = Column(
        Float, default=0.0, comment="Growth velocity indicator"
    )

    # Relationships
    video = relationship("Video", back_populates="analytics")

    def __repr__(self):
        return f"<VideoAnalytics(video_id={self.video_id}, scraped_at={self.scraped_at})>"

    def to_dict(self) -> dict:
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "video_id": self.video_id,
            "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
            "view_count": self.view_count,
            "like_count": self.like_count,
            "comment_count": self.comment_count,
            "view_growth": self.view_growth,
            "like_growth": self.like_growth,
            "comment_growth": self.comment_growth,
            "views_per_hour": self.views_per_hour,
            "engagement_rate": self.engagement_rate,
            "trending_score": self.trending_score,
        }


# Indexes for time-series queries
Index("idx_analytics_video_time", VideoAnalytics.video_id, VideoAnalytics.scraped_at.desc())
Index("idx_analytics_trending", VideoAnalytics.trending_score.desc())
