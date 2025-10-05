# src/infrastructure/tasks/celery_app.py
"""
Celery Application Factory
Creates and configures Celery app with project settings
"""

import logging
from typing import Optional
from celery import Celery, Task
from celery.signals import task_prerun, task_postrun, task_failure, task_success
from kombu import Queue, Exchange

from src.app.config import get_config
from src.app.shared_cache import get_shared_cache

logger = logging.getLogger(__name__)


class DatabaseTask(Task):
    """
    Base task class with database session management
    Ensures proper cleanup after task execution
    """

    _db = None
    _cache = None

    @property
    def db(self):
        """Get database session (lazy initialization)"""
        if self._db is None:
            from src.app.database import db_manager

            self._db = db_manager
        return self._db

    @property
    def cache(self):
        """Get shared cache instance"""
        if self._cache is None:
            self._cache = get_shared_cache()
        return self._cache

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        """Cleanup after task execution"""
        if self._db is not None:
            # Close any open database connections
            pass
        super().after_return(status, retval, task_id, args, kwargs, einfo)


def create_celery_app(app_name: str = "youtube_automation") -> Celery:
    """
    Create and configure Celery application

    Args:
        app_name: Application name for Celery

    Returns:
        Configured Celery instance
    """
    config = get_config()
    celery_config = config.celery

    # Create Celery instance
    celery_app = Celery(
        app_name,
        broker=celery_config.broker_url,
        backend=celery_config.result_backend,
        task_cls=DatabaseTask,  # Use custom base task class
    )

    # Configure Celery
    celery_app.conf.update(
        # Serialization
        task_serializer=celery_config.task_serializer,
        result_serializer=celery_config.result_serializer,
        accept_content=celery_config.accept_content,
        # Task execution
        task_track_started=celery_config.task_track_started,
        task_time_limit=celery_config.task_time_limit,
        task_soft_time_limit=celery_config.task_soft_time_limit,
        task_acks_late=celery_config.task_acks_late,
        task_reject_on_worker_lost=celery_config.task_reject_on_worker_lost,
        # Retry settings
        task_default_retry_delay=celery_config.task_default_retry_delay,
        # Result backend
        result_expires=celery_config.result_expires,
        result_persistent=celery_config.result_persistent,
        # Worker settings
        worker_prefetch_multiplier=celery_config.worker_prefetch_multiplier,
        worker_max_tasks_per_child=celery_config.worker_max_tasks_per_child,
        # Logging
        worker_hijack_root_logger=celery_config.worker_hijack_root_logger,
        worker_log_format=celery_config.worker_log_format,
        # Timezone
        timezone="UTC",
        enable_utc=True,
        # Task routing
        task_default_queue=celery_config.task_default_queue,
        task_routes=celery_config.task_routes,
        # Beat scheduler
        beat_scheduler=celery_config.beat_scheduler,
        beat_schedule_filename=celery_config.beat_schedule_filename,
        beat_max_loop_interval=celery_config.beat_max_loop_interval,
        # Performance
        task_compression=(
            celery_config.task_compression if celery_config.task_compression else None
        ),
        # Priority
        task_inherit_parent_priority=celery_config.task_inherit_parent_priority,
    )

    # Define task queues with priorities
    default_exchange = Exchange("default", type="direct")

    celery_app.conf.task_queues = (
        Queue("default", exchange=default_exchange, routing_key="default", priority=5),
        Queue(
            "scraping", exchange=default_exchange, routing_key="scraping", priority=3
        ),
        Queue(
            "analysis", exchange=default_exchange, routing_key="analysis", priority=7
        ),
        Queue(
            "priority", exchange=default_exchange, routing_key="priority", priority=10
        ),
    )

    # Auto-discover tasks from all task modules
    celery_app.autodiscover_tasks(
        [
            "src.infrastructure.tasks",
        ],
        related_name="video_tasks",
        force=True,
    )

    celery_app.autodiscover_tasks(
        [
            "src.infrastructure.tasks",
        ],
        related_name="comment_tasks",
        force=True,
    )

    celery_app.autodiscover_tasks(
        [
            "src.infrastructure.tasks",
        ],
        related_name="channel_tasks",
        force=True,
    )

    celery_app.autodiscover_tasks(
        [
            "src.infrastructure.tasks",
        ],
        related_name="analysis_tasks",
        force=True,
    )

    celery_app.autodiscover_tasks(
        [
            "src.infrastructure.tasks",
        ],
        related_name="scheduled_tasks",
        force=True,
    )

    celery_app.autodiscover_tasks(
        [
            "src.infrastructure.tasks",
        ],
        related_name="workflow_tasks",
        force=True,
    )

    logger.info(f"✅ Celery app initialized: {app_name}")
    logger.info(f"📡 Broker: {celery_config.broker_url}")
    logger.info(f"📦 Result backend: {celery_config.result_backend}")
    logger.info(f"🔄 Worker concurrency: {celery_config.worker_concurrency}")

    return celery_app


# Create global Celery instance
celery_app = create_celery_app()


# ============================================================================
# Signal Handlers
# ============================================================================


