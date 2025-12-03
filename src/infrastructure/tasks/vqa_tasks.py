# src/infrastructure/tasks/vqa_tasks.py
"""
VQA Background Tasks
Celery tasks for Visual Question Answering operations
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from src.infrastructure.tasks.celery_app import celery_app
from src.app.database import db_manager
from src.infrastructure.repositories import (
    VideoRepository,
    VideoFrameRepository,
    FrameAnalysisRepository,
    VQASessionRepository,
    VQAQuestionRepository,
    VideoFrameExtractionRepository,
)
from src.services.task_tracking_service import create_task_record, update_task_status

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="tasks.vqa.extract_video_frames",
    max_retries=2,
    default_retry_delay=120,
)
def extract_video_frames(
    self,
    video_id: str,
    method: str = "keyframe",
    max_frames: int = 50,
    interval_seconds: Optional[float] = None,
    force_reextract: bool = False,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Extract frames from a video

    Args:
        video_id: YouTube video ID
        method: Extraction method (keyframe, interval, scene_change)
        max_frames: Maximum frames to extract
        interval_seconds: Interval for interval-based extraction
        force_reextract: Re-extract even if exists
        user_id: User identifier

    Returns:
        Extraction result
    """
    import asyncio

    async def _extract():
        await create_task_record(
            task_id=self.request.id,
            task_name="extract_video_frames",
            task_type="vqa",
            args=(video_id,),
            kwargs={
                "method": method,
                "max_frames": max_frames,
                "interval_seconds": interval_seconds,
            },
            user_id=user_id,
        )

        logger.info(f"🎬 Extracting frames for video: {video_id}")

        try:
            from src.services.vqa_service import VQAService

            async with db_manager.session() as session:
                # Create service
                vqa_service = VQAService(
                    frame_repo=VideoFrameRepository(session),
                    analysis_repo=FrameAnalysisRepository(session),
                    session_repo=VQASessionRepository(session),
                    question_repo=VQAQuestionRepository(session),
                    extraction_repo=VideoFrameExtractionRepository(session),
                    video_repo=VideoRepository(session),
                )

                await update_task_status(
                    self.request.id, "running", progress=10
                )

                # Extract frames
                result = await vqa_service.extract_frames(
                    db=session,
                    video_id=video_id,
                    method=method,
                    max_frames=max_frames,
                    interval_seconds=interval_seconds,
                    force_reextract=force_reextract,
                )

                logger.info(
                    f"✅ Extracted {result.get('frames_count', 0)} frames "
                    f"for video {video_id}"
                )

                await update_task_status(
                    self.request.id, "success", progress=100, result=result
                )

                return result

        except Exception as e:
            logger.error(f"Failed to extract frames for {video_id}: {e}")
            await update_task_status(
                self.request.id, "failed", error_message=str(e)
            )
            raise self.retry(exc=e)

    return asyncio.run(_extract())


