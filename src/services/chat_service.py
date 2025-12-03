# src/services/chat_service.py
"""
Chat Service
Business logic for conversational AI operations
"""

from typing import Optional, List, Dict, Any, AsyncIterator
from datetime import datetime
import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.base_service import BaseService
from src.services.exceptions import (
    ResourceNotFoundError,
    ValidationError,
    ExternalServiceError,
    ProcessingError,
)
from src.services.llm_client import (
    get_llm_client,
    Message,
    BaseLLMClient,
)

from src.infrastructure.repositories.chat_repository import (
    ChatSessionRepository,
    ChatMessageRepository,
    ChatTemplateRepository,
)
from src.infrastructure.repositories.video_repository import VideoRepository
from src.app.models import (
    ChatSession,
    ChatMessage,
    ChatTemplate,
    ChatRole,
    ChatModelType,
)

logger = logging.getLogger(__name__)


class ChatService(BaseService):
    """
    Chat operations service

    Handles:
    - Chat session management
    - Message handling
    - LLM integration
    - Context management
    - Template management
    """

    def __init__(
        self,
        session_repo: ChatSessionRepository,
        message_repo: ChatMessageRepository,
        template_repo: ChatTemplateRepository,
        video_repo: VideoRepository,
        cache=None,
        config=None,
    ):
        super().__init__(cache=cache, config=config)
        self.session_repo = session_repo
        self.message_repo = message_repo
        self.template_repo = template_repo
        self.video_repo = video_repo

        # LLM client (lazy loaded)
        self._llm_client = None
        self._model_type = None

    def get_service_name(self) -> str:
        return "chat"

    # ========================================================================
    # Session Management
    # ========================================================================

    async def create_session(
        self,
        db: AsyncSession,
        user_id: str,
        video_id: Optional[str] = None,
        title: Optional[str] = None,
        model_type: str = ChatModelType.GPT35.value,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        template_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Create a new chat session

        Args:
            db: Database session
            user_id: User identifier
            video_id: Optional video ID for video-specific chat
            title: Session title
            model_type: LLM model type
            system_prompt: Custom system prompt
            temperature: Model temperature
            max_tokens: Max tokens per response
            template_id: Optional template to use

        Returns:
            Created session details
        """
        self.log_operation("create_session", user_id=user_id, video_id=video_id)

        try:
            # Generate session ID
            session_id = str(uuid.uuid4())

            # Load template if specified
            if template_id:
                template = await self.template_repo.get_by_id(template_id)
                if template:
                    if not system_prompt:
                        system_prompt = template.system_prompt
                    if not title:
                        title = f"Chat using {template.name}"
                    # Increment template usage
                    await self.template_repo.increment_usage(template_id)

            # Get video context if video_id provided
            video_context = None
            if video_id:
                video = await self.video_repo.get_by_id(video_id)
                if video:
                    video_context = {
                        "video_id": video.id,
                        "title": video.title,
                        "channel": video.channel_title,
                        "description": video.description[:500] if video.description else None,
                        "duration": video.duration,
                    }
                    if not title:
                        title = f"Chat about: {video.title[:50]}"

            # Set default title
            if not title:
                title = f"Chat Session {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"

            # Set default system prompt
            if not system_prompt:
                system_prompt = self._get_default_system_prompt(video_context)

            # Create session
            session = await self.session_repo.create(
                id=session_id,
                user_id=user_id,
                video_id=video_id,
                title=title,
                model_type=model_type,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                video_context=video_context,
                is_active=True,
                message_count=0,
            )

            # Add system message if prompt exists
            if system_prompt:
                await self.message_repo.create(
                    session_id=session_id,
                    role=ChatRole.SYSTEM.value,
                    content=system_prompt,
                )
                await self.session_repo.increment_message_count(session_id)

            logger.info(f"Created chat session {session_id} for user {user_id}")

            return {
                "session_id": session.id,
                "user_id": session.user_id,
                "video_id": session.video_id,
                "title": session.title,
                "model_type": session.model_type,
                "created_at": session.created_at.isoformat() if session.created_at else None,
            }

        except Exception as e:
            logger.error(f"Failed to create chat session: {e}")
            raise ProcessingError(f"Failed to create chat session: {e}")

    async def get_session(
        self,
        db: AsyncSession,
        session_id: str,
        include_messages: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Get chat session details

        Args:
            db: Database session
            session_id: Session ID
            include_messages: Include message history

        Returns:
            Session details or None
        """
        try:
            if include_messages:
                session = await self.session_repo.get_with_messages(session_id)
            else:
                session = await self.session_repo.get_by_id(session_id)

            if not session:
                return None

            result = session.to_dict()

            if include_messages and hasattr(session, 'messages'):
                result["messages"] = [
                    {
                        "id": msg.id,
                        "role": msg.role,
                        "content": msg.content,
                        "created_at": msg.created_at.isoformat() if msg.created_at else None,
                    }
                    for msg in session.messages
                ]

            return result

        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {e}")
            raise

    async def get_user_sessions(
        self,
        db: AsyncSession,
        user_id: str,
        include_inactive: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get chat sessions for a user

        Args:
            db: Database session
            user_id: User identifier
            include_inactive: Include inactive sessions
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of session summaries
        """
        try:
            sessions = await self.session_repo.get_by_user_id(
                user_id=user_id,
                include_inactive=include_inactive,
                skip=skip,
                limit=limit,
            )

            return [session.to_dict() for session in sessions]

        except Exception as e:
            logger.error(f"Failed to get sessions for user {user_id}: {e}")
            raise

    async def end_session(
        self,
        db: AsyncSession,
        session_id: str,
    ) -> bool:
        """
        End/deactivate a chat session

        Args:
            db: Database session
            session_id: Session ID

        Returns:
            True if session was deactivated
        """
        try:
            result = await self.session_repo.deactivate_session(session_id)
            if result:
                logger.info(f"Deactivated session {session_id}")
            return result

        except Exception as e:
            logger.error(f"Failed to end session {session_id}: {e}")
            raise

    async def delete_session(
        self,
        db: AsyncSession,
        session_id: str,
    ) -> bool:
        """
        Delete a chat session and all messages

        Args:
            db: Database session
            session_id: Session ID

        Returns:
            True if deleted
        """
        try:
            # Messages will cascade delete due to relationship
            session = await self.session_repo.delete(session_id)
            if session:
                logger.info(f"Deleted session {session_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            raise

    # ========================================================================
    # Message Handling
    # ========================================================================

    async def send_message(
        self,
        db: AsyncSession,
        session_id: str,
        content: str,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """
        Send a message and get AI response

        Args:
            db: Database session
            session_id: Session ID
            content: User message content
            stream: Enable streaming response

        Returns:
            AI response details
        """
        self.log_operation("send_message", session_id=session_id)

        try:
            # Get session
            session = await self.session_repo.get_with_messages(session_id)
            if not session:
                raise ResourceNotFoundError(f"Session {session_id} not found")

            if not session.is_active:
                raise ValidationError("Cannot send message to inactive session")

            # Validate content
            if not content or not content.strip():
                raise ValidationError("Message content cannot be empty")

            start_time = datetime.utcnow()

            # Save user message
            user_msg = await self.message_repo.create(
                session_id=session_id,
                role=ChatRole.USER.value,
                content=content.strip(),
                token_count=self._estimate_tokens(content),
            )
            await self.session_repo.increment_message_count(session_id)

            # Build conversation context
            messages = self._build_context(session, content)

            # Get AI response
            ai_response = await self._get_llm_response(
                messages=messages,
                model_type=session.model_type,
                temperature=session.temperature,
                max_tokens=session.max_tokens,
            )

            processing_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Save assistant message
            assistant_msg = await self.message_repo.create(
                session_id=session_id,
                role=ChatRole.ASSISTANT.value,
                content=ai_response["content"],
                token_count=ai_response.get("tokens", 0),
                model_used=ai_response.get("model", session.model_type),
                finish_reason=ai_response.get("finish_reason"),
                processing_time_ms=processing_time,
            )
            await self.session_repo.increment_message_count(session_id)

            # Update activity
            await self.session_repo.update_activity(session_id)

            logger.info(
                f"Processed message for session {session_id} in {processing_time}ms"
            )

            return {
                "user_message": {
                    "id": user_msg.id,
                    "content": user_msg.content,
                    "created_at": user_msg.created_at.isoformat(),
                },
                "assistant_message": {
                    "id": assistant_msg.id,
                    "content": assistant_msg.content,
                    "model": assistant_msg.model_used,
                    "processing_time_ms": processing_time,
                    "created_at": assistant_msg.created_at.isoformat(),
                },
            }

        except (ResourceNotFoundError, ValidationError):
            raise
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            raise ProcessingError(f"Failed to process message: {e}")

    async def get_messages(
        self,
        db: AsyncSession,
        session_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get messages for a session

        Args:
            db: Database session
            session_id: Session ID
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of messages
        """
        try:
            messages = await self.message_repo.get_by_session_id(
                session_id=session_id,
                skip=skip,
                limit=limit,
            )

            return [msg.to_dict() for msg in messages]

        except Exception as e:
            logger.error(f"Failed to get messages for session {session_id}: {e}")
            raise

    async def rate_message(
        self,
        db: AsyncSession,
        message_id: int,
        rating: int,
        is_helpful: Optional[bool] = None,
    ) -> bool:
        """
        Rate an assistant message

        Args:
            db: Database session
            message_id: Message ID
            rating: Rating value (1-5)
            is_helpful: Optional helpful flag

        Returns:
            True if updated
        """
        try:
            if rating < 1 or rating > 5:
                raise ValidationError("Rating must be between 1 and 5")

            result = await self.message_repo.update_rating(
                message_id=message_id,
                rating=rating,
                is_helpful=is_helpful,
            )

            if result:
                logger.info(f"Rated message {message_id}: {rating}")

            return result

        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Failed to rate message {message_id}: {e}")
            raise

    # ========================================================================
    # Template Management
    # ========================================================================

    async def get_templates(
        self,
        db: AsyncSession,
        category: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get available chat templates

        Args:
            db: Database session
            category: Optional category filter
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of templates
        """
        try:
            if category:
                templates = await self.template_repo.get_by_category(
                    category=category,
                    skip=skip,
                    limit=limit,
                )
            else:
                templates = await self.template_repo.get_active_templates(
                    skip=skip,
                    limit=limit,
                )

            return [template.to_dict() for template in templates]

        except Exception as e:
            logger.error(f"Failed to get templates: {e}")
            raise

    async def create_template(
        self,
        db: AsyncSession,
        name: str,
        system_prompt: str,
        description: Optional[str] = None,
        category: Optional[str] = None,
        example_queries: Optional[List[str]] = None,
        default_temperature: float = 0.7,
        default_max_tokens: int = 2000,
        recommended_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new chat template

        Args:
            db: Database session
            name: Template name
            system_prompt: System prompt template
            description: Template description
            category: Template category
            example_queries: Example user queries
            default_temperature: Default temperature
            default_max_tokens: Default max tokens
            recommended_model: Recommended model type

        Returns:
            Created template details
        """
        try:
            # Check if name exists
            existing = await self.template_repo.get_by_name(name)
            if existing:
                raise ValidationError(f"Template with name '{name}' already exists")

            template = await self.template_repo.create(
                name=name,
                system_prompt=system_prompt,
                description=description,
                category=category,
                example_queries=example_queries,
                default_temperature=default_temperature,
                default_max_tokens=default_max_tokens,
                recommended_model=recommended_model,
                is_active=True,
                usage_count=0,
            )

            logger.info(f"Created template: {name}")

            return template.to_dict()

        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Failed to create template: {e}")
            raise ProcessingError(f"Failed to create template: {e}")

    async def get_template_categories(
        self,
        db: AsyncSession,
    ) -> List[str]:
        """Get available template categories"""
        try:
            return await self.template_repo.get_categories()
        except Exception as e:
            logger.error(f"Failed to get template categories: {e}")
            raise

    # ========================================================================
    # Context Management
    # ========================================================================

    async def summarize_context(
        self,
        db: AsyncSession,
        session_id: str,
    ) -> str:
        """
        Generate a summary of the conversation context

        Args:
            db: Database session
            session_id: Session ID

        Returns:
            Context summary
        """
        try:
            session = await self.session_repo.get_with_messages(session_id)
            if not session:
                raise ResourceNotFoundError(f"Session {session_id} not found")

            if len(session.messages) < 4:
                return ""  # Not enough messages to summarize

            # Build conversation text
            conversation = "\n".join([
                f"{msg.role}: {msg.content[:500]}"
                for msg in session.messages[:-2]  # Exclude last 2 messages
            ])

            # Generate summary using LLM
            summary_prompt = f"""Summarize the key points of this conversation in 2-3 sentences:

{conversation}

Summary:"""

            response = await self._get_llm_response(
                messages=[{"role": "user", "content": summary_prompt}],
                model_type=session.model_type,
                temperature=0.3,
                max_tokens=200,
            )

            summary = response["content"]

            # Save summary
            await self.session_repo.update_context_summary(session_id, summary)

            logger.info(f"Generated context summary for session {session_id}")

            return summary

        except ResourceNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to summarize context: {e}")
            raise

    # ========================================================================
    # Statistics
    # ========================================================================

    async def get_session_stats(
        self,
        db: AsyncSession,
        session_id: str,
    ) -> Dict[str, Any]:
        """
        Get statistics for a session

        Args:
            db: Database session
            session_id: Session ID

        Returns:
            Session statistics
        """
        try:
            session = await self.session_repo.get_by_id(session_id)
            if not session:
                raise ResourceNotFoundError(f"Session {session_id} not found")

            message_count = await self.message_repo.count_by_session(session_id)
            total_tokens = await self.message_repo.get_total_tokens(session_id)
            avg_rating = await self.message_repo.get_average_rating(session_id)

            return {
                "session_id": session_id,
                "message_count": message_count,
                "total_tokens": total_tokens,
                "average_rating": avg_rating,
                "model_type": session.model_type,
                "is_active": session.is_active,
                "created_at": session.created_at.isoformat() if session.created_at else None,
                "last_activity": session.last_activity_at.isoformat() if session.last_activity_at else None,
            }

        except ResourceNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to get session stats: {e}")
            raise

    async def get_user_stats(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> Dict[str, Any]:
        """
        Get chat statistics for a user

        Args:
            db: Database session
            user_id: User identifier

        Returns:
            User chat statistics
        """
        try:
            session_count = await self.session_repo.count_by_user(user_id)
            sessions = await self.session_repo.get_by_user_id(
                user_id=user_id,
                include_inactive=True,
                limit=100,
            )

            total_messages = 0
            for session in sessions:
                total_messages += session.message_count or 0

            return {
                "user_id": user_id,
                "total_sessions": session_count,
                "total_messages": total_messages,
                "active_sessions": sum(1 for s in sessions if s.is_active),
            }

        except Exception as e:
            logger.error(f"Failed to get user stats: {e}")
            raise

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    def _get_default_system_prompt(
        self,
        video_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate default system prompt"""
        base_prompt = """You are a helpful AI assistant specialized in analyzing and discussing YouTube videos.
You provide accurate, insightful, and engaging responses about video content, trends, and analytics."""

        if video_context:
            return f"""{base_prompt}

You are currently helping with a video titled: "{video_context.get('title', 'Unknown')}"
Channel: {video_context.get('channel', 'Unknown')}

Use this context to provide relevant and specific responses about the video."""

        return base_prompt

    def _build_context(
        self,
        session: ChatSession,
        current_message: str,
    ) -> List[Dict[str, str]]:
        """Build conversation context for LLM"""
        messages = []

        # Add system message
        if session.system_prompt:
            messages.append({
                "role": "system",
                "content": session.system_prompt,
            })

        # Add context summary if available
        if session.context_summary:
            messages.append({
                "role": "system",
                "content": f"Previous conversation summary: {session.context_summary}",
            })

        # Add recent messages (last 10 for context window management)
        if hasattr(session, 'messages') and session.messages:
            recent_messages = session.messages[-10:]
            for msg in recent_messages:
                if msg.role != ChatRole.SYSTEM.value:
                    messages.append({
                        "role": msg.role,
                        "content": msg.content,
                    })

        # Add current message
        messages.append({
            "role": "user",
            "content": current_message,
        })

        return messages

    def _get_llm_provider(self, model_type: str) -> tuple[str, str]:
        """
        Determine LLM provider and model from model_type string

        Returns:
            (provider, model) tuple
        """
        model_type_lower = model_type.lower()

        # OpenAI models
        if any(x in model_type_lower for x in ["gpt-4", "gpt-3.5", "gpt4", "gpt35"]):
            if "gpt-4" in model_type_lower or "gpt4" in model_type_lower:
                return ("openai", "gpt-4o-mini")
            return ("openai", "gpt-3.5-turbo")

        # LLMVendor models
        if any(x in model_type_lower for x in ["llm_provider", "llm_vendor"]):
            if "opus" in model_type_lower:
                return ("llm_vendor", "llm_provider-3-opus-20240229")
            if "sonnet" in model_type_lower:
                return ("llm_vendor", "llm_provider-3-sonnet-20240229")
            return ("llm_vendor", "llm_provider-3-haiku-20240307")

        # Ollama/local models
        if any(x in model_type_lower for x in ["llama", "mistral", "ollama", "local"]):
            if "llama" in model_type_lower:
                return ("ollama", "llama3.2")
            if "mistral" in model_type_lower:
                return ("ollama", "mistral")
            return ("ollama", "llama3.2")

        # Default to auto-detection
        return (None, None)

    async def _get_llm_response(
        self,
        messages: List[Dict[str, str]],
        model_type: str,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> Dict[str, Any]:
        """
        Get response from LLM using the unified LLM client

        Supports OpenAI, LLMVendor LLMProvider, and Ollama (local models)
        """
        try:
            # Determine provider and model
            provider, model = self._get_llm_provider(model_type)

            # Get LLM client
            if provider:
                llm_client = get_llm_client(provider=provider, model=model)
            else:
                # Auto-detect based on available API keys
                llm_client = get_llm_client()

            # Convert messages to Message objects
            llm_messages = [
                Message(role=msg["role"], content=msg["content"])
                for msg in messages
            ]

            # Get response
            response = await llm_client.chat(
                messages=llm_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            return {
                "content": response.content,
                "tokens": response.usage.get("completion_tokens", self._estimate_tokens(response.content)),
                "model": response.model,
                "finish_reason": response.finish_reason or "stop",
            }

        except Exception as e:
            logger.error(f"LLM request failed: {e}")
            raise ExternalServiceError(f"LLM service error: {e}")

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text (rough approximation)"""
        # Roughly 4 characters per token for English
        # Adjust for other languages as needed
        return len(text) // 4


__all__ = ["ChatService"]
