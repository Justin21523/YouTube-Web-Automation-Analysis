# tests/unit/test_video_repository.py
"""
Unit Tests for VideoRepository
Tests all CRUD operations and query methods
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from src.app.models import Base, Video, Channel, VideoStatus
from src.infrastructure.repositories.video_repository import VideoRepository


# ============================================================================
# Pytest Configuration
# ============================================================================

# Configure pytest-asyncio
pytest_plugins = ("pytest_asyncio",)


# ============================================================================
# Test Fixtures (using pytest_asyncio)
# ============================================================================


@pytest_asyncio.fixture
async def async_engine():
    """Create async engine for testing"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,  # Required for in-memory SQLite
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
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
        id="test_channel_123",
        name="Test Channel",
        handle="@testchannel",
        subscriber_count=1000000,
        first_scraped_at=datetime.utcnow(),
        last_updated_at=datetime.utcnow(),
    )
    db_session.add(channel)
    await db_session.commit()
    await db_session.refresh(channel)
    return channel


@pytest_asyncio.fixture
async def sample_videos(db_session, sample_channel):
    """Create sample videos for testing"""
    videos = []

    for i in range(5):
        video = Video(
            id=f"video_{i}",
            channel_id=sample_channel.id,
            title=f"Test Video {i}",
            description=f"Description for video {i}",
            view_count=1000 * (i + 1),
            like_count=100 * (i + 1),
            comment_count=10 * (i + 1),
            published_at=datetime.utcnow() - timedelta(days=i),
            status=VideoStatus.COMPLETED,
            first_scraped_at=datetime.utcnow(),
            last_updated_at=datetime.utcnow(),
        )
        videos.append(video)
        db_session.add(video)

    await db_session.commit()

    # Refresh all videos
    for video in videos:
        await db_session.refresh(video)

    return videos


# ============================================================================
# Repository Tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_video(db_session, sample_channel):
    """Test creating a video"""
    repo = VideoRepository(db_session)

    video_data = {
        "id": "new_video_123",
        "channel_id": sample_channel.id,
        "title": "New Test Video",
        "view_count": 5000,
        "published_at": datetime.utcnow(),
        "status": VideoStatus.PENDING,
    }

    video = await repo.create(**video_data)

    assert video is not None
    assert video.id == "new_video_123"
    assert video.title == "New Test Video"
    assert video.view_count == 5000


@pytest.mark.asyncio
async def test_get_by_id(db_session, sample_videos):
    """Test getting video by ID"""
    repo = VideoRepository(db_session)

    video = await repo.get_by_id("video_0")

    assert video is not None
    assert video.id == "video_0"
    assert video.title == "Test Video 0"


@pytest.mark.asyncio
async def test_get_trending_videos(db_session, sample_videos):
    """Test getting trending videos"""
    repo = VideoRepository(db_session)

    trending = await repo.get_trending(days=7, limit=10, min_views=1000)

    assert len(trending) > 0
    # Should be sorted by view count descending
    if len(trending) > 1:
        assert trending[0].view_count >= trending[-1].view_count


@pytest.mark.asyncio
async def test_search_videos(db_session, sample_videos):
    """Test searching videos"""
    repo = VideoRepository(db_session)

    results = await repo.search("Test Video")

    assert len(results) > 0
    for video in results:
        assert "Test Video" in video.title


@pytest.mark.asyncio
async def test_get_by_channel(db_session, sample_channel, sample_videos):
    """Test getting videos by channel"""
    repo = VideoRepository(db_session)

    videos = await repo.get_by_channel(sample_channel.id)

    assert len(videos) == 5
    for video in videos:
        assert video.channel_id == sample_channel.id


@pytest.mark.asyncio
async def test_get_statistics(db_session, sample_channel, sample_videos):
    """Test getting video statistics"""
    repo = VideoRepository(db_session)

    stats = await repo.get_statistics(channel_id=sample_channel.id)

    assert stats["total_videos"] == 5
    assert stats["total_views"] > 0
    assert stats["avg_views"] > 0


@pytest.mark.asyncio
async def test_upsert_video(db_session, sample_channel):
    """Test upserting a video"""
    repo = VideoRepository(db_session)

    # First insert
    video_data = {
        "id": "upsert_test",
        "channel_id": sample_channel.id,
        "title": "Upsert Test",
        "view_count": 1000,
        "published_at": datetime.utcnow(),
        "status": VideoStatus.PENDING,
    }

    video1 = await repo.upsert_video(video_data)
    assert video1 is not None
    assert video1.scrape_count == 1

    # Update with new data
    video_data["view_count"] = 2000
    video2 = await repo.upsert_video(video_data)

    assert video2 is not None
    assert video2.view_count == 2000
    assert video2.scrape_count == 2


@pytest.mark.asyncio
async def test_mark_status(db_session, sample_videos):
    """Test status management"""
    repo = VideoRepository(db_session)

    video_id = "video_0"

    # Mark as processing
    result = await repo.mark_as_processing(video_id)
    assert result is True

    video = await repo.get_by_id(video_id)
    assert video.status == VideoStatus.PROCESSING

    # Mark as completed
    result = await repo.mark_as_completed(video_id)
    assert result is True

    video = await repo.get_by_id(video_id)
    assert video.status == VideoStatus.COMPLETED


@pytest.mark.asyncio
async def test_get_most_viewed(db_session, sample_videos):
    """Test getting most viewed videos"""
    repo = VideoRepository(db_session)

    most_viewed = await repo.get_most_viewed(limit=3)

    assert len(most_viewed) > 0
    # Should be sorted by view count descending
    if len(most_viewed) > 1:
        assert most_viewed[0].view_count >= most_viewed[1].view_count


@pytest.mark.asyncio
async def test_filter_by_views(db_session, sample_videos):
    """Test filtering by view count"""
    repo = VideoRepository(db_session)

    # Get videos with at least 3000 views
    filtered = await repo.filter_by_views(min_views=3000)

    assert len(filtered) > 0
    for video in filtered:
        assert video.view_count >= 3000


@pytest.mark.asyncio
async def test_get_engagement_metrics(db_session, sample_videos):
    """Test engagement metrics calculation"""
    repo = VideoRepository(db_session)

    metrics = await repo.get_engagement_metrics("video_0")

    assert metrics is not None
    assert "engagement_rate" in metrics
    assert "like_rate" in metrics
    assert "comment_rate" in metrics
    assert metrics["video_id"] == "video_0"


@pytest.mark.asyncio
async def test_count(db_session, sample_videos):
    """Test counting videos"""
    repo = VideoRepository(db_session)

    count = await repo.count()
    assert count == 5

    # Count by channel
    count_by_channel = await repo.count(channel_id="test_channel_123")
    assert count_by_channel == 5


@pytest.mark.asyncio
async def test_exists(db_session, sample_videos):
    """Test checking video existence"""
    repo = VideoRepository(db_session)

    exists = await repo.exists("video_0")
    assert exists is True

    not_exists = await repo.exists("nonexistent_video")
    assert not_exists is False


@pytest.mark.asyncio
async def test_delete_video(db_session, sample_videos):
    """Test deleting a video"""
    repo = VideoRepository(db_session)

    # Delete video
    deleted = await repo.delete("video_0")
    assert deleted is True

    # Verify deleted
    video = await repo.get_by_id("video_0")
    assert video is None

    # Try deleting non-existent video
    deleted = await repo.delete("nonexistent")
    assert deleted is False


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
