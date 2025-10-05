"""
Analysis Background Tasks
Celery tasks for sentiment analysis and NLP processing
"""

import logging
from typing import Dict, Any, List
from datetime import datetime

from src.infrastructure.tasks.celery_app import celery_app
from src.app.database import db_manager
from src.infrastructure.repositories import CommentRepository
from src.services.task_tracking_service import create_task_record, update_task_status

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="tasks.analysis.analyze_video_sentiment",
    max_retries=2,
    queue="analysis",
)
def analyze_video_sentiment(
    self,
    video_id: str,
    max_comments: int = 500,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Analyze sentiment of video comments

    Args:
        video_id: YouTube video ID
        max_comments: Max comments to analyze
        user_id: User identifier

    Returns:
        Sentiment analysis result
    """
    import asyncio

    async def _analyze():
        await create_task_record(
            task_id=self.request.id,
            task_name="analyze_video_sentiment",
            task_type="analysis",
            args=(video_id,),
            kwargs={"max_comments": max_comments},
            user_id=user_id,
        )

        logger.info(f"😊 Analyzing sentiment for video: {video_id}")

        try:
            from transformers import pipeline

            # Load sentiment analysis model
            sentiment_analyzer = pipeline(
                "sentiment-analysis",
                model="distilbert-base-uncased-finetuned-sst-2-english",
                device=-1,  # CPU
            )

            update_task_status(self.request.id, "running", progress=20)

            # Fetch comments
            async with db_manager.session() as session:
                comment_repo = CommentRepository(session)

                comments = await comment_repo.get_by_video_id(
                    video_id=video_id,
                    limit=max_comments,
                )

                if not comments:
                    result = {
                        "video_id": video_id,
                        "comments_analyzed": 0,
                        "sentiment_distribution": {},
                    }
                    update_task_status(self.request.id, "success", progress=100, result=result)
                    return result

                # Analyze sentiment for each comment
                sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0}
                analyzed_count = 0

                for i, comment in enumerate(comments):
                    try:
                        # Analyze text
                        result_sentiment = sentiment_analyzer(comment.text[:512])[0]

                        # Map to our labels
                        label = result_sentiment["label"].lower()
                        score = result_sentiment["score"]

                        if label == "positive":
                            sentiment_label = "positive"
                        elif label == "negative":
                            sentiment_label = "negative"
                        else:
                            sentiment_label = "neutral"

                        # Update comment with sentiment
                        comment.sentiment_label = sentiment_label
                        comment.sentiment_score = score if sentiment_label == "positive" else -score
                        comment.sentiment_confidence = score
                        comment.analyzed_at = datetime.utcnow()

                        sentiment_counts[sentiment_label] += 1
                        analyzed_count += 1

                        # Update progress
                        if i % 50 == 0:
                            progress = 20 + int((i / len(comments)) * 70)
                            update_task_status(self.request.id, "running", progress=progress)

                    except Exception as e:
                        logger.warning(f"Failed to analyze comment {comment.id}: {e}")
                        continue

                # Commit updates
                await session.commit()

            # Calculate statistics
            total = sum(sentiment_counts.values())
            distribution = {
                label: {
                    "count": count,
                    "percentage": round(count / total * 100, 2) if total > 0 else 0,
                }
                for label, count in sentiment_counts.items()
            }

            result = {
                "video_id": video_id,
                "comments_analyzed": analyzed_count,
                "sentiment_distribution": distribution,
                "avg_sentiment": round(
                    (sentiment_counts["positive"] - sentiment_counts["negative"]) / total,
                    3
                ) if total > 0 else 0,
                "analyzed_at": datetime.utcnow().isoformat(),
            }

            update_task_status(self.request.id, "success", progress=100, result=result)

            logger.info(f"✅ Analyzed {analyzed_count} comments for {video_id}")

            return result

        except Exception as e:
            logger.error(f"Sentiment analysis failed for {video_id}: {e}")
            update_task_status(self.request.id, "failed", error_message=str(e))
            raise self.retry(exc=e)

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_analyze())


@celery_app.task(
    bind=True,
    name="tasks.analysis.detect_comment_language",
    max_retries=2,
    queue="analysis",
)
def detect_comment_language(
    self,
    video_id: str,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Detect language of video comments

    Args:
        video_id: YouTube video ID
        user_id: User identifier

    Returns:
        Language detection result
    """
    import asyncio

    async def _detect():
        await create_task_record(
            task_id=self.request.id,
            task_name="detect_comment_language",
            task_type="analysis",
            args=(video_id,),
            user_id=user_id,
        )

        logger.info(f"🌍 Detecting languages for video: {video_id}")

        try:
            from langdetect import detect_langs

            # Fetch comments
            async with db_manager.session() as session:
                comment_repo = CommentRepository(session)

                comments = await comment_repo.get_by_video_id(
                    video_id=video_id,
                    limit=1000,
                )

                if not comments:
                    result = {
                        "video_id": video_id,
                        "comments_processed": 0,
                        "languages": {},
                    }
                    update_task_status(self.request.id, "success", progress=100, result=result)
                    return result

                language_counts = {}
                processed = 0

                for comment in comments:
                    try:
                        # Detect language
                        langs = detect_langs(comment.text)

                        if langs:
                            lang = langs[0]
                            comment.language = lang.lang
                            comment.language_confidence = lang.prob

                            language_counts[lang.lang] = language_counts.get(lang.lang, 0) + 1
                            processed += 1

                    except Exception as e:
                        logger.debug(f"Failed to detect language for comment {comment.id}: {e}")
                        continue

                await session.commit()

            result = {
                "video_id": video_id,
                "comments_processed": processed,
                "languages": language_counts,
                "primary_language": max(language_counts, key=language_counts.get) if language_counts else None,
                "detected_at": datetime.utcnow().isoformat(),
            }

            update_task_status(self.request.id, "success", progress=100, result=result)

            return result

        except Exception as e:
            logger.error(f"Language detection failed for {video_id}: {e}")
            update_task_status(self.request.id, "failed", error_message=str(e))
            raise self.retry(exc=e)

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_detect())


