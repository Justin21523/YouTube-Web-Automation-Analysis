# src/infrastructure/repositories/comment_repository.py
"""
Comment Repository
Handles all comment-related database operations with reply threading
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import select, func, and_, or_, desc, asc, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import logging

from .base import BaseRepository
from src.app.models import Comment, Video

logger = logging.getLogger(__name__)


class CommentRepository(BaseRepository[Comment]):
    """
    Repository for Comment operations
    Provides comment-specific queries with threading and sentiment support
    """

    def __init__(self, session: AsyncSession):
        """Initialize comment repository"""
        super().__init__(session, Comment)

    # ========================================================================
    # Comment Retrieval Methods
    # ========================================================================

    async def get_by_video(
        self,
        video_id: str,
        skip: int = 0,
        limit: int = 100,
        order_by: str = "published_at",
    ) -> List[Comment]:
        """
        Get all comments for a video

        Args:
            video_id: YouTube video ID
            skip: Pagination offset
            limit: Max results
            order_by: Sort field (published_at, like_count, reply_count)

        Returns:
            List of comments
        """
        try:
            query = (
                select(Comment)
                .where(Comment.video_id == video_id)
                .where(Comment.parent_id.is_(None))  # Only top-level comments
                .offset(skip)
                .limit(limit)
            )

            # Apply ordering
            if order_by == "published_at":
                query = query.order_by(desc(Comment.published_at))
            elif order_by == "like_count":
                query = query.order_by(desc(Comment.like_count))
            elif order_by == "reply_count":
                query = query.order_by(desc(Comment.reply_count))
            else:
                query = query.order_by(desc(Comment.published_at))

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get comments by video: {e}")
            raise

    async def get_by_video_with_replies(
        self, video_id: str, skip: int = 0, limit: int = 100
    ) -> List[Comment]:
        """
        Get comments with replies eagerly loaded

        Args:
            video_id: YouTube video ID
            skip: Pagination offset
            limit: Max results

        Returns:
            List of comments with replies
        """
        try:
            result = await self.session.execute(
                select(Comment)
                .options(selectinload(Comment.replies))
                .where(Comment.video_id == video_id)
                .where(Comment.parent_id.is_(None))
                .order_by(desc(Comment.like_count))
                .offset(skip)
                .limit(limit)
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get comments with replies: {e}")
            raise

    async def get_replies(
        self, parent_id: str, skip: int = 0, limit: int = 50
    ) -> List[Comment]:
        """
        Get all replies to a comment

        Args:
            parent_id: Parent comment ID
            skip: Pagination offset
            limit: Max results

        Returns:
            List of reply comments
        """
        try:
            result = await self.session.execute(
                select(Comment)
                .where(Comment.parent_id == parent_id)
                .order_by(asc(Comment.published_at))
                .offset(skip)
                .limit(limit)
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get replies: {e}")
            raise

    async def get_by_author(
        self, author_channel_id: str, skip: int = 0, limit: int = 100
    ) -> List[Comment]:
        """
        Get all comments by an author

        Args:
            author_channel_id: Author's channel ID
            skip: Pagination offset
            limit: Max results

        Returns:
            List of comments by author
        """
        try:
            result = await self.session.execute(
                select(Comment)
                .where(Comment.author_channel_id == author_channel_id)
                .order_by(desc(Comment.published_at))
                .offset(skip)
                .limit(limit)
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get comments by author: {e}")
            raise

    async def get_pinned_comments(self, video_id: str) -> List[Comment]:
        """
        Get pinned comments for a video

        Args:
            video_id: YouTube video ID

        Returns:
            List of pinned comments
        """
        try:
            result = await self.session.execute(
                select(Comment)
                .where(and_(Comment.video_id == video_id, Comment.is_pinned == True))
                .order_by(desc(Comment.published_at))
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get pinned comments: {e}")
            raise

    # ========================================================================
    # Comment Search & Filtering
    # ========================================================================

    async def search_comments(
        self,
        query: str,
        video_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Comment]:
        """
        Search comments by text content

        Args:
            query: Search query string
            video_id: Filter by video (optional)
            skip: Pagination offset
            limit: Max results

        Returns:
            List of matching comments
        """
        try:
            search_query = select(Comment).where(
                or_(
                    Comment.text.ilike(f"%{query}%"),
                    Comment.text_display.ilike(f"%{query}%"),
                )
            )

            if video_id:
                search_query = search_query.where(Comment.video_id == video_id)

            search_query = (
                search_query.order_by(desc(Comment.like_count))
                .offset(skip)
                .limit(limit)
            )

            result = await self.session.execute(search_query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to search comments: {e}")
            raise

    async def get_top_comments(
        self, video_id: str, limit: int = 10, min_likes: int = 0
    ) -> List[Comment]:
        """
        Get top comments by like count

        Args:
            video_id: YouTube video ID
            limit: Max results
            min_likes: Minimum like threshold

        Returns:
            List of top comments
        """
        try:
            result = await self.session.execute(
                select(Comment)
                .where(
                    and_(
                        Comment.video_id == video_id,
                        Comment.like_count >= min_likes,
                        Comment.parent_id.is_(None),
                    )
                )
                .order_by(desc(Comment.like_count))
                .limit(limit)
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get top comments: {e}")
            raise

    async def get_recent_comments(
        self, video_id: Optional[str] = None, hours: int = 24, limit: int = 100
    ) -> List[Comment]:
        """
        Get recent comments within time window

        Args:
            video_id: Filter by video (optional)
            hours: Time window in hours
            limit: Max results

        Returns:
            List of recent comments
        """
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)

            query = select(Comment).where(Comment.published_at >= cutoff_time)

            if video_id:
                query = query.where(Comment.video_id == video_id)

            query = query.order_by(desc(Comment.published_at)).limit(limit)

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get recent comments: {e}")
            raise

    # ========================================================================
    # Sentiment Analysis Support
    # ========================================================================

    async def get_comments_by_sentiment(
        self, video_id: str, sentiment_label: str, skip: int = 0, limit: int = 100
    ) -> List[Comment]:
        """
        Get comments filtered by sentiment label

        Args:
            video_id: YouTube video ID
            sentiment_label: positive/negative/neutral
            skip: Pagination offset
            limit: Max results

        Returns:
            List of comments with matching sentiment
        """
        try:
            result = await self.session.execute(
                select(Comment)
                .where(
                    and_(
                        Comment.video_id == video_id,
                        Comment.sentiment_label == sentiment_label,
                    )
                )
                .order_by(desc(Comment.published_at))
                .offset(skip)
                .limit(limit)
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get comments by sentiment: {e}")
            raise

    async def get_sentiment_distribution(self, video_id: str) -> Dict[str, Any]:
        """
        Get sentiment distribution for video comments

        Args:
            video_id: YouTube video ID

        Returns:
            Dictionary with sentiment counts and percentages
        """
        try:
            result = await self.session.execute(
                select(
                    Comment.sentiment_label,
                    func.count(Comment.id).label("count"),
                    func.avg(Comment.sentiment_score).label("avg_score"),
                )
                .where(
                    and_(
                        Comment.video_id == video_id,
                        Comment.sentiment_label.isnot(None),
                    )
                )
                .group_by(Comment.sentiment_label)
            )

            total_analyzed = 0
            distribution = {}

            for row in result.all():
                sentiment = row.sentiment_label
                count = row.count
                avg_score = row.avg_score

                distribution[sentiment] = {
                    "count": count,
                    "avg_score": float(avg_score) if avg_score else 0.0,
                }
                total_analyzed += count

            # Calculate percentages
            for sentiment in distribution:
                count = distribution[sentiment]["count"]
                distribution[sentiment]["percentage"] = (
                    round((count / total_analyzed) * 100, 2)
                    if total_analyzed > 0
                    else 0
                )

            return {
                "video_id": video_id,
                "total_analyzed": total_analyzed,
                "distribution": distribution,
            }
        except Exception as e:
            logger.error(f"❌ Failed to get sentiment distribution: {e}")
            raise

    async def get_unanalyzed_comments(self, limit: int = 100) -> List[Comment]:
        """
        Get comments without sentiment analysis

        Args:
            limit: Max results

        Returns:
            List of unanalyzed comments
        """
        try:
            result = await self.session.execute(
                select(Comment)
                .where(Comment.sentiment_label.is_(None))
                .order_by(desc(Comment.published_at))
                .limit(limit)
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get unanalyzed comments: {e}")
            raise

    async def update_sentiment(
        self,
        comment_id: str,
        sentiment_score: float,
        sentiment_label: str,
        sentiment_confidence: float,
    ) -> bool:
        """
        Update comment sentiment analysis results

        Args:
            comment_id: Comment ID
            sentiment_score: Score from -1.0 to 1.0
            sentiment_label: positive/negative/neutral
            sentiment_confidence: Confidence score 0.0-1.0

        Returns:
            True if updated successfully
        """
        try:
            await self.update(
                comment_id,
                sentiment_score=sentiment_score,
                sentiment_label=sentiment_label,
                sentiment_confidence=sentiment_confidence,
                analyzed_at=datetime.utcnow(),
            )
            return True
        except Exception as e:
            logger.error(f"❌ Failed to update sentiment: {e}")
            return False

    # ========================================================================
    # Comment Statistics
    # ========================================================================

    async def get_comment_statistics(self, video_id: str) -> Dict[str, Any]:
        """
        Get comprehensive comment statistics for a video

        Args:
            video_id: YouTube video ID

        Returns:
            Dictionary with comment stats
        """
        try:
            result = await self.session.execute(
                select(
                    func.count(Comment.id).label("total_comments"),
                    func.sum(case((Comment.parent_id.is_(None), 1), else_=0)).label(
                        "top_level_comments"
                    ),
                    func.sum(case((Comment.parent_id.isnot(None), 1), else_=0)).label(
                        "replies"
                    ),
                    func.sum(Comment.like_count).label("total_likes"),
                    func.avg(Comment.like_count).label("avg_likes"),
                    func.max(Comment.like_count).label("max_likes"),
                    func.count(Comment.sentiment_label).label("analyzed_count"),
                ).where(Comment.video_id == video_id)
            )

            stats_row = result.first()

            return {
                "video_id": video_id,
                "total_comments": stats_row.total_comments or 0,
                "top_level_comments": stats_row.top_level_comments or 0,
                "replies": stats_row.replies or 0,
                "total_likes": stats_row.total_likes or 0,
                "avg_likes_per_comment": float(stats_row.avg_likes or 0),
                "most_liked_comment_likes": stats_row.max_likes or 0,
                "analyzed_count": stats_row.analyzed_count or 0,
                "analysis_percentage": (
                    round(
                        (stats_row.analyzed_count / stats_row.total_comments) * 100, 2
                    )
                    if stats_row.total_comments and stats_row.total_comments > 0
                    else 0
                ),
            }
        except Exception as e:
            logger.error(f"❌ Failed to get comment statistics: {e}")
            raise

    async def get_most_active_commenters(
        self, video_id: Optional[str] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get most active commenters by comment count

        Args:
            video_id: Filter by video (optional)
            limit: Max results

        Returns:
            List of authors with comment counts
        """
        try:
            query = (
                select(
                    Comment.author_name,
                    Comment.author_channel_id,
                    func.count(Comment.id).label("comment_count"),
                    func.sum(Comment.like_count).label("total_likes"),
                )
                .group_by(Comment.author_name, Comment.author_channel_id)
                .order_by(desc("comment_count"))
                .limit(limit)
            )

            if video_id:
                query = query.where(Comment.video_id == video_id)

            result = await self.session.execute(query)

            active_commenters = []
            for row in result.all():
                active_commenters.append(
                    {
                        "author_name": row.author_name,
                        "author_channel_id": row.author_channel_id,
                        "comment_count": row.comment_count,
                        "total_likes": row.total_likes or 0,
                    }
                )

            return active_commenters
        except Exception as e:
            logger.error(f"❌ Failed to get active commenters: {e}")
            raise

    async def get_comment_engagement_timeline(
        self, video_id: str, days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get comment activity over time

        Args:
            video_id: YouTube video ID
            days: Number of days to analyze

        Returns:
            List of daily comment counts
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            result = await self.session.execute(
                select(
                    func.date(Comment.published_at).label("date"),
                    func.count(Comment.id).label("comment_count"),
                    func.sum(Comment.like_count).label("total_likes"),
                )
                .where(
                    and_(
                        Comment.video_id == video_id,
                        Comment.published_at >= cutoff_date,
                    )
                )
                .group_by(func.date(Comment.published_at))
                .order_by(asc("date"))
            )

            timeline = []
            for row in result.all():
                timeline.append(
                    {
                        "date": row.date.isoformat() if row.date else None,
                        "comment_count": row.comment_count,
                        "total_likes": row.total_likes or 0,
                    }
                )

            return timeline
        except Exception as e:
            logger.error(f"❌ Failed to get engagement timeline: {e}")
            raise

    # ========================================================================
    # Batch Operations
    # ========================================================================

    async def upsert_comment(self, comment_data: Dict[str, Any]) -> Comment:
        """
        Insert or update comment (upsert)

        Args:
            comment_data: Comment attributes dictionary

        Returns:
            Comment instance (created or updated)
        """
        try:
            comment_id = comment_data.get("id")
            existing_comment = await self.get_by_id(comment_id)

            if existing_comment:
                # Update existing comment
                updated_comment = await self.update(comment_id, **comment_data)
                logger.info(f"✅ Updated comment: {comment_id}")
                return updated_comment
            else:
                # Create new comment
                comment_data["scraped_at"] = datetime.utcnow()
                new_comment = await self.create(**comment_data)
                logger.info(f"✅ Created new comment: {comment_id}")
                return new_comment
        except Exception as e:
            logger.error(f"❌ Failed to upsert comment: {e}")
            raise

    async def bulk_upsert_comments(
        self, comments_data: List[Dict[str, Any]]
    ) -> tuple[int, int]:
        """
        Bulk insert or update comments

        Args:
            comments_data: List of comment attribute dictionaries

        Returns:
            Tuple of (created_count, updated_count)
        """
        try:
            created_count = 0
            updated_count = 0

            for comment_data in comments_data:
                comment_id = comment_data.get("id")
                existing = await self.exists(comment_id)

                if existing:
                    await self.update(comment_id, **comment_data)
                    updated_count += 1
                else:
                    comment_data["scraped_at"] = datetime.utcnow()
                    await self.create(**comment_data)
                    created_count += 1

            await self.session.commit()
            logger.info(
                f"✅ Bulk upsert complete: {created_count} created, {updated_count} updated"
            )
            return created_count, updated_count
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Failed to bulk upsert comments: {e}")
            raise

    # ========================================================================
    # Language Detection Support
    # ========================================================================

    async def get_comments_by_language(
        self, video_id: str, language: str, skip: int = 0, limit: int = 100
    ) -> List[Comment]:
        """
        Get comments filtered by language

        Args:
            video_id: YouTube video ID
            language: Language code (e.g., 'en', 'es')
            skip: Pagination offset
            limit: Max results

        Returns:
            List of comments in specified language
        """
        try:
            result = await self.session.execute(
                select(Comment)
                .where(and_(Comment.video_id == video_id, Comment.language == language))
                .order_by(desc(Comment.published_at))
                .offset(skip)
                .limit(limit)
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get comments by language: {e}")
            raise

    async def get_language_distribution(self, video_id: str) -> Dict[str, int]:
        """
        Get language distribution for video comments

        Args:
            video_id: YouTube video ID

        Returns:
            Dictionary mapping language codes to counts
        """
        try:
            result = await self.session.execute(
                select(Comment.language, func.count(Comment.id).label("count"))
                .where(and_(Comment.video_id == video_id, Comment.language.isnot(None)))
                .group_by(Comment.language)
                .order_by(desc("count"))
            )

            distribution = {}
            for row in result.all():
                if row.language:
                    distribution[row.language] = row.count

            return distribution
        except Exception as e:
            logger.error(f"❌ Failed to get language distribution: {e}")
            raise


# ============================================================================
# Export
# ============================================================================

__all__ = ["CommentRepository"]
