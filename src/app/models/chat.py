# src/app/models/chat.py
"""
Chat Models
Represents chat sessions, messages, and conversation history
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


class ChatRole(str, Enum):
    """Message role in conversation"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatModelType(str, Enum):
    """Supported chat model types"""
    GPT4 = "gpt-4"
    GPT35 = "gpt-3.5-turbo"
    LLM_PROVIDER = "llm_provider"
    LLAMA = "llama"
    QWEN = "qwen"
    LOCAL = "local"


class ChatSession(Base):
    """
    Chat Session entity

    Stores chat conversation sessions about videos
    """

    __tablename__ = "chat_sessions"
    __table_args__ = {"extend_existing": True}

    # Primary Key
    id = Column(String(50), primary_key=True, comment="Session UUID")

    # Foreign Key (optional - chat can be about a video or general)
    video_id = Column(
        String(50),
        ForeignKey("videos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Associated video ID (optional)",
    )

    # Session Info
    user_id = Column(String(100), index=True, comment="User identifier")
    title = Column(String(200), comment="Session title/topic")

    # Model settings
    model_type = Column(
        String(50),
        default=ChatModelType.GPT35.value,
        comment="Chat model type",
    )
    system_prompt = Column(Text, comment="Custom system prompt")
    temperature = Column(Float, default=0.7, comment="Model temperature")
    max_tokens = Column(Integer, default=2000, comment="Max tokens per response")

    # Session state
    is_active = Column(Boolean, default=True, comment="Session is active")
    message_count = Column(Integer, default=0, comment="Total messages")

    # Context
    context_summary = Column(Text, comment="Summarized conversation context")
    video_context = Column(JSON, comment="Video metadata for context")

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_activity_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    video = relationship("Video", backref="chat_sessions")
    messages = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    def __repr__(self):
        return f"<ChatSession(id={self.id}, video_id={self.video_id})>"

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "video_id": self.video_id,
            "user_id": self.user_id,
            "title": self.title,
            "model_type": self.model_type,
            "is_active": self.is_active,
            "message_count": self.message_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None,
        }


class ChatMessage(Base):
    """
    Chat Message entity

    Stores individual messages in a chat session
    """

    __tablename__ = "chat_messages"
    __table_args__ = {"extend_existing": True}

    # Primary Key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign Key
    session_id = Column(
        String(50),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent session ID",
    )

    # Message content
    role = Column(
        String(20),
        nullable=False,
        comment="Message role (user/assistant/system)",
    )
    content = Column(Text, nullable=False, comment="Message content")

    # Message metadata
    token_count = Column(Integer, comment="Token count for this message")
    model_used = Column(String(50), comment="Model that generated response")

    # For assistant messages
    finish_reason = Column(String(50), comment="Why generation stopped")
    processing_time_ms = Column(Integer, comment="Processing time in milliseconds")

    # References (for context-aware responses)
    references = Column(JSON, comment="Referenced timestamps, frames, etc.")

    # Feedback
    user_rating = Column(Integer, comment="User rating (1-5)")
    is_helpful = Column(Boolean, comment="Was this helpful?")

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    session = relationship("ChatSession", back_populates="messages")

    def __repr__(self):
        return f"<ChatMessage(id={self.id}, role={self.role})>"

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "token_count": self.token_count,
            "model_used": self.model_used,
            "references": self.references,
            "user_rating": self.user_rating,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ChatTemplate(Base):
    """
    Chat Template entity

    Stores reusable prompt templates for chat sessions
    """

    __tablename__ = "chat_templates"
    __table_args__ = {"extend_existing": True}

    # Primary Key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Template info
    name = Column(String(100), nullable=False, unique=True, comment="Template name")
    description = Column(Text, comment="Template description")
    category = Column(String(50), index=True, comment="Template category")

    # Prompt content
    system_prompt = Column(Text, nullable=False, comment="System prompt template")
    example_queries = Column(JSON, comment="Example user queries")

    # Settings
    default_temperature = Column(Float, default=0.7)
    default_max_tokens = Column(Integer, default=2000)
    recommended_model = Column(String(50))

    # Metadata
    is_active = Column(Boolean, default=True)
    usage_count = Column(Integer, default=0, comment="Times used")

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    def __repr__(self):
        return f"<ChatTemplate(id={self.id}, name={self.name})>"

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "system_prompt": self.system_prompt,
            "example_queries": self.example_queries,
            "default_temperature": self.default_temperature,
            "default_max_tokens": self.default_max_tokens,
            "recommended_model": self.recommended_model,
            "is_active": self.is_active,
            "usage_count": self.usage_count,
        }


# Indexes for common queries
Index("idx_chat_session_user", ChatSession.user_id, ChatSession.created_at.desc())
Index("idx_chat_session_video", ChatSession.video_id, ChatSession.created_at.desc())
Index("idx_chat_message_session", ChatMessage.session_id, ChatMessage.created_at)


__all__ = [
    "ChatSession",
    "ChatMessage",
    "ChatTemplate",
    "ChatRole",
    "ChatModelType",
]
