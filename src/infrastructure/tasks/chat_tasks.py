# src/infrastructure/tasks/chat_tasks.py
"""
Chat Background Tasks
Celery tasks for chat and conversation operations
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from src.infrastructure.tasks.celery_app import celery_app
from src.app.database import db_manager
from src.infrastructure.repositories import (
    ChatSessionRepository,
    ChatMessageRepository,
    ChatTemplateRepository,
    VideoRepository,
)
from src.services.task_tracking_service import create_task_record, update_task_status

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="tasks.chat.process_message",
    max_retries=3,
    default_retry_delay=30,
)
def process_message(
    self,
    session_id: str,
    content: str,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Process a chat message asynchronously

    Args:
        session_id: Chat session ID
        content: Message content
        user_id: User identifier

    Returns:
        Processing result with AI response
    """
    import asyncio

    async def _process():
        await create_task_record(
            task_id=self.request.id,
            task_name="process_message",
            task_type="chat",
            args=(session_id,),
            kwargs={"content_length": len(content)},
            user_id=user_id,
        )

        logger.info(f"💬 Processing message for session: {session_id}")

        try:
            from src.services.chat_service import ChatService

            async with db_manager.session() as session:
                chat_service = ChatService(
                    session_repo=ChatSessionRepository(session),
                    message_repo=ChatMessageRepository(session),
                    template_repo=ChatTemplateRepository(session),
                    video_repo=VideoRepository(session),
                )

                await update_task_status(
                    self.request.id, "running", progress=30
                )

                # Send message and get response
                result = await chat_service.send_message(
                    db=session,
                    session_id=session_id,
                    content=content,
                    stream=False,
                )

                logger.info(f"✅ Message processed for session {session_id}")

                await update_task_status(
                    self.request.id, "success", progress=100, result=result
                )

                return result

        except Exception as e:
            logger.error(f"Failed to process message for {session_id}: {e}")
            await update_task_status(
                self.request.id, "failed", error_message=str(e)
            )
            raise self.retry(exc=e)

    return asyncio.run(_process())


