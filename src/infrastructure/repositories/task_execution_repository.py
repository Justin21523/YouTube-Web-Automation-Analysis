# src/infrastructure/repositories/task_execution_repository.py
"""
Task Execution Repository
Handles all task execution tracking database operations
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import select, func, and_, or_, desc, asc, update
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from .base import BaseRepository
from src.app.models.task_execution import TaskExecution, TaskStatus

logger = logging.getLogger(__name__)


class TaskExecutionRepository(BaseRepository[TaskExecution]):
    """
    Repository for TaskExecution operations
    Provides task tracking, status management, and analytics
    """

    def __init__(self, session: AsyncSession):
        """Initialize task execution repository"""
        super().__init__(session, TaskExecution)

    # ========================================================================
    # Task Retrieval Methods
    # ========================================================================

    async def get_by_task_id(self, task_id: str) -> Optional[TaskExecution]:
        """
        Get task by Celery task UUID

        Args:
            task_id: Celery task UUID

        Returns:
            TaskExecution or None
        """
        try:
            result = await self.session.execute(
                select(TaskExecution).where(TaskExecution.task_id == task_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"❌ Failed to get task by task_id: {e}")
            raise

    async def get_by_user(
        self,
        user_id: str,
        status: Optional[TaskStatus] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[TaskExecution]:
        """
        Get tasks by user ID

        Args:
            user_id: User identifier
            status: Filter by status (optional)
            skip: Pagination offset
            limit: Max results

        Returns:
            List of task executions
        """
        try:
            query = select(TaskExecution).where(TaskExecution.user_id == user_id)

            if status:
                query = query.where(TaskExecution.status == status)

            query = query.order_by(desc(TaskExecution.created_at)).offset(skip).limit(limit)

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get tasks by user: {e}")
            raise

    async def get_active_tasks(self, limit: int = 100) -> List[TaskExecution]:
        """
        Get currently running tasks

        Args:
            limit: Max results

        Returns:
            List of running tasks
        """
        try:
            result = await self.session.execute(
                select(TaskExecution)
                .where(TaskExecution.status == TaskStatus.RUNNING)
                .order_by(desc(TaskExecution.started_at))
                .limit(limit)
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get active tasks: {e}")
            raise

    async def get_failed_tasks(
        self, hours: int = 24, limit: int = 100
    ) -> List[TaskExecution]:
        """
        Get recently failed tasks

        Args:
            hours: Time window in hours
            limit: Max results

        Returns:
            List of failed tasks
        """
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)

            result = await self.session.execute(
                select(TaskExecution)
                .where(
                    and_(
                        TaskExecution.status == TaskStatus.FAILED,
                        TaskExecution.completed_at >= cutoff_time,
                    )
                )
                .order_by(desc(TaskExecution.completed_at))
                .limit(limit)
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get failed tasks: {e}")
            raise

    async def get_pending_tasks(self, limit: int = 100) -> List[TaskExecution]:
        """
        Get pending tasks waiting to be executed

        Args:
            limit: Max results

        Returns:
            List of pending tasks
        """
        try:
            result = await self.session.execute(
                select(TaskExecution)
                .where(TaskExecution.status == TaskStatus.PENDING)
                .order_by(asc(TaskExecution.created_at))
                .limit(limit)
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get pending tasks: {e}")
            raise

    # ========================================================================
    # Status Management
    # ========================================================================

    async def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        progress: Optional[int] = None,
        result: Optional[Dict] = None,
        error_message: Optional[str] = None,
        traceback_info: Optional[str] = None,
        worker_name: Optional[str] = None,
    ) -> Optional[TaskExecution]:
        """
        Update task status and related fields

        Args:
            task_id: Celery task UUID
            status: New status
            progress: Progress percentage
            result: Task result data
            error_message: Error message if failed
            traceback_info: Traceback info if failed
            worker_name: Worker hostname

        Returns:
            Updated TaskExecution or None
        """
        try:
            task = await self.get_by_task_id(task_id)
            if not task:
                return None

            # Update fields
            task.status = status

            if progress is not None:
                task.progress = progress

            if result is not None:
                task.result = result

            if error_message is not None:
                task.error_message = error_message

            if traceback_info is not None:
                task.traceback_info = traceback_info

            if worker_name is not None:
                task.worker_name = worker_name

            # Update timestamps based on status
            now = datetime.utcnow()
            if status == TaskStatus.RUNNING and task.started_at is None:
                task.started_at = now
            elif status in [TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.REVOKED]:
                task.completed_at = now
                if task.started_at:
                    task.execution_time_seconds = int(
                        (now - task.started_at).total_seconds()
                    )

            await self.session.commit()
            await self.session.refresh(task)
            return task
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Failed to update task status: {e}")
            raise

    async def mark_running(
        self, task_id: str, worker_name: Optional[str] = None
    ) -> Optional[TaskExecution]:
        """Mark task as running"""
        return await self.update_status(
            task_id, TaskStatus.RUNNING, progress=0, worker_name=worker_name
        )

    async def mark_success(
        self, task_id: str, result: Optional[Dict] = None
    ) -> Optional[TaskExecution]:
        """Mark task as successful"""
        return await self.update_status(
            task_id, TaskStatus.SUCCESS, progress=100, result=result
        )

    async def mark_failed(
        self,
        task_id: str,
        error_message: str,
        traceback_info: Optional[str] = None,
    ) -> Optional[TaskExecution]:
        """Mark task as failed"""
        return await self.update_status(
            task_id,
            TaskStatus.FAILED,
            error_message=error_message,
            traceback_info=traceback_info,
        )

    async def increment_retry(self, task_id: str) -> Optional[TaskExecution]:
        """
        Increment retry count for a task

        Args:
            task_id: Celery task UUID

        Returns:
            Updated TaskExecution or None
        """
        try:
            task = await self.get_by_task_id(task_id)
            if not task:
                return None

            task.retry_count += 1
            task.status = TaskStatus.RETRY
            task.next_retry_at = datetime.utcnow() + timedelta(
                minutes=2 ** task.retry_count
            )

            await self.session.commit()
            await self.session.refresh(task)
            return task
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Failed to increment retry: {e}")
            raise

    # ========================================================================
    # Analytics & Statistics
    # ========================================================================

    async def get_statistics(
        self, hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get task execution statistics

        Args:
            hours: Time window for statistics

        Returns:
            Dictionary with task statistics
        """
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)

            # Count by status
            result = await self.session.execute(
                select(
                    TaskExecution.status,
                    func.count(TaskExecution.id).label("count"),
                )
                .where(TaskExecution.created_at >= cutoff_time)
                .group_by(TaskExecution.status)
            )

            status_counts = {row.status.value: row.count for row in result.all()}

            # Average execution time
            avg_result = await self.session.execute(
                select(func.avg(TaskExecution.execution_time_seconds))
                .where(
                    and_(
                        TaskExecution.created_at >= cutoff_time,
                        TaskExecution.execution_time_seconds.isnot(None),
                    )
                )
            )
            avg_execution_time = avg_result.scalar() or 0

            # Total counts
            total = sum(status_counts.values())

            return {
                "period_hours": hours,
                "total_tasks": total,
                "by_status": status_counts,
                "success_rate": (
                    round(status_counts.get("success", 0) / total * 100, 2)
                    if total > 0
                    else 0
                ),
                "avg_execution_time_seconds": round(avg_execution_time, 2),
            }
        except Exception as e:
            logger.error(f"❌ Failed to get task statistics: {e}")
            raise

    async def get_children(self, parent_task_id: str) -> List[TaskExecution]:
        """
        Get child tasks for a workflow

        Args:
            parent_task_id: Parent task UUID

        Returns:
            List of child tasks
        """
        try:
            result = await self.session.execute(
                select(TaskExecution)
                .where(TaskExecution.parent_task_id == parent_task_id)
                .order_by(asc(TaskExecution.created_at))
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get child tasks: {e}")
            raise

    # ========================================================================
    # Cleanup Operations
    # ========================================================================

    async def cleanup_old_tasks(self, days: int = 30) -> int:
        """
        Delete old completed tasks

        Args:
            days: Keep tasks newer than this

        Returns:
            Number of deleted tasks
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            # Get count before deletion
            count_result = await self.session.execute(
                select(func.count(TaskExecution.id)).where(
                    and_(
                        TaskExecution.completed_at.isnot(None),
                        TaskExecution.completed_at < cutoff_date,
                        TaskExecution.status.in_([
                            TaskStatus.SUCCESS,
                            TaskStatus.FAILED,
                            TaskStatus.REVOKED,
                        ]),
                    )
                )
            )
            count = count_result.scalar() or 0

            if count > 0:
                # Delete old tasks
                await self.session.execute(
                    TaskExecution.__table__.delete().where(
                        and_(
                            TaskExecution.completed_at.isnot(None),
                            TaskExecution.completed_at < cutoff_date,
                            TaskExecution.status.in_([
                                TaskStatus.SUCCESS,
                                TaskStatus.FAILED,
                                TaskStatus.REVOKED,
                            ]),
                        )
                    )
                )
                await self.session.commit()
                logger.info(f"✅ Cleaned up {count} old task records")

            return count
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Failed to cleanup old tasks: {e}")
            raise


# ============================================================================
# Export
# ============================================================================

__all__ = ["TaskExecutionRepository", "TaskStatus"]
