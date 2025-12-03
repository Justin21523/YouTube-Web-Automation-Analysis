# src/api/routers/health_router.py
"""
Health Check Router
Comprehensive health check endpoints for monitoring and alerting
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.config import get_config
from src.app.database import db_manager
from src.app.shared_cache import get_shared_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["Health"])


# ============================================================================
# Response Models
# ============================================================================


class HealthStatus(str, Enum):
    """Health status enumeration"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentHealth(BaseModel):
    """Individual component health status"""
    name: str = Field(..., description="Component name")
    status: HealthStatus = Field(..., description="Health status")
    latency_ms: Optional[float] = Field(None, description="Response latency in ms")
    message: Optional[str] = Field(None, description="Additional status message")
    last_check: datetime = Field(default_factory=datetime.utcnow, description="Last check time")


class HealthResponse(BaseModel):
    """Overall health response"""
    status: HealthStatus = Field(..., description="Overall health status")
    version: str = Field(..., description="Application version")
    environment: str = Field(..., description="Current environment")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Check timestamp")
    uptime_seconds: Optional[float] = Field(None, description="Application uptime")
    components: Dict[str, ComponentHealth] = Field(default_factory=dict, description="Component health")


class ReadinessResponse(BaseModel):
    """Readiness check response"""
    ready: bool = Field(..., description="Whether application is ready")
    checks: Dict[str, bool] = Field(default_factory=dict, description="Individual check results")
    message: Optional[str] = Field(None, description="Status message")


class LivenessResponse(BaseModel):
    """Liveness check response"""
    alive: bool = Field(..., description="Whether application is alive")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Check timestamp")


class MetricsResponse(BaseModel):
    """Application metrics response"""
    database: Dict[str, Any] = Field(default_factory=dict, description="Database metrics")
    cache: Dict[str, Any] = Field(default_factory=dict, description="Cache metrics")
    system: Dict[str, Any] = Field(default_factory=dict, description="System metrics")
    features: Dict[str, bool] = Field(default_factory=dict, description="Feature status")


# ============================================================================
# Global State
# ============================================================================

_startup_time: Optional[datetime] = None


def set_startup_time():
    """Set application startup time"""
    global _startup_time
    _startup_time = datetime.utcnow()


def get_uptime() -> Optional[float]:
    """Get application uptime in seconds"""
    if _startup_time:
        return (datetime.utcnow() - _startup_time).total_seconds()
    return None


# ============================================================================
# Health Check Functions
# ============================================================================


async def check_database() -> ComponentHealth:
    """Check database connectivity"""
    start_time = time.time()
    try:
        async with db_manager.session() as session:
            await session.execute(text("SELECT 1"))
            latency = (time.time() - start_time) * 1000
            return ComponentHealth(
                name="database",
                status=HealthStatus.HEALTHY,
                latency_ms=round(latency, 2),
                message="Database connection successful"
            )
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        logger.error(f"Database health check failed: {e}")
        return ComponentHealth(
            name="database",
            status=HealthStatus.UNHEALTHY,
            latency_ms=round(latency, 2),
            message=f"Database error: {str(e)}"
        )


async def check_redis() -> ComponentHealth:
    """Check Redis connectivity"""
    start_time = time.time()
    config = get_config()

    if not config.cache.redis_enable:
        return ComponentHealth(
            name="redis",
            status=HealthStatus.HEALTHY,
            message="Redis disabled - using local cache"
        )

    try:
        import redis.asyncio as redis
        client = redis.from_url(config.cache.redis_url)
        await client.ping()
        await client.close()
        latency = (time.time() - start_time) * 1000
        return ComponentHealth(
            name="redis",
            status=HealthStatus.HEALTHY,
            latency_ms=round(latency, 2),
            message="Redis connection successful"
        )
    except ImportError:
        return ComponentHealth(
            name="redis",
            status=HealthStatus.DEGRADED,
            message="Redis client not installed"
        )
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        logger.error(f"Redis health check failed: {e}")
        return ComponentHealth(
            name="redis",
            status=HealthStatus.UNHEALTHY,
            latency_ms=round(latency, 2),
            message=f"Redis error: {str(e)}"
        )