@celery_app.task(
    bind=True,
    name="tasks.vqa.analyze_frame",
    max_retries=3,
    default_retry_delay=60,
)
def analyze_frame(
    self,
    frame_id: int,
    model_type: str = "blip2",
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Analyze a single frame

    Args:
        frame_id: Frame ID
        model_type: VQA model type
        user_id: User identifier

    Returns:
        Analysis result
    """
    import asyncio

    async def _analyze():
        await create_task_record(
            task_id=self.request.id,
            task_name="analyze_frame",
            task_type="vqa",
            args=(frame_id,),
            kwargs={"model_type": model_type},
            user_id=user_id,
        )

        logger.info(f"🔍 Analyzing frame {frame_id} with model {model_type}")

        try:
            from src.services.vqa_service import VQAService

            async with db_manager.session() as session:
                vqa_service = VQAService(
                    frame_repo=VideoFrameRepository(session),
                    analysis_repo=FrameAnalysisRepository(session),
                    session_repo=VQASessionRepository(session),
                    question_repo=VQAQuestionRepository(session),
                    extraction_repo=VideoFrameExtractionRepository(session),
                    video_repo=VideoRepository(session),
                )

                await update_task_status(
                    self.request.id, "running", progress=30
                )

                result = await vqa_service.analyze_frame(
                    db=session,
                    frame_id=frame_id,
                    model_type=model_type,
                )

                logger.info(f"✅ Analysis complete for frame {frame_id}")

                await update_task_status(
                    self.request.id, "success", progress=100, result=result
                )

                return result

        except Exception as e:
            logger.error(f"Failed to analyze frame {frame_id}: {e}")
            await update_task_status(
                self.request.id, "failed", error_message=str(e)
            )
            raise self.retry(exc=e)

    return asyncio.run(_analyze())


@celery_app.task(
    bind=True,
    name="tasks.vqa.analyze_video_frames",
    max_retries=2,
    default_retry_delay=180,
)
def analyze_video_frames(
    self,
    video_id: str,
    model_type: str = "blip2",
    max_frames: int = 20,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Analyze multiple frames from a video

    Args:
        video_id: Video ID
        model_type: VQA model type
        max_frames: Maximum frames to analyze
        user_id: User identifier

    Returns:
        Analysis summary
    """
    import asyncio

    async def _analyze_all():
        await create_task_record(
            task_id=self.request.id,
            task_name="analyze_video_frames",
            task_type="vqa",
            args=(video_id,),
            kwargs={"model_type": model_type, "max_frames": max_frames},
            user_id=user_id,
        )

        logger.info(f"🔍 Analyzing frames for video {video_id}")

        try:
            from src.services.vqa_service import VQAService

            async with db_manager.session() as session:
                vqa_service = VQAService(
                    frame_repo=VideoFrameRepository(session),
                    analysis_repo=FrameAnalysisRepository(session),
                    session_repo=VQASessionRepository(session),
                    question_repo=VQAQuestionRepository(session),
                    extraction_repo=VideoFrameExtractionRepository(session),
                    video_repo=VideoRepository(session),
                )

                await update_task_status(
                    self.request.id, "running", progress=10
                )

                result = await vqa_service.analyze_video_frames(
                    db=session,
                    video_id=video_id,
                    model_type=model_type,
                    max_frames=max_frames,
                )

                logger.info(
                    f"✅ Analyzed {len(result.get('success', []))} frames "
                    f"for video {video_id}"
                )

                await update_task_status(
                    self.request.id, "success", progress=100, result=result
                )

                return result

        except Exception as e:
            logger.error(f"Failed to analyze video frames for {video_id}: {e}")
            await update_task_status(
                self.request.id, "failed", error_message=str(e)
            )
            raise self.retry(exc=e)

    return asyncio.run(_analyze_all())


@celery_app.task(
    bind=True,
    name="tasks.vqa.full_video_vqa_pipeline",
    max_retries=2,
    default_retry_delay=300,
)
def full_video_vqa_pipeline(
    self,
    video_id: str,
    extraction_method: str = "keyframe",
    max_frames: int = 30,
    model_type: str = "blip2",
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Full VQA pipeline: extract frames + analyze all

    Args:
        video_id: YouTube video ID
        extraction_method: Frame extraction method
        max_frames: Maximum frames
        model_type: VQA model type
        user_id: User identifier

    Returns:
        Pipeline result
    """
    import asyncio

    async def _pipeline():
        await create_task_record(
            task_id=self.request.id,
            task_name="full_video_vqa_pipeline",
            task_type="vqa",
            args=(video_id,),
            kwargs={
                "extraction_method": extraction_method,
                "max_frames": max_frames,
                "model_type": model_type,
            },
            user_id=user_id,
        )

        logger.info(f"🚀 Starting full VQA pipeline for video {video_id}")

        results = {
            "video_id": video_id,
            "extraction": None,
            "analysis": None,
            "started_at": datetime.utcnow().isoformat(),
        }

        try:
            from src.services.vqa_service import VQAService

            async with db_manager.session() as session:
                vqa_service = VQAService(
                    frame_repo=VideoFrameRepository(session),
                    analysis_repo=FrameAnalysisRepository(session),
                    session_repo=VQASessionRepository(session),
                    question_repo=VQAQuestionRepository(session),
                    extraction_repo=VideoFrameExtractionRepository(session),
                    video_repo=VideoRepository(session),
                )

                # Step 1: Extract frames
                await update_task_status(
                    self.request.id, "running", progress=10
                )
                logger.info(f"Step 1: Extracting frames for {video_id}")

                extraction_result = await vqa_service.extract_frames(
                    db=session,
                    video_id=video_id,
                    method=extraction_method,
                    max_frames=max_frames,
                    force_reextract=False,
                )
                results["extraction"] = extraction_result

                await update_task_status(
                    self.request.id, "running", progress=50
                )

                # Step 2: Analyze frames
                logger.info(f"Step 2: Analyzing frames for {video_id}")

                analysis_result = await vqa_service.analyze_video_frames(
                    db=session,
                    video_id=video_id,
                    model_type=model_type,
                    max_frames=max_frames,
                )
                results["analysis"] = analysis_result

                results["completed_at"] = datetime.utcnow().isoformat()

                logger.info(f"✅ Full VQA pipeline complete for {video_id}")

                await update_task_status(
                    self.request.id, "success", progress=100, result=results
                )

                return results

        except Exception as e:
            logger.error(f"VQA pipeline failed for {video_id}: {e}")
            results["error"] = str(e)
            await update_task_status(
                self.request.id, "failed", error_message=str(e)
            )
            raise self.retry(exc=e)

    return asyncio.run(_pipeline())


@celery_app.task(
    bind=True,
    name="tasks.vqa.batch_extract_frames",
    max_retries=2,
)
def batch_extract_frames(
    self,
    video_ids: List[str],
    method: str = "keyframe",
    max_frames: int = 30,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Batch extract frames from multiple videos

    Args:
        video_ids: List of video IDs
        method: Extraction method
        max_frames: Maximum frames per video
        user_id: User identifier

    Returns:
        Batch extraction results
    """
    import asyncio

    async def _batch():
        await create_task_record(
            task_id=self.request.id,
            task_name="batch_extract_frames",
            task_type="vqa",
            args=(video_ids,),
            kwargs={"method": method, "max_frames": max_frames},
            user_id=user_id,
        )

        logger.info(f"🎬 Batch extracting frames for {len(video_ids)} videos")

        results = {
            "total_videos": len(video_ids),
            "success": [],
            "failed": [],
            "started_at": datetime.utcnow().isoformat(),
        }

        try:
            from src.services.vqa_service import VQAService

            async with db_manager.session() as session:
                vqa_service = VQAService(
                    frame_repo=VideoFrameRepository(session),
                    analysis_repo=FrameAnalysisRepository(session),
                    session_repo=VQASessionRepository(session),
                    question_repo=VQAQuestionRepository(session),
                    extraction_repo=VideoFrameExtractionRepository(session),
                    video_repo=VideoRepository(session),
                )

                for i, video_id in enumerate(video_ids):
                    progress = int((i / len(video_ids)) * 90) + 5
                    await update_task_status(
                        self.request.id, "running", progress=progress
                    )

                    try:
                        result = await vqa_service.extract_frames(
                            db=session,
                            video_id=video_id,
                            method=method,
                            max_frames=max_frames,
                            force_reextract=False,
                        )
                        results["success"].append({
                            "video_id": video_id,
                            "frames_count": result.get("frames_count", 0),
                        })
                    except Exception as e:
                        logger.warning(
                            f"Failed to extract frames for {video_id}: {e}"
                        )
                        results["failed"].append({
                            "video_id": video_id,
                            "error": str(e),
                        })

            results["completed_at"] = datetime.utcnow().isoformat()

            logger.info(
                f"✅ Batch extraction complete: "
                f"{len(results['success'])} success, "
                f"{len(results['failed'])} failed"
            )

            await update_task_status(
                self.request.id, "success", progress=100, result=results
            )

            return results

        except Exception as e:
            logger.error(f"Batch extraction failed: {e}")
            results["error"] = str(e)
            await update_task_status(
                self.request.id, "failed", error_message=str(e)
            )
            raise self.retry(exc=e)

    return asyncio.run(_batch())


@celery_app.task(
    bind=True,
    name="tasks.vqa.cleanup_old_frames",
    max_retries=1,
)
def cleanup_old_frames(
    self,
    video_id: str,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Clean up extracted frames for a video

    Args:
        video_id: Video ID
        user_id: User identifier

    Returns:
        Cleanup result
    """
    import asyncio
    import shutil
    import os

    async def _cleanup():
        await create_task_record(
            task_id=self.request.id,
            task_name="cleanup_old_frames",
            task_type="vqa",
            args=(video_id,),
            user_id=user_id,
        )

        logger.info(f"🧹 Cleaning up frames for video {video_id}")

        try:
            async with db_manager.session() as session:
                frame_repo = VideoFrameRepository(session)
                extraction_repo = VideoFrameExtractionRepository(session)

                # Delete from database
                frames_deleted = await frame_repo.delete_by_video(video_id)

                # Delete extraction record
                extraction = await extraction_repo.get_by_video_id(video_id)
                if extraction:
                    await extraction_repo.delete(extraction.id)

                # Delete frame files
                frames_dir = f"./output/frames/{video_id}"
                files_deleted = 0
                if os.path.exists(frames_dir):
                    files_deleted = len(os.listdir(frames_dir))
                    shutil.rmtree(frames_dir)

                result = {
                    "video_id": video_id,
                    "frames_deleted": frames_deleted,
                    "files_deleted": files_deleted,
                }

                logger.info(
                    f"✅ Cleanup complete for {video_id}: "
                    f"{frames_deleted} DB records, {files_deleted} files"
                )

                await update_task_status(
                    self.request.id, "success", progress=100, result=result
                )

                return result

        except Exception as e:
            logger.error(f"Cleanup failed for {video_id}: {e}")
            await update_task_status(
                self.request.id, "failed", error_message=str(e)
            )
            raise

    return asyncio.run(_cleanup())


# ============================================================================
# Exported Tasks
# ============================================================================

__all__ = [
    "extract_video_frames",
    "analyze_frame",
    "analyze_video_frames",
    "full_video_vqa_pipeline",
    "batch_extract_frames",
    "cleanup_old_frames",
]
