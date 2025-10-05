"""
Video Scraping Background Tasks
Celery tasks for YouTube video data collection
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from src.infrastructure.tasks.celery_app import celery_app
from src.infrastructure.clients.youtube_api import create_youtube_client
from src.app.database import db_manager
from src.infrastructure.repositories import VideoRepository
from src.services.task_tracking_service import create_task_record, update_task_status

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="tasks.scraping.refresh_video_analytics",
    max_retries=3,
)
def refresh_video_analytics(
    self,
    video_id: str,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Refresh video analytics snapshot

    Args:
        video_id: YouTube video ID
        user_id: User identifier

    Returns:
        Analytics update result
    """
    import asyncio

    async def _refresh():
        await create_task_record(
            task_id=self.request.id,
            task_name="refresh_video_analytics",
            task_type="scraping",
            args=(video_id,),
            user_id=user_id,
        )

        logger.info(f"📊 Refreshing analytics for video: {video_id}")

        try:
            from src.infrastructure.repositories import VideoAnalyticsRepository

            # Fetch latest video data
            with create_youtube_client() as client:
                video_data = client.get_video(video_id)

            update_task_status(self.request.id, "running", progress=50)

            # Create analytics snapshot
            async with db_manager.session() as session:
                analytics_repo = VideoAnalyticsRepository(session)

                snapshot = await analytics_repo.create_snapshot(
                    video_id=video_id,
                    view_count=video_data.statistics.view_count,
                    like_count=video_data.statistics.like_count,
                    comment_count=video_data.statistics.comment_count,
                )

                logger.info(f"✅ Created analytics snapshot for {video_id}")

            result = {
                "video_id": video_id,
                "view_count": video_data.statistics.view_count,
                "like_count": video_data.statistics.like_count,
                "snapshot_id": snapshot.id,
                "scraped_at": datetime.utcnow().isoformat(),
            }

            update_task_status(self.request.id, "success", progress=100, result=result)

            return result

        except Exception as e:
            logger.error(f"Failed to refresh analytics for {video_id}: {e}")
            update_task_status(self.request.id, "failed", error_message=str(e))
            raise self.retry(exc=e)

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_refresh())


