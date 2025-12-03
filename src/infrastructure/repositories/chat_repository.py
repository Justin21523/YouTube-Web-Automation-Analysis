# src/infrastructure/repositories/chat_repository.py
"""
Chat Repository
Database operations for chat session, message, and template entities
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, delete, update
from sqlalchemy.orm import selectinload
import logging

from src.infrastructure.repositories.base import BaseRepository
from src.app.models import ChatSession, ChatMessage, ChatTemplate

logger = logging.getLogger(__name__)


class ChatSessionRepository(BaseRepository[ChatSession]):
    """Repository for ChatSession operations"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, ChatSession)

    async def get_by_user_id(
        self,
        user_id: str,
        include_inactive: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> List[ChatSession]:
        """
        Get chat sessions for a user

        Args:
            user_id: User identifier
            include_inactive: Include inactive sessions
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of chat sessions
        """
        try:
            query = select(ChatSession).where(ChatSession.user_id == user_id)

            if not include_inactive:
                query = query.where(ChatSession.is_active == True)

            query = query.order_by(ChatSession.last_activity_at.desc())
            query = query.offset(skip).limit(limit)

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get sessions for user {user_id}: {e}")
            raise

    async def get_by_video_id(
        self,
        video_id: str,
        user_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[ChatSession]:
        """
        Get chat sessions for a video

        Args:
            video_id: YouTube video ID
            user_id: Optional user filter
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of chat sessions
        """
        try:
            query = select(ChatSession).where(ChatSession.video_id == video_id)

            if user_id:
                query = query.where(ChatSession.user_id == user_id)

            query = query.order_by(ChatSession.last_activity_at.desc())
            query = query.offset(skip).limit(limit)

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get sessions for video {video_id}: {e}")
            raise

    async def get_with_messages(
        self, session_id: str, message_limit: int = 100
    ) -> Optional[ChatSession]:
        """
        Get session with its messages

        Args:
            session_id: Session ID
            message_limit: Maximum messages to load

        Returns:
            ChatSession with messages or None
        """
        try:
            query = (
                select(ChatSession)
                .options(selectinload(ChatSession.messages))
                .where(ChatSession.id == session_id)
            )

            result = await self.session.execute(query)
            chat_session = result.scalar_one_or_none()

            if chat_session and len(chat_session.messages) > message_limit:
                # Trim to last N messages
                chat_session.messages = chat_session.messages[-message_limit:]

            return chat_session
        except Exception as e:
            logger.error(f"Failed to get session with messages {session_id}: {e}")
            raise

    async def get_active_sessions(
        self,
        since_hours: int = 24,
        skip: int = 0,
        limit: int = 100,
    ) -> List[ChatSession]:
        """
        Get recently active sessions

        Args:
            since_hours: Hours to look back
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of active sessions
        """
        try:
            cutoff = datetime.utcnow() - timedelta(hours=since_hours)
            query = (
                select(ChatSession)
                .where(
                    and_(
                        ChatSession.is_active == True,
                        ChatSession.last_activity_at >= cutoff,
                    )
                )
                .order_by(ChatSession.last_activity_at.desc())
                .offset(skip)
                .limit(limit)
            )

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get active sessions: {e}")
            raise

    async def update_activity(self, session_id: str) -> bool:
        """
        Update last activity timestamp

        Args:
            session_id: Session ID

        Returns:
            True if updated
        """
        try:
            stmt = (
                update(ChatSession)
                .where(ChatSession.id == session_id)
                .values(last_activity_at=datetime.utcnow())
            )
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount > 0
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to update activity for session {session_id}: {e}")
            raise

    async def increment_message_count(self, session_id: str) -> bool:
        """
        Increment message count for a session

        Args:
            session_id: Session ID

        Returns:
            True if updated
        """
        try:
            stmt = (
                update(ChatSession)
                .where(ChatSession.id == session_id)
                .values(
                    message_count=ChatSession.message_count + 1,
                    last_activity_at=datetime.utcnow(),
                )
            )
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount > 0
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to increment message count for {session_id}: {e}")
            raise

    async def deactivate_session(self, session_id: str) -> bool:
        """
        Deactivate a chat session

        Args:
            session_id: Session ID

        Returns:
            True if deactivated
        """
        try:
            stmt = (
                update(ChatSession)
                .where(ChatSession.id == session_id)
                .values(is_active=False)
            )
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount > 0
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to deactivate session {session_id}: {e}")
            raise

    async def update_context_summary(
        self, session_id: str, summary: str
    ) -> bool:
        """
        Update conversation context summary

        Args:
            session_id: Session ID
            summary: New context summary

        Returns:
            True if updated
        """
        try:
            stmt = (
                update(ChatSession)
                .where(ChatSession.id == session_id)
                .values(context_summary=summary)
            )
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount > 0
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to update context for session {session_id}: {e}")
            raise

    async def count_by_user(self, user_id: str) -> int:
        """Count sessions for a user"""
        try:
            query = (
                select(func.count())
                .select_from(ChatSession)
                .where(ChatSession.user_id == user_id)
            )
            result = await self.session.execute(query)
            return int(result.scalar_one_or_none() or 0)
        except Exception as e:
            logger.error(f"Failed to count sessions for user {user_id}: {e}")
            raise

    async def delete_inactive_sessions(self, older_than_days: int = 30) -> int:
        """
        Delete inactive sessions older than specified days

        Args:
            older_than_days: Days threshold

        Returns:
            Number of deleted sessions
        """
        try:
            cutoff = datetime.utcnow() - timedelta(days=older_than_days)
            stmt = delete(ChatSession).where(
                and_(
                    ChatSession.is_active == False,
                    ChatSession.last_activity_at < cutoff,
                )
            )
            result = await self.session.execute(stmt)
            await self.session.commit()
            deleted_count = result.rowcount or 0
            logger.info(f"Deleted {deleted_count} inactive sessions")
            return deleted_count
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to delete inactive sessions: {e}")
            raise


class ChatMessageRepository(BaseRepository[ChatMessage]):
    """Repository for ChatMessage operations"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, ChatMessage)

    async def get_by_session_id(
        self,
        session_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> List[ChatMessage]:
        """
        Get messages for a session

        Args:
            session_id: Parent session ID
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of messages ordered by creation time
        """
        try:
            query = (
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at)
                .offset(skip)
                .limit(limit)
            )

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get messages for session {session_id}: {e}")
            raise

    async def get_recent_messages(
        self,
        session_id: str,
        limit: int = 10,
    ) -> List[ChatMessage]:
        """
        Get most recent messages for context

        Args:
            session_id: Session ID
            limit: Number of recent messages

        Returns:
            List of recent messages
        """
        try:
            query = (
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.desc())
                .limit(limit)
            )

            result = await self.session.execute(query)
            messages = list(result.scalars().all())
            # Return in chronological order
            return list(reversed(messages))
        except Exception as e:
            logger.error(f"Failed to get recent messages for session {session_id}: {e}")
            raise

    async def get_by_role(
        self,
        session_id: str,
        role: str,
        skip: int = 0,
        limit: int = 50,
    ) -> List[ChatMessage]:
        """
        Get messages by role

        Args:
            session_id: Session ID
            role: Message role (user/assistant/system)
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of messages with specified role
        """
        try:
            query = (
                select(ChatMessage)
                .where(
                    and_(
                        ChatMessage.session_id == session_id,
                        ChatMessage.role == role,
                    )
                )
                .order_by(ChatMessage.created_at)
                .offset(skip)
                .limit(limit)
            )

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get messages by role for session {session_id}: {e}")
            raise

    async def search_messages(
        self,
        query_text: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Search message content

        Args:
            query_text: Text to search for
            session_id: Optional session filter
            user_id: Optional user filter (requires join with sessions)
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of matching messages
        """
        try:
            query = select(ChatMessage).where(
                ChatMessage.content.ilike(f"%{query_text}%")
            )

            if session_id:
                query = query.where(ChatMessage.session_id == session_id)

            query = query.order_by(ChatMessage.created_at.desc())
            query = query.offset(skip).limit(limit)

            result = await self.session.execute(query)
            messages = result.scalars().all()

            return [
                {
                    "message_id": msg.id,
                    "session_id": msg.session_id,
                    "role": msg.role,
                    "content_preview": msg.content[:200] + "..." if len(msg.content) > 200 else msg.content,
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                }
                for msg in messages
            ]
        except Exception as e:
            logger.error(f"Failed to search messages: {e}")
            raise

    async def count_by_session(self, session_id: str) -> int:
        """Count messages in a session"""
        try:
            query = (
                select(func.count())
                .select_from(ChatMessage)
                .where(ChatMessage.session_id == session_id)
            )
            result = await self.session.execute(query)
            return int(result.scalar_one_or_none() or 0)
        except Exception as e:
            logger.error(f"Failed to count messages for session {session_id}: {e}")
            raise

    async def get_total_tokens(self, session_id: str) -> int:
        """Get total token count for a session"""
        try:
            query = (
                select(func.sum(ChatMessage.token_count))
                .where(ChatMessage.session_id == session_id)
            )
            result = await self.session.execute(query)
            return int(result.scalar_one_or_none() or 0)
        except Exception as e:
            logger.error(f"Failed to get token count for session {session_id}: {e}")
            raise

    async def update_rating(
        self,
        message_id: int,
        rating: int,
        is_helpful: Optional[bool] = None,
    ) -> bool:
        """
        Update user rating for a message

        Args:
            message_id: Message ID
            rating: Rating value (1-5)
            is_helpful: Optional helpful flag

        Returns:
            True if updated
        """
        try:
            values = {"user_rating": rating}
            if is_helpful is not None:
                values["is_helpful"] = is_helpful

            stmt = (
                update(ChatMessage)
                .where(ChatMessage.id == message_id)
                .values(**values)
            )
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount > 0
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to update rating for message {message_id}: {e}")
            raise

    async def delete_by_session(self, session_id: str) -> int:
        """Delete all messages for a session"""
        try:
            stmt = delete(ChatMessage).where(ChatMessage.session_id == session_id)
            result = await self.session.execute(stmt)
            await self.session.commit()
            deleted_count = result.rowcount or 0
            logger.info(f"Deleted {deleted_count} messages for session {session_id}")
            return deleted_count
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to delete messages for session {session_id}: {e}")
            raise

    async def get_average_rating(self, session_id: str) -> Optional[float]:
        """Get average rating for assistant messages in a session"""
        try:
            query = (
                select(func.avg(ChatMessage.user_rating))
                .where(
                    and_(
                        ChatMessage.session_id == session_id,
                        ChatMessage.user_rating.isnot(None),
                    )
                )
            )
            result = await self.session.execute(query)
            avg = result.scalar_one_or_none()
            return float(avg) if avg else None
        except Exception as e:
            logger.error(f"Failed to get average rating for session {session_id}: {e}")
            raise


class ChatTemplateRepository(BaseRepository[ChatTemplate]):
    """Repository for ChatTemplate operations"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, ChatTemplate)

    async def get_by_name(self, name: str) -> Optional[ChatTemplate]:
        """
        Get template by name

        Args:
            name: Template name

        Returns:
            ChatTemplate or None
        """
        try:
            query = select(ChatTemplate).where(ChatTemplate.name == name)
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to get template by name {name}: {e}")
            raise

    async def get_by_category(
        self,
        category: str,
        active_only: bool = True,
        skip: int = 0,
        limit: int = 50,
    ) -> List[ChatTemplate]:
        """
        Get templates by category

        Args:
            category: Template category
            active_only: Only return active templates
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of templates
        """
        try:
            query = select(ChatTemplate).where(ChatTemplate.category == category)

            if active_only:
                query = query.where(ChatTemplate.is_active == True)

            query = query.order_by(ChatTemplate.usage_count.desc())
            query = query.offset(skip).limit(limit)

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get templates by category {category}: {e}")
            raise

    async def get_active_templates(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> List[ChatTemplate]:
        """
        Get all active templates

        Args:
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of active templates
        """
        try:
            query = (
                select(ChatTemplate)
                .where(ChatTemplate.is_active == True)
                .order_by(ChatTemplate.usage_count.desc())
                .offset(skip)
                .limit(limit)
            )

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get active templates: {e}")
            raise

    async def get_popular_templates(
        self,
        limit: int = 10,
    ) -> List[ChatTemplate]:
        """
        Get most used templates

        Args:
            limit: Maximum results

        Returns:
            List of popular templates
        """
        try:
            query = (
                select(ChatTemplate)
                .where(ChatTemplate.is_active == True)
                .order_by(ChatTemplate.usage_count.desc())
                .limit(limit)
            )

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get popular templates: {e}")
            raise

    async def increment_usage(self, template_id: int) -> bool:
        """
        Increment usage count for a template

        Args:
            template_id: Template ID

        Returns:
            True if updated
        """
        try:
            stmt = (
                update(ChatTemplate)
                .where(ChatTemplate.id == template_id)
                .values(usage_count=ChatTemplate.usage_count + 1)
            )
            result = await self.session.execute(stmt)
            await self.session.commit()
            return result.rowcount > 0
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to increment usage for template {template_id}: {e}")
            raise

    async def search_templates(
        self,
        query_text: str,
        category: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> List[ChatTemplate]:
        """
        Search templates by name or description

        Args:
            query_text: Search text
            category: Optional category filter
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of matching templates
        """
        try:
            query = select(ChatTemplate).where(
                or_(
                    ChatTemplate.name.ilike(f"%{query_text}%"),
                    ChatTemplate.description.ilike(f"%{query_text}%"),
                )
            )

            if category:
                query = query.where(ChatTemplate.category == category)

            query = query.where(ChatTemplate.is_active == True)
            query = query.order_by(ChatTemplate.usage_count.desc())
            query = query.offset(skip).limit(limit)

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to search templates: {e}")
            raise

    async def get_categories(self) -> List[str]:
        """Get list of all template categories"""
        try:
            query = (
                select(ChatTemplate.category)
                .where(ChatTemplate.is_active == True)
                .distinct()
                .order_by(ChatTemplate.category)
            )

            result = await self.session.execute(query)
            return [row[0] for row in result.all() if row[0]]
        except Exception as e:
            logger.error(f"Failed to get template categories: {e}")
            raise


__all__ = [
    "ChatSessionRepository",
    "ChatMessageRepository",
    "ChatTemplateRepository",
]
