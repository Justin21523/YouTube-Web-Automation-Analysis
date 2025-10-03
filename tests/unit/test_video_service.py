"""
Unit Tests for VideoService
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta

from src.services.video_service import VideoService
from src.services.exceptions import (
    ResourceNotFoundError,
    ResourceAlreadyExistsError,
    ValidationError,
)
from src.api.schemas import VideoCreateRequest, VideoSearchRequest
from src.infrastructure.database.models import Video, VideoStatus


@pytest.fixture
def mock_youtube_client():
    """Mock YouTube API client"""
    client = Mock()

    # Mock video response
    mock_video = Mock()
    mock_video.id = "test123"
    mock_video.snippet = Mock(
        channel_id="UC_test",
        title="Test Video",
        description="Test description",
        published_at=datetime.utcnow(),
        category_id="22",
        tags=["test", "video"],
        thumbnails=Mock(high=Mock(url="https://example.com/thumb.jpg")),
    )
    mock_video.statistics = Mock(view_count=1000, like_count=100, comment_count=50)
    mock_video.content_details = Mock(duration="PT5M30S")

    client.get_video.return_value = mock_video
    client.get_videos_batch.return_value = [mock_video]

    return client


@pytest.fixture
def mock_video_repo():
    """Mock video repository"""
    repo = Mock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.delete = AsyncMock()
    repo.search = AsyncMock(return_value=[])
    repo.count_search = AsyncMock(return_value=0)
    repo.get_by_channel = AsyncMock(return_value=[])
    repo.count_by_channel = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def mock_channel_repo():
    """Mock channel repository"""
    repo = Mock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.create = AsyncMock()
    return repo


@pytest.fixture
def mock_db():
    """Mock database session"""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def video_service(mock_youtube_client, mock_video_repo, mock_channel_repo):
    """Create VideoService with mocked dependencies"""
    return VideoService(
        youtube_client=mock_youtube_client,
        video_repo=mock_video_repo,
        channel_repo=mock_channel_repo,
    )


class TestVideoServiceCreate:
    """Test video creation"""

    @pytest.mark.asyncio
    async def test_create_video_success(
        self, video_service, mock_db, mock_video_repo, mock_youtube_client
    ):
        """Test successful video creation"""
        # Setup
        request = VideoCreateRequest(video_id="test123")

        mock_video = Mock()
        mock_video.id = "test123"
        mock_video.title = "Test Video"
        mock_video.channel_id = "UC_test"
        mock_video.view_count = 1000

        mock_video_repo.get_by_id.return_value = None  # Not exists
        mock_video_repo.create.return_value = mock_video

        # Test
        result = await video_service.create_video(mock_db, request)

        # Assert
        assert result.id == "test123"
        mock_youtube_client.get_video.assert_called_once_with("test123")
        mock_video_repo.create.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_video_already_exists(
        self, video_service, mock_db, mock_video_repo
    ):
        """Test creating video that already exists"""
        # Setup
        request = VideoCreateRequest(video_id="test123")

        existing_video = Mock()
        existing_video.id = "test123"
        mock_video_repo.get_by_id.return_value = existing_video

        # Test & Assert
        with pytest.raises(ResourceAlreadyExistsError) as exc_info:
            await video_service.create_video(mock_db, request)

        assert exc_info.value.resource_id == "test123"
        mock_video_repo.create.assert_not_called()


class TestVideoServiceRead:
    """Test video retrieval"""

    @pytest.mark.asyncio
    async def test_get_video_success(self, video_service, mock_db, mock_video_repo):
        """Test successful video retrieval"""
        # Setup
        mock_video = Mock()
        mock_video.id = "test123"
        mock_video.title = "Test Video"
        mock_video.view_count = 1000
        mock_video.like_count = 100
        mock_video.comment_count = 50
        mock_video.published_at = datetime.utcnow()
        mock_video.status = VideoStatus.COMPLETED

        mock_video_repo.get_by_id.return_value = mock_video

        # Test
        result = await video_service.get_video(mock_db, "test123", use_cache=False)

        # Assert
        assert result.id == "test123"
        mock_video_repo.get_by_id.assert_called_once_with(mock_db, "test123")

    @pytest.mark.asyncio
    async def test_get_video_not_found(self, video_service, mock_db, mock_video_repo):
        """Test video not found error"""
        # Setup
        mock_video_repo.get_by_id.return_value = None

        # Test & Assert
        with pytest.raises(ResourceNotFoundError) as exc_info:
            await video_service.get_video(mock_db, "invalid")

        assert exc_info.value.resource_id == "invalid"

    @pytest.mark.asyncio
    async def test_get_video_with_cache(self, video_service, mock_db, mock_video_repo):
        """Test video retrieval uses cache"""
        # Setup - Cache miss then hit
        mock_video = Mock()
        mock_video.id = "test123"
        mock_video.title = "Test Video"
        mock_video.view_count = 1000
        mock_video.like_count = 100
        mock_video.comment_count = 50
        mock_video.published_at = datetime.utcnow()
        mock_video.status = VideoStatus.COMPLETED

        mock_video_repo.get_by_id.return_value = mock_video

        # First call - cache miss
        result1 = await video_service.get_video(mock_db, "test123", use_cache=True)
        assert mock_video_repo.get_by_id.call_count == 1

        # Second call - should use cache
        result2 = await video_service.get_video(mock_db, "test123", use_cache=True)
        assert result2.id == "test123"
        # Repo should not be called again (cached)
        assert mock_video_repo.get_by_id.call_count == 1


class TestVideoServiceUpdate:
    """Test video updates"""

    @pytest.mark.asyncio
    async def test_update_video_success(self, video_service, mock_db, mock_video_repo):
        """Test successful video update"""
        from src.api.schemas import VideoUpdateRequest

        # Setup
        existing_video = Mock()
        existing_video.id = "test123"

        updated_video = Mock()
        updated_video.id = "test123"
        updated_video.title = "Updated Title"
        updated_video.status = VideoStatus.COMPLETED
        updated_video.published_at = datetime.utcnow()
        updated_video.view_count = 2000
        updated_video.like_count = 200
        updated_video.comment_count = 100

        mock_video_repo.get_by_id.return_value = existing_video
        mock_video_repo.update.return_value = updated_video

        request = VideoUpdateRequest(title="Updated Title")

        # Test
        result = await video_service.update_video(mock_db, "test123", request)

        # Assert
        assert result.id == "test123"
        mock_video_repo.update.assert_called_once()
        mock_db.commit.assert_called_once()


class TestVideoServiceDelete:
    """Test video deletion"""

    @pytest.mark.asyncio
    async def test_delete_video_success(self, video_service, mock_db, mock_video_repo):
        """Test successful video deletion"""
        # Setup
        existing_video = Mock()
        existing_video.id = "test123"
        mock_video_repo.get_by_id.return_value = existing_video

        # Test
        result = await video_service.delete_video(mock_db, "test123")

        # Assert
        assert result["success"] is True
        assert result["video_id"] == "test123"
        mock_video_repo.delete.assert_called_once_with(mock_db, "test123")
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_video_not_found(
        self, video_service, mock_db, mock_video_repo
    ):
        """Test deleting non-existent video"""
        # Setup
        mock_video_repo.get_by_id.return_value = None

        # Test & Assert
        with pytest.raises(ResourceNotFoundError):
            await video_service.delete_video(mock_db, "invalid")


class TestVideoServiceSearch:
    """Test video search"""

    @pytest.mark.asyncio
    async def test_search_videos(self, video_service, mock_db, mock_video_repo):
        """Test video search with filters"""
        # Setup
        mock_videos = [
            Mock(
                id="test1",
                title="Video 1",
                view_count=1000,
                published_at=datetime.utcnow(),
            ),
            Mock(
                id="test2",
                title="Video 2",
                view_count=2000,
                published_at=datetime.utcnow(),
            ),
        ]

        mock_video_repo.search.return_value = mock_videos
        mock_video_repo.count_search.return_value = 2

        params = VideoSearchRequest(query="test", page=1, page_size=20)

        # Test
        summaries, total = await video_service.search_videos(mock_db, params)

        # Assert
        assert len(summaries) == 2
        assert total == 2
        mock_video_repo.search.assert_called_once()
        mock_video_repo.count_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_trending_videos(self, video_service, mock_db):
        """Test getting trending videos"""
        # Setup
        with patch.object(mock_db, "execute") as mock_execute:
            mock_result = Mock()
            mock_videos = [
                Mock(
                    id="test1",
                    title="Trending 1",
                    channel_id="UC_test",
                    view_count=10000,
                    like_count=1000,
                    comment_count=500,
                    published_at=datetime.utcnow() - timedelta(days=2),
                )
            ]
            mock_result.scalars.return_value.all.return_value = mock_videos
            mock_execute.return_value = mock_result

            # Test
            results = await video_service.get_trending_videos(mock_db, days=7, limit=10)

            # Assert
            assert len(results) == 1
            assert results[0].video_id == "test1"
            assert results[0].trending_score > 0


class TestVideoServiceStats:
    """Test video statistics"""

    @pytest.mark.asyncio
    async def test_get_video_stats(self, video_service, mock_db, mock_video_repo):
        """Test getting video statistics"""
        # Setup
        mock_video = Mock()
        mock_video.id = "test123"
        mock_video.view_count = 10000
        mock_video.like_count = 1000
        mock_video.comment_count = 500
        mock_video.published_at = datetime.utcnow() - timedelta(days=10)
        mock_video.last_updated_at = datetime.utcnow()

        mock_video_repo.get_by_id.return_value = mock_video

        # Test
        stats = await video_service.get_video_stats(mock_db, "test123")

        # Assert
        assert stats.video_id == "test123"
        assert stats.view_count == 10000
        assert stats.engagement_rate > 0
        assert stats.views_per_day > 0

    @pytest.mark.asyncio
    async def test_get_aggregate_stats(self, video_service, mock_db):
        """Test aggregate statistics"""
        # Setup
        with patch.object(mock_db, "execute") as mock_execute:
            mock_result = Mock()
            mock_stats = Mock(
                total_videos=10,
                total_views=100000,
                total_likes=10000,
                total_comments=5000,
                avg_views=10000.0,
            )
            mock_result.one.return_value = mock_stats
            mock_execute.return_value = mock_result

            # Test
            stats = await video_service.get_aggregate_stats(mock_db)

            # Assert
            assert stats["total_videos"] == 10
            assert stats["total_views"] == 100000
            assert stats["avg_views"] == 10000.0


class TestVideoServiceOrchestration:
    """Test orchestration methods"""

    @pytest.mark.asyncio
    async def test_refresh_video_metadata(
        self, video_service, mock_db, mock_video_repo, mock_youtube_client
    ):
        """Test refreshing video metadata"""
        # Setup
        existing_video = Mock()
        existing_video.id = "test123"
        existing_video.scrape_count = 1

        updated_video = Mock()
        updated_video.id = "test123"
        updated_video.title = "Updated Title"
        updated_video.view_count = 2000
        updated_video.scrape_count = 2
        updated_video.published_at = datetime.utcnow()
        updated_video.status = VideoStatus.COMPLETED
        updated_video.like_count = 200
        updated_video.comment_count = 100

        mock_video_repo.get_by_id.return_value = existing_video
        mock_video_repo.update.return_value = updated_video

        # Test
        result = await video_service.refresh_video_metadata(mock_db, "test123")

        # Assert
        assert result.id == "test123"
        mock_youtube_client.get_video.assert_called_once_with("test123")
        mock_video_repo.update.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_fetch_videos(
        self, video_service, mock_db, mock_video_repo, mock_youtube_client
    ):
        """Test batch fetching videos"""
        # Setup
        video_ids = ["test1", "test2", "test3"]
        mock_video_repo.get_by_id.return_value = None  # None exist

        # Test
        results = await video_service.batch_fetch_videos(mock_db, video_ids)

        # Assert
        assert len(results["success"]) > 0
        mock_youtube_client.get_videos_batch.assert_called_once_with(video_ids)
        mock_db.commit.assert_called_once()


class TestVideoServiceHelpers:
    """Test helper methods"""

    def test_parse_duration(self, video_service):
        """Test ISO 8601 duration parsing"""
        assert video_service._parse_duration("PT5M30S") == 330  # 5:30
        assert video_service._parse_duration("PT1H30M") == 5400  # 1:30:00
        assert video_service._parse_duration("PT45S") == 45
        assert video_service._parse_duration("PT2H") == 7200

    def test_calculate_engagement_rate(self, video_service):
        """Test engagement rate calculation"""
        video = Mock()
        video.view_count = 10000
        video.like_count = 500
        video.comment_count = 250

        rate = video_service._calculate_engagement_rate(video)
        assert rate == 7.5  # (500 + 250) / 10000 * 100

    def test_calculate_views_per_day(self, video_service):
        """Test views per day calculation"""
        video = Mock()
        video.view_count = 10000
        video.published_at = datetime.utcnow() - timedelta(days=10)

        vpd = video_service._calculate_views_per_day(video)
        assert vpd == 1000.0  # 10000 / 10

    def test_calculate_trending_score(self, video_service):
        """Test trending score calculation"""
        video = Mock()
        video.view_count = 10000
        video.like_count = 1000
        video.comment_count = 500
        video.published_at = datetime.utcnow() - timedelta(days=2)

        score = video_service._calculate_trending_score(video, days=7)
        assert score > 0


class TestVideoServiceValidation:
    """Test validation"""

    @pytest.mark.asyncio
    async def test_validation_errors(self, video_service, mock_db):
        """Test validation errors"""
        # Empty video_id
        with pytest.raises(ValidationError):
            await video_service.get_video(mock_db, "")

        # Invalid days for trending
        with pytest.raises(ValidationError):
            await video_service.get_trending_videos(mock_db, days=-1)

        # Empty batch list
        with pytest.raises(ValidationError):
            await video_service.batch_fetch_videos(mock_db, [])

        # Too many videos in batch
        with pytest.raises(ValidationError):
            await video_service.batch_fetch_videos(mock_db, ["id"] * 100)


if __name__ == "__main__":
    """Run tests"""
    pytest.main([__file__, "-v", "--tb=short"])
