# src/infrastructure/tasks/caption_tasks.py
"""
Caption Background Tasks
Celery tasks for YouTube caption/subtitle operations
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from src.infrastructure.tasks.celery_app import celery_app
from src.app.database import db_manager
from src.infrastructure.repositories import (
    VideoRepository,
    CaptionRepository,
    CaptionSegmentRepository,
)
from src.services.task_tracking_service import create_task_record, update_task_status

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="tasks.caption.fetch_video_captions",
    max_retries=3,
    default_retry_delay=60,
)
def fetch_video_captions(
    self,
    video_id: str,
    languages: Optional[List[str]] = None,
    include_auto: bool = True,
    force_refresh: bool = False,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Fetch captions for a single video

    Args:
        video_id: YouTube video ID
        languages: Specific languages to fetch (None = all available)
        include_auto: Include auto-generated captions
        force_refresh: Re-fetch even if exists
        user_id: User identifier

    Returns:
        Fetch operation result
    """
    import asyncio

    async def _fetch():
        await create_task_record(
            task_id=self.request.id,
            task_name="fetch_video_captions",
            task_type="caption",
            args=(video_id,),
            kwargs={
                "languages": languages,
                "include_auto": include_auto,
                "force_refresh": force_refresh,
            },
            user_id=user_id,
        )

        logger.info(f"📝 Fetching captions for video: {video_id}")

        try:
            from src.services.caption_service import CaptionService

            async with db_manager.session() as session:
                # Create service
                caption_repo = CaptionRepository(session)
                segment_repo = CaptionSegmentRepository(session)
                video_repo = VideoRepository(session)

                caption_service = CaptionService(
                    caption_repo=caption_repo,
                    segment_repo=segment_repo,
                    video_repo=video_repo,
                )

                await update_task_status(
                    self.request.id, "running", progress=20
                )

                # Fetch captions
                result = await caption_service.fetch_captions(
                    db=session,
                    video_id=video_id,
                    languages=languages,
                    include_auto=include_auto,
                    force_refresh=force_refresh,
                )

                await update_task_status(
                    self.request.id, "running", progress=70
                )

                # Process segments for each fetched caption
                for lang_code in result.get("success", []):
                    try:
                        await caption_service.process_caption_segments(
                            db=session,
                            video_id=video_id,
                            language_code=lang_code,
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to process segments for {video_id}:{lang_code}: {e}"
                        )

                logger.info(
                    f"✅ Captions fetched for {video_id}: "
                    f"{len(result.get('success', []))} languages"
                )

                await update_task_status(
                    self.request.id,
                    "success",
                    progress=100,
                    result=result,
                )

                return result

        except Exception as e:
            logger.error(f"Failed to fetch captions for {video_id}: {e}")
            await update_task_status(
                self.request.id, "failed", error_message=str(e)
            )
            raise self.retry(exc=e)

    return asyncio.run(_fetch())


