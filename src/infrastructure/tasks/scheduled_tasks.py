"""
Scheduled Background Tasks
Periodic tasks using Celery Beat
"""

import logging
from typing import Dict, Any
from datetime import datetime, timedelta
from celery.schedules import crontab

from src.infrastructure.tasks.celery_app import celery_app
from src.app.database import db_manager
from src.infrastructure.repositories import ChannelRepository, VideoRepository
from src.services.task_tracking_service import cleanup_old_tasks

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.scheduled.refresh_trending_videos")
def refresh_trending_videos() -> Dict[str, Any]:
    """
    Refresh trending videos every 6 hours

    Returns:
        Refresh result
    """
    import asyncio

    async def _refresh():
        logger.info("📈 Refreshing trending videos...")

        try:
            from src.infrastructure.tasks.workflow_tasks import trending_videos_analysis

            # Analyze trending videos
            result = trending_videos_analysis.apply(
                kwargs={"query": "trending 2025", "max_videos": 50},
            ).get(timeout=1800)

            logger.info(
                f"✅ Trending videos refreshed: {result.get('videos_found', 0)} found"
            )

            return result

        except Exception as e:
            logger.error(f"Failed to refresh trending videos: {e}")
            return {"error": str(e)}

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_refresh())


@celery_app.task(name="tasks.scheduled.update_all_channels")
def update_all_channels() -> Dict[str, Any]:
    """
    Update statistics for all monitored channels (daily)

    Returns:
        Update result
    """
    import asyncio

    async def _update():
        logger.info("🔄 Updating all channel statistics...")

        try:
            from src.infrastructure.tasks.channel_tasks import scrape_channel_metadata
            from celery import group

            # Get all active channels
            async with db_manager.session() as session:
                repo = ChannelRepository(session)
                channels = await repo.list_active(limit=100)

            if not channels:
                logger.info("No active channels to update")
                return {"channels_updated": 0}

            # Create parallel update tasks
            update_jobs = group(
                [scrape_channel_metadata.s(channel_id=ch.id) for ch in channels]
            )

            # Execute updates
            results = update_jobs.apply_async().get(timeout=1800)

            successful = len([r for r in results if r])

            logger.info(f"✅ Updated {successful}/{len(channels)} channels")

            return {
                "total_channels": len(channels),
                "successful": successful,
                "failed": len(channels) - successful,
            }

        except Exception as e:
            logger.error(f"Failed to update channels: {e}")
            return {"error": str(e)}

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_update())


@celery_app.task(name="tasks.scheduled.monitor_active_channels")
def monitor_active_channels() -> Dict[str, Any]:
    """
    Monitor active channels for new content (every 3 hours)

    Returns:
        Monitoring result
    """
    import asyncio

    async def _monitor():
        logger.info("👀 Monitoring active channels for new content...")

        try:
            from src.infrastructure.tasks.channel_tasks import monitor_channel
            from celery import group

            # Get all active channels
            async with db_manager.session() as session:
                repo = ChannelRepository(session)
                channels = await repo.list_active(limit=50)

            if not channels:
                return {"channels_monitored": 0}

            # Monitor each channel
            monitor_jobs = group(
                [
                    monitor_channel.s(channel_id=ch.id, check_new_videos=True)
                    for ch in channels
                ]
            )

            results = monitor_jobs.apply_async().get(timeout=1200)

            # Count new videos found
            total_new_videos = sum(len(r.get("new_videos", [])) for r in results if r)

            logger.info(
                f"✅ Monitored {len(channels)} channels, found {total_new_videos} new videos"
            )

            return {
                "channels_monitored": len(channels),
                "new_videos_found": total_new_videos,
            }

        except Exception as e:
            logger.error(f"Failed to monitor channels: {e}")
            return {"error": str(e)}

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_monitor())


@celery_app.task(name="tasks.scheduled.cleanup_old_data")
def cleanup_old_data() -> Dict[str, Any]:
    """
    Clean up old data (weekly)

    Returns:
        Cleanup result
    """
    import asyncio

    async def _cleanup():
        logger.info("🗑️ Cleaning up old data...")

        try:
            # Cleanup old task records (>30 days)
            tasks_deleted = await cleanup_old_tasks(days=30)

            # Cleanup old analytics snapshots (>90 days)
            async with db_manager.session() as session:
                from src.infrastructure.repositories import VideoAnalyticsRepository

                analytics_repo = VideoAnalyticsRepository(session)
                cutoff_date = datetime.utcnow() - timedelta(days=90)

                # This would need to be implemented in the repository
                # analytics_deleted = await analytics_repo.delete_old_snapshots(cutoff_date)
                analytics_deleted = 0  # Placeholder

            logger.info(
                f"✅ Cleanup complete: {tasks_deleted} tasks, {analytics_deleted} analytics"
            )

            return {
                "tasks_deleted": tasks_deleted,
                "analytics_deleted": analytics_deleted,
                "cleaned_at": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to cleanup old data: {e}")
            return {"error": str(e)}

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_cleanup())


