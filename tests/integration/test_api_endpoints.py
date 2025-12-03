# tests/integration/test_api_endpoints.py
"""
Integration Tests for API Endpoints
Tests FastAPI endpoint definitions and schemas
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from src.app.models import Base, Video, Channel, VideoStatus
from src.app.models.caption import Caption
from src.app.models.vqa import VQASession
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
        id="api_test_channel",
        name="API Test Channel",
        handle="@apitestchannel",
        subscriber_count=100000,
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
        id="api_test_video",
        channel_id=sample_channel.id,
        title="API Test Video",
        description="A test video for API testing",
        view_count=50000,
        like_count=2500,
        comment_count=500,
        duration_seconds=1200,
        published_at=datetime.utcnow() - timedelta(days=14),
        status=VideoStatus.COMPLETED,
        first_scraped_at=datetime.utcnow(),
        last_updated_at=datetime.utcnow(),
    )
    db_session.add(video)
    await db_session.commit()
    await db_session.refresh(video)
    return video


# ============================================================================
# Celery availability check
# ============================================================================

try:
    import celery
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False


# ============================================================================
# Router Import Tests
# ============================================================================


class TestRouterImports:
    """Test that all routers can be imported (requires Celery)"""

    @pytest.mark.skipif(not CELERY_AVAILABLE, reason="Celery not installed")
    @pytest.mark.asyncio
    async def test_task_router_import(self):
        """Test task router can be imported"""
        from src.api.routers.task_router import router
        assert router is not None

    @pytest.mark.skipif(not CELERY_AVAILABLE, reason="Celery not installed")
    @pytest.mark.asyncio
    async def test_caption_router_import(self):
        """Test caption router can be imported"""
        from src.api.routers.caption_router import router
        assert router is not None

    @pytest.mark.skipif(not CELERY_AVAILABLE, reason="Celery not installed")
    @pytest.mark.asyncio
    async def test_vqa_router_import(self):
        """Test VQA router can be imported"""
        from src.api.routers.vqa_router import router
        assert router is not None

    @pytest.mark.skipif(not CELERY_AVAILABLE, reason="Celery not installed")
    @pytest.mark.asyncio
    async def test_chat_router_import(self):
        """Test chat router can be imported"""
        from src.api.routers.chat_router import router
        assert router is not None

    @pytest.mark.skipif(not CELERY_AVAILABLE, reason="Celery not installed")
    @pytest.mark.asyncio
    async def test_rag_router_import(self):
        """Test RAG router can be imported"""
        from src.api.routers.rag_router import router
        assert router is not None


# ============================================================================
# Schema Import Tests
# ============================================================================


class TestSchemaImports:
    """Test that all schemas can be imported"""

    @pytest.mark.asyncio
    async def test_api_schemas_import(self):
        """Test API schemas can be imported"""
        from src.api.schemas import (
            VideoCreateRequest,
            VideoUpdateRequest,
            VideoResponse,
            VideoSummary,
        )
        assert VideoCreateRequest is not None
        assert VideoUpdateRequest is not None
        assert VideoResponse is not None
        assert VideoSummary is not None


# ============================================================================
# Router Configuration Tests
# ============================================================================


class TestRouterConfiguration:
    """Test router configurations (requires Celery)"""

    @pytest.mark.skipif(not CELERY_AVAILABLE, reason="Celery not installed")
    @pytest.mark.asyncio
    async def test_task_router_has_routes(self):
        """Test task router has expected routes"""
        from src.api.routers.task_router import router

        # Get all routes
        routes = [route.path for route in router.routes]

        assert len(routes) > 0

    @pytest.mark.skipif(not CELERY_AVAILABLE, reason="Celery not installed")
    @pytest.mark.asyncio
    async def test_caption_router_has_routes(self):
        """Test caption router has expected routes"""
        from src.api.routers.caption_router import router

        routes = [route.path for route in router.routes]
        assert len(routes) > 0

    @pytest.mark.skipif(not CELERY_AVAILABLE, reason="Celery not installed")
    @pytest.mark.asyncio
    async def test_vqa_router_has_routes(self):
        """Test VQA router has expected routes"""
        from src.api.routers.vqa_router import router

        routes = [route.path for route in router.routes]
        assert len(routes) > 0

    @pytest.mark.skipif(not CELERY_AVAILABLE, reason="Celery not installed")
    @pytest.mark.asyncio
    async def test_chat_router_has_routes(self):
        """Test chat router has expected routes"""
        from src.api.routers.chat_router import router

        routes = [route.path for route in router.routes]
        assert len(routes) > 0

    @pytest.mark.skipif(not CELERY_AVAILABLE, reason="Celery not installed")
    @pytest.mark.asyncio
    async def test_rag_router_has_routes(self):
        """Test RAG router has expected routes"""
        from src.api.routers.rag_router import router

        routes = [route.path for route in router.routes]
        assert len(routes) > 0


# ============================================================================
# Model Validation Tests
# ============================================================================


class TestModelValidation:
    """Test model validation in API context"""

    @pytest.mark.asyncio
    async def test_video_model_creation(self, db_session, sample_channel):
        """Test video model can be created"""
        video = Video(
            id="validation_test_video",
            channel_id=sample_channel.id,
            title="Validation Test Video",
            description="Test description",
            view_count=1000,
            published_at=datetime.utcnow(),
            status=VideoStatus.PENDING,
        )
        db_session.add(video)
        await db_session.commit()
        await db_session.refresh(video)

        assert video.id == "validation_test_video"
        assert video.title == "Validation Test Video"

    @pytest.mark.asyncio
    async def test_caption_model_creation(self, db_session, sample_video):
        """Test caption model can be created"""
        import uuid
        caption = Caption(
            id=f"caption_{uuid.uuid4().hex[:8]}",
            video_id=sample_video.id,
            language_code="en",
            language_name="English",
            caption_type="manual",
            content="Test caption text",
        )
        db_session.add(caption)
        await db_session.commit()
        await db_session.refresh(caption)

        assert caption.video_id == sample_video.id

    @pytest.mark.asyncio
    async def test_vqa_session_model_creation(self, db_session, sample_video):
        """Test VQA session model can be created"""
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

        assert session.video_id == sample_video.id

    @pytest.mark.asyncio
    async def test_chat_session_model_creation(self, db_session, sample_video):
        """Test chat session model can be created"""
        import uuid
        chat_session = ChatSession(
            id=f"chat_{uuid.uuid4().hex[:8]}",
            video_id=sample_video.id,
            model_type="gpt-4",
            title="Test Chat",
        )
        db_session.add(chat_session)
        await db_session.commit()
        await db_session.refresh(chat_session)

        assert chat_session.video_id == sample_video.id

    @pytest.mark.asyncio
    async def test_rag_index_model_creation(self, db_session):
        """Test RAG index model can be created"""
        index = RAGIndex(
            name="api_test_index",
            description="API test RAG index",
            embedding_model="all-MiniLM-L6-v2",
            embedding_dimension=384,
            index_type="flat",
        )
        db_session.add(index)
        await db_session.commit()
        await db_session.refresh(index)

        assert index.name == "api_test_index"


# ============================================================================
# Router __all__ Exports Tests
# ============================================================================


class TestRouterExports:
    """Test router module exports"""

    @pytest.mark.skipif(not CELERY_AVAILABLE, reason="Celery not installed")
    @pytest.mark.asyncio
    async def test_routers_init_exports(self):
        """Test routers __init__ exports all routers"""
        from src.api.routers import (
            task_router,
            caption_router,
            vqa_router,
            chat_router,
            rag_router,
        )

        assert task_router is not None
        assert caption_router is not None
        assert vqa_router is not None
        assert chat_router is not None
        assert rag_router is not None


# ============================================================================
# API Dependencies Tests
# ============================================================================


class TestAPIDependencies:
    """Test API dependencies"""

    @pytest.mark.asyncio
    async def test_dependencies_module_exists(self):
        """Test dependencies module exists"""
        import importlib.util
        spec = importlib.util.find_spec("src.app.dependencies")
        assert spec is not None, "dependencies module should exist"

    @pytest.mark.asyncio
    async def test_database_module_exists(self):
        """Test database module exists"""
        import importlib.util
        spec = importlib.util.find_spec("src.app.database")
        assert spec is not None, "database module should exist"


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