@celery_app.task(
    bind=True,
    name="tasks.caption.fetch_batch_captions",
    max_retries=2,
    default_retry_delay=120,
)
def fetch_batch_captions(
    self,
    video_ids: List[str],
    languages: Optional[List[str]] = None,
    include_auto: bool = True,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Batch fetch captions for multiple videos

    Args:
        video_ids: List of YouTube video IDs
        languages: Specific languages to fetch
        include_auto: Include auto-generated captions
        user_id: User identifier

    Returns:
        Batch operation results
    """
    import asyncio

    async def _batch_fetch():
        await create_task_record(
            task_id=self.request.id,
            task_name="fetch_batch_captions",
            task_type="caption",
            args=(video_ids,),
            kwargs={"languages": languages, "include_auto": include_auto},
            user_id=user_id,
        )

        logger.info(f"📝 Batch fetching captions for {len(video_ids)} videos")

        results = {
            "total_videos": len(video_ids),
            "success": [],
            "failed": [],
            "started_at": datetime.utcnow().isoformat(),
        }

        try:
            from src.services.caption_service import CaptionService

            async with db_manager.session() as session:
                caption_repo = CaptionRepository(session)
                segment_repo = CaptionSegmentRepository(session)
                video_repo = VideoRepository(session)

                caption_service = CaptionService(
                    caption_repo=caption_repo,
                    segment_repo=segment_repo,
                    video_repo=video_repo,
                )

                for i, video_id in enumerate(video_ids):
                    progress = int((i / len(video_ids)) * 90) + 5
                    await update_task_status(
                        self.request.id, "running", progress=progress
                    )

                    try:
                        result = await caption_service.fetch_captions(
                            db=session,
                            video_id=video_id,
                            languages=languages,
                            include_auto=include_auto,
                            force_refresh=False,
                        )

                        results["success"].append({
                            "video_id": video_id,
                            "languages": result.get("success", []),
                        })

                    except Exception as e:
                        logger.warning(f"Failed to fetch captions for {video_id}: {e}")
                        results["failed"].append({
                            "video_id": video_id,
                            "error": str(e),
                        })

            results["completed_at"] = datetime.utcnow().isoformat()

            logger.info(
                f"✅ Batch caption fetch complete: "
                f"{len(results['success'])} success, "
                f"{len(results['failed'])} failed"
            )

            await update_task_status(
                self.request.id, "success", progress=100, result=results
            )

            return results

        except Exception as e:
            logger.error(f"Batch caption fetch failed: {e}")
            results["error"] = str(e)
            await update_task_status(
                self.request.id, "failed", error_message=str(e)
            )
            raise self.retry(exc=e)

    return asyncio.run(_batch_fetch())


@celery_app.task(
    bind=True,
    name="tasks.caption.process_caption_segments",
    max_retries=3,
)
def process_caption_segments(
    self,
    video_id: str,
    language_code: str,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Process caption into searchable segments

    Args:
        video_id: YouTube video ID
        language_code: Language code
        user_id: User identifier

    Returns:
        Processing result
    """
    import asyncio

    async def _process():
        await create_task_record(
            task_id=self.request.id,
            task_name="process_caption_segments",
            task_type="caption",
            args=(video_id, language_code),
            user_id=user_id,
        )

        logger.info(f"🔧 Processing segments for {video_id}:{language_code}")

        try:
            from src.services.caption_service import CaptionService

            async with db_manager.session() as session:
                caption_repo = CaptionRepository(session)
                segment_repo = CaptionSegmentRepository(session)
                video_repo = VideoRepository(session)

                caption_service = CaptionService(
                    caption_repo=caption_repo,
                    segment_repo=segment_repo,
                    video_repo=video_repo,
                )

                await update_task_status(
                    self.request.id, "running", progress=30
                )

                result = await caption_service.process_caption_segments(
                    db=session,
                    video_id=video_id,
                    language_code=language_code,
                )

                logger.info(
                    f"✅ Processed {result['segments_created']} segments "
                    f"for {video_id}:{language_code}"
                )

                await update_task_status(
                    self.request.id, "success", progress=100, result=result
                )

                return result

        except Exception as e:
            logger.error(
                f"Failed to process segments for {video_id}:{language_code}: {e}"
            )
            await update_task_status(
                self.request.id, "failed", error_message=str(e)
            )
            raise self.retry(exc=e)

    return asyncio.run(_process())


@celery_app.task(
    bind=True,
    name="tasks.caption.fetch_channel_captions",
    max_retries=2,
    default_retry_delay=300,
)
def fetch_channel_captions(
    self,
    channel_id: str,
    max_videos: int = 50,
    languages: Optional[List[str]] = None,
    include_auto: bool = True,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Fetch captions for all videos in a channel

    Args:
        channel_id: YouTube channel ID
        max_videos: Maximum videos to process
        languages: Specific languages to fetch
        include_auto: Include auto-generated captions
        user_id: User identifier

    Returns:
        Channel caption fetch results
    """
    import asyncio

    async def _fetch_channel():
        await create_task_record(
            task_id=self.request.id,
            task_name="fetch_channel_captions",
            task_type="caption",
            args=(channel_id,),
            kwargs={"max_videos": max_videos, "languages": languages},
            user_id=user_id,
        )

        logger.info(f"📝 Fetching captions for channel: {channel_id}")

        results = {
            "channel_id": channel_id,
            "videos_processed": 0,
            "success": [],
            "failed": [],
            "started_at": datetime.utcnow().isoformat(),
        }

        try:
            from src.services.caption_service import CaptionService

            async with db_manager.session() as session:
                # Get channel videos
                video_repo = VideoRepository(session)
                videos = await video_repo.find_by(channel_id=channel_id)

                # Limit to max_videos
                videos = videos[:max_videos]
                results["total_videos"] = len(videos)

                if not videos:
                    logger.warning(f"No videos found for channel {channel_id}")
                    await update_task_status(
                        self.request.id,
                        "success",
                        progress=100,
                        result=results,
                    )
                    return results

                caption_repo = CaptionRepository(session)
                segment_repo = CaptionSegmentRepository(session)

                caption_service = CaptionService(
                    caption_repo=caption_repo,
                    segment_repo=segment_repo,
                    video_repo=video_repo,
                )

                for i, video in enumerate(videos):
                    progress = int((i / len(videos)) * 90) + 5
                    await update_task_status(
                        self.request.id, "running", progress=progress
                    )

                    try:
                        result = await caption_service.fetch_captions(
                            db=session,
                            video_id=video.id,
                            languages=languages,
                            include_auto=include_auto,
                            force_refresh=False,
                        )

                        results["success"].append({
                            "video_id": video.id,
                            "languages": result.get("success", []),
                        })
                        results["videos_processed"] += 1

                    except Exception as e:
                        logger.warning(
                            f"Failed to fetch captions for video {video.id}: {e}"
                        )
                        results["failed"].append({
                            "video_id": video.id,
                            "error": str(e),
                        })

            results["completed_at"] = datetime.utcnow().isoformat()

            logger.info(
                f"✅ Channel caption fetch complete for {channel_id}: "
                f"{len(results['success'])} success, "
                f"{len(results['failed'])} failed"
            )

            await update_task_status(
                self.request.id, "success", progress=100, result=results
            )

            return results

        except Exception as e:
            logger.error(f"Failed to fetch channel captions for {channel_id}: {e}")
            results["error"] = str(e)
            await update_task_status(
                self.request.id, "failed", error_message=str(e)
            )
            raise self.retry(exc=e)

    return asyncio.run(_fetch_channel())


@celery_app.task(
    bind=True,
    name="tasks.caption.delete_video_captions",
    max_retries=2,
)
def delete_video_captions(
    self,
    video_id: str,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Delete all captions for a video

    Args:
        video_id: YouTube video ID
        user_id: User identifier

    Returns:
        Deletion result
    """
    import asyncio

    async def _delete():
        await create_task_record(
            task_id=self.request.id,
            task_name="delete_video_captions",
            task_type="caption",
            args=(video_id,),
            user_id=user_id,
        )

        logger.info(f"🗑️ Deleting captions for video: {video_id}")

        try:
            from src.services.caption_service import CaptionService

            async with db_manager.session() as session:
                caption_repo = CaptionRepository(session)
                segment_repo = CaptionSegmentRepository(session)
                video_repo = VideoRepository(session)

                caption_service = CaptionService(
                    caption_repo=caption_repo,
                    segment_repo=segment_repo,
                    video_repo=video_repo,
                )

                result = await caption_service.delete_video_captions(
                    db=session,
                    video_id=video_id,
                )

                logger.info(
                    f"✅ Deleted captions for {video_id}: "
                    f"{result['captions_deleted']} captions, "
                    f"{result['segments_deleted']} segments"
                )

                await update_task_status(
                    self.request.id, "success", progress=100, result=result
                )

                return result

        except Exception as e:
            logger.error(f"Failed to delete captions for {video_id}: {e}")
            await update_task_status(
                self.request.id, "failed", error_message=str(e)
            )
            raise self.retry(exc=e)

    return asyncio.run(_delete())


# ============================================================================
# Exported Tasks
# ============================================================================

__all__ = [
    "fetch_video_captions",
    "fetch_batch_captions",
    "process_caption_segments",
    "fetch_channel_captions",
    "delete_video_captions",
]
