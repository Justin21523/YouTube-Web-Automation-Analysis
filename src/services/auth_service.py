# src/services/auth_service.py
"""
Authentication Service
Handles user authentication, JWT tokens, and password management
"""

import os
import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple

from passlib.context import CryptContext
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from src.services.base_service import BaseService
from src.services.exceptions import (
    ResourceNotFoundError,
    ValidationError,
    AuthenticationError,
    AuthorizationError,
)
from src.app.models.user import User, UserRole, UserStatus, RefreshToken

logger = logging.getLogger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))


class AuthService(BaseService):
    """
    Authentication service

    Handles:
    - User registration and login
    - Password hashing and verification
    - JWT token generation and validation
    - Refresh token management
    - API key authentication
    """

    def __init__(self, session: AsyncSession, cache=None, config=None):
        super().__init__(cache=cache, config=config)
        self.session = session

    def get_service_name(self) -> str:
        return "auth"

    # ========================================================================
    # Password Utilities
    # ========================================================================

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt"""
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def validate_password_strength(password: str) -> Tuple[bool, str]:
        """
        Validate password strength

        Requirements:
        - Minimum 8 characters
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one digit
        """
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"

        if not any(c.isupper() for c in password):
            return False, "Password must contain at least one uppercase letter"

        if not any(c.islower() for c in password):
            return False, "Password must contain at least one lowercase letter"

        if not any(c.isdigit() for c in password):
            return False, "Password must contain at least one digit"

        return True, "Password is valid"

    # ========================================================================
    # JWT Token Management
    # ========================================================================

    @staticmethod
    def create_access_token(
        data: Dict[str, Any],
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """
        Create a JWT access token

        Args:
            data: Payload data
            expires_delta: Custom expiration time

        Returns:
            Encoded JWT token
        """
        to_encode = data.copy()

        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

        to_encode.update({
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access",
        })

        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    def create_refresh_token(
        data: Dict[str, Any],
        expires_delta: Optional[timedelta] = None,
    ) -> Tuple[str, datetime]:
        """
        Create a JWT refresh token

        Args:
            data: Payload data
            expires_delta: Custom expiration time

        Returns:
            Tuple of (encoded token, expiration datetime)
        """
        to_encode = data.copy()

        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

        to_encode.update({
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "refresh",
            "jti": secrets.token_urlsafe(16),  # Token ID for revocation
        })

        token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return token, expire

    @staticmethod
    def decode_token(token: str) -> Dict[str, Any]:
        """
        Decode and validate a JWT token

        Args:
            token: JWT token string

        Returns:
            Decoded payload

        Raises:
            AuthenticationError: If token is invalid or expired
        """
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload
        except JWTError as e:
            logger.warning(f"JWT decode error: {e}")
            raise AuthenticationError("Invalid or expired token")

    # ========================================================================
    # User Registration
    # ========================================================================

    async def register(
        self,
        username: str,
        email: str,
        password: str,
        full_name: Optional[str] = None,
        role: UserRole = UserRole.USER,
    ) -> Dict[str, Any]:
        """
        Register a new user

        Args:
            username: Unique username
            email: User email
            password: Plain text password
            full_name: Optional full name
            role: User role

        Returns:
            Created user info and tokens
        """
        self.log_operation("register", username=username, email=email)

        # Validate password strength
        is_valid, message = self.validate_password_strength(password)
        if not is_valid:
            raise ValidationError(message)

        # Check if username exists
        existing_user = await self.session.execute(
            select(User).where(User.username == username)
        )
        if existing_user.scalar_one_or_none():
            raise ValidationError("Username already exists")

        # Check if email exists
        existing_email = await self.session.execute(
            select(User).where(User.email == email)
        )
        if existing_email.scalar_one_or_none():
            raise ValidationError("Email already registered")

        try:
            # Create user
            user = User(
                username=username,
                email=email,
                hashed_password=self.hash_password(password),
                full_name=full_name,
                role=role,
                status=UserStatus.ACTIVE,
                api_key=secrets.token_urlsafe(32),
            )

            self.session.add(user)
            await self.session.commit()
            await self.session.refresh(user)

            # Generate tokens
            access_token = self.create_access_token({
                "sub": str(user.id),
                "username": user.username,
                "role": user.role.value,
            })

            refresh_token, refresh_expires = self.create_refresh_token({
                "sub": str(user.id),
            })

            # Store refresh token
            token_record = RefreshToken(
                token=refresh_token,
                user_id=user.id,
                expires_at=refresh_expires,
            )
            self.session.add(token_record)
            await self.session.commit()

            logger.info(f"User registered: {username}")

            return {
                "user": user.to_dict(),
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            }

        except Exception as e:
            await self.session.rollback()
            logger.error(f"Registration failed: {e}")
            raise

    # ========================================================================
    # User Login
    # ========================================================================

    async def login(
        self,
        username_or_email: str,
        password: str,
        device_info: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Authenticate user and return tokens

        Args:
            username_or_email: Username or email
            password: Plain text password
            device_info: Optional device information
            ip_address: Optional IP address

        Returns:
            User info and tokens
        """
        self.log_operation("login", identifier=username_or_email)

        # Find user by username or email
        result = await self.session.execute(
            select(User).where(
                (User.username == username_or_email) |
                (User.email == username_or_email)
            )
        )
        user = result.scalar_one_or_none()

        if not user:
            raise AuthenticationError("Invalid credentials")

        # Verify password
        if not self.verify_password(password, user.hashed_password):
            raise AuthenticationError("Invalid credentials")

        # Check account status
        if user.status != UserStatus.ACTIVE:
            raise AuthenticationError(f"Account is {user.status.value}")

        try:
            # Update last login
            user.last_login_at = datetime.utcnow()

            # Generate tokens
            access_token = self.create_access_token({
                "sub": str(user.id),
                "username": user.username,
                "role": user.role.value,
            })

            refresh_token, refresh_expires = self.create_refresh_token({
                "sub": str(user.id),
            })

            # Store refresh token
            token_record = RefreshToken(
                token=refresh_token,
                user_id=user.id,
                expires_at=refresh_expires,
                device_info=device_info,
                ip_address=ip_address,
            )
            self.session.add(token_record)
            await self.session.commit()

            logger.info(f"User logged in: {user.username}")

            return {
                "user": user.to_dict(),
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            }

        except Exception as e:
            await self.session.rollback()
            logger.error(f"Login failed: {e}")
            raise

    # ========================================================================
    # Token Refresh
    # ========================================================================

    async def refresh_access_token(
        self,
        refresh_token: str,
    ) -> Dict[str, Any]:
        """
        Refresh access token using refresh token

        Args:
            refresh_token: Valid refresh token

        Returns:
            New access token
        """
        # Decode refresh token
        payload = self.decode_token(refresh_token)

        if payload.get("type") != "refresh":
            raise AuthenticationError("Invalid token type")

        user_id = payload.get("sub")
        if not user_id:
            raise AuthenticationError("Invalid token payload")

        # Verify token exists and is not revoked
        result = await self.session.execute(
            select(RefreshToken).where(
                and_(
                    RefreshToken.token == refresh_token,
                    RefreshToken.is_revoked == False,
                )
            )
        )
        token_record = result.scalar_one_or_none()

        if not token_record or token_record.is_expired:
            raise AuthenticationError("Invalid or expired refresh token")

        # Get user
        result = await self.session.execute(
            select(User).where(User.id == int(user_id))
        )
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            raise AuthenticationError("User not found or inactive")

        # Update last used
        token_record.last_used_at = datetime.utcnow()

        # Generate new access token
        access_token = self.create_access_token({
            "sub": str(user.id),
            "username": user.username,
            "role": user.role.value,
        })

        await self.session.commit()

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }

    # ========================================================================
    # Logout
    # ========================================================================

    async def logout(
        self,
        refresh_token: Optional[str] = None,
        user_id: Optional[int] = None,
        logout_all: bool = False,
    ) -> bool:
        """
        Logout user by revoking refresh tokens

        Args:
            refresh_token: Specific token to revoke
            user_id: User ID for logout_all
            logout_all: Revoke all user tokens

        Returns:
            Success status
        """
        try:
            if logout_all and user_id:
                # Revoke all user tokens
                result = await self.session.execute(
                    select(RefreshToken).where(
                        and_(
                            RefreshToken.user_id == user_id,
                            RefreshToken.is_revoked == False,
                        )
                    )
                )
                tokens = result.scalars().all()
                for token in tokens:
                    token.is_revoked = True
                logger.info(f"Revoked all tokens for user {user_id}")

            elif refresh_token:
                # Revoke specific token
                result = await self.session.execute(
                    select(RefreshToken).where(RefreshToken.token == refresh_token)
                )
                token = result.scalar_one_or_none()
                if token:
                    token.is_revoked = True
                    logger.info(f"Revoked token for user {token.user_id}")

            await self.session.commit()
            return True

        except Exception as e:
            await self.session.rollback()
            logger.error(f"Logout failed: {e}")
            return False

    # ========================================================================
    # User Management
    # ========================================================================

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID"""
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username"""
        result = await self.session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def get_user_by_api_key(self, api_key: str) -> Optional[User]:
        """Get user by API key"""
        result = await self.session.execute(
            select(User).where(User.api_key == api_key)
        )
        return result.scalar_one_or_none()

    async def update_password(
        self,
        user_id: int,
        current_password: str,
        new_password: str,
    ) -> bool:
        """
        Update user password

        Args:
            user_id: User ID
            current_password: Current password
            new_password: New password

        Returns:
            Success status
        """
        user = await self.get_user_by_id(user_id)
        if not user:
            raise ResourceNotFoundError("User", str(user_id))

        # Verify current password
        if not self.verify_password(current_password, user.hashed_password):
            raise AuthenticationError("Current password is incorrect")

        # Validate new password
        is_valid, message = self.validate_password_strength(new_password)
        if not is_valid:
            raise ValidationError(message)

        try:
            user.hashed_password = self.hash_password(new_password)
            user.password_changed_at = datetime.utcnow()

            # Revoke all existing refresh tokens
            result = await self.session.execute(
                select(RefreshToken).where(
                    and_(
                        RefreshToken.user_id == user_id,
                        RefreshToken.is_revoked == False,
                    )
                )
            )
            tokens = result.scalars().all()
            for token in tokens:
                token.is_revoked = True

            await self.session.commit()
            logger.info(f"Password updated for user {user_id}")
            return True

        except Exception as e:
            await self.session.rollback()
            logger.error(f"Password update failed: {e}")
            raise

    async def regenerate_api_key(self, user_id: int) -> str:
        """
        Regenerate user API key

        Args:
            user_id: User ID

        Returns:
            New API key
        """
        user = await self.get_user_by_id(user_id)
        if not user:
            raise ResourceNotFoundError("User", str(user_id))

        try:
            new_api_key = secrets.token_urlsafe(32)
            user.api_key = new_api_key
            await self.session.commit()

            logger.info(f"API key regenerated for user {user_id}")
            return new_api_key

        except Exception as e:
            await self.session.rollback()
            logger.error(f"API key regeneration failed: {e}")
            raise

    # ========================================================================
    # Token Validation
    # ========================================================================

    async def validate_token(self, token: str) -> Optional[User]:
        """
        Validate access token and return user

        Args:
            token: JWT access token

        Returns:
            User object if valid, None otherwise
        """
        try:
            payload = self.decode_token(token)

            if payload.get("type") != "access":
                return None

            user_id = payload.get("sub")
            if not user_id:
                return None

            user = await self.get_user_by_id(int(user_id))
            if not user or not user.is_active:
                return None

            return user

        except AuthenticationError:
            return None


# Custom exceptions
class AuthenticationError(Exception):
    """Authentication error"""
    pass


class AuthorizationError(Exception):
    """Authorization error"""
    pass


__all__ = ["AuthService", "AuthenticationError", "AuthorizationError"]
