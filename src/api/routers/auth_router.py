# src/api/routers/auth_router.py
"""
Authentication API Router
REST endpoints for user authentication and account management
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Header, Request, Body
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.dependencies import get_db
from src.app.models.user import UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


# ============================================================================
# Request/Response Models
# ============================================================================


class RegisterRequest(BaseModel):
    """User registration request"""
    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        pattern="^[a-zA-Z0-9_-]+$",
        description="Username (alphanumeric, underscore, hyphen)",
    )
    email: EmailStr = Field(..., description="Email address")
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Password (min 8 chars)",
    )
    full_name: Optional[str] = Field(
        None,
        max_length=100,
        description="Full name",
    )


class LoginRequest(BaseModel):
    """User login request"""
    username: str = Field(..., description="Username or email")
    password: str = Field(..., description="Password")


class TokenResponse(BaseModel):
    """Token response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshTokenRequest(BaseModel):
    """Refresh token request"""
    refresh_token: str = Field(..., description="Refresh token")


class ChangePasswordRequest(BaseModel):
    """Change password request"""
    current_password: str = Field(..., description="Current password")
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="New password",
    )


class UpdateProfileRequest(BaseModel):
    """Update profile request"""
    full_name: Optional[str] = Field(None, max_length=100)
    bio: Optional[str] = Field(None, max_length=500)
    avatar_url: Optional[str] = Field(None, max_length=500)
    email_notifications: Optional[bool] = None


class UserResponse(BaseModel):
    """User response"""
    id: int
    username: str
    email: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    role: str
    status: str
    is_email_verified: bool
    created_at: Optional[str] = None
    last_login_at: Optional[str] = None


class AuthResponse(BaseModel):
    """Authentication response"""
    user: UserResponse
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class MessageResponse(BaseModel):
    """Generic message response"""
    message: str
    success: bool = True


# ============================================================================
# Dependency Injection
# ============================================================================


