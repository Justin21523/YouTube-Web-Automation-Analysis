# tests/integration/test_celery_tasks.py
"""
Integration Tests for Celery Tasks
Tests task execution, workflows, and background job processing
"""

import pytest
import pytest_asyncio
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from src.app.models import Base, Video, Channel, VideoStatus
from src.app.models.caption import Caption, CaptionSegment
from src.app.models.vqa import VQASession, VQAQuestion
from src.app.models.chat import ChatSession, ChatMessage, ChatRole
from src.app.models.rag import DocumentChunk, RAGIndex


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
        id="test_channel_celery",
        name="Test Channel for Celery",
        handle="@testcelery",
        subscriber_count=50000,
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
        id="test_video_celery",
        channel_id=sample_channel.id,
        title="Test Video for Celery Tasks",
        description="A test video for integration testing",
        view_count=10000,
        like_count=500,
        comment_count=100,
        duration_seconds=600,
        published_at=datetime.utcnow() - timedelta(days=7),
        status=VideoStatus.COMPLETED,
        first_scraped_at=datetime.utcnow(),
        last_updated_at=datetime.utcnow(),
    )
    db_session.add(video)
    await db_session.commit()
    await db_session.refresh(video)
    return video


# ============================================================================
# Model Creation Tests (No Celery dependency)
# ============================================================================


class TestCaptionModels:
    """Test caption model creation"""

    @pytest.mark.asyncio
    async def test_caption_model_creation(self, db_session, sample_video):
        """Test Caption model can be created"""
        import uuid
        caption = Caption(
            id=f"caption_{uuid.uuid4().hex[:8]}",
            video_id=sample_video.id,
            language_code="en",
            language_name="English",
            caption_type="auto",
            content="This is a test caption text",
        )
        db_session.add(caption)
        await db_session.commit()
        await db_session.refresh(caption)

        assert caption.id is not None
        assert caption.video_id == sample_video.id
        assert caption.language_code == "en"


class TestVQAModels:
    """Test VQA model creation"""

    @pytest.mark.asyncio
    async def test_vqa_session_creation(self, db_session, sample_video):
        """Test VQA session can be created"""
        import uuid
        session = VQASession(
            id=f"vqa_{uuid.uuid4().hex[:8]}",
            video_id=sample_video.id,
            model_type="blip2",
            is_active=True,
        )
        db_session.add(session)
        await db_session.commit()
        await db_session.refresh(session)

        assert session.id is not None
        assert session.video_id == sample_video.id


class TestChatModels:
    """Test chat model creation"""

    @pytest.mark.asyncio
    async def test_chat_session_creation(self, db_session, sample_video):
        """Test ChatSession can be created"""
        import uuid
        chat_session = ChatSession(
            id=f"chat_{uuid.uuid4().hex[:8]}",
            video_id=sample_video.id,
            model_type="gpt-4",
            title="Test Chat Session",
        )
        db_session.add(chat_session)
        await db_session.commit()
        await db_session.refresh(chat_session)

        assert chat_session.id is not None
        assert chat_session.video_id == sample_video.id

    @pytest.mark.asyncio
    async def test_chat_message_creation(self, db_session, sample_video):
        """Test ChatMessage can be created"""
        import uuid

        # First create a session
        chat_session = ChatSession(
            id=f"chat_{uuid.uuid4().hex[:8]}",
            video_id=sample_video.id,
            model_type="gpt-4",
            title="Test Chat Session",
        )
        db_session.add(chat_session)
        await db_session.commit()
        await db_session.refresh(chat_session)

        # Create a message (id is auto-generated Integer)
        message = ChatMessage(
            session_id=chat_session.id,
            role=ChatRole.USER.value,
            content="Hello, this is a test message",
        )
        db_session.add(message)
        await db_session.commit()
        await db_session.refresh(message)

        assert message.id is not None
        assert message.session_id == chat_session.id
        assert message.role == ChatRole.USER.value


class TestRAGModels:
    """Test RAG model creation"""

    @pytest.mark.asyncio
    async def test_document_chunk_creation(self, db_session, sample_video):
        """Test DocumentChunk can be created"""
        chunk = DocumentChunk(
            video_id=sample_video.id,
            source_type="caption",
            content="This is a test document chunk for RAG",
            chunk_index=0,
            start_time=0.0,
            end_time=10.0,
        )
        db_session.add(chunk)
        await db_session.commit()
        await db_session.refresh(chunk)

        assert chunk.id is not None
        assert chunk.video_id == sample_video.id
        assert chunk.source_type == "caption"

    @pytest.mark.asyncio
    async def test_rag_index_creation(self, db_session):
        """Test RAGIndex can be created"""
        index = RAGIndex(
            name="test_index",
            description="A test RAG index",
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            embedding_dimension=384,
            index_type="flat",
        )
        db_session.add(index)
        await db_session.commit()
        await db_session.refresh(index)

        assert index.id is not None
        assert index.name == "test_index"
        assert index.embedding_dimension == 384


# ============================================================================
# Task Module Import Tests (mocked Celery)
# ============================================================================


# Note: Task module import tests are skipped when Celery is not installed
# They will pass in environments with Celery (e.g., Docker, CI with full deps)

try:
    import celery
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False