@celery_app.task(
    bind=True,
    name="tasks.scraping.search_and_scrape_videos",
    max_retries=2,
)
def search_and_scrape_videos(
    self,
    query: str,
    max_results: int = 50,
    order: str = "relevance",
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Search for videos and scrape their metadata

    Args:
        query: Search query
        max_results: Max videos to scrape
        order: Sort order
        user_id: User identifier

    Returns:
        Search and scrape result
    """
    import asyncio

    async def _search_scrape():
        await create_task_record(
            task_id=self.request.id,
            task_name="search_and_scrape_videos",
            task_type="scraping",
            kwargs={"query": query, "max_results": max_results},
            user_id=user_id,
        )

        logger.info(f"🔍 Searching and scraping: '{query}' (max: {max_results})")

        try:
            with create_youtube_client() as client:
                # Search for videos
                video_ids = client.search_videos(
                    query=query,
                    max_results=max_results,
                    order=order,
                )

                update_task_status(self.request.id, "running", progress=30)

                if not video_ids:
                    result = {
                        "query": query,
                        "videos_found": 0,
                        "videos_scraped": 0,
                    }
                    update_task_status(self.request.id, "success", progress=100, result=result)
                    return result

                # Batch fetch video details
                videos = client.get_videos_batch(video_ids)

                update_task_status(self.request.id, "running", progress=60)

                # Store in database
                scraped_videos = []
                async with db_manager.session() as session:
                    repo = VideoRepository(session)

                    for video_data in videos:
                        video = await repo.upsert_from_api(video_data)
                        scraped_videos.append({
                            "video_id": video.id,
                            "title": video.title,
                            "view_count": video.view_count,
                        })

            result = {
                "query": query,
                "videos_found": len(video_ids),
                "videos_scraped": len(scraped_videos),
                "videos": scraped_videos,
                "scraped_at": datetime.utcnow().isoformat(),
            }

            update_task_status(self.request.id, "success", progress=100, result=result)

            return result

        except Exception as e:
            logger.error(f"Search and scrape failed for '{query}': {e}")
            update_task_status(self.request.id, "failed", error_message=str(e))
            raise self.retry(exc=e)

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_search_scrape()).scrape_video_metadata",
    max_retries=3,
    default_retry_delay=60,
)
def scrape_video_metadata(self, video_id: str, user_id: str = None) -> Dict[str, Any]:
    """
    Scrape video metadata from YouTube

    Args:
        video_id: YouTube video ID
        user_id: User who triggered task

    Returns:
        Video metadata dictionary
    """
    import asyncio

    async def _scrape():
        # Create task record
        await create_task_record(
            task_id=self.request.id,
            task_name="scrape_video_metadata",
            task_type="scraping",
            args=(video_id,),
            user_id=user_id,
        )

        logger.info(f"📹 Scraping video metadata: {video_id}")

        try:
            # Fetch from YouTube API
            with create_youtube_client() as client:
                video_data = client.get_video(video_id)

            # Update progress
            update_task_status(self.request.id, "running", progress=50)

            # Store in database
            async with db_manager.session() as session:
                repo = VideoRepository(session)

                video = await repo.upsert_from_api(video_data)

                logger.info(f"✅ Saved video: {video.title}")

            # Update progress to complete
            result = {
                "video_id": video_id,
                "title": video_data.snippet.title,
                "view_count": video_data.statistics.view_count,
                "scraped_at": datetime.utcnow().isoformat(),
            }

            update_task_status(self.request.id, "success", progress=100, result=result)

            return result

        except Exception as e:
            logger.error(f"Failed to scrape video {video_id}: {e}")
            update_task_status(
                self.request.id,
                "failed",
                error_message=str(e),
            )

            # Retry with exponential backoff
            raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_scrape())


@celery_app.task(
    bind=True,
    name="tasks.scraping.scrape_video_comments",
    max_retries=3,
    soft_time_limit=600,
)
def scrape_video_comments(
    self,
    video_id: str,
    max_comments: int = 1000,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Scrape comments for a video

    Args:
        video_id: YouTube video ID
        max_comments: Maximum comments to fetch
        user_id: User who triggered task

    Returns:
        Comment scraping result
    """
    import asyncio

    async def _scrape():
        await create_task_record(
            task_id=self.request.id,
            task_name="scrape_video_comments",
            task_type="scraping",
            args=(video_id,),
            kwargs={"max_comments": max_comments},
            user_id=user_id,
        )

        logger.info(f"💬 Scraping comments for video: {video_id}")

        try:
            from src.infrastructure.repositories import CommentRepository

            total_scraped = 0
            page_token = None

            with create_youtube_client() as client:
                while total_scraped < max_comments:
                    # Fetch comment page
                    comments = client.get_video_comments(
                        video_id=video_id,
                        max_results=min(100, max_comments - total_scraped),
                        page_token=page_token,
                    )

                    if not comments:
                        break

                    # Store in database
                    async with db_manager.session() as session:
                        repo = CommentRepository(session)

                        for comment_data in comments:
                            await repo.upsert_from_api(comment_data, video_id)

                    total_scraped += len(comments)

                    # Update progress
                    progress = min(int(total_scraped / max_comments * 100), 100)
                    update_task_status(self.request.id, "running", progress=progress)

                    logger.info(f"📝 Scraped {total_scraped}/{max_comments} comments")

                    # Check if there's more
                    if len(comments) < 100:
                        break

            result = {
                "video_id": video_id,
                "comments_scraped": total_scraped,
                "scraped_at": datetime.utcnow().isoformat(),
            }

            update_task_status(self.request.id, "success", progress=100, result=result)

            return result

        except Exception as e:
            logger.error(f"Failed to scrape comments for {video_id}: {e}")
            update_task_status(self.request.id, "failed", error_message=str(e))
            raise self.retry(exc=e)

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_scrape())


@celery_app.task(
    bind=True,
    name="tasks.scraping.scrape_videos_batch",
    max_retries=2,
)
def scrape_videos_batch(
    self,
    video_ids: List[str],
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Scrape multiple videos in batch

    Args:
        video_ids: List of video IDs
        user_id: User identifier

    Returns:
        Batch scraping result
    """
    import asyncio

    async def _scrape():
        await create_task_record(
            task_id=self.request.id,
            task_name="scrape_videos_batch",
            task_type="scraping",
            args=(video_ids,),
            user_id=user_id,
        )

        logger.info(f"📦 Batch scraping {len(video_ids)} videos")

        try:
            results = []

            with create_youtube_client() as client:
                # Use batch API call
                videos = client.get_videos_batch(video_ids)

                async with db_manager.session() as session:
                    repo = VideoRepository(session)

                    for i, video_data in enumerate(videos):
                        video = await repo.upsert_from_api(video_data)
                        results.append({
                            "video_id": video.id,
                            "title": video.title,
                        })

                        # Update progress
                        progress = int((i + 1) / len(video_ids) * 100)
                        update_task_status(self.request.id, "running", progress=progress)

            result = {
                "total_videos": len(video_ids),
                "successful": len(results),
                "videos": results,
                "scraped_at": datetime.utcnow().isoformat(),
            }

            update_task_status(self.request.id, "success", progress=100, result=result)

            return result

        except Exception as e:
            logger.error(f"Batch scraping failed: {e}")
            update_task_status(self.request.id, "failed", error_message=str(e))
            raise self.retry(exc=e)

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_scrape())


@celery_app.task(
    bind=True,
    name="tasks.scraping
)