async def get_auth_service(db: AsyncSession = Depends(get_db)):
    """Get auth service instance"""
    from src.services.auth_service import AuthService
    return AuthService(session=db)


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current authenticated user from token

    Returns None if no token or invalid token (for optional auth)
    """
    if not token:
        return None

    from src.services.auth_service import AuthService
    auth_service = AuthService(session=db)
    return await auth_service.validate_token(token)


async def get_current_user_required(
    user=Depends(get_current_user),
):
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


async def get_admin_user(
    user=Depends(get_current_user_required),
):
    """
    Get current admin user

    Raises 403 if not admin
    """
    if not user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Admin access required",
        )
    return user


# ============================================================================
# Authentication Endpoints
# ============================================================================


@router.post(
    "/register",
    response_model=AuthResponse,
    summary="Register User",
    description="Register a new user account",
)
async def register(
    request: RegisterRequest,
    req: Request,
    auth_service=Depends(get_auth_service),
):
    """Register a new user"""
    try:
        result = await auth_service.register(
            username=request.username,
            email=request.email,
            password=request.password,
            full_name=request.full_name,
        )

        return AuthResponse(
            user=UserResponse(**result["user"]),
            access_token=result["access_token"],
            refresh_token=result["refresh_token"],
            token_type=result["token_type"],
            expires_in=result["expires_in"],
        )

    except Exception as e:
        error_msg = str(e).lower()
        if "already exists" in error_msg or "already registered" in error_msg:
            raise HTTPException(status_code=409, detail=str(e))
        if "password" in error_msg:
            raise HTTPException(status_code=400, detail=str(e))
        logger.error(f"Registration failed: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Login",
    description="Authenticate user and return tokens",
)
async def login(
    request: LoginRequest,
    req: Request,
    auth_service=Depends(get_auth_service),
):
    """Login with username/email and password"""
    try:
        # Get client info
        device_info = req.headers.get("User-Agent", "")[:255]
        ip_address = req.client.host if req.client else None

        result = await auth_service.login(
            username_or_email=request.username,
            password=request.password,
            device_info=device_info,
            ip_address=ip_address,
        )

        return AuthResponse(
            user=UserResponse(**result["user"]),
            access_token=result["access_token"],
            refresh_token=result["refresh_token"],
            token_type=result["token_type"],
            expires_in=result["expires_in"],
        )

    except Exception as e:
        error_msg = str(e).lower()
        if "invalid credentials" in error_msg:
            raise HTTPException(status_code=401, detail="Invalid username or password")
        if "account is" in error_msg:
            raise HTTPException(status_code=403, detail=str(e))
        logger.error(f"Login failed: {e}")
        raise HTTPException(status_code=500, detail="Login failed")


@router.post(
    "/login/form",
    response_model=TokenResponse,
    summary="Login (OAuth2 Form)",
    description="OAuth2 compatible login endpoint",
)
async def login_form(
    form_data: OAuth2PasswordRequestForm = Depends(),
    req: Request = None,
    auth_service=Depends(get_auth_service),
):
    """OAuth2 compatible login endpoint"""
    try:
        device_info = req.headers.get("User-Agent", "")[:255] if req else None
        ip_address = req.client.host if req and req.client else None

        result = await auth_service.login(
            username_or_email=form_data.username,
            password=form_data.password,
            device_info=device_info,
            ip_address=ip_address,
        )

        return TokenResponse(
            access_token=result["access_token"],
            refresh_token=result["refresh_token"],
            token_type=result["token_type"],
            expires_in=result["expires_in"],
        )

    except Exception as e:
        error_msg = str(e).lower()
        if "invalid credentials" in error_msg:
            raise HTTPException(status_code=401, detail="Invalid username or password")
        if "account is" in error_msg:
            raise HTTPException(status_code=403, detail=str(e))
        logger.error(f"Login failed: {e}")
        raise HTTPException(status_code=500, detail="Login failed")


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh Token",
    description="Refresh access token using refresh token",
)
async def refresh_token(
    request: RefreshTokenRequest,
    auth_service=Depends(get_auth_service),
):
    """Refresh access token"""
    try:
        result = await auth_service.refresh_access_token(
            refresh_token=request.refresh_token,
        )

        return TokenResponse(
            access_token=result["access_token"],
            refresh_token=request.refresh_token,
            token_type=result["token_type"],
            expires_in=result["expires_in"],
        )

    except Exception as e:
        error_msg = str(e).lower()
        if "invalid" in error_msg or "expired" in error_msg:
            raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
        logger.error(f"Token refresh failed: {e}")
        raise HTTPException(status_code=500, detail="Token refresh failed")


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Logout",
    description="Logout and revoke refresh token",
)
async def logout(
    request: Optional[RefreshTokenRequest] = None,
    current_user=Depends(get_current_user_required),
    auth_service=Depends(get_auth_service),
):
    """Logout user"""
    try:
        refresh_token = request.refresh_token if request else None

        await auth_service.logout(
            refresh_token=refresh_token,
            user_id=current_user.id,
        )

        return MessageResponse(message="Logged out successfully")

    except Exception as e:
        logger.error(f"Logout failed: {e}")
        raise HTTPException(status_code=500, detail="Logout failed")


@router.post(
    "/logout/all",
    response_model=MessageResponse,
    summary="Logout All Devices",
    description="Logout from all devices by revoking all refresh tokens",
)
async def logout_all(
    current_user=Depends(get_current_user_required),
    auth_service=Depends(get_auth_service),
):
    """Logout from all devices"""
    try:
        await auth_service.logout(
            user_id=current_user.id,
            logout_all=True,
        )

        return MessageResponse(message="Logged out from all devices")

    except Exception as e:
        logger.error(f"Logout all failed: {e}")
        raise HTTPException(status_code=500, detail="Logout failed")


# ============================================================================
# User Profile Endpoints
# ============================================================================


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get Current User",
    description="Get current authenticated user profile",
)
async def get_me(
    current_user=Depends(get_current_user_required),
):
    """Get current user profile"""
    return UserResponse(**current_user.to_dict())


@router.put(
    "/me",
    response_model=UserResponse,
    summary="Update Profile",
    description="Update current user profile",
)
async def update_profile(
    request: UpdateProfileRequest,
    current_user=Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db),
):
    """Update user profile"""
    try:
        # Update fields
        if request.full_name is not None:
            current_user.full_name = request.full_name
        if request.bio is not None:
            current_user.bio = request.bio
        if request.avatar_url is not None:
            current_user.avatar_url = request.avatar_url
        if request.email_notifications is not None:
            current_user.email_notifications = request.email_notifications

        await db.commit()
        await db.refresh(current_user)

        return UserResponse(**current_user.to_dict())

    except Exception as e:
        await db.rollback()
        logger.error(f"Profile update failed: {e}")
        raise HTTPException(status_code=500, detail="Profile update failed")


@router.post(
    "/me/password",
    response_model=MessageResponse,
    summary="Change Password",
    description="Change current user password",
)
async def change_password(
    request: ChangePasswordRequest,
    current_user=Depends(get_current_user_required),
    auth_service=Depends(get_auth_service),
):
    """Change password"""
    try:
        await auth_service.update_password(
            user_id=current_user.id,
            current_password=request.current_password,
            new_password=request.new_password,
        )

        return MessageResponse(message="Password changed successfully")

    except Exception as e:
        error_msg = str(e).lower()
        if "incorrect" in error_msg:
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        if "password" in error_msg:
            raise HTTPException(status_code=400, detail=str(e))
        logger.error(f"Password change failed: {e}")
        raise HTTPException(status_code=500, detail="Password change failed")


@router.post(
    "/me/api-key",
    response_model=dict,
    summary="Regenerate API Key",
    description="Generate a new API key",
)
async def regenerate_api_key(
    current_user=Depends(get_current_user_required),
    auth_service=Depends(get_auth_service),
):
    """Regenerate API key"""
    try:
        new_api_key = await auth_service.regenerate_api_key(current_user.id)

        return {
            "api_key": new_api_key,
            "message": "API key regenerated successfully",
        }

    except Exception as e:
        logger.error(f"API key regeneration failed: {e}")
        raise HTTPException(status_code=500, detail="API key regeneration failed")


@router.get(
    "/me/sessions",
    response_model=List[dict],
    summary="Get Active Sessions",
    description="Get list of active sessions (refresh tokens)",
)
async def get_sessions(
    current_user=Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db),
):
    """Get active sessions"""
    try:
        from sqlalchemy import select, and_
        from src.app.models.user import RefreshToken

        result = await db.execute(
            select(RefreshToken).where(
                and_(
                    RefreshToken.user_id == current_user.id,
                    RefreshToken.is_revoked == False,
                )
            )
        )
        tokens = result.scalars().all()

        return [
            {
                "id": t.id,
                "device_info": t.device_info,
                "ip_address": t.ip_address,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None,
                "expires_at": t.expires_at.isoformat() if t.expires_at else None,
            }
            for t in tokens
            if not t.is_expired
        ]

    except Exception as e:
        logger.error(f"Get sessions failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get sessions")


# ============================================================================
# Admin Endpoints
# ============================================================================


@router.get(
    "/users",
    response_model=List[UserResponse],
    summary="List Users (Admin)",
    description="Get list of all users (admin only)",
)
async def list_users(
    skip: int = 0,
    limit: int = 50,
    admin_user=Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List all users (admin only)"""
    try:
        from sqlalchemy import select
        from src.app.models.user import User

        result = await db.execute(
            select(User).offset(skip).limit(limit)
        )
        users = result.scalars().all()

        return [UserResponse(**u.to_dict()) for u in users]

    except Exception as e:
        logger.error(f"List users failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to list users")


@router.put(
    "/users/{user_id}/status",
    response_model=MessageResponse,
    summary="Update User Status (Admin)",
    description="Update user account status (admin only)",
)
async def update_user_status(
    user_id: int,
    status: str = Body(..., embed=True),
    admin_user=Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Update user status (admin only)"""
    try:
        from sqlalchemy import select
        from src.app.models.user import User, UserStatus

        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        try:
            user.status = UserStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status value")

        await db.commit()

        return MessageResponse(message=f"User status updated to {status}")

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Update user status failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to update user status")


__all__ = [
    "router",
    "get_current_user",
    "get_current_user_required",
    "get_admin_user",
    "oauth2_scheme",
]
