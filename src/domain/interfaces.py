# src/domain/interfaces.py
"""
Domain-facing repository and client interfaces (Protocols).

These are intentionally minimal and reflect only what the current services
actually use. Concrete repositories can satisfy these via duck typing; there
is no inheritance requirement.

Keeping this as a thin shim preserves Claude's original import style while
we stabilize the codebase.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable, Any, Dict, List, Optional, Iterable

# Forward imports are placed inside type-checking-only blocks to avoid
# heavy runtime dependencies and circular imports.
try:
    from src.domain.models import Comment, Video, Channel  # type: ignore
except Exception:  # pragma: no cover
    # Fallbacks for type-checkers when ORM is not importable in tooling.
    Comment = Any  # type: ignore
    Video = Any  # type: ignore
    Channel = Any  # type: ignore


@runtime_checkable
class ICommentRepository(Protocol):
    """Interface for comment persistence/query operations."""

    async def get_by_id(self, comment_id: str) -> Optional[Comment]: ...  # type: ignore

    async def get_by_video(self, video_id: str) -> List[Comment]:  # type: ignore
        """Return all comments for a given video."""
        ...

    async def find_by(self, **filters: Any) -> List[Comment]:  # type: ignore
        """Generic filter-based lookup (fallback used by services)."""
        ...

    async def create(self, comment: Optional[Comment] = None, **values: Any) -> Comment:  # type: ignore
        """Create a comment either from an ORM instance or keyword values."""
        ...

    async def update(self, comment: Comment) -> Comment: ...  # type: ignore

    async def bulk_create(self, items: List[Dict[str, Any]]) -> int:
        """Insert many comments, returning the number created."""
        ...

    # Helpers frequently referenced by services (naming kept Claude-like)
    async def create_from_youtube_data(self, data: Dict[str, Any]) -> Comment: ...  # type: ignore

    async def update_from_youtube_data(self, data: Dict[str, Any]) -> Comment: ...  # type: ignore

    async def upsert_from_youtube_data(self, data: Dict[str, Any]) -> Comment: ...  # type: ignore

    async def search(self, **params: Any) -> List[Comment]:  # type: ignore
        """Free-form search (by video_id, keyword, time range, sentiment...)."""
        ...

    async def get_average_sentiment(self, video_id: str) -> float: ...

    async def get_sentiment_distribution(self, video_id: str) -> Dict[str, int]: ...

    async def get_top_comments(
        self, video_id: str, limit: int = 20
    ) -> List[Comment]: ...  # type: ignore


@runtime_checkable
class IVideoRepository(Protocol):
    """Interface for video persistence/query operations."""

    async def get_by_id(self, video_id: str) -> Optional[Video]: ...  # type: ignore

    async def create(self, video: Optional[Video] = None, **values: Any) -> Video: ...  # type: ignore

    async def update(self, video: Video) -> Video: ...  # type: ignore

    async def search(self, **params: Any) -> List[Video]: ...  # type: ignore

    async def get_aggregate_stats(self, **params: Any) -> Dict[str, Any]: ...

    async def create_from_youtube_data(self, data: Dict[str, Any]) -> Video: ...  # type: ignore

    async def update_from_youtube_data(self, data: Dict[str, Any]) -> Video: ...  # type: ignore

    async def upsert_from_youtube_data(self, data: Dict[str, Any]) -> Video: ...  # type: ignore


@runtime_checkable
class IChannelRepository(Protocol):
    """Interface for channel persistence/query operations."""

    async def get_by_id(self, channel_id: str) -> Optional[Channel]: ...  # type: ignore

    async def create(
        self, channel: Optional[Channel] = None, **values: Any  # type: ignore
    ) -> Channel: ...  # type: ignore

    async def update(self, channel: Channel) -> Channel: ...  # type: ignore

    async def search(self, **params: Any) -> List[Channel]: ...  # type: ignore ...

    # Common analytics helpers referenced by services
    async def get_statistics(self, **params: Any) -> Dict[str, Any]: ...

    async def get_aggregate_stats(self, **params: Any) -> Dict[str, Any]: ...

    async def create_from_youtube_data(self, data: Dict[str, Any]) -> Channel: ...  # type: ignore ...

    async def update_from_youtube_data(self, data: Dict[str, Any]) -> Channel: ...  # type: ignore

    async def upsert_from_youtube_data(self, data: Dict[str, Any]) -> Channel: ...  # type: ignore


@runtime_checkable
class YouTubeAPIClientProtocol(Protocol):
    """
    Thin surface used by services and ETL pipelines.

    A concrete client may implement only a subset; services can call what they need.
    """

    # --- Comments ---
    def get_video_comments(
        self, video_id: str, **kwargs: Any
    ) -> Iterable[Dict[str, Any]]:
        """Synchronous fetch (optional)."""
        ...

    async def get_comments_async(
        self, video_id: str, **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """Preferred async fetch used by services; may wrap a sync call via to_thread."""
        ...

    def get_comments(self, video_id: str, **kwargs: Any) -> List[Dict[str, Any]]:
        """Convenience name some modules expect; may delegate to get_video_comments."""
        ...

    # --- Video / Channel (optional) ---
    def get_video(self, video_id: str, **kwargs: Any) -> Any: ...

    def get_channel(self, channel_id: str, **kwargs: Any) -> Any: ...