@celery_app.task(name="tasks.scheduled.refresh_video_analytics")
def refresh_video_analytics() -> Dict[str, Any]:
    """
    Refresh analytics for recently updated videos (every 12 hours)

    Returns:
        Refresh result
    """
    import asyncio

    async def _refresh():
        logger.info("📊 Refreshing video analytics...")

        try:
            from src.infrastructure.tasks.video_tasks import (
                refresh_video_analytics as refresh_task,
            )
            from celery import group

            # Get videos updated in last 7 days
            cutoff_date = datetime.utcnow() - timedelta(days=7)

            async with db_manager.session() as session:
                repo = VideoRepository(session)
                videos = await repo.list_recent(since=cutoff_date, limit=100)

            if not videos:
                return {"videos_refreshed": 0}

            # Refresh analytics for each video
            refresh_jobs = group([refresh_task.s(video_id=v.id) for v in videos])

            results = refresh_jobs.apply_async().get(timeout=1200)

            successful = len([r for r in results if r])

            logger.info(f"✅ Refreshed analytics for {successful}/{len(videos)} videos")

            return {
                "total_videos": len(videos),
                "successful": successful,
                "failed": len(videos) - successful,
            }

        except Exception as e:
            logger.error(f"Failed to refresh analytics: {e}")
            return {"error": str(e)}

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_refresh())


@celery_app.task(name="tasks.scheduled.analyze_pending_comments")
def analyze_pending_comments() -> Dict[str, Any]:
    """
    Analyze comments that haven't been analyzed yet (hourly)

    Returns:
        Analysis result
    """
    import asyncio

    async def _analyze():
        logger.info("🧠 Analyzing pending comments...")

        try:
            from src.infrastructure.repositories import CommentRepository
            from src.infrastructure.tasks.analysis_tasks import batch_analyze_comments

            # Get unanalyzed comments
            async with db_manager.session() as session:
                repo = CommentRepository(session)

                # This would need to be implemented in the repository
                # unanalyzed = await repo.list_unanalyzed(limit=500)
                unanalyzed = []  # Placeholder

            if not unanalyzed:
                return {"comments_analyzed": 0}

            # Batch analyze
            comment_ids = [c.id for c in unanalyzed]

            result = batch_analyze_comments.apply(
                args=(comment_ids,),
            ).get(timeout=600)

            logger.info(f"✅ Analyzed {result.get('analyzed', 0)} pending comments")

            return result

        except Exception as e:
            logger.error(f"Failed to analyze pending comments: {e}")
            return {"error": str(e)}

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_analyze())


# ============================================================================
# Celery Beat Schedule Configuration
# ============================================================================

celery_app.conf.beat_schedule = {
    # Every 6 hours: Refresh trending videos
    "refresh-trending-videos": {
        "task": "tasks.scheduled.refresh_trending_videos",
        "schedule": crontab(hour="*/6", minute=0),
    },
    # Daily at 2 AM: Update all channel statistics
    "update-all-channels": {
        "task": "tasks.scheduled.update_all_channels",
        "schedule": crontab(hour=2, minute=0),
    },
    # Every 3 hours: Monitor channels for new content
    "monitor-active-channels": {
        "task": "tasks.scheduled.monitor_active_channels",
        "schedule": crontab(hour="*/3", minute=30),
    },
    # Weekly on Sunday at 3 AM: Cleanup old data
    "cleanup-old-data": {
        "task": "tasks.scheduled.cleanup_old_data",
        "schedule": crontab(hour=3, minute=0, day_of_week=0),
    },
    # Every 12 hours: Refresh video analytics
    "refresh-video-analytics": {
        "task": "tasks.scheduled.refresh_video_analytics",
        "schedule": crontab(hour="*/12", minute=0),
    },
    # Hourly: Analyze pending comments
    "analyze-pending-comments": {
        "task": "tasks.scheduled.analyze_pending_comments",
        "schedule": crontab(minute=15),  # Every hour at :15
    },
}
