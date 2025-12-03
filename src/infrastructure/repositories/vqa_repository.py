# src/infrastructure/repositories/vqa_repository.py
"""
VQA Repository
Database operations for VQA (Visual Question Answering) entities
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, delete, update
from sqlalchemy.orm import selectinload
import logging

from src.infrastructure.repositories.base import BaseRepository
from src.app.models import (
    VideoFrame,
    FrameAnalysis,
    VQASession,
    VQAQuestion,
    VideoFrameExtraction,
    FrameExtractionStatus,
)

logger = logging.getLogger(__name__)


class VideoFrameRepository(BaseRepository[VideoFrame]):
    """Repository for VideoFrame operations"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, VideoFrame)

    async def get_by_video_id(
        self,
        video_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> List[VideoFrame]:
        """Get all frames for a video"""
        try:
            query = (
                select(VideoFrame)
                .where(VideoFrame.video_id == video_id)
                .order_by(VideoFrame.timestamp)
                .offset(skip)
                .limit(limit)
            )
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get frames for video {video_id}: {e}")
            raise

    async def get_frame_at_timestamp(
        self,
        video_id: str,
        timestamp: float,
        tolerance: float = 1.0,
    ) -> Optional[VideoFrame]:
        """Get frame closest to a timestamp"""
        try:
            query = (
                select(VideoFrame)
                .where(
                    and_(
                        VideoFrame.video_id == video_id,
                        VideoFrame.timestamp >= timestamp - tolerance,
                        VideoFrame.timestamp <= timestamp + tolerance,
                    )
                )
                .order_by(func.abs(VideoFrame.timestamp - timestamp))
                .limit(1)
            )
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to get frame at timestamp {timestamp}: {e}")
            raise

    async def get_keyframes(
        self,
        video_id: str,
        limit: int = 20,
    ) -> List[VideoFrame]:
        """Get keyframes for a video"""
        try:
            query = (
                select(VideoFrame)
                .where(
                    and_(
                        VideoFrame.video_id == video_id,
                        VideoFrame.is_keyframe == True,
                    )
                )
                .order_by(VideoFrame.timestamp)
                .limit(limit)
            )
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get keyframes for video {video_id}: {e}")
            raise

    async def get_frames_in_range(
        self,
        video_id: str,
        start_time: float,
        end_time: float,
    ) -> List[VideoFrame]:
        """Get frames within a time range"""
        try:
            query = (
                select(VideoFrame)
                .where(
                    and_(
                        VideoFrame.video_id == video_id,
                        VideoFrame.timestamp >= start_time,
                        VideoFrame.timestamp <= end_time,
                    )
                )
                .order_by(VideoFrame.timestamp)
            )
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get frames in range: {e}")
            raise

    async def count_by_video(self, video_id: str) -> int:
        """Count frames for a video"""
        try:
            query = (
                select(func.count())
                .select_from(VideoFrame)
                .where(VideoFrame.video_id == video_id)
            )
            result = await self.session.execute(query)
            return int(result.scalar_one_or_none() or 0)
        except Exception as e:
            logger.error(f"Failed to count frames for video {video_id}: {e}")
            raise

    async def delete_by_video(self, video_id: str) -> int:
        """Delete all frames for a video"""
        try:
            stmt = delete(VideoFrame).where(VideoFrame.video_id == video_id)
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount or 0
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to delete frames for video {video_id}: {e}")
            raise

    async def bulk_create_frames(
        self,
        frames_data: List[Dict[str, Any]],
    ) -> List[VideoFrame]:
        """Bulk create frames"""
        try:
            return await self.bulk_create(frames_data)
        except Exception as e:
            logger.error(f"Failed to bulk create frames: {e}")
            raise


class FrameAnalysisRepository(BaseRepository[FrameAnalysis]):
    """Repository for FrameAnalysis operations"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, FrameAnalysis)

    async def get_by_frame_id(
        self,
        frame_id: int,
        model_type: Optional[str] = None,
    ) -> List[FrameAnalysis]:
        """Get analyses for a frame"""
        try:
            query = select(FrameAnalysis).where(FrameAnalysis.frame_id == frame_id)

            if model_type:
                query = query.where(FrameAnalysis.model_type == model_type)

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get analyses for frame {frame_id}: {e}")
            raise

    async def get_latest_analysis(
        self,
        frame_id: int,
        model_type: str,
    ) -> Optional[FrameAnalysis]:
        """Get the latest analysis for a frame with specific model"""
        try:
            query = (
                select(FrameAnalysis)
                .where(
                    and_(
                        FrameAnalysis.frame_id == frame_id,
                        FrameAnalysis.model_type == model_type,
                    )
                )
                .order_by(FrameAnalysis.created_at.desc())
                .limit(1)
            )
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to get latest analysis: {e}")
            raise

    async def search_by_caption(
        self,
        query_text: str,
        video_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Search analyses by caption content"""
        try:
            query = (
                select(FrameAnalysis, VideoFrame)
                .join(VideoFrame, FrameAnalysis.frame_id == VideoFrame.id)
                .where(
                    or_(
                        FrameAnalysis.caption.ilike(f"%{query_text}%"),
                        FrameAnalysis.description.ilike(f"%{query_text}%"),
                    )
                )
            )

            if video_id:
                query = query.where(VideoFrame.video_id == video_id)

            query = query.offset(skip).limit(limit)

            result = await self.session.execute(query)
            rows = result.all()

            return [
                {
                    "analysis": analysis.to_dict(),
                    "frame": frame.to_dict(),
                }
                for analysis, frame in rows
            ]
        except Exception as e:
            logger.error(f"Failed to search analyses: {e}")
            raise


class VQASessionRepository(BaseRepository[VQASession]):
    """Repository for VQASession operations"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, VQASession)

    async def get_by_video_id(
        self,
        video_id: str,
        user_id: Optional[str] = None,
        active_only: bool = False,
    ) -> List[VQASession]:
        """Get sessions for a video"""
        try:
            query = select(VQASession).where(VQASession.video_id == video_id)

            if user_id:
                query = query.where(VQASession.user_id == user_id)

            if active_only:
                query = query.where(VQASession.is_active == True)

            query = query.order_by(VQASession.last_activity_at.desc())

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get sessions for video {video_id}: {e}")
            raise

    async def get_user_sessions(
        self,
        user_id: str,
        active_only: bool = False,
        skip: int = 0,
        limit: int = 20,
    ) -> List[VQASession]:
        """Get sessions for a user"""
        try:
            query = select(VQASession).where(VQASession.user_id == user_id)

            if active_only:
                query = query.where(VQASession.is_active == True)

            query = (
                query.order_by(VQASession.last_activity_at.desc())
                .offset(skip)
                .limit(limit)
            )

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get sessions for user {user_id}: {e}")
            raise

    async def get_with_questions(
        self,
        session_id: str,
    ) -> Optional[VQASession]:
        """Get session with all questions loaded"""
        try:
            query = (
                select(VQASession)
                .where(VQASession.id == session_id)
                .options(selectinload(VQASession.questions))
            )
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to get session with questions: {e}")
            raise

    async def deactivate_session(self, session_id: str) -> bool:
        """Deactivate a session"""
        try:
            stmt = (
                update(VQASession)
                .where(VQASession.id == session_id)
                .values(is_active=False)
            )
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount > 0
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to deactivate session: {e}")
            raise

    async def cleanup_inactive_sessions(
        self,
        older_than_hours: int = 24,
    ) -> int:
        """Clean up old inactive sessions"""
        try:
            cutoff = datetime.utcnow() - timedelta(hours=older_than_hours)
            stmt = delete(VQASession).where(
                and_(
                    VQASession.is_active == False,
                    VQASession.last_activity_at < cutoff,
                )
            )
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount or 0
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to cleanup sessions: {e}")
            raise


class VQAQuestionRepository(BaseRepository[VQAQuestion]):
    """Repository for VQAQuestion operations"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, VQAQuestion)

    async def get_by_session_id(
        self,
        session_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> List[VQAQuestion]:
        """Get questions for a session"""
        try:
            query = (
                select(VQAQuestion)
                .where(VQAQuestion.session_id == session_id)
                .order_by(VQAQuestion.created_at)
                .offset(skip)
                .limit(limit)
            )
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get questions for session {session_id}: {e}")
            raise

    async def get_recent_questions(
        self,
        session_id: str,
        limit: int = 5,
    ) -> List[VQAQuestion]:
        """Get most recent questions for context"""
        try:
            query = (
                select(VQAQuestion)
                .where(VQAQuestion.session_id == session_id)
                .order_by(VQAQuestion.created_at.desc())
                .limit(limit)
            )
            result = await self.session.execute(query)
            # Reverse to get chronological order
            questions = list(result.scalars().all())
            return list(reversed(questions))
        except Exception as e:
            logger.error(f"Failed to get recent questions: {e}")
            raise

    async def update_rating(
        self,
        question_id: int,
        rating: int,
        feedback: Optional[str] = None,
    ) -> bool:
        """Update user rating for a question"""
        try:
            values = {"user_rating": rating}
            if feedback:
                values["user_feedback"] = feedback

            stmt = (
                update(VQAQuestion)
                .where(VQAQuestion.id == question_id)
                .values(**values)
            )
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount > 0
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to update rating: {e}")
            raise

    async def get_questions_by_video(
        self,
        video_id: str,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get all questions for a video across all sessions"""
        try:
            query = (
                select(VQAQuestion, VQASession)
                .join(VQASession, VQAQuestion.session_id == VQASession.id)
                .where(VQASession.video_id == video_id)
                .order_by(VQAQuestion.created_at.desc())
                .offset(skip)
                .limit(limit)
            )
            result = await self.session.execute(query)
            rows = result.all()

            return [
                {
                    "question": q.to_dict(),
                    "session_id": s.id,
                    "user_id": s.user_id,
                }
                for q, s in rows
            ]
        except Exception as e:
            logger.error(f"Failed to get questions by video: {e}")
            raise


class VideoFrameExtractionRepository(BaseRepository[VideoFrameExtraction]):
    """Repository for VideoFrameExtraction operations"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, VideoFrameExtraction)

    async def get_by_video_id(
        self,
        video_id: str,
    ) -> Optional[VideoFrameExtraction]:
        """Get extraction job for a video"""
        try:
            query = select(VideoFrameExtraction).where(
                VideoFrameExtraction.video_id == video_id
            )
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to get extraction for video {video_id}: {e}")
            raise

    async def get_pending_extractions(
        self,
        limit: int = 10,
    ) -> List[VideoFrameExtraction]:
        """Get pending extraction jobs"""
        try:
            query = (
                select(VideoFrameExtraction)
                .where(
                    VideoFrameExtraction.status == FrameExtractionStatus.PENDING.value
                )
                .order_by(VideoFrameExtraction.created_at)
                .limit(limit)
            )
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get pending extractions: {e}")
            raise

    async def update_status(
        self,
        video_id: str,
        status: str,
        progress: int = 0,
        error_message: Optional[str] = None,
        frames_extracted: Optional[int] = None,
    ) -> bool:
        """Update extraction status"""
        try:
            values = {
                "status": status,
                "progress": progress,
            }

            if error_message:
                values["error_message"] = error_message

            if frames_extracted is not None:
                values["frames_extracted"] = frames_extracted

            if status == FrameExtractionStatus.EXTRACTING.value:
                values["started_at"] = datetime.utcnow()
            elif status in [
                FrameExtractionStatus.COMPLETED.value,
                FrameExtractionStatus.FAILED.value,
            ]:
                values["completed_at"] = datetime.utcnow()

            stmt = (
                update(VideoFrameExtraction)
                .where(VideoFrameExtraction.video_id == video_id)
                .values(**values)
            )
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount > 0
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to update extraction status: {e}")
            raise

    async def create_or_reset(
        self,
        video_id: str,
        extraction_method: str = "keyframe",
        max_frames: int = 100,
        interval_seconds: Optional[float] = None,
    ) -> VideoFrameExtraction:
        """Create or reset extraction job"""
        try:
            existing = await self.get_by_video_id(video_id)

            if existing:
                # Reset existing
                stmt = (
                    update(VideoFrameExtraction)
                    .where(VideoFrameExtraction.video_id == video_id)
                    .values(
                        extraction_method=extraction_method,
                        max_frames=max_frames,
                        interval_seconds=interval_seconds,
                        status=FrameExtractionStatus.PENDING.value,
                        progress=0,
                        frames_extracted=0,
                        error_message=None,
                        retry_count=0,
                        started_at=None,
                        completed_at=None,
                    )
                )
                await self.session.execute(stmt)
                await self.session.commit()
                return await self.get_by_video_id(video_id)
            else:
                # Create new
                return await self.create(
                    video_id=video_id,
                    extraction_method=extraction_method,
                    max_frames=max_frames,
                    interval_seconds=interval_seconds,
                )
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to create/reset extraction: {e}")
            raise


__all__ = [
    "VideoFrameRepository",
    "FrameAnalysisRepository",
    "VQASessionRepository",
    "VQAQuestionRepository",
    "VideoFrameExtractionRepository",
]