async def check_celery() -> ComponentHealth:
    """Check Celery worker availability"""
    start_time = time.time()

    try:
        from src.infrastructure.tasks.celery_app import celery_app
        inspect = celery_app.control.inspect()
        active = inspect.active()

        latency = (time.time() - start_time) * 1000

        if active:
            worker_count = len(active)
            return ComponentHealth(
                name="celery",
                status=HealthStatus.HEALTHY,
                latency_ms=round(latency, 2),
                message=f"{worker_count} worker(s) active"
            )
        else:
            return ComponentHealth(
                name="celery",
                status=HealthStatus.DEGRADED,
                latency_ms=round(latency, 2),
                message="No active workers found"
            )
    except ImportError:
        return ComponentHealth(
            name="celery",
            status=HealthStatus.DEGRADED,
            message="Celery not available"
        )
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        logger.warning(f"Celery health check failed: {e}")
        return ComponentHealth(
            name="celery",
            status=HealthStatus.DEGRADED,
            latency_ms=round(latency, 2),
            message=f"Celery check failed: {str(e)}"
        )


def check_disk_space() -> ComponentHealth:
    """Check disk space availability"""
    try:
        import shutil
        config = get_config()
        cache_root = config.cache.cache_root

        total, used, free = shutil.disk_usage(cache_root)
        free_gb = free / (1024 ** 3)
        used_percent = (used / total) * 100

        if free_gb < 1:
            status = HealthStatus.UNHEALTHY
            message = f"Critical: Only {free_gb:.2f}GB free"
        elif free_gb < 5:
            status = HealthStatus.DEGRADED
            message = f"Warning: {free_gb:.2f}GB free"
        else:
            status = HealthStatus.HEALTHY
            message = f"{free_gb:.2f}GB free ({used_percent:.1f}% used)"

        return ComponentHealth(
            name="disk",
            status=status,
            message=message
        )
    except Exception as e:
        logger.warning(f"Disk space check failed: {e}")
        return ComponentHealth(
            name="disk",
            status=HealthStatus.DEGRADED,
            message=f"Check failed: {str(e)}"
        )


def check_memory() -> ComponentHealth:
    """Check memory usage"""
    try:
        import psutil
        memory = psutil.virtual_memory()
        used_percent = memory.percent
        available_gb = memory.available / (1024 ** 3)

        if used_percent > 95:
            status = HealthStatus.UNHEALTHY
            message = f"Critical: {used_percent:.1f}% used"
        elif used_percent > 85:
            status = HealthStatus.DEGRADED
            message = f"Warning: {used_percent:.1f}% used"
        else:
            status = HealthStatus.HEALTHY
            message = f"{available_gb:.2f}GB available ({used_percent:.1f}% used)"

        return ComponentHealth(
            name="memory",
            status=status,
            message=message
        )
    except ImportError:
        return ComponentHealth(
            name="memory",
            status=HealthStatus.DEGRADED,
            message="psutil not installed"
        )
    except Exception as e:
        logger.warning(f"Memory check failed: {e}")
        return ComponentHealth(
            name="memory",
            status=HealthStatus.DEGRADED,
            message=f"Check failed: {str(e)}"
        )


# ============================================================================
# Health Endpoints
# ============================================================================


@router.get(
    "",
    response_model=HealthResponse,
    summary="Full health check",
    description="Comprehensive health check of all system components"
)
async def health_check() -> HealthResponse:
    """
    Full health check endpoint
    Checks: database, redis, celery, disk, memory
    """
    config = get_config()

    # Run all checks concurrently
    db_health, redis_health, celery_health = await asyncio.gather(
        check_database(),
        check_redis(),
        check_celery(),
    )

    disk_health = check_disk_space()
    memory_health = check_memory()

    components = {
        "database": db_health,
        "redis": redis_health,
        "celery": celery_health,
        "disk": disk_health,
        "memory": memory_health,
    }

    # Determine overall status
    statuses = [c.status for c in components.values()]

    if HealthStatus.UNHEALTHY in statuses:
        overall_status = HealthStatus.UNHEALTHY
    elif HealthStatus.DEGRADED in statuses:
        overall_status = HealthStatus.DEGRADED
    else:
        overall_status = HealthStatus.HEALTHY

    return HealthResponse(
        status=overall_status,
        version="0.1.0",
        environment=config.get("app.env", "development"),
        uptime_seconds=get_uptime(),
        components=components,
    )


