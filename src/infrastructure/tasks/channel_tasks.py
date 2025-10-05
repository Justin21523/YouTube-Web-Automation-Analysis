"""
Channel Scraping Background Tasks
Celery tasks for YouTube channel data collection
"""

import logging
from typing import Dict, Any, List
from datetime import datetime

from src.infrastructure.tasks.celery_app import celery_app
from src.infrastructure.clients.youtube_api import create_youtube_client
from src.app.database import db_manager
from src.infrastructure.repositories import ChannelRepository, VideoRepository
from src.services.task_tracking_service import create_task_record, update_task_status

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="tasks.scraping.scrape_channel_metadata",
    max_retries=3,
)
def scrape_channel_metadata(
    self,
    channel_id: str,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Scrape channel metadata from YouTube

    Args:
        channel_id: YouTube channel ID
        user_id: User identifier

    Returns:
        Channel metadata dictionary
    """
    import asyncio

    async def _scrape():
        await create_task_record(
            task_id=self.request.id,
            task_name="scrape_channel_metadata",
            task_type="scraping",
            args=(channel_id,),
            user_id=user_id,
        )

        logger.info(f"📺 Scraping channel metadata: {channel_id}")

        try:
            # Fetch from YouTube API
            with create_youtube_client() as client:
                channel_data = client.get_channel(channel_id)

            update_task_status(self.request.id, "running", progress=50)

            # Store in database
            async with db_manager.session() as session:
                repo = ChannelRepository(session)

                channel = await repo.upsert_from_api(channel_data)

                logger.info(f"✅ Saved channel: {channel.name}")

            result = {
                "channel_id": channel_id,
                "name": channel_data.snippet.title,
                "subscriber_count": channel_data.statistics.subscriber_count,
                "video_count": channel_data.statistics.video_count,
                "scraped_at": datetime.utcnow().isoformat(),
            }

            update_task_status(self.request.id, "success", progress=100, result=result)

            return result

        except Exception as e:
            logger.error(f"Failed to scrape channel {channel_id}: {e}")
            update_task_status(self.request.id, "failed", error_message=str(e))
            raise self.retry(exc=e)

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_scrape())


@celery_app.task(
    bind=True,
    name="tasks.scraping.scrape_channel_videos",
    max_retries=3,
    soft_time_limit=1800,
)
def scrape_channel_videos(
    self,
    channel_id: str,
    max_videos: int = 50,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Scrape latest videos from a channel

    Args:
        channel_id: YouTube channel ID
        max_videos: Maximum videos to fetch
        user_id: User identifier

    Returns:
        Channel videos scraping result
    """
    import asyncio

    async def _scrape():
        await create_task_record(
            task_id=self.request.id,
            task_name="scrape_channel_videos",
            task_type="scraping",
            args=(channel_id,),
            kwargs={"max_videos": max_videos},
            user_id=user_id,
        )

        logger.info(f"🎬 Scraping videos from channel: {channel_id}")

        try:
            with create_youtube_client() as client:
                # Search for channel's videos
                video_ids = client.search_videos(
                    query="",
                    channel_id=channel_id,
                    max_results=max_videos,
                    order="date",
                )

                if not video_ids:
                    result = {
                        "channel_id": channel_id,
                        "videos_found": 0,
                        "videos_scraped": 0,
                    }
                    update_task_status(
                        self.request.id, "success", progress=100, result=result
                    )
                    return result

                update_task_status(self.request.id, "running", progress=30)

                # Batch fetch video details
                videos = client.get_videos_batch(video_ids)

                update_task_status(self.request.id, "running", progress=60)

                # Store in database
                scraped_videos = []
                async with db_manager.session() as session:
                    repo = VideoRepository(session)

                    for video_data in videos:
                        video = await repo.upsert_from_api(video_data)
                        scraped_videos.append(
                            {
                                "video_id": video.id,
                                "title": video.title,
                                "published_at": video.published_at.isoformat(),
                            }
                        )

            result = {
                "channel_id": channel_id,
                "videos_found": len(video_ids),
                "videos_scraped": len(scraped_videos),
                "videos": scraped_videos,
                "scraped_at": datetime.utcnow().isoformat(),
            }

            update_task_status(self.request.id, "success", progress=100, result=result)

            return result

        except Exception as e:
            logger.error(f"Failed to scrape channel videos for {channel_id}: {e}")
            update_task_status(self.request.id, "failed", error_message=str(e))
            raise self.retry(exc=e)

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_scrape())


