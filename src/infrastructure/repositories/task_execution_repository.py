# src/infrastructure/repositories/task_execution_repository.py

"""
Task Execution Tracking Model
Stores task execution history and status
"""

from sqlalchemy import Column, String, Integer, DateTime, Text, JSON, Enum as SQLEnum
from sqlalchemy.sql import func
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any

from src.infrastructure.database.connection import Base


class TaskStatus(str, Enum):
    """Task execution status"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRY = "retry"
    REVOKED = "revoked"


class TaskExecutionRepository(Base):
    """
    Task Execution Tracking
    Stores history and status of background tasks
    """

    __tablename__ = "task_executions"

    # Primary identification
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(
        String(255), unique=True, nullable=False, index=True, comment="Celery task UUID"
    )

    # Task metadata
    task_name = Column(
        String(255),
        nullable=False,
        index=True,
        comment="Task function name (e.g., scrape_video_metadata)",
    )
    task_type = Column(
        String(50), index=True, comment="Task category: scraping/analysis/workflow"
    )

    # Task parameters
    task_args = Column(JSON, comment="Positional arguments as JSON")
    task_kwargs = Column(JSON, comment="Keyword arguments as JSON")

    # Execution tracking
    status = Column(
        SQLEnum(TaskStatus),
        nullable=False,
        default=TaskStatus.PENDING,
        index=True,
        comment="Current task status",
    )
    progress = Column(Integer, default=0, comment="Progress percentage (0-100)")

    # Results
    result = Column(JSON, comment="Task result data as JSON")
    error_message = Column(Text, comment="Error message if failed")
    traceback_info = Column(Text, comment="Full traceback on failure")

    # Retry tracking
    retry_count = Column(Integer, default=0, comment="Number of retry attempts")
    max_retries = Column(Integer, default=3, comment="Maximum retry limit")
    next_retry_at = Column(DateTime, comment="Scheduled next retry time")

    # Worker information
    worker_name = Column(String(255), comment="Worker hostname that executed task")
    queue_name = Column(String(50), default="default", comment="Queue name")

    # Timing
    created_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, comment="Task creation time"
    )
    started_at = Column(DateTime, index=True, comment="Task execution start time")
    completed_at = Column(DateTime, comment="Task completion time")

    # Performance metrics
    execution_time_seconds = Column(Integer, comment="Total execution time")

    # User context (optional)
    user_id = Column(String(100), index=True, comment="User who triggered task")
    session_id = Column(String(100), comment="Session identifier")

    # Priority
    priority = Column(Integer, default=5, comment="Task priority (0-10)")

    # Parent-child relationships
    parent_task_id = Column(
        String(255), index=True, comment="Parent task ID for workflows"
    )

    def __repr__(self):
        return f"<TaskExecution(id={self.task_id}, name={self.task_name}, status={self.status})>"

    @property
    def is_completed(self) -> bool:
        """Check if task is in terminal state"""
        return self.status in [
            TaskStatus.SUCCESS,
            TaskStatus.FAILED,
            TaskStatus.REVOKED,
        ]

    @property
    def is_running(self) -> bool:
        """Check if task is currently executing"""
        return self.status == TaskStatus.RUNNING

    @property
    def can_retry(self) -> bool:
        """Check if task can be retried"""
        return self.status == TaskStatus.FAILED and self.retry_count < self.max_retries

    @property
    def duration_seconds(self) -> Optional[int]:
        """Calculate task duration if completed"""
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            return int(delta.total_seconds())
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "task_type": self.task_type,
            "status": self.status.value,
            "progress": self.progress,
            "result": self.result,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "worker_name": self.worker_name,
            "queue_name": self.queue_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "execution_time_seconds": self.duration_seconds,
            "priority": self.priority,
            "parent_task_id": self.parent_task_id,
        }

    @classmethod
    def create_from_task(
        cls,
        task_id: str,
        task_name: str,
        task_type: str = "general",
        args: tuple = None,
        kwargs: dict = None,
        user_id: str = None,
        priority: int = 5,
        parent_task_id: str = None,
    ):
        """
        Factory method to create task execution record

        Args:
            task_id: Celery task UUID
            task_name: Task function name
            task_type: Task category
            args: Task positional arguments
            kwargs: Task keyword arguments
            user_id: User identifier
            priority: Task priority
            parent_task_id: Parent task for workflows

        Returns:
            TaskExecution instance
        """
        return cls(
            task_id=task_id,
            task_name=task_name,
            task_type=task_type,
            task_args=list(args) if args else [],
            task_kwargs=kwargs or {},
            user_id=user_id,
            priority=priority,
            parent_task_id=parent_task_id,
            status=TaskStatus.PENDING,
        )


# Create index for common queries
from sqlalchemy import Index

# Index for finding user's tasks
Index("idx_task_user_status", TaskExecution.user_id, TaskExecution.status)

# Index for finding tasks by type and status
Index("idx_task_type_status", TaskExecution.task_type, TaskExecution.status)

# Index for finding child tasks
Index("idx_task_parent", TaskExecution.parent_task_id)

# Index for time-based queries
Index("idx_task_created", TaskExecution.created_at.desc())
