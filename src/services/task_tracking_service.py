# src/services/task_tracking_service.py
"""
Task Tracking Service
Business logic for task execution tracking
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

from src.app.models.task_execution import TaskStatus
from src.infrastructure.repositories.task_execution_repository import (
    TaskExecutionRepository,
)
from src.app.database import db_manager

logger = logging.getLogger(__name__)


async def create_task_record(
    task_id: str,
    task_name: str,
    task_type: str = "general",
    args: tuple = None,
    kwargs: dict = None,
    user_id: str = None,
    priority: int = 5,
    parent_task_id: str = None,
) -> Dict[str, Any]:
    """
    Create task execution record in database

    Args:
        task_id: Celery task UUID
        task_name: Task function name
        task_type: Task category
        args: Positional arguments
        kwargs: Keyword arguments
        user_id: User identifier
        priority: Task priority
        parent_task_id: Parent task ID

    Returns:
        Task record dictionary
    """
    async with db_manager.session() as session:
        repo = TaskExecutionRepository(session)

        task = await repo.create(
            task_id=task_id,
            task_name=task_name,
            task_type=task_type,
            args=args,
            kwargs=kwargs,
            user_id=user_id,
            priority=priority,
            parent_task_id=parent_task_id,
        )

        logger.info(f"📝 Created task record: {task_id} ({task_name})")

        return task.to_dict()


def update_task_status(
    task_id: str,
    status: str,
    progress: int = None,
    result: Any = None,
    error_message: str = None,
    traceback_info: str = None,
    worker_name: str = None,
) -> None:
    """
    Update task status (synchronous wrapper for signal handlers)

    Args:
        task_id: Task UUID
        status: New status string
        progress: Progress percentage
        result: Task result
        error_message: Error message
        traceback_info: Traceback string
        worker_name: Worker hostname
    """
    import asyncio

    async def _update():
        async with db_manager.session() as session:
            repo = TaskExecutionRepository(session)

            task_status = TaskStatus(status)

            task = await repo.update_status(
                task_id=task_id,
                status=task_status,
                progress=progress,
                result=result,
                error_message=error_message,
                traceback_info=traceback_info,
                worker_name=worker_name,
            )

            if task:
                logger.info(
                    f"✅ Updated task {task_id}: {status} (progress: {progress}%)"
                )
            else:
                logger.warning(f"⚠️ Task {task_id} not found in database")

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(_update())
        else:
            loop.run_until_complete(_update())
    except Exception as e:
        logger.error(f"Failed to update task status: {e}")


async def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    """
    Get task status from database

    Args:
        task_id: Task UUID

    Returns:
        Task status dictionary or None
    """
    async with db_manager.session() as session:
        repo = TaskExecutionRepository(session)

        task = await repo.get_by_id(task_id)

        if not task:
            return None

        return task.to_dict()


async def get_user_tasks(
    user_id: str,
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Get tasks for specific user

    Args:
        user_id: User identifier
        status: Filter by status
        task_type: Filter by type
        limit: Max results
        offset: Pagination offset

    Returns:
        Dictionary with tasks and pagination
    """
    async with db_manager.session() as session:
        repo = TaskExecutionRepository(session)

        task_status = TaskStatus(status) if status else None

        tasks = await repo.list_by_user(
            user_id=user_id,
            status=task_status,
            task_type=task_type,
            limit=limit,
            offset=offset,
        )

        return {
            "tasks": [task.to_dict() for task in tasks],
            "total": len(tasks),
            "limit": limit,
            "offset": offset,
        }


async def get_active_tasks() -> Dict[str, Any]:
    """
    Get all currently running tasks

    Returns:
        Dictionary with active tasks
    """
    async with db_manager.session() as session:
        repo = TaskExecutionRepository(session)

        tasks = await repo.list_active(limit=1000)

        return {
            "tasks": [task.to_dict() for task in tasks],
            "total": len(tasks),
        }


async def get_failed_tasks(since: datetime = None) -> Dict[str, Any]:
    """
    Get failed tasks

    Args:
        since: Start date filter

    Returns:
        Dictionary with failed tasks
    """
    async with db_manager.session() as session:
        repo = TaskExecutionRepository(session)

        tasks = await repo.list_failed(since=since, limit=1000)

        return {
            "tasks": [task.to_dict() for task in tasks],
            "total": len(tasks),
        }


async def retry_failed_task(task_id: str) -> Dict[str, Any]:
    """
    Retry a failed task

    Args:
        task_id: Task UUID

    Returns:
        Updated task dictionary
    """
    async with db_manager.session() as session:
        repo = TaskExecutionRepository(session)

        task = await repo.get_by_id(task_id)

        if not task:
            raise ValueError(f"Task {task_id} not found")

        if not task.can_retry:
            raise ValueError(f"Task {task_id} cannot be retried")

        updated_task = await repo.increment_retry(task_id)

        logger.info(f"🔄 Retrying task {task_id} (attempt {updated_task.retry_count})")

        return updated_task.to_dict()


async def get_task_statistics(
    since: datetime = None,
    task_type: str = None,
) -> Dict[str, Any]:
    """
    Get task execution statistics

    Args:
        since: Start date
        task_type: Filter by type

    Returns:
        Statistics dictionary
    """
    async with db_manager.session() as session:
        repo = TaskExecutionRepository(session)

        stats = await repo.get_statistics(since=since, task_type=task_type)

        return stats


async def cleanup_old_tasks(days: int = 30) -> int:
    """
    Clean up old completed tasks

    Args:
        days: Age threshold

    Returns:
        Number of deleted tasks
    """
    async with db_manager.session() as session:
        repo = TaskExecutionRepository(session)

        count = await repo.cleanup_old_tasks(days=days)

        logger.info(f"🗑️ Cleaned up {count} old task records (>{days} days)")

        return count


async def get_workflow_status(parent_task_id: str) -> Dict[str, Any]:
    """
    Get status of workflow and all child tasks

    Args:
        parent_task_id: Parent task UUID

    Returns:
        Workflow status with child tasks
    """
    async with db_manager.session() as session:
        repo = TaskExecutionRepository(session)

        parent = await repo.get_by_id(parent_task_id)

        if not parent:
            raise ValueError(f"Parent task {parent_task_id} not found")

        children = await repo.get_children(parent_task_id)

        # Calculate overall workflow status
        all_completed = all(task.is_completed for task in children)
        any_failed = any(task.status == TaskStatus.FAILED for task in children)

        if any_failed:
            workflow_status = "failed"
        elif all_completed:
            workflow_status = "completed"
        elif any(task.is_running for task in children):
            workflow_status = "running"
        else:
            workflow_status = "pending"

        # Calculate total progress
        if children:
            total_progress = sum(task.progress for task in children) / len(children)
        else:
            total_progress = parent.progress

        return {
            "parent_task": parent.to_dict(),
            "workflow_status": workflow_status,
            "total_progress": round(total_progress, 2),
            "child_tasks": [task.to_dict() for task in children],
            "total_children": len(children),
            "completed_children": sum(1 for task in children if task.is_completed),
            "failed_children": sum(
                1 for task in children if task.status == TaskStatus.FAILED
            ),
        }
