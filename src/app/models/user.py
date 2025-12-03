# src/app/models/user.py
"""
User Model
User authentication and profile management
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Text,
    Boolean,
    Enum as SQLEnum,
    Index,
)
from sqlalchemy.orm import relationship
import enum

from src.infrastructure.database.connection import Base


class UserRole(str, enum.Enum):
    """User role enumeration"""
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"


class UserStatus(str, enum.Enum):
    """User account status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"


class User(Base):
    """
    User entity for authentication and authorization

    Stores user credentials, profile information, and access settings
    """

    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_email", "email"),
        Index("ix_users_username", "username"),
        {"extend_existing": True},
    )

    # Primary Key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Authentication
    username = Column(
        String(50),
        unique=True,
        nullable=False,
        comment="Unique username"
    )
    email = Column(
        String(255),
        unique=True,
        nullable=False,
        comment="User email address"
    )
    hashed_password = Column(
        String(255),
        nullable=False,
        comment="Bcrypt hashed password"
    )

    # Profile
    full_name = Column(String(100), nullable=True, comment="Full name")
    avatar_url = Column(String(500), nullable=True, comment="Avatar URL")
    bio = Column(Text, nullable=True, comment="User biography")

    # Role and Status
    role = Column(
        SQLEnum(UserRole),
        default=UserRole.USER,
        nullable=False,
        comment="User role"
    )
    status = Column(
        SQLEnum(UserStatus),
        default=UserStatus.ACTIVE,
        nullable=False,
        comment="Account status"
    )

    # Settings
    is_email_verified = Column(
        Boolean,
        default=False,
        comment="Email verification status"
    )
    email_notifications = Column(
        Boolean,
        default=True,
        comment="Email notification preference"
    )
    api_key = Column(
        String(64),
        unique=True,
        nullable=True,
        comment="API key for programmatic access"
    )

    # Rate Limiting
    daily_api_limit = Column(
        Integer,
        default=1000,
        comment="Daily API call limit"
    )
    monthly_api_limit = Column(
        Integer,
        default=30000,
        comment="Monthly API call limit"
    )

    # Timestamps
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        comment="Account creation timestamp"
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="Last update timestamp"
    )
    last_login_at = Column(
        DateTime,
        nullable=True,
        comment="Last login timestamp"
    )
    password_changed_at = Column(
        DateTime,
        nullable=True,
        comment="Last password change timestamp"
    )

    # Relationships
    chat_sessions = relationship(
        "ChatSession",
        back_populates="user",
        foreign_keys="ChatSession.user_id",
        lazy="dynamic",
    )
    vqa_sessions = relationship(
        "VQASession",
        back_populates="user",
        foreign_keys="VQASession.user_id",
        lazy="dynamic",
    )
    refresh_tokens = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', role={self.role})>"

    def to_dict(self, include_sensitive: bool = False) -> dict:
        """Convert to dictionary"""
        data = {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "avatar_url": self.avatar_url,
            "bio": self.bio,
            "role": self.role.value if self.role else None,
            "status": self.status.value if self.status else None,
            "is_email_verified": self.is_email_verified,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
        }

        if include_sensitive:
            data["api_key"] = self.api_key
            data["daily_api_limit"] = self.daily_api_limit
            data["monthly_api_limit"] = self.monthly_api_limit

        return data

    @property
    def is_active(self) -> bool:
        """Check if user account is active"""
        return self.status == UserStatus.ACTIVE

    @property
    def is_admin(self) -> bool:
        """Check if user has admin role"""
        return self.role == UserRole.ADMIN


class RefreshToken(Base):
    """
    Refresh Token entity for JWT authentication

    Stores refresh tokens for token renewal
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_token", "token"),
        Index("ix_refresh_tokens_user_id", "user_id"),
        {"extend_existing": True},
    )

    # Primary Key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Token
    token = Column(
        String(500),
        unique=True,
        nullable=False,
        comment="Refresh token value"
    )
    user_id = Column(
        Integer,
        nullable=False,
        comment="User ID"
    )

    # Metadata
    device_info = Column(
        String(255),
        nullable=True,
        comment="Device/browser information"
    )
    ip_address = Column(
        String(45),
        nullable=True,
        comment="IP address"
    )

    # Status
    is_revoked = Column(
        Boolean,
        default=False,
        comment="Token revocation status"
    )

    # Timestamps
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    expires_at = Column(
        DateTime,
        nullable=False,
        comment="Token expiration time"
    )
    last_used_at = Column(
        DateTime,
        nullable=True,
        comment="Last usage timestamp"
    )

    # Relationships
    user = relationship("User", back_populates="refresh_tokens")

    def __repr__(self) -> str:
        return f"<RefreshToken(id={self.id}, user_id={self.user_id}, revoked={self.is_revoked})>"

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "device_info": self.device_info,
            "ip_address": self.ip_address,
            "is_revoked": self.is_revoked,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
        }

    @property
    def is_expired(self) -> bool:
        """Check if token is expired"""
        return datetime.utcnow() > self.expires_at

    @property
    def is_valid(self) -> bool:
        """Check if token is valid (not revoked and not expired)"""
        return not self.is_revoked and not self.is_expired


__all__ = ["User", "UserRole", "UserStatus", "RefreshToken"]
