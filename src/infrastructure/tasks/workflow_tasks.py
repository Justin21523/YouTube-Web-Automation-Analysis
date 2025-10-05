"""
Workflow Tasks
Complex task chains and workflows for coordinated operations
"""

import logging
from typing import Dict, Any, List
from datetime import datetime
from celery import chain, group, chord

from src.infrastructure.tasks.celery_app import celery_app
from src.infrastructure.tasks.video_tasks import (
    scrape_video_metadata,
    scrape_video_comments,
)
from src.infrastructure.tasks.channel_tasks import (
    scrape_channel_metadata,
    scrape_channel_videos,
)
from src.infrastructure.tasks.analysis_tasks import (
    analyze_video_sentiment,
    detect_comment_language,
)
from src.services.task_tracking_service import create_task_record, update_task_status

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="tasks.workflow.full_video_analysis",
    max_retries=1,
)
def full_video_analysis(
    self,
    video_id: str,
    include_comments: bool = True,
    max_comments: int = 500,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Complete video analysis workflow:
    1. Scrape video metadata
    2. Scrape comments
    3. Analyze sentiment
    4. Detect language

    Args:
        video_id: YouTube video ID
        include_comments: Include comment analysis
        max_comments: Max comments to analyze
        user_id: User identifier

    Returns:
        Workflow result
    """
    import asyncio

    async def _workflow():
        await create_task_record(
            task_id=self.request.id,
            task_name="full_video_analysis",
            task_type="workflow",
            args=(video_id,),
            kwargs={"include_comments": include_comments},
            user_id=user_id,
        )

        logger.info(f"🔄 Starting full analysis workflow for video: {video_id}")

        try:
            # Step 1: Scrape video metadata
            logger.info(f"Step 1/4: Scraping video metadata...")
            update_task_status(self.request.id, "running", progress=25)

            video_result = scrape_video_metadata.apply(
                args=(video_id, user_id),
            ).get(timeout=120)

            results = {
                "video_id": video_id,
                "video_metadata": video_result,
                "comments_scraped": 0,
                "sentiment_analyzed": False,
                "language_detected": False,
            }

            if not include_comments:
                update_task_status(
                    self.request.id, "success", progress=100, result=results
                )
                return results

            # Step 2: Scrape comments
            logger.info(f"Step 2/4: Scraping comments...")
            update_task_status(self.request.id, "running", progress=50)

            comments_result = scrape_video_comments.apply(
                args=(video_id, max_comments, user_id),
            ).get(timeout=600)

            results["comments_scraped"] = comments_result.get("comments_scraped", 0)

            if results["comments_scraped"] == 0:
                logger.info("No comments found, skipping analysis")
                update_task_status(
                    self.request.id, "success", progress=100, result=results
                )
                return results

            # Step 3: Analyze sentiment
            logger.info(f"Step 3/4: Analyzing sentiment...")
            update_task_status(self.request.id, "running", progress=75)

            sentiment_result = analyze_video_sentiment.apply(
                args=(video_id, max_comments, user_id),
            ).get(timeout=300)

            results["sentiment_analysis"] = sentiment_result
            results["sentiment_analyzed"] = True

            # Step 4: Detect language
            logger.info(f"Step 4/4: Detecting language...")
            update_task_status(self.request.id, "running", progress=90)

            language_result = detect_comment_language.apply(
                args=(video_id, user_id),
            ).get(timeout=120)

            results["language_detection"] = language_result
            results["language_detected"] = True

            # Workflow complete
            results["workflow_completed_at"] = datetime.utcnow().isoformat()

            update_task_status(self.request.id, "success", progress=100, result=results)

            logger.info(f"✅ Full analysis workflow completed for {video_id}")

            return results

        except Exception as e:
            logger.error(f"Workflow failed for {video_id}: {e}")
            update_task_status(self.request.id, "failed", error_message=str(e))
            raise

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_workflow())


@celery_app.task(
    bind=True,
    name="tasks.workflow.full_channel_analysis",
    max_retries=1,
)
def full_channel_analysis(
    self,
    channel_id: str,
    max_videos: int = 20,
    analyze_videos: bool = True,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Complete channel analysis workflow:
    1. Scrape channel metadata
    2. Scrape latest videos
    3. Analyze each video (optional)

    Args:
        channel_id: YouTube channel ID
        max_videos: Max videos to process
        analyze_videos: Perform video analysis
        user_id: User identifier

    Returns:
        Workflow result
    """
    import asyncio

    async def _workflow():
        await create_task_record(
            task_id=self.request.id,
            task_name="full_channel_analysis",
            task_type="workflow",
            args=(channel_id,),
            kwargs={"max_videos": max_videos, "analyze_videos": analyze_videos},
            user_id=user_id,
        )

        logger.info(f"🔄 Starting channel analysis workflow: {channel_id}")

        try:
            # Step 1: Scrape channel metadata
            logger.info(f"Step 1/3: Scraping channel metadata...")
            update_task_status(self.request.id, "running", progress=20)

            channel_result = scrape_channel_metadata.apply(
                args=(channel_id, user_id),
            ).get(timeout=120)

            # Step 2: Scrape videos
            logger.info(f"Step 2/3: Scraping channel videos...")
            update_task_status(self.request.id, "running", progress=40)

            videos_result = scrape_channel_videos.apply(
                args=(channel_id, max_videos, user_id),
            ).get(timeout=600)

            results = {
                "channel_id": channel_id,
                "channel_metadata": channel_result,
                "videos_scraped": videos_result.get("videos_scraped", 0),
                "videos_analyzed": [],
            }

            if not analyze_videos or results["videos_scraped"] == 0:
                update_task_status(
                    self.request.id, "success", progress=100, result=results
                )
                return results

            # Step 3: Analyze videos (parallel)
            logger.info(f"Step 3/3: Analyzing {results['videos_scraped']} videos...")
            update_task_status(self.request.id, "running", progress=60)

            video_ids = [v["video_id"] for v in videos_result.get("videos", [])][
                :5
            ]  # Limit to 5

            # Launch parallel analysis tasks
            analysis_jobs = group(
                [
                    full_video_analysis.s(
                        video_id=vid,
                        include_comments=True,
                        max_comments=200,
                        user_id=user_id,
                    )
                    for vid in video_ids
                ]
            )

            analysis_results = analysis_jobs.apply_async().get(timeout=1800)

            results["videos_analyzed"] = analysis_results
            results["workflow_completed_at"] = datetime.utcnow().isoformat()

            update_task_status(self.request.id, "success", progress=100, result=results)

            logger.info(f"✅ Channel analysis workflow completed for {channel_id}")

            return results

        except Exception as e:
            logger.error(f"Channel workflow failed for {channel_id}: {e}")
            update_task_status(self.request.id, "failed", error_message=str(e))
            raise

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_workflow())