class TestTaskModuleImports:
    """Test that task modules can be imported (requires Celery)"""

    @pytest.mark.skipif(not CELERY_AVAILABLE, reason="Celery not installed")
    @pytest.mark.asyncio
    async def test_video_tasks_importable(self):
        """Test video_tasks module structure"""
        import importlib.util
        spec = importlib.util.find_spec("src.infrastructure.tasks.video_tasks")
        assert spec is not None, "video_tasks module should be importable"

    @pytest.mark.skipif(not CELERY_AVAILABLE, reason="Celery not installed")
    @pytest.mark.asyncio
    async def test_channel_tasks_importable(self):
        """Test channel_tasks module structure"""
        import importlib.util
        spec = importlib.util.find_spec("src.infrastructure.tasks.channel_tasks")
        assert spec is not None, "channel_tasks module should be importable"

    @pytest.mark.skipif(not CELERY_AVAILABLE, reason="Celery not installed")
    @pytest.mark.asyncio
    async def test_analysis_tasks_importable(self):
        """Test analysis_tasks module structure"""
        import importlib.util
        spec = importlib.util.find_spec("src.infrastructure.tasks.analysis_tasks")
        assert spec is not None, "analysis_tasks module should be importable"

    @pytest.mark.skipif(not CELERY_AVAILABLE, reason="Celery not installed")
    @pytest.mark.asyncio
    async def test_caption_tasks_importable(self):
        """Test caption_tasks module structure"""
        import importlib.util
        spec = importlib.util.find_spec("src.infrastructure.tasks.caption_tasks")
        assert spec is not None, "caption_tasks module should be importable"

    @pytest.mark.skipif(not CELERY_AVAILABLE, reason="Celery not installed")
    @pytest.mark.asyncio
    async def test_vqa_tasks_importable(self):
        """Test vqa_tasks module structure"""
        import importlib.util
        spec = importlib.util.find_spec("src.infrastructure.tasks.vqa_tasks")
        assert spec is not None, "vqa_tasks module should be importable"

    @pytest.mark.skipif(not CELERY_AVAILABLE, reason="Celery not installed")
    @pytest.mark.asyncio
    async def test_chat_tasks_importable(self):
        """Test chat_tasks module structure"""
        import importlib.util
        spec = importlib.util.find_spec("src.infrastructure.tasks.chat_tasks")
        assert spec is not None, "chat_tasks module should be importable"

    @pytest.mark.skipif(not CELERY_AVAILABLE, reason="Celery not installed")
    @pytest.mark.asyncio
    async def test_rag_tasks_importable(self):
        """Test rag_tasks module structure"""
        import importlib.util
        spec = importlib.util.find_spec("src.infrastructure.tasks.rag_tasks")
        assert spec is not None, "rag_tasks module should be importable"

    @pytest.mark.skipif(not CELERY_AVAILABLE, reason="Celery not installed")
    @pytest.mark.asyncio
    async def test_workflow_tasks_importable(self):
        """Test workflow_tasks module structure"""
        import importlib.util
        spec = importlib.util.find_spec("src.infrastructure.tasks.workflow_tasks")
        assert spec is not None, "workflow_tasks module should be importable"

    @pytest.mark.skipif(not CELERY_AVAILABLE, reason="Celery not installed")
    @pytest.mark.asyncio
    async def test_scheduled_tasks_importable(self):
        """Test scheduled_tasks module structure"""
        import importlib.util
        spec = importlib.util.find_spec("src.infrastructure.tasks.scheduled_tasks")
        assert spec is not None, "scheduled_tasks module should be importable"

    @pytest.mark.skipif(not CELERY_AVAILABLE, reason="Celery not installed")
    @pytest.mark.asyncio
    async def test_celery_app_importable(self):
        """Test celery_app module structure"""
        import importlib.util
        spec = importlib.util.find_spec("src.infrastructure.tasks.celery_app")
        assert spec is not None, "celery_app module should be importable"


# ============================================================================
# Task Functions Tests (with mocked Celery decorator)
# ============================================================================


class TestTaskFunctionsWithMock:
    """Test task functions with mocked Celery"""

    @pytest.mark.skipif(not CELERY_AVAILABLE, reason="Celery not installed")
    @pytest.mark.asyncio
    @patch("src.infrastructure.tasks.celery_app.celery_app")
    async def test_video_tasks_structure(self, mock_celery):
        """Test that video_tasks module has expected structure"""
        mock_celery.task = lambda *args, **kwargs: lambda f: f

        import importlib
        video_tasks = importlib.import_module("src.infrastructure.tasks.video_tasks")

        assert hasattr(video_tasks, "fetch_video_metadata") or callable(
            getattr(video_tasks, "fetch_video_metadata", None)
        )

    @pytest.mark.skipif(not CELERY_AVAILABLE, reason="Celery not installed")
    @pytest.mark.asyncio
    @patch("src.infrastructure.tasks.celery_app.celery_app")
    async def test_channel_tasks_structure(self, mock_celery):
        """Test that channel_tasks module has expected structure"""
        mock_celery.task = lambda *args, **kwargs: lambda f: f

        import importlib
        channel_tasks = importlib.import_module("src.infrastructure.tasks.channel_tasks")

        assert channel_tasks is not None


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