@celery_app.task(
    bind=True,
    name="tasks.chat.summarize_conversation",
    max_retries=2,
    default_retry_delay=60,
)
def summarize_conversation(
    self,
    session_id: str,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Summarize a conversation for context management

    Args:
        session_id: Chat session ID
        user_id: User identifier

    Returns:
        Summary result
    """
    import asyncio

    async def _summarize():
        await create_task_record(
            task_id=self.request.id,
            task_name="summarize_conversation",
            task_type="chat",
            args=(session_id,),
            user_id=user_id,
        )

        logger.info(f"📝 Summarizing conversation for session: {session_id}")

        try:
            from src.services.chat_service import ChatService

            async with db_manager.session() as session:
                chat_service = ChatService(
                    session_repo=ChatSessionRepository(session),
                    message_repo=ChatMessageRepository(session),
                    template_repo=ChatTemplateRepository(session),
                    video_repo=VideoRepository(session),
                )

                await update_task_status(
                    self.request.id, "running", progress=50
                )

                summary = await chat_service.summarize_context(
                    db=session,
                    session_id=session_id,
                )

                result = {
                    "session_id": session_id,
                    "summary": summary,
                    "summarized_at": datetime.utcnow().isoformat(),
                }

                logger.info(f"✅ Conversation summarized for session {session_id}")

                await update_task_status(
                    self.request.id, "success", progress=100, result=result
                )

                return result

        except Exception as e:
            logger.error(f"Failed to summarize conversation for {session_id}: {e}")
            await update_task_status(
                self.request.id, "failed", error_message=str(e)
            )
            raise self.retry(exc=e)

    return asyncio.run(_summarize())


@celery_app.task(
    bind=True,
    name="tasks.chat.cleanup_inactive_sessions",
    max_retries=1,
)
def cleanup_inactive_sessions(
    self,
    older_than_days: int = 30,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Clean up inactive chat sessions

    Args:
        older_than_days: Days threshold for cleanup
        user_id: User identifier

    Returns:
        Cleanup result
    """
    import asyncio

    async def _cleanup():
        await create_task_record(
            task_id=self.request.id,
            task_name="cleanup_inactive_sessions",
            task_type="chat",
            args=(),
            kwargs={"older_than_days": older_than_days},
            user_id=user_id,
        )

        logger.info(f"🧹 Cleaning up sessions older than {older_than_days} days")

        try:
            async with db_manager.session() as session:
                session_repo = ChatSessionRepository(session)

                await update_task_status(
                    self.request.id, "running", progress=30
                )

                deleted_count = await session_repo.delete_inactive_sessions(
                    older_than_days=older_than_days
                )

                result = {
                    "sessions_deleted": deleted_count,
                    "older_than_days": older_than_days,
                    "cleaned_at": datetime.utcnow().isoformat(),
                }

                logger.info(f"✅ Cleaned up {deleted_count} inactive sessions")

                await update_task_status(
                    self.request.id, "success", progress=100, result=result
                )

                return result

        except Exception as e:
            logger.error(f"Failed to cleanup inactive sessions: {e}")
            await update_task_status(
                self.request.id, "failed", error_message=str(e)
            )
            raise

    return asyncio.run(_cleanup())


@celery_app.task(
    bind=True,
    name="tasks.chat.batch_summarize",
    max_retries=1,
)
def batch_summarize_sessions(
    self,
    session_ids: List[str],
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Batch summarize multiple sessions

    Args:
        session_ids: List of session IDs
        user_id: User identifier

    Returns:
        Batch summarization results
    """
    import asyncio

    async def _batch_summarize():
        await create_task_record(
            task_id=self.request.id,
            task_name="batch_summarize_sessions",
            task_type="chat",
            args=(session_ids,),
            user_id=user_id,
        )

        logger.info(f"📝 Batch summarizing {len(session_ids)} sessions")

        results = {
            "total_sessions": len(session_ids),
            "success": [],
            "failed": [],
            "started_at": datetime.utcnow().isoformat(),
        }

        try:
            from src.services.chat_service import ChatService

            async with db_manager.session() as session:
                chat_service = ChatService(
                    session_repo=ChatSessionRepository(session),
                    message_repo=ChatMessageRepository(session),
                    template_repo=ChatTemplateRepository(session),
                    video_repo=VideoRepository(session),
                )

                for i, session_id in enumerate(session_ids):
                    progress = int((i / len(session_ids)) * 90) + 5
                    await update_task_status(
                        self.request.id, "running", progress=progress
                    )

                    try:
                        summary = await chat_service.summarize_context(
                            db=session,
                            session_id=session_id,
                        )
                        results["success"].append({
                            "session_id": session_id,
                            "summary_length": len(summary) if summary else 0,
                        })
                    except Exception as e:
                        logger.warning(
                            f"Failed to summarize session {session_id}: {e}"
                        )
                        results["failed"].append({
                            "session_id": session_id,
                            "error": str(e),
                        })

            results["completed_at"] = datetime.utcnow().isoformat()

            logger.info(
                f"✅ Batch summarization complete: "
                f"{len(results['success'])} success, "
                f"{len(results['failed'])} failed"
            )

            await update_task_status(
                self.request.id, "success", progress=100, result=results
            )

            return results

        except Exception as e:
            logger.error(f"Batch summarization failed: {e}")
            results["error"] = str(e)
            await update_task_status(
                self.request.id, "failed", error_message=str(e)
            )
            raise

    return asyncio.run(_batch_summarize())


@celery_app.task(
    bind=True,
    name="tasks.chat.export_conversation",
    max_retries=2,
    default_retry_delay=60,
)
def export_conversation(
    self,
    session_id: str,
    format: str = "json",
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Export a conversation to a file

    Args:
        session_id: Chat session ID
        format: Export format (json, txt, md)
        user_id: User identifier

    Returns:
        Export result with file path
    """
    import asyncio
    import json
    import os

    async def _export():
        await create_task_record(
            task_id=self.request.id,
            task_name="export_conversation",
            task_type="chat",
            args=(session_id,),
            kwargs={"format": format},
            user_id=user_id,
        )

        logger.info(f"📤 Exporting conversation for session: {session_id}")

        try:
            from src.services.chat_service import ChatService

            async with db_manager.session() as session:
                chat_service = ChatService(
                    session_repo=ChatSessionRepository(session),
                    message_repo=ChatMessageRepository(session),
                    template_repo=ChatTemplateRepository(session),
                    video_repo=VideoRepository(session),
                )

                await update_task_status(
                    self.request.id, "running", progress=30
                )

                # Get session with messages
                session_data = await chat_service.get_session(
                    db=session,
                    session_id=session_id,
                    include_messages=True,
                )

                if not session_data:
                    raise ValueError(f"Session {session_id} not found")

                await update_task_status(
                    self.request.id, "running", progress=60
                )

                # Create export directory
                export_dir = f"./output/chat_exports/{session_id}"
                os.makedirs(export_dir, exist_ok=True)

                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                filename = f"conversation_{timestamp}.{format}"
                file_path = os.path.join(export_dir, filename)

                if format == "json":
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(session_data, f, indent=2, ensure_ascii=False)

                elif format == "txt":
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(f"Chat Session: {session_data.get('title', 'Untitled')}\n")
                        f.write(f"Created: {session_data.get('created_at', 'Unknown')}\n")
                        f.write("=" * 50 + "\n\n")

                        for msg in session_data.get("messages", []):
                            role = msg.get("role", "unknown").upper()
                            content = msg.get("content", "")
                            f.write(f"[{role}]\n{content}\n\n")

                elif format == "md":
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(f"# {session_data.get('title', 'Chat Session')}\n\n")
                        f.write(f"**Created:** {session_data.get('created_at', 'Unknown')}\n\n")
                        f.write("---\n\n")

                        for msg in session_data.get("messages", []):
                            role = msg.get("role", "unknown")
                            content = msg.get("content", "")
                            if role == "user":
                                f.write(f"**User:** {content}\n\n")
                            elif role == "assistant":
                                f.write(f"**Assistant:** {content}\n\n")
                            elif role == "system":
                                f.write(f"*System: {content}*\n\n")

                else:
                    raise ValueError(f"Unsupported export format: {format}")

                result = {
                    "session_id": session_id,
                    "file_path": file_path,
                    "format": format,
                    "message_count": len(session_data.get("messages", [])),
                    "exported_at": datetime.utcnow().isoformat(),
                }

                logger.info(f"✅ Conversation exported to {file_path}")

                await update_task_status(
                    self.request.id, "success", progress=100, result=result
                )

                return result

        except Exception as e:
            logger.error(f"Failed to export conversation for {session_id}: {e}")
            await update_task_status(
                self.request.id, "failed", error_message=str(e)
            )
            raise self.retry(exc=e)

    return asyncio.run(_export())


@celery_app.task(
    bind=True,
    name="tasks.chat.analyze_session_sentiment",
    max_retries=2,
    default_retry_delay=60,
)
def analyze_session_sentiment(
    self,
    session_id: str,
    user_id: str = None,
) -> Dict[str, Any]:
    """
    Analyze sentiment of messages in a session

    Args:
        session_id: Chat session ID
        user_id: User identifier

    Returns:
        Sentiment analysis result
    """
    import asyncio

    async def _analyze():
        await create_task_record(
            task_id=self.request.id,
            task_name="analyze_session_sentiment",
            task_type="chat",
            args=(session_id,),
            user_id=user_id,
        )

        logger.info(f"📊 Analyzing sentiment for session: {session_id}")

        try:
            async with db_manager.session() as session:
                message_repo = ChatMessageRepository(session)

                await update_task_status(
                    self.request.id, "running", progress=30
                )

                # Get all messages
                messages = await message_repo.get_by_session_id(
                    session_id=session_id,
                    limit=500,
                )

                if not messages:
                    raise ValueError(f"No messages found for session {session_id}")

                await update_task_status(
                    self.request.id, "running", progress=50
                )

                # Simple sentiment analysis (placeholder)
                # In production, use proper NLP library
                user_messages = [m for m in messages if m.role == "user"]
                assistant_messages = [m for m in messages if m.role == "assistant"]

                # Calculate average message length as engagement proxy
                avg_user_length = (
                    sum(len(m.content) for m in user_messages) / len(user_messages)
                    if user_messages else 0
                )
                avg_assistant_length = (
                    sum(len(m.content) for m in assistant_messages) / len(assistant_messages)
                    if assistant_messages else 0
                )

                # Get average rating
                session_repo = ChatSessionRepository(session)
                ratings = [m.user_rating for m in messages if m.user_rating is not None]
                avg_rating = sum(ratings) / len(ratings) if ratings else None

                result = {
                    "session_id": session_id,
                    "total_messages": len(messages),
                    "user_messages": len(user_messages),
                    "assistant_messages": len(assistant_messages),
                    "avg_user_message_length": round(avg_user_length, 1),
                    "avg_assistant_message_length": round(avg_assistant_length, 1),
                    "average_rating": round(avg_rating, 2) if avg_rating else None,
                    "rated_messages": len(ratings),
                    "analyzed_at": datetime.utcnow().isoformat(),
                }

                logger.info(f"✅ Sentiment analysis complete for session {session_id}")

                await update_task_status(
                    self.request.id, "success", progress=100, result=result
                )

                return result

        except Exception as e:
            logger.error(f"Failed to analyze sentiment for {session_id}: {e}")
            await update_task_status(
                self.request.id, "failed", error_message=str(e)
            )
            raise self.retry(exc=e)

    return asyncio.run(_analyze())


# ============================================================================
# Exported Tasks
# ============================================================================

__all__ = [
    "process_message",
    "summarize_conversation",
    "cleanup_inactive_sessions",
    "batch_summarize_sessions",
    "export_conversation",
    "analyze_session_sentiment",
]
