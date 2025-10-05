"""
Task Management API Router
REST endpoints for background task operations
"""

import logging
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Query, Path, Body
from pydantic import BaseModel, Field

from src.infrastructure.tasks.celery_app import (
    celery_app,
    get_task_info,
    revoke_task,
    get_active_tasks,
    get_worker_stats,
)
from src.infrastructure.tasks.video_tasks import (
    scrape_video_metadata,
    scrape_video_comments,
    scrape_videos_batch,
    search_and_scrape_videos,
)
from src.infrastructure.tasks.channel_tasks import (
    scrape_channel_metadata,
    scrape_channel_videos,
    sync_channel_data,
)
from src.infrastructure.tasks.workflow_tasks import (
    full_video_analysis,
    full_channel_analysis,
    bulk_video_scraping,
)
from src.services.task_tracking_service import (
    get_task_status,
    get_user_tasks,
    get_active_tasks as get_active_db_tasks,
    get_failed_tasks,
    retry_failed_task,
    get_task_statistics,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tasks", tags=["Background Tasks"])


# ============================================================================
# Request/Response Models
# ============================================================================


class VideoScrapeRequest(BaseModel):
    """Request to scrape video"""

    video_id: str = Field(..., description="YouTube video ID")
    fetch_comments: bool = Field(default=False, description="Include comment scraping")
    max_comments: int = Field(default=500, description="Max comments to fetch")


class ChannelScrapeRequest(BaseModel):
    """Request to scrape channel"""

    channel_id: str = Field(..., description="YouTube channel ID")
    max_videos: int = Field(default=50, description="Max videos to fetch")
    include_analysis: bool = Field(default=False, description="Analyze videos")


class SearchScrapeRequest(BaseModel):
    """Request to search and scrape videos"""

    query: str = Field(..., description="Search query")
    max_results: int = Field(default=20, description="Max results")
    order: str = Field(default="relevance", description="Sort order")


class TaskResponse(BaseModel):
    """Task submission response"""

    task_id: str = Field(..., description="Celery task ID")
    status: str = Field(..., description="Task status")
    message: str = Field(..., description="Response message")


class TaskStatusResponse(BaseModel):
    """Task status response"""

    task_id: str
    task_name: Optional[str] = None
    status: str
    progress: int = 0
    result: Optional[dict] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


# ============================================================================
# Video Scraping Endpoints
# ============================================================================


@router.post("/scrape/video", response_model=TaskResponse)
async def scrape_video(request: VideoScrapeRequest, user_id: str = Query(None)):
    """
    Start video scraping task

    - **video_id**: YouTube video ID
    - **fetch_comments**: Whether to fetch comments
    - **max_comments**: Maximum comments to fetch
    """
    try:
        if request.fetch_comments:
            # Full analysis workflow
            task = full_video_analysis.apply_async(
                kwargs={
                    "video_id": request.video_id,
                    "include_comments": True,
                    "max_comments": request.max_comments,
                    "user_id": user_id,
                }
            )
            message = f"Full analysis started for video {request.video_id}"
        else:
            # Just metadata
            task = scrape_video_metadata.apply_async(args=(request.video_id, user_id))
            message = f"Metadata scraping started for video {request.video_id}"

        return TaskResponse(
            task_id=task.id,
            status="pending",
            message=message,
        )

    except Exception as e:
        logger.error(f"Failed to start video scraping: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scrape/videos/batch", response_model=TaskResponse)
async def scrape_videos_batch_endpoint(
    video_ids: List[str] = Body(..., description="List of video IDs"),
    include_comments: bool = Body(default=False),
    user_id: str = Query(None),
):
    """
    Batch scrape multiple videos

    - **video_ids**: List of YouTube video IDs
    - **include_comments**: Include comment scraping
    """
    try:
        task = bulk_video_scraping.apply_async(
            kwargs={
                "video_ids": video_ids,
                "include_comments": include_comments,
                "user_id": user_id,
            }
        )

        return TaskResponse(
            task_id=task.id,
            status="pending",
            message=f"Batch scraping started for {len(video_ids)} videos",
        )

    except Exception as e:
        logger.error(f"Failed to start batch scraping: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scrape/search", response_model=TaskResponse)
async def search_and_scrape(request: SearchScrapeRequest, user_id: str = Query(None)):
    """
    Search for videos and scrape them

    - **query**: Search query
    - **max_results**: Maximum results to scrape
    - **order**: Sort order (relevance, date, rating, viewCount, title)
    """
    try:
        task = search_and_scrape_videos.apply_async(
            kwargs={
                "query": request.query,
                "max_results": request.max_results,
                "order": request.order,
                "user_id": user_id,
            }
        )

        return TaskResponse(
            task_id=task.id,
            status="pending",
            message=f"Search and scrape started for query: '{request.query}'",
        )

    except Exception as e:
        logger.error(f"Failed to start search scraping: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Channel Scraping Endpoints
# ============================================================================


@router.post("/scrape/channel", response_model=TaskResponse)
async def scrape_channel(request: ChannelScrapeRequest, user_id: str = Query(None)):
    """
    Start channel scraping task

    - **channel_id**: YouTube channel ID
    - **max_videos**: Maximum videos to fetch
    - **include_analysis**: Perform video analysis
    """
    try:
        if request.include_analysis:
            # Full channel analysis
            task = full_channel_analysis.apply_async(
                kwargs={
                    "channel_id": request.channel_id,
                    "max_videos": request.max_videos,
                    "analyze_videos": True,
                    "user_id": user_id,
                }
            )
            message = f"Full analysis started for channel {request.channel_id}"
        else:
            # Just sync data
            task = sync_channel_data.apply_async(
                kwargs={
                    "channel_id": request.channel_id,
                    "include_videos": True,
                    "max_videos": request.max_videos,
                    "user_id": user_id,
                }
            )
            message = f"Sync started for channel {request.channel_id}"

        return TaskResponse(
            task_id=task.id,
            status="pending",
            message=message,
        )

    except Exception as e:
        logger.error(f"Failed to start channel scraping: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Task Status & Management
# ============================================================================


@router.get("/{task_id}/status", response_model=TaskStatusResponse)
async def get_task_status_endpoint(
    task_id: str = Path(..., description="Task ID"),
):
    """
    Get task status by ID
    """
    try:
        # Try database first
        db_status = await get_task_status(task_id)

        if db_status:
            return TaskStatusResponse(**db_status)

        # Fallback to Celery
        celery_info = get_task_info(task_id)

        return TaskStatusResponse(
            task_id=task_id,
            status=celery_info["status"].lower(),
            result=celery_info.get("result"),
        )

    except Exception as e:
        logger.error(f"Failed to get task status: {e}")
        raise HTTPException(status_code=404, detail="Task not found")


@router.delete("/{task_id}")
async def cancel_task(
    task_id: str = Path(..., description="Task ID"),
    terminate: bool = Query(default=False, description="Force terminate"),
):
    """
    Cancel a running task

    - **task_id**: Task ID to cancel
    - **terminate**: Force terminate (dangerous)
    """
    try:
        success = revoke_task(task_id, terminate=terminate)

        if success:
            return {"message": f"Task {task_id} cancelled", "terminated": terminate}
        else:
            raise HTTPException(status_code=500, detail="Failed to cancel task")

    except Exception as e:
        logger.error(f"Failed to cancel task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/retry")
async def retry_task(
    task_id: str = Path(..., description="Task ID"),
):
    """
    Retry a failed task
    """
    try:
        result = await retry_failed_task(task_id)

        return {
            "message": f"Task {task_id} queued for retry",
            "retry_count": result.get("retry_count", 0),
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to retry task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user/{user_id}")
async def get_user_tasks_endpoint(
    user_id: str = Path(..., description="User ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    task_type: Optional[str] = Query(None, description="Filter by type"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """
    Get tasks for a specific user
    """
    try:
        result = await get_user_tasks(
            user_id=user_id,
            status=status,
            task_type=task_type,
            limit=limit,
            offset=offset,
        )

        return result

    except Exception as e:
        logger.error(f"Failed to get user tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/active/list")
async def list_active_tasks():
    """
    List all currently running tasks
    """
    try:
        # Get from both Celery and database
        celery_tasks = get_active_tasks()
        db_tasks = await get_active_db_tasks()

        return {
            "celery_workers": celery_tasks,
            "database_tasks": db_tasks,
        }

    except Exception as e:
        logger.error(f"Failed to list active tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/failed/list")
async def list_failed_tasks(
    hours: int = Query(24, ge=1, le=168, description="Last N hours"),
):
    """
    List failed tasks
    """
    try:
        since = datetime.utcnow() - timedelta(hours=hours)
        result = await get_failed_tasks(since=since)

        return result

    except Exception as e:
        logger.error(f"Failed to list failed tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
async def get_statistics(
    days: int = Query(7, ge=1, le=90, description="Last N days"),
    task_type: Optional[str] = Query(None, description="Filter by type"),
):
    """
    Get task execution statistics
    """
    try:
        since = datetime.utcnow() - timedelta(days=days)
        stats = await get_task_statistics(since=since, task_type=task_type)

        return stats

    except Exception as e:
        logger.error(f"Failed to get statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workers/status")
async def get_workers_status():
    """
    Get Celery worker statistics
    """
    try:
        stats = get_worker_stats()

        return {
            "active_tasks": stats.get("active", {}),
            "scheduled_tasks": stats.get("scheduled", {}),
            "reserved_tasks": stats.get("reserved", {}),
            "worker_stats": stats.get("stats", {}),
            "registered_tasks": stats.get("registered", {}),
        }

    except Exception as e:
        logger.error(f"Failed to get worker stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
