"""
Background Tasks Package
Celery-based asynchronous task processing
"""

from src.infrastructure.tasks.celery_app import (
    celery_app,
    get_task_info,
    revoke_task,
    purge_queue,
    get_active_tasks,
    get_worker_stats,
)

# Import all task modules to register them
from src.infrastructure.tasks import (
    video_tasks,
    channel_tasks,
    analysis_tasks,
    workflow_tasks,
    scheduled_tasks,
)

__all__ = [
    "celery_app",
    "get_task_info",
    "revoke_task",
    "purge_queue",
    "get_active_tasks",
    "get_worker_stats",
    "video_tasks",
    "channel_tasks",
    "analysis_tasks",
    "workflow_tasks",
    "scheduled_tasks",
]
