# src/app/models/vqa.py
"""
VQA (Visual Question Answering) Models
Represents video frames, visual analysis results, and Q&A sessions
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
)
from sqlalchemy.orm import relationship

from src.infrastructure.database.connection import Base


class FrameExtractionStatus(str, Enum):
    """Frame extraction status"""
    PENDING = "pending"
    EXTRACTING = "extracting"
    COMPLETED = "completed"
    FAILED = "failed"


class VQAModelType(str, Enum):
    """Supported VQA model types"""
    BLIP2 = "blip2"
    LLAVA = "llava"
    COGVLM = "cogvlm"
    QWEN_VL = "qwen_vl"
    GPT4V = "gpt4v"


class VideoFrame(Base):
    """
    Video Frame entity

    Stores extracted keyframes from videos for visual analysis
    """

    __tablename__ = "video_frames"
    __table_args__ = {"extend_existing": True}

    # Primary Key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign Key
    video_id = Column(
        String(50),
        ForeignKey("videos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Associated video ID",
    )

    # Frame Info
    frame_number = Column(Integer, nullable=False, comment="Frame sequence number")
    timestamp = Column(Float, nullable=False, comment="Timestamp in seconds")

    # File paths
    file_path = Column(String(500), comment="Local file path to frame image")
    thumbnail_path = Column(String(500), comment="Thumbnail image path")

    # Frame properties
    width = Column(Integer, comment="Frame width in pixels")
    height = Column(Integer, comment="Frame height in pixels")
    file_size = Column(Integer, comment="File size in bytes")
    format = Column(String(10), default="jpg", comment="Image format (jpg, png)")

    # Extraction metadata
    extraction_method = Column(
        String(50),
        default="keyframe",
        comment="Extraction method (keyframe, interval, scene_change)",
    )
    is_keyframe = Column(Boolean, default=True, comment="Is this a keyframe")
    scene_score = Column(Float, comment="Scene change score (0-1)")

    # Visual features (can store embeddings or feature vectors)
    visual_embedding = Column(JSON, comment="Visual embedding vector")

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    video = relationship("Video", backref="frames")
    analyses = relationship(
        "FrameAnalysis",
        back_populates="frame",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<VideoFrame(id={self.id}, video_id={self.video_id}, timestamp={self.timestamp})>"

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "video_id": self.video_id,
            "frame_number": self.frame_number,
            "timestamp": self.timestamp,
            "file_path": self.file_path,
            "width": self.width,
            "height": self.height,
            "is_keyframe": self.is_keyframe,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class FrameAnalysis(Base):
    """
    Frame Analysis entity

    Stores visual analysis results for individual frames
    """

    __tablename__ = "frame_analyses"
    __table_args__ = {"extend_existing": True}

    # Primary Key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign Key
    frame_id = Column(
        Integer,
        ForeignKey("video_frames.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Associated frame ID",
    )

    # Analysis Info
    model_type = Column(
        String(50),
        nullable=False,
        comment="Model used for analysis (blip2, llava, etc.)",
    )
    model_version = Column(String(50), comment="Model version")

    # Analysis Results
    caption = Column(Text, comment="Generated image caption")
    description = Column(Text, comment="Detailed description")

    # Detected elements
    objects_detected = Column(JSON, comment="List of detected objects with confidence")
    text_detected = Column(JSON, comment="OCR detected text")
    faces_detected = Column(Integer, default=0, comment="Number of faces detected")

    # Scene classification
    scene_type = Column(String(100), comment="Scene classification")
    scene_confidence = Column(Float, comment="Scene classification confidence")

    # Tags and keywords
    tags = Column(JSON, comment="Generated tags")

    # Raw model output
    raw_output = Column(JSON, comment="Raw model output for reference")

    # Processing info
    processing_time_ms = Column(Integer, comment="Processing time in milliseconds")

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    frame = relationship("VideoFrame", back_populates="analyses")

    def __repr__(self):
        return f"<FrameAnalysis(id={self.id}, frame_id={self.frame_id}, model={self.model_type})>"

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "frame_id": self.frame_id,
            "model_type": self.model_type,
            "caption": self.caption,
            "description": self.description,
            "objects_detected": self.objects_detected,
            "text_detected": self.text_detected,
            "scene_type": self.scene_type,
            "tags": self.tags,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class VQASession(Base):
    """
    VQA Session entity

    Stores visual question-answering sessions and history
    """

    __tablename__ = "vqa_sessions"
    __table_args__ = {"extend_existing": True}

    # Primary Key
    id = Column(String(50), primary_key=True, comment="Session UUID")

    # Foreign Key
    video_id = Column(
        String(50),
        ForeignKey("videos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Associated video ID",
    )

    # Session Info
    user_id = Column(String(100), index=True, comment="User identifier")
    model_type = Column(
        String(50),
        default=VQAModelType.BLIP2.value,
        comment="VQA model type",
    )

    # Session state
    is_active = Column(Boolean, default=True, comment="Session is active")
    question_count = Column(Integer, default=0, comment="Number of questions asked")

    # Context
    selected_frames = Column(JSON, comment="List of frame IDs used in session")
    context_summary = Column(Text, comment="Accumulated context summary")

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_activity_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    video = relationship("Video", backref="vqa_sessions")
    questions = relationship(
        "VQAQuestion",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="VQAQuestion.created_at",
    )

    def __repr__(self):
        return f"<VQASession(id={self.id}, video_id={self.video_id})>"

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "video_id": self.video_id,
            "user_id": self.user_id,
            "model_type": self.model_type,
            "is_active": self.is_active,
            "question_count": self.question_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None,
        }


class VQAQuestion(Base):
    """
    VQA Question entity

    Stores individual questions and answers in a VQA session
    """

    __tablename__ = "vqa_questions"
    __table_args__ = {"extend_existing": True}

    # Primary Key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign Keys
    session_id = Column(
        String(50),
        ForeignKey("vqa_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent session ID",
    )
    frame_id = Column(
        Integer,
        ForeignKey("video_frames.id", ondelete="SET NULL"),
        nullable=True,
        comment="Specific frame for question (optional)",
    )

    # Question
    question = Column(Text, nullable=False, comment="User's question")
    question_type = Column(
        String(50),
        comment="Question type (what, who, where, when, why, how, describe)",
    )

    # Context
    timestamp_start = Column(Float, comment="Video timestamp range start")
    timestamp_end = Column(Float, comment="Video timestamp range end")

    # Answer
    answer = Column(Text, comment="Generated answer")
    confidence = Column(Float, comment="Answer confidence score (0-1)")

    # Supporting info
    relevant_frames = Column(JSON, comment="Frame IDs used to generate answer")
    evidence = Column(JSON, comment="Evidence/reasoning for answer")

    # Model info
    model_type = Column(String(50), comment="Model used for this answer")
    processing_time_ms = Column(Integer, comment="Processing time in milliseconds")

    # Feedback
    user_rating = Column(Integer, comment="User rating (1-5)")
    user_feedback = Column(Text, comment="User feedback text")

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    answered_at = Column(DateTime, comment="When answer was generated")

    # Relationships
    session = relationship("VQASession", back_populates="questions")
    frame = relationship("VideoFrame")

    def __repr__(self):
        return f"<VQAQuestion(id={self.id}, question={self.question[:30]}...)>"

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "frame_id": self.frame_id,
            "question": self.question,
            "question_type": self.question_type,
            "answer": self.answer,
            "confidence": self.confidence,
            "relevant_frames": self.relevant_frames,
            "model_type": self.model_type,
            "user_rating": self.user_rating,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "answered_at": self.answered_at.isoformat() if self.answered_at else None,
        }


class VideoFrameExtraction(Base):
    """
    Video Frame Extraction Job entity

    Tracks frame extraction jobs for videos
    """

    __tablename__ = "video_frame_extractions"
    __table_args__ = {"extend_existing": True}

    # Primary Key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign Key
    video_id = Column(
        String(50),
        ForeignKey("videos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True,
        comment="Associated video ID",
    )

    # Extraction settings
    extraction_method = Column(
        String(50),
        default="keyframe",
        comment="Method: keyframe, interval, scene_change",
    )
    interval_seconds = Column(Float, comment="Interval for interval-based extraction")
    max_frames = Column(Integer, default=100, comment="Maximum frames to extract")

    # Status
    status = Column(
        String(20),
        default=FrameExtractionStatus.PENDING.value,
        index=True,
        comment="Extraction status",
    )
    progress = Column(Integer, default=0, comment="Progress percentage")

    # Results
    frames_extracted = Column(Integer, default=0, comment="Number of frames extracted")
    total_duration = Column(Float, comment="Video duration in seconds")

    # Error handling
    error_message = Column(Text, comment="Error message if failed")
    retry_count = Column(Integer, default=0, comment="Number of retries")

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime, comment="When extraction started")
    completed_at = Column(DateTime, comment="When extraction completed")

    # Relationships
    video = relationship("Video", backref="frame_extraction")

    def __repr__(self):
        return f"<VideoFrameExtraction(id={self.id}, video_id={self.video_id}, status={self.status})>"

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "video_id": self.video_id,
            "extraction_method": self.extraction_method,
            "status": self.status,
            "progress": self.progress,
            "frames_extracted": self.frames_extracted,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


# Indexes for common queries
Index("idx_frame_video_timestamp", VideoFrame.video_id, VideoFrame.timestamp)
Index("idx_frame_analysis_model", FrameAnalysis.frame_id, FrameAnalysis.model_type)
Index("idx_vqa_session_user", VQASession.user_id, VQASession.created_at.desc())
Index("idx_vqa_question_session", VQAQuestion.session_id, VQAQuestion.created_at)


__all__ = [
    "VideoFrame",
    "FrameAnalysis",
    "VQASession",
    "VQAQuestion",
    "VideoFrameExtraction",
    "FrameExtractionStatus",
    "VQAModelType",
]
