# src/infrastructure/repositories/caption_repository.py
"""
Caption Repository
Database operations for caption/subtitle entities
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, delete
from sqlalchemy.orm import selectinload
import logging

from src.infrastructure.repositories.base import BaseRepository
from src.app.models import Caption, CaptionSegment

logger = logging.getLogger(__name__)


class CaptionRepository(BaseRepository[Caption]):
    """Repository for Caption operations"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Caption)

    async def get_by_video_id(
        self, video_id: str, language_code: Optional[str] = None
    ) -> List[Caption]:
        """
        Get captions for a video

        Args:
            video_id: YouTube video ID
            language_code: Optional language filter

        Returns:
            List of captions
        """
        try:
            query = select(Caption).where(Caption.video_id == video_id)

            if language_code:
                query = query.where(Caption.language_code == language_code)

            query = query.order_by(Caption.language_code)

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get captions for video {video_id}: {e}")
            raise

    async def get_by_video_and_language(
        self, video_id: str, language_code: str
    ) -> Optional[Caption]:
        """
        Get specific caption by video and language

        Args:
            video_id: YouTube video ID
            language_code: Language code (e.g., 'en', 'zh-TW')

        Returns:
            Caption or None
        """
        try:
            query = select(Caption).where(
                and_(
                    Caption.video_id == video_id,
                    Caption.language_code == language_code,
                )
            )
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(
                f"Failed to get caption for video {video_id} language {language_code}: {e}"
            )
            raise

    async def get_available_languages(self, video_id: str) -> List[Dict[str, Any]]:
        """
        Get list of available languages for a video

        Args:
            video_id: YouTube video ID

        Returns:
            List of language info dicts
        """
        try:
            query = (
                select(
                    Caption.language_code,
                    Caption.language_name,
                    Caption.caption_type,
                    Caption.word_count,
                )
                .where(Caption.video_id == video_id)
                .order_by(Caption.language_code)
            )

            result = await self.session.execute(query)
            rows = result.all()

            return [
                {
                    "language_code": row.language_code,
                    "language_name": row.language_name,
                    "caption_type": row.caption_type,
                    "word_count": row.word_count,
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Failed to get available languages for video {video_id}: {e}")
            raise

    async def search_in_captions(
        self,
        query_text: str,
        video_ids: Optional[List[str]] = None,
        language_code: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Search for text within captions

        Args:
            query_text: Text to search for
            video_ids: Optional list of video IDs to limit search
            language_code: Optional language filter
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of matching caption results
        """
        try:
            query = select(Caption).where(Caption.content.ilike(f"%{query_text}%"))

            if video_ids:
                query = query.where(Caption.video_id.in_(video_ids))

            if language_code:
                query = query.where(Caption.language_code == language_code)

            query = query.offset(skip).limit(limit)

            result = await self.session.execute(query)
            captions = result.scalars().all()

            return [
                {
                    "video_id": cap.video_id,
                    "language_code": cap.language_code,
                    "caption_id": cap.id,
                    "word_count": cap.word_count,
                    "match_preview": self._extract_match_preview(cap.content, query_text),
                }
                for cap in captions
            ]
        except Exception as e:
            logger.error(f"Failed to search captions: {e}")
            raise

    async def count_by_video(self, video_id: str) -> int:
        """Count captions for a video"""
        try:
            query = (
                select(func.count())
                .select_from(Caption)
                .where(Caption.video_id == video_id)
            )
            result = await self.session.execute(query)
            return int(result.scalar_one_or_none() or 0)
        except Exception as e:
            logger.error(f"Failed to count captions for video {video_id}: {e}")
            raise

    async def delete_by_video(self, video_id: str) -> int:
        """Delete all captions for a video"""
        try:
            stmt = delete(Caption).where(Caption.video_id == video_id)
            result = await self.session.execute(stmt)
            await self.session.commit()
            deleted_count = result.rowcount or 0
            logger.info(f"Deleted {deleted_count} captions for video {video_id}")
            return deleted_count
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to delete captions for video {video_id}: {e}")
            raise

    async def upsert_caption(self, caption_data: Dict[str, Any]) -> Caption:
        """
        Insert or update caption

        Args:
            caption_data: Caption attributes including id

        Returns:
            Created or updated Caption
        """
        try:
            existing = await self.get_by_id(caption_data["id"])

            if existing:
                # Update existing
                update_data = {k: v for k, v in caption_data.items() if k != "id"}
                return await self.update(caption_data["id"], **update_data)
            else:
                # Create new
                return await self.create(**caption_data)
        except Exception as e:
            logger.error(f"Failed to upsert caption: {e}")
            raise

    def _extract_match_preview(
        self, content: str, query_text: str, context_chars: int = 100
    ) -> str:
        """Extract preview text around the matched query"""
        if not content:
            return ""

        content_lower = content.lower()
        query_lower = query_text.lower()
        pos = content_lower.find(query_lower)

        if pos == -1:
            return content[:200] + "..." if len(content) > 200 else content

        start = max(0, pos - context_chars)
        end = min(len(content), pos + len(query_text) + context_chars)

        preview = content[start:end]
        if start > 0:
            preview = "..." + preview
        if end < len(content):
            preview = preview + "..."

        return preview


class CaptionSegmentRepository(BaseRepository[CaptionSegment]):
    """Repository for CaptionSegment operations"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, CaptionSegment)

    async def get_by_caption_id(
        self, caption_id: str, skip: int = 0, limit: int = 1000
    ) -> List[CaptionSegment]:
        """
        Get segments for a caption

        Args:
            caption_id: Parent caption ID
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of caption segments ordered by time
        """
        try:
            query = (
                select(CaptionSegment)
                .where(CaptionSegment.caption_id == caption_id)
                .order_by(CaptionSegment.start_time)
                .offset(skip)
                .limit(limit)
            )

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get segments for caption {caption_id}: {e}")
            raise

    async def get_by_video_id(
        self, video_id: str, skip: int = 0, limit: int = 1000
    ) -> List[CaptionSegment]:
        """
        Get all segments for a video

        Args:
            video_id: YouTube video ID
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of caption segments
        """
        try:
            query = (
                select(CaptionSegment)
                .where(CaptionSegment.video_id == video_id)
                .order_by(CaptionSegment.start_time)
                .offset(skip)
                .limit(limit)
            )

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get segments for video {video_id}: {e}")
            raise

    async def search_segments(
        self,
        query_text: str,
        video_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Search within caption segments for precise timestamp matching

        Args:
            query_text: Text to search for
            video_id: Optional video ID filter
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of matching segments with timestamps
        """
        try:
            # Search in normalized text for better matching
            query = select(CaptionSegment).where(
                or_(
                    CaptionSegment.text.ilike(f"%{query_text}%"),
                    CaptionSegment.text_normalized.ilike(f"%{query_text}%"),
                )
            )

            if video_id:
                query = query.where(CaptionSegment.video_id == video_id)

            query = query.order_by(CaptionSegment.start_time).offset(skip).limit(limit)

            result = await self.session.execute(query)
            segments = result.scalars().all()

            return [
                {
                    "video_id": seg.video_id,
                    "caption_id": seg.caption_id,
                    "segment_id": seg.id,
                    "start_time": seg.start_time,
                    "end_time": seg.end_time,
                    "text": seg.text,
                    "timestamp_link": f"?t={int(seg.start_time)}",
                }
                for seg in segments
            ]
        except Exception as e:
            logger.error(f"Failed to search segments: {e}")
            raise

    async def get_segment_at_time(
        self, video_id: str, timestamp: float
    ) -> Optional[CaptionSegment]:
        """
        Get the caption segment at a specific timestamp

        Args:
            video_id: YouTube video ID
            timestamp: Time in seconds

        Returns:
            Caption segment at that time or None
        """
        try:
            query = (
                select(CaptionSegment)
                .where(
                    and_(
                        CaptionSegment.video_id == video_id,
                        CaptionSegment.start_time <= timestamp,
                        CaptionSegment.end_time >= timestamp,
                    )
                )
                .limit(1)
            )

            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(
                f"Failed to get segment at time {timestamp} for video {video_id}: {e}"
            )
            raise

    async def bulk_create_segments(
        self, segments: List[Dict[str, Any]]
    ) -> List[CaptionSegment]:
        """
        Bulk create caption segments

        Args:
            segments: List of segment data dicts

        Returns:
            List of created segments
        """
        try:
            return await self.bulk_create(segments)
        except Exception as e:
            logger.error(f"Failed to bulk create segments: {e}")
            raise

    async def delete_by_caption_id(self, caption_id: str) -> int:
        """Delete all segments for a caption"""
        try:
            stmt = delete(CaptionSegment).where(CaptionSegment.caption_id == caption_id)
            result = await self.session.execute(stmt)
            await self.session.commit()
            deleted_count = result.rowcount or 0
            logger.info(f"Deleted {deleted_count} segments for caption {caption_id}")
            return deleted_count
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to delete segments for caption {caption_id}: {e}")
            raise

    async def delete_by_video_id(self, video_id: str) -> int:
        """Delete all segments for a video"""
        try:
            stmt = delete(CaptionSegment).where(CaptionSegment.video_id == video_id)
            result = await self.session.execute(stmt)
            await self.session.commit()
            deleted_count = result.rowcount or 0
            logger.info(f"Deleted {deleted_count} segments for video {video_id}")
            return deleted_count
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to delete segments for video {video_id}: {e}")
            raise


__all__ = ["CaptionRepository", "CaptionSegmentRepository"]