@celery_app.task(
    bind=True,
    name="tasks.scraping.sync_channel_data",
    max_retries=2,
)
def sync_channel_data(
    self,
    channel_id: str,
    include_videos: bool = True,
    max_videos: int = 20,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Comprehensive channel data synchronization

    Args:
        channel_id: YouTube channel ID
        include_videos: Whether to fetch videos
        max_videos: Max videos to fetch
        user_id: User identifier

    Returns:
        Sync result dictionary
    """
    import asyncio

    async def _sync():
        await create_task_record(
            task_id=self.request.id,
            task_name="sync_channel_data",
            task_type="scraping",
            args=(channel_id,),
            kwargs={"include_videos": include_videos, "max_videos": max_videos},
            user_id=user_id,
        )

        logger.info(f"🔄 Syncing channel data: {channel_id}")

        try:
            result = {
                "channel_id": channel_id,
                "channel_updated": False,
                "videos_scraped": 0,
            }

            with create_youtube_client() as client:
                # 1. Update channel metadata
                channel_data = client.get_channel(channel_id)

                async with db_manager.session() as session:
                    repo = ChannelRepository(session)
                    channel = await repo.upsert_from_api(channel_data)
                    result["channel_updated"] = True
                    result["channel_name"] = channel.name

                update_task_status(self.request.id, "running", progress=40)

                # 2. Optionally fetch videos
                if include_videos:
                    video_ids = client.search_videos(
                        query="",
                        channel_id=channel_id,
                        max_results=max_videos,
                        order="date",
                    )

                    if video_ids:
                        videos = client.get_videos_batch(video_ids)

                        async with db_manager.session() as session:
                            video_repo = VideoRepository(session)

                            for video_data in videos:
                                await video_repo.upsert_from_api(video_data)

                        result["videos_scraped"] = len(videos)
                        result["latest_video_ids"] = video_ids[:5]

                update_task_status(self.request.id, "running", progress=90)

            result["synced_at"] = datetime.utcnow().isoformat()

            update_task_status(self.request.id, "success", progress=100, result=result)

            return result

        except Exception as e:
            logger.error(f"Failed to sync channel {channel_id}: {e}")
            update_task_status(self.request.id, "failed", error_message=str(e))
            raise self.retry(exc=e)

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_sync())


@celery_app.task(
    bind=True,
    name="tasks.scraping.monitor_channel",
    max_retries=1,
)
def monitor_channel(
    self,
    channel_id: str,
    check_new_videos: bool = True,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Monitor channel for new content

    Args:
        channel_id: YouTube channel ID
        check_new_videos: Check for new uploads
        user_id: User identifier

    Returns:
        Monitoring result
    """
    import asyncio

    async def _monitor():
        await create_task_record(
            task_id=self.request.id,
            task_name="monitor_channel",
            task_type="scraping",
            args=(channel_id,),
            user_id=user_id,
        )

        logger.info(f"👀 Monitoring channel: {channel_id}")

        try:
            result = {
                "channel_id": channel_id,
                "new_videos": [],
                "stats_updated": False,
            }

            async with db_manager.session() as session:
                channel_repo = ChannelRepository(session)

                # Get existing channel data
                existing_channel = await channel_repo.get_by_id(channel_id)

                if not existing_channel:
                    logger.warning(f"Channel {channel_id} not in database, creating...")

                # Fetch latest channel data
                with create_youtube_client() as client:
                    channel_data = client.get_channel(channel_id)

                    # Update channel
                    channel = await channel_repo.upsert_from_api(channel_data)
                    result["stats_updated"] = True

                    # Check for new videos
                    if check_new_videos:
                        video_ids = client.search_videos(
                            query="",
                            channel_id=channel_id,
                            max_results=10,
                            order="date",
                        )

                        if video_ids:
                            video_repo = VideoRepository(session)

                            for video_id in video_ids:
                                existing = await video_repo.get_by_id(video_id)

                                if not existing:
                                    # New video found!
                                    video_data = client.get_video(video_id)
                                    new_video = await video_repo.upsert_from_api(
                                        video_data
                                    )

                                    result["new_videos"].append(
                                        {
                                            "video_id": new_video.id,
                                            "title": new_video.title,
                                            "published_at": new_video.published_at.isoformat(),
                                        }
                                    )

                                    logger.info(
                                        f"🆕 New video detected: {new_video.title}"
                                    )

            result["monitored_at"] = datetime.utcnow().isoformat()
            result["new_videos_count"] = len(result["new_videos"])

            update_task_status(self.request.id, "success", progress=100, result=result)

            return result

        except Exception as e:
            logger.error(f"Failed to monitor channel {channel_id}: {e}")
            update_task_status(self.request.id, "failed", error_message=str(e))
            raise self.retry(exc=e)

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_monitor())