@router.get(
    "/live",
    response_model=LivenessResponse,
    summary="Liveness probe",
    description="Simple liveness check for Kubernetes"
)
async def liveness_probe() -> LivenessResponse:
    """
    Kubernetes liveness probe
    Returns 200 if application is running
    """
    return LivenessResponse(alive=True)


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description="Readiness check for load balancer"
)
async def readiness_probe() -> ReadinessResponse:
    """
    Kubernetes readiness probe
    Checks if application is ready to serve traffic
    """
    checks = {}

    # Database check
    try:
        db_health = await check_database()
        checks["database"] = db_health.status == HealthStatus.HEALTHY
    except Exception:
        checks["database"] = False

    # Redis check (if enabled)
    config = get_config()
    if config.cache.redis_enable:
        try:
            redis_health = await check_redis()
            checks["redis"] = redis_health.status == HealthStatus.HEALTHY
        except Exception:
            checks["redis"] = False
    else:
        checks["redis"] = True

    ready = all(checks.values())

    if not ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ReadinessResponse(
                ready=False,
                checks=checks,
                message="Service not ready"
            ).model_dump()
        )

    return ReadinessResponse(
        ready=True,
        checks=checks,
        message="Service ready"
    )


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    summary="Application metrics",
    description="Get application metrics for monitoring"
)
async def get_metrics() -> MetricsResponse:
    """
    Get application metrics
    Useful for Prometheus scraping or custom dashboards
    """
    config = get_config()
    cache = get_shared_cache()

    # Database metrics
    db_metrics = {}
    try:
        async with db_manager.session() as session:
            # Get table counts
            from src.infrastructure.repositories import (
                VideoRepository,
                ChannelRepository,
                CommentRepository,
            )
            video_repo = VideoRepository(session)
            channel_repo = ChannelRepository(session)
            comment_repo = CommentRepository(session)

            db_metrics = {
                "total_videos": await video_repo.count(),
                "total_channels": await channel_repo.count(),
                "total_comments": await comment_repo.count(),
                "connected": True,
            }
    except Exception as e:
        db_metrics = {"connected": False, "error": str(e)}

    # Cache metrics
    cache_metrics = cache.get_cache_stats()

    # System metrics
    system_metrics = {
        "uptime_seconds": get_uptime(),
        "python_version": None,
        "cpu_percent": None,
        "memory_percent": None,
    }

    try:
        import sys
        import psutil

        system_metrics["python_version"] = sys.version
        system_metrics["cpu_percent"] = psutil.cpu_percent()
        system_metrics["memory_percent"] = psutil.virtual_memory().percent
    except ImportError:
        pass

    # Feature flags
    features = {
        "caption": config.features.enable_caption,
        "vqa": config.features.enable_vqa,
        "chat": config.features.enable_chat,
        "rag": config.features.enable_rag,
        "monitoring": config.features.enable_monitoring,
    }

    return MetricsResponse(
        database=db_metrics,
        cache=cache_metrics,
        system=system_metrics,
        features=features,
    )


@router.get(
    "/ping",
    summary="Simple ping",
    description="Simple ping endpoint for basic connectivity check"
)
async def ping() -> Dict[str, str]:
    """Simple ping endpoint"""
    return {"status": "pong", "timestamp": datetime.utcnow().isoformat()}


@router.get(
    "/version",
    summary="Version info",
    description="Get application version information"
)
async def version_info() -> Dict[str, Any]:
    """Get version and build information"""
    config = get_config()

    return {
        "version": "0.1.0",
        "environment": config.get("app.env", "development"),
        "api_version": config.api.prefix,
        "features": {
            "caption": config.features.enable_caption,
            "vqa": config.features.enable_vqa,
            "chat": config.features.enable_chat,
            "rag": config.features.enable_rag,
        },
        "build_info": {
            "python": None,
            "fastapi": None,
            "sqlalchemy": None,
        }
    }
