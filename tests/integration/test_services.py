# tests/integration/test_services.py
"""
Integration Tests for Service Layer
Tests service operations across components
"""

import pytest
import pytest_asyncio
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from src.app.models import Base, Video, Channel, VideoStatus
from src.app.models.caption import Caption, CaptionSegment
from src.app.models.vqa import VQASession, VQAQuestion
from src.app.models.chat import ChatSession, ChatMessage, ChatRole, ChatTemplate
from src.app.models.rag import DocumentChunk, RAGIndex, RAGQuery


# ============================================================================
# Pytest Configuration
# ============================================================================

pytest_plugins = ("pytest_asyncio",)


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def async_engine():
    """Create async engine for testing"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine):
    """Create async database session for testing"""
    async_session = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session


@pytest_asyncio.fixture
async def sample_channel(db_session):
    """Create sample channel for testing"""
    channel = Channel(
        id="service_test_channel",
        name="Service Test Channel",
        handle="@servicetestchannel",
        subscriber_count=75000,
        first_scraped_at=datetime.utcnow(),
        last_updated_at=datetime.utcnow(),
    )
    db_session.add(channel)
    await db_session.commit()
    await db_session.refresh(channel)
    return channel


@pytest_asyncio.fixture
async def sample_video(db_session, sample_channel):
    """Create sample video for testing"""
    video = Video(
        id="service_test_video",
        channel_id=sample_channel.id,
        title="Service Test Video",
        description="A test video for service layer testing",
        view_count=25000,
        like_count=1250,
        comment_count=250,
        duration_seconds=900,
        published_at=datetime.utcnow() - timedelta(days=10),
        status=VideoStatus.COMPLETED,
        first_scraped_at=datetime.utcnow(),
        last_updated_at=datetime.utcnow(),
    )
    db_session.add(video)
    await db_session.commit()
    await db_session.refresh(video)
    return video


@pytest_asyncio.fixture
async def sample_caption(db_session, sample_video):
    """Create sample caption for testing"""
    import uuid
    caption = Caption(
        id=f"caption_{uuid.uuid4().hex[:8]}",
        video_id=sample_video.id,
        language_code="en",
        language_name="English",
        caption_type="manual",
        content="This is a test caption for the video.",
    )
    db_session.add(caption)
    await db_session.commit()
    await db_session.refresh(caption)
    return caption


# ============================================================================
# Video Service Tests
# ============================================================================


class TestVideoService:
    """Test VideoService operations"""

    @pytest.mark.asyncio
    async def test_service_import(self):
        """Test that VideoService can be imported"""
        from src.services import VideoService

        assert VideoService is not None

    @pytest.mark.asyncio
    async def test_video_repository_standalone(self, db_session, sample_video):
        """Test VideoRepository can work standalone"""
        from src.infrastructure.repositories import VideoRepository

        repo = VideoRepository(db_session)

        video = await repo.get_by_id(sample_video.id)

        assert video is not None
        assert video.id == sample_video.id
        assert video.title == sample_video.title

    @pytest.mark.asyncio
    async def test_search_videos_via_repository(self, db_session, sample_video):
        """Test searching videos through repository"""
        from src.infrastructure.repositories import VideoRepository

        repo = VideoRepository(db_session)

        results = await repo.search("Service Test")

        assert len(results) > 0
        assert any(v.id == sample_video.id for v in results)


# ============================================================================
# Caption Service Tests
# ============================================================================


class TestCaptionService:
    """Test CaptionService operations"""

    @pytest.mark.asyncio
    async def test_service_import(self):
        """Test that CaptionService can be imported"""
        from src.services import CaptionService

        assert CaptionService is not None

    @pytest.mark.asyncio
    async def test_caption_repository_standalone(self, db_session, sample_caption, sample_video):
        """Test CaptionRepository can work standalone"""
        from src.infrastructure.repositories import CaptionRepository

        repo = CaptionRepository(db_session)

        captions = await repo.get_by_video_id(sample_video.id)

        assert len(captions) > 0
        assert captions[0].video_id == sample_video.id


# ============================================================================
# VQA Service Tests
# ============================================================================


class TestVQAService:
    """Test VQAService operations"""

    @pytest.mark.asyncio
    async def test_service_import(self):
        """Test that VQAService can be imported"""
        from src.services import VQAService

        assert VQAService is not None

    @pytest.mark.asyncio
    async def test_vqa_session_repository_standalone(self, db_session, sample_video):
        """Test VQASessionRepository can work standalone"""
        from src.infrastructure.repositories import VQASessionRepository
        import uuid

        repo = VQASessionRepository(db_session)

        # Create a VQA session
        session = await repo.create(
            id=f"vqa_{uuid.uuid4().hex[:8]}",
            video_id=sample_video.id,
            model_type="blip2",
            is_active=True
        )

        assert session is not None
        assert session.video_id == sample_video.id
        assert session.model_type == "blip2"


# ============================================================================
# Chat Service Tests
# ============================================================================


class TestChatService:
    """Test ChatService operations"""

    @pytest.mark.asyncio
    async def test_service_import(self):
        """Test that ChatService can be imported"""
        from src.services import ChatService

        assert ChatService is not None

    @pytest.mark.asyncio
    async def test_chat_session_repository_standalone(self, db_session, sample_video):
        """Test ChatSessionRepository can work standalone"""
        from src.infrastructure.repositories import ChatSessionRepository
        import uuid

        repo = ChatSessionRepository(db_session)

        # Create a chat session
        session = await repo.create(
            id=f"chat_{uuid.uuid4().hex[:8]}",
            video_id=sample_video.id,
            model_type="gpt-4",
            title="Test Chat Session"
        )

        assert session is not None
        assert session.video_id == sample_video.id
        assert session.title == "Test Chat Session"

    @pytest.mark.asyncio
    async def test_chat_message_repository_standalone(self, db_session, sample_video):
        """Test ChatMessageRepository can work standalone"""
        from src.infrastructure.repositories import ChatSessionRepository, ChatMessageRepository
        import uuid

        session_repo = ChatSessionRepository(db_session)
        message_repo = ChatMessageRepository(db_session)

        # Create session first
        session = await session_repo.create(
            id=f"chat_{uuid.uuid4().hex[:8]}",
            video_id=sample_video.id,
            model_type="gpt-4",
            title="Test Chat"
        )

        # Create message (id is auto-generated Integer)
        message = await message_repo.create(
            session_id=session.id,
            role=ChatRole.USER.value,
            content="Hello, this is a test message"
        )

        assert message is not None
        assert message.session_id == session.id
        assert message.role == ChatRole.USER.value


# ============================================================================
# RAG Service Tests
# ============================================================================


class TestRAGService:
    """Test RAGService operations"""

    @pytest.mark.asyncio
    async def test_service_import(self):
        """Test that RAGService can be imported"""
        from src.services import RAGService

        assert RAGService is not None

    @pytest.mark.asyncio
    async def test_document_chunk_repository_standalone(self, db_session, sample_video):
        """Test DocumentChunkRepository can work standalone"""
        from src.infrastructure.repositories import DocumentChunkRepository

        repo = DocumentChunkRepository(db_session)

        # Create a document chunk
        chunk = await repo.create(
            video_id=sample_video.id,
            source_type="caption",
            content="This is a test document chunk for RAG",
            chunk_index=0,
            start_time=0.0,
            end_time=10.0
        )

        assert chunk is not None
        assert chunk.video_id == sample_video.id
        assert chunk.source_type == "caption"

    @pytest.mark.asyncio
    async def test_rag_index_repository_standalone(self, db_session):
        """Test RAGIndexRepository can work standalone"""
        from src.infrastructure.repositories import RAGIndexRepository

        repo = RAGIndexRepository(db_session)

        # Create a RAG index
        index = await repo.create(
            name="test_rag_index",
            description="A test RAG index for service testing",
            embedding_model="all-MiniLM-L6-v2",
            embedding_dimension=384,
            index_type="flat"
        )

        assert index is not None
        assert index.name == "test_rag_index"
        assert index.embedding_dimension == 384


# ============================================================================
# Task Tracking Service Tests
# ============================================================================


class TestTaskTrackingService:
    """Test TaskTrackingService operations"""

    @pytest.mark.asyncio
    async def test_service_import(self):
        """Test that TaskTrackingService module can be imported"""
        from src.services import TaskTrackingService

        assert TaskTrackingService is not None

    @pytest.mark.asyncio
    async def test_task_execution_repository_standalone(self, db_session):
        """Test TaskExecutionRepository can work standalone"""
        from src.infrastructure.repositories import TaskExecutionRepository
        from src.app.models.task_execution import TaskStatus

        repo = TaskExecutionRepository(db_session)

        # Create a task execution record
        task = await repo.create(
            task_id="test-task-123",
            task_name="test_task",
            task_type="test",
            status=TaskStatus.PENDING,
            priority=5
        )

        assert task is not None
        assert task.task_id == "test-task-123"
        assert task.task_name == "test_task"


# ============================================================================
# Service Integration Tests
# ============================================================================


class TestServiceIntegration:
    """Test service layer integration"""

    @pytest.mark.asyncio
    async def test_all_services_importable(self):
        """Test that all services can be imported"""
        from src.services import (
            VideoService,
            CaptionService,
            VQAService,
            ChatService,
            RAGService,
            TaskTrackingService,
        )

        assert VideoService is not None
        assert CaptionService is not None
        assert VQAService is not None
        assert ChatService is not None
        assert RAGService is not None
        assert TaskTrackingService is not None

    @pytest.mark.asyncio
    async def test_service_base_class(self):
        """Test BaseService class exists"""
        from src.services.base_service import BaseService

        assert BaseService is not None
        assert hasattr(BaseService, "get_service_name")

    @pytest.mark.asyncio
    async def test_all_repositories_importable(self):
        """Test that all repositories can be imported"""
        from src.infrastructure.repositories import (
            VideoRepository,
            ChannelRepository,
            CommentRepository,
            CaptionRepository,
            CaptionSegmentRepository,
            VQASessionRepository,
            VQAQuestionRepository,
            ChatSessionRepository,
            ChatMessageRepository,
            ChatTemplateRepository,
            DocumentChunkRepository,
            ChunkEmbeddingRepository,
            RAGIndexRepository,
            RAGQueryRepository,
            TaskExecutionRepository,
        )

        assert VideoRepository is not None
        assert ChannelRepository is not None
        assert CommentRepository is not None
        assert CaptionRepository is not None
        assert VQASessionRepository is not None
        assert ChatSessionRepository is not None
        assert DocumentChunkRepository is not None
        assert RAGIndexRepository is not None
        assert TaskExecutionRepository is not None


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