@celery_app.task(
    bind=True,
    name="tasks.workflow.bulk_video_scraping",
    max_retries=1,
)
def bulk_video_scraping(
    self,
    video_ids: List[str],
    include_comments: bool = False,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Bulk scrape multiple videos in parallel

    Args:
        video_ids: List of video IDs
        include_comments: Include comment scraping
        user_id: User identifier

    Returns:
        Bulk scraping result
    """
    import asyncio

    async def _bulk_scrape():
        await create_task_record(
            task_id=self.request.id,
            task_name="bulk_video_scraping",
            task_type="workflow",
            args=(video_ids,),
            kwargs={"include_comments": include_comments},
            user_id=user_id,
        )

        logger.info(f"📦 Bulk scraping {len(video_ids)} videos")

        try:
            # Create parallel scraping tasks
            if include_comments:
                scrape_jobs = group(
                    [
                        full_video_analysis.s(
                            video_id=vid,
                            include_comments=True,
                            user_id=user_id,
                        )
                        for vid in video_ids
                    ]
                )
            else:
                scrape_jobs = group(
                    [
                        scrape_video_metadata.s(video_id=vid, user_id=user_id)
                        for vid in video_ids
                    ]
                )

            # Execute in parallel
            scrape_results = scrape_jobs.apply_async().get(timeout=1800)

            result = {
                "total_videos": len(video_ids),
                "successful": len([r for r in scrape_results if r]),
                "failed": len([r for r in scrape_results if not r]),
                "results": scrape_results,
                "completed_at": datetime.utcnow().isoformat(),
            }

            update_task_status(self.request.id, "success", progress=100, result=result)

            logger.info(
                f"✅ Bulk scraping completed: {result['successful']}/{result['total_videos']} successful"
            )

            return result

        except Exception as e:
            logger.error(f"Bulk scraping failed: {e}")
            update_task_status(self.request.id, "failed", error_message=str(e))
            raise

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_bulk_scrape())


@celery_app.task(
    bind=True,
    name="tasks.workflow.trending_videos_analysis",
    max_retries=1,
)
def trending_videos_analysis(
    self,
    query: str = "trending",
    max_videos: int = 20,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Search for trending videos and analyze them

    Args:
        query: Search query
        max_videos: Max videos to analyze
        user_id: User identifier

    Returns:
        Trending analysis result
    """
    import asyncio

    async def _trending():
        await create_task_record(
            task_id=self.request.id,
            task_name="trending_videos_analysis",
            task_type="workflow",
            kwargs={"query": query, "max_videos": max_videos},
            user_id=user_id,
        )

        logger.info(f"📈 Analyzing trending videos: '{query}'")

        try:
            from src.infrastructure.tasks.video_tasks import search_and_scrape_videos

            # Step 1: Search and scrape videos
            logger.info(f"Step 1/2: Searching for videos...")
            update_task_status(self.request.id, "running", progress=30)

            search_result = search_and_scrape_videos.apply(
                args=(query, max_videos, "relevance", user_id),
            ).get(timeout=600)

            video_ids = [v["video_id"] for v in search_result.get("videos", [])]

            if not video_ids:
                result = {
                    "query": query,
                    "videos_found": 0,
                    "videos_analyzed": 0,
                }
                update_task_status(
                    self.request.id, "success", progress=100, result=result
                )
                return result

            # Step 2: Analyze videos in parallel
            logger.info(f"Step 2/2: Analyzing {len(video_ids)} videos...")
            update_task_status(self.request.id, "running", progress=60)

            analysis_jobs = group(
                [
                    full_video_analysis.s(
                        video_id=vid,
                        include_comments=True,
                        max_comments=100,
                        user_id=user_id,
                    )
                    for vid in video_ids[:10]  # Limit to 10 for performance
                ]
            )

            analysis_results = analysis_jobs.apply_async().get(timeout=1800)

            result = {
                "query": query,
                "videos_found": len(video_ids),
                "videos_analyzed": len(analysis_results),
                "analysis_results": analysis_results,
                "completed_at": datetime.utcnow().isoformat(),
            }

            update_task_status(self.request.id, "success", progress=100, result=result)

            logger.info(
                f"✅ Trending analysis completed: {len(analysis_results)} videos"
            )

            return result

        except Exception as e:
            logger.error(f"Trending analysis failed: {e}")
            update_task_status(self.request.id, "failed", error_message=str(e))
            raise

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_trending())