@task_prerun.connect
def task_prerun_handler(
    sender=None, task_id=None, task=None, args=None, kwargs=None, **extra
):
    """
    Log task start and update status in database
    """
    logger.info(f"🚀 Task started: {task.name} [ID: {task_id}]")

    # Update task status to 'running' in database
    from src.services.task_tracking_service import update_task_status

    update_task_status(task_id, "running", progress=0)


@task_postrun.connect
def task_postrun_handler(
    sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, **extra
):
    """
    Log task completion
    """
    logger.info(f"✅ Task completed: {task.name} [ID: {task_id}]")


@task_success.connect
def task_success_handler(sender=None, result=None, **kwargs):
    """
    Handle successful task execution
    """
    task_id = kwargs.get("task_id")
    logger.info(f"🎉 Task succeeded: {sender.name} [ID: {task_id}]")

    # Update task status to 'success'
    from src.services.task_tracking_service import update_task_status

    update_task_status(task_id, "success", result=result, progress=100)


@task_failure.connect
def task_failure_handler(
    sender=None, task_id=None, exception=None, traceback=None, **kwargs
):
    """
    Handle task failure
    """
    logger.error(f"❌ Task failed: {sender.name} [ID: {task_id}]")
    logger.error(f"Error: {exception}")
    logger.error(f"Traceback: {traceback}")

    # Update task status to 'failed'
    from src.services.task_tracking_service import update_task_status

    update_task_status(
        task_id, "failed", error_message=str(exception), traceback_info=str(traceback)
    )


# ============================================================================
# Utility Functions
# ============================================================================


def get_task_info(task_id: str) -> dict:
    """
    Get information about a running task

    Args:
        task_id: Celery task ID

    Returns:
        Task information dictionary
    """
    result = celery_app.AsyncResult(task_id)

    return {
        "task_id": task_id,
        "status": result.status,
        "result": result.result if result.successful() else None,
        "traceback": result.traceback if result.failed() else None,
        "info": result.info,
    }


def revoke_task(task_id: str, terminate: bool = False) -> bool:
    """
    Cancel a running task

    Args:
        task_id: Celery task ID
        terminate: Force terminate the task

    Returns:
        True if task was revoked
    """
    try:
        celery_app.control.revoke(task_id, terminate=terminate)
        logger.info(f"🛑 Task revoked: {task_id} (terminate={terminate})")
        return True
    except Exception as e:
        logger.error(f"Failed to revoke task {task_id}: {e}")
        return False


def purge_queue(queue_name: str = "default") -> int:
    """
    Purge all tasks from a queue

    Args:
        queue_name: Name of queue to purge

    Returns:
        Number of tasks purged
    """
    try:
        count = celery_app.control.purge()
        logger.warning(f"🗑️ Purged {count} tasks from queue: {queue_name}")
        return count
    except Exception as e:
        logger.error(f"Failed to purge queue {queue_name}: {e}")
        return 0


def get_active_tasks() -> list:
    """
    Get list of currently executing tasks

    Returns:
        List of active task dictionaries
    """
    inspect = celery_app.control.inspect()
    active = inspect.active()

    if not active:
        return []

    all_tasks = []
    for worker, tasks in active.items():
        for task in tasks:
            task["worker"] = worker
            all_tasks.append(task)

    return all_tasks


def get_worker_stats() -> dict:
    """
    Get statistics about active workers

    Returns:
        Dictionary of worker statistics
    """
    inspect = celery_app.control.inspect()

    return {
        "active": inspect.active(),
        "scheduled": inspect.scheduled(),
        "reserved": inspect.reserved(),
        "stats": inspect.stats(),
        "registered": inspect.registered(),
    }


# ============================================================================
# Testing & Debug
# ============================================================================


@celery_app.task(bind=True)
def debug_task(self):
    """
    Debug task to test Celery configuration
    """
    logger.info(f"Request: {self.request!r}")
    return {
        "task_id": self.request.id,
        "task_name": self.request.task,
        "args": self.request.args,
        "kwargs": self.request.kwargs,
        "worker": self.request.hostname,
    }


if __name__ == "__main__":
    """Test Celery app creation"""
    print("🧪 Testing Celery Application...")
    print("=" * 60)

    app = create_celery_app()

    print(f"\n📋 Celery Configuration:")
    print(f"  App Name: {app.main}")
    print(f"  Broker: {app.conf.broker_url}")
    print(f"  Backend: {app.conf.result_backend}")
    print(f"  Queues: {[q.name for q in app.conf.task_queues]}")
    print(f"  Serializer: {app.conf.task_serializer}")

    print(f"\n🔧 Worker Settings:")
    print(f"  Concurrency: {app.conf.worker_concurrency}")
    print(f"  Prefetch: {app.conf.worker_prefetch_multiplier}")
    print(f"  Max tasks/child: {app.conf.worker_max_tasks_per_child}")

    print(f"\n⏱️ Timeout Settings:")
    print(f"  Hard limit: {app.conf.task_time_limit}s")
    print(f"  Soft limit: {app.conf.task_soft_time_limit}s")

    print("\n" + "=" * 60)
    print("✅ Celery app created successfully!")
