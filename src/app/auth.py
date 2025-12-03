# src/app/auth.py
"""
Authentication Middleware and Dependencies
Provides authentication utilities for FastAPI routes
"""

import logging
from typing import Optional, Callable
from functools import wraps

from fastapi import Depends, HTTPException, Request, Header
from fastapi.security import OAuth2PasswordBearer, APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.dependencies import get_db
from src.app.models.user import User, UserRole

logger = logging.getLogger(__name__)

# OAuth2 scheme for Bearer token authentication
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login/form",
    auto_error=False,
)

# API Key header scheme
api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
)


# ============================================================================
# Authentication Dependencies
# ============================================================================


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    api_key: Optional[str] = Depends(api_key_header),
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Get current authenticated user

    Supports:
    - Bearer token authentication (OAuth2)
    - API key authentication (X-API-Key header)
    - Authorization header (Bearer token)

    Returns None if no valid authentication provided
    """
    from src.services.auth_service import AuthService

    auth_service = AuthService(session=db)

    # Try Bearer token from oauth2_scheme
    if token:
        user = await auth_service.validate_token(token)
        if user:
            return user

    # Try Authorization header
    if authorization and authorization.startswith("Bearer "):
        bearer_token = authorization[7:]
        user = await auth_service.validate_token(bearer_token)
        if user:
            return user

    # Try API key
    if api_key:
        user = await auth_service.get_user_by_api_key(api_key)
        if user and user.is_active:
            return user

    return None


async def get_current_user_required(
    user: Optional[User] = Depends(get_current_user),
) -> User:
    """
    Get current authenticated user (required)

    Raises 401 if not authenticated
    """
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_active_user(
    user: User = Depends(get_current_user_required),
) -> User:
    """
    Get current active user

    Raises 403 if user is not active
    """
    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="User account is inactive",
        )
    return user


async def get_admin_user(
    user: User = Depends(get_current_active_user),
) -> User:
    """
    Get current admin user

    Raises 403 if user is not admin
    """
    if not user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Admin privileges required",
        )
    return user


async def get_optional_user(
    user: Optional[User] = Depends(get_current_user),
) -> Optional[User]:
    """
    Get current user if authenticated, None otherwise

    Does not raise error if not authenticated
    """
    return user


# ============================================================================
# Role-based Access Control
# ============================================================================


def require_roles(*allowed_roles: UserRole):
    """
    Dependency factory for role-based access control

    Usage:
        @router.get("/admin-only")
        async def admin_endpoint(user: User = Depends(require_roles(UserRole.ADMIN))):
            ...
    """
    async def role_checker(
        user: User = Depends(get_current_active_user),
    ) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Required roles: {[r.value for r in allowed_roles]}",
            )
        return user

    return role_checker


def require_any_role(*allowed_roles: UserRole):
    """Alias for require_roles"""
    return require_roles(*allowed_roles)


def admin_required():
    """Dependency that requires admin role"""
    return require_roles(UserRole.ADMIN)


def user_required():
    """Dependency that requires user or admin role"""
    return require_roles(UserRole.USER, UserRole.ADMIN)


# ============================================================================
# Rate Limiting (Basic Implementation)
# ============================================================================


class RateLimiter:
    """
    Simple rate limiter based on user's API limits

    Note: For production, use Redis-based rate limiting
    """

    def __init__(self, limit_type: str = "daily"):
        self.limit_type = limit_type
        self._request_counts = {}  # In-memory store (use Redis in production)

    async def check_limit(self, user: User) -> bool:
        """
        Check if user is within rate limit

        Returns True if within limit, raises HTTPException if exceeded
        """
        # Skip for admin users
        if user.is_admin:
            return True

        # Get limit based on type
        if self.limit_type == "daily":
            limit = user.daily_api_limit
        else:
            limit = user.monthly_api_limit

        # Simple in-memory counting (use Redis in production)
        key = f"{user.id}:{self.limit_type}"
        current_count = self._request_counts.get(key, 0)

        if current_count >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. {self.limit_type.capitalize()} limit: {limit}",
            )

        self._request_counts[key] = current_count + 1
        return True


def rate_limit(limit_type: str = "daily"):
    """
    Rate limiting dependency factory

    Usage:
        @router.get("/limited")
        async def limited_endpoint(
            user: User = Depends(get_current_active_user),
            _: bool = Depends(rate_limit("daily")),
        ):
            ...
    """
    limiter = RateLimiter(limit_type)

    async def check_rate_limit(
        user: User = Depends(get_current_active_user),
    ) -> bool:
        return await limiter.check_limit(user)

    return check_rate_limit


# ============================================================================
# Utility Functions
# ============================================================================


def get_client_ip(request: Request) -> str:
    """Get client IP address from request"""
    # Check for forwarded IP (behind proxy)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    # Check for real IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fall back to client host
    if request.client:
        return request.client.host

    return "unknown"


def get_user_agent(request: Request) -> str:
    """Get user agent from request"""
    return request.headers.get("User-Agent", "unknown")[:255]


# ============================================================================
# Exports
# ============================================================================


__all__ = [
    # Dependencies
    "get_current_user",
    "get_current_user_required",
    "get_current_active_user",
    "get_admin_user",
    "get_optional_user",
    # Role-based access
    "require_roles",
    "require_any_role",
    "admin_required",
    "user_required",
    # Rate limiting
    "rate_limit",
    "RateLimiter",
    # Utilities
    "get_client_ip",
    "get_user_agent",
    # Schemes
    "oauth2_scheme",
    "api_key_header",
]