@celery_app.task(
    bind=True,
    name="tasks.analysis.extract_comment_keywords",
    max_retries=2,
    queue="analysis",
)
def extract_comment_keywords(
    self,
    video_id: str,
    top_n: int = 20,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Extract keywords from video comments

    Args:
        video_id: YouTube video ID
        top_n: Number of top keywords
        user_id: User identifier

    Returns:
        Keyword extraction result
    """
    import asyncio

    async def _extract():
        await create_task_record(
            task_id=self.request.id,
            task_name="extract_comment_keywords",
            task_type="analysis",
            args=(video_id,),
            kwargs={"top_n": top_n},
            user_id=user_id,
        )

        logger.info(f"🔑 Extracting keywords for video: {video_id}")

        try:
            from collections import Counter
            import re

            # Fetch comments
            async with db_manager.session() as session:
                comment_repo = CommentRepository(session)

                comments = await comment_repo.get_by_video_id(
                    video_id=video_id,
                    limit=1000,
                )

                if not comments:
                    result = {
                        "video_id": video_id,
                        "keywords": [],
                    }
                    update_task_status(self.request.id, "success", progress=100, result=result)
                    return result

                # Combine all comment text
                all_text = " ".join([comment.text for comment in comments])

                # Simple keyword extraction (lowercase, remove punctuation)
                words = re.findall(r'\b\w+\b', all_text.lower())

                # Filter stopwords (simple list)
                stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
                            'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
                            'could', 'should', 'may', 'might', 'can', 'this', 'that', 'these',
                            'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'what', 'which',
                            'who', 'when', 'where', 'why', 'how', 'all', 'each', 'every', 'both',
                            'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not',