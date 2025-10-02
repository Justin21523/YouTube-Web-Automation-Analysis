"""
Shared Cache Management for YouTube Web Automation Analysis
Manages cache directories and provides unified access to cached data
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class SharedCache:
    """
    Manages shared cache directories and cached data
    Provides unified interface for all caching operations
    """

    def __init__(self, cache_root: Optional[str] = None):
        """
        Initialize shared cache

        Args:
            cache_root: Root directory for cache (defaults to ./cache)
        """
        if cache_root is None:
            cache_root = os.getenv(
                "CACHE_ROOT", "../AI_LLM_projects/ai_warehouse/cache"
            )

        self.cache_root = str(Path(cache_root).resolve())
        self._memory_cache: Dict[str, Any] = {}
        self.app_dirs = {}

        self._setup_environment()
        self._create_directories()
        self._log_setup()

    def _setup_environment(self) -> None:
        """Setup environment variables for cache"""
        os.environ["CACHE_ROOT"] = self.cache_root
        logger.info(f"Cache root set to: {self.cache_root}")

    def _create_directories(self) -> None:
        """Create application-specific cache directories"""
        self.app_dirs = {
            # Core directories
            "CACHE_ROOT": self.cache_root,
            # YouTube data
            "VIDEOS": f"{self.cache_root}/videos",
            "CHANNELS": f"{self.cache_root}/channels",
            "PLAYLISTS": f"{self.cache_root}/playlists",
            "COMMENTS": f"{self.cache_root}/comments",
            # Analysis results
            "ANALYSIS": f"{self.cache_root}/analysis",
            "SENTIMENT": f"{self.cache_root}/analysis/sentiment",
            "TOPICS": f"{self.cache_root}/analysis/topics",
            "TRANSCRIPTS": f"{self.cache_root}/analysis/transcripts",
            # Models and datasets
            "MODELS": f"{self.cache_root}/models",
            "DATASETS": f"{self.cache_root}/datasets",
            "EMBEDDINGS": f"{self.cache_root}/embeddings",
            # Outputs
            "OUTPUT_DIR": f"{self.cache_root}/outputs",
            "OUTPUT_REPORTS": f"{self.cache_root}/outputs/reports",
            "OUTPUT_EXPORTS": f"{self.cache_root}/outputs/exports",
            "OUTPUT_LOGS": f"{self.cache_root}/outputs/logs",
            # Temporary files
            "TEMP_DIR": f"{self.cache_root}/temp",
            "TEMP_DOWNLOADS": f"{self.cache_root}/temp/downloads",
            "TEMP_PROCESSING": f"{self.cache_root}/temp/processing",
            # Configuration
            "CONFIG_DIR": f"{self.cache_root}/config",
            "REGISTRY_FILE": f"{self.cache_root}/config/data_registry.json",
        }

        # Create all directories
        for key, dir_path in self.app_dirs.items():
            if dir_path.endswith(".json"):
                # Create parent directory for files
                Path(dir_path).parent.mkdir(parents=True, exist_ok=True)
            else:
                Path(dir_path).mkdir(parents=True, exist_ok=True)

    def _log_setup(self) -> None:
        """Log cache setup information"""
        logger.info(f"✅ SharedCache initialized: {self.cache_root}")
        logger.info(f"📁 Created {len(self.app_dirs)} cache directories")

    def get_path(self, key: str) -> str:
        """
        Get directory path by key

        Args:
            key: Directory key (e.g., 'VIDEOS', 'ANALYSIS')

        Returns:
            Full path to directory

        Raises:
            KeyError: If key not found
        """
        if key not in self.app_dirs:
            raise KeyError(f"Unknown cache directory: {key}")
        return self.app_dirs[key]

    def get_video_cache_path(self, video_id: str) -> Path:
        """Get cache path for video data"""
        video_dir = Path(self.get_path("VIDEOS")) / video_id
        video_dir.mkdir(parents=True, exist_ok=True)
        return video_dir

    def get_channel_cache_path(self, channel_id: str) -> Path:
        """Get cache path for channel data"""
        channel_dir = Path(self.get_path("CHANNELS")) / channel_id
        channel_dir.mkdir(parents=True, exist_ok=True)
        return channel_dir

    def get_analysis_path(self, analysis_type: str, item_id: str) -> Path:
        """Get path for analysis results"""
        analysis_dir = Path(self.get_path("ANALYSIS")) / analysis_type / item_id
        analysis_dir.mkdir(parents=True, exist_ok=True)
        return analysis_dir

    def get_output_path(self, output_type: str = "reports") -> Path:
        """Get output directory path"""
        output_dir = Path(self.get_path("OUTPUT_DIR")) / output_type
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    # ========================================================================
    # Memory Cache Operations
    # ========================================================================

    def set_cache_item(
        self, key: str, value: Any, ttl_seconds: Optional[int] = None
    ) -> None:
        """
        Set item in memory cache with optional TTL

        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time to live in seconds (None = no expiration)
        """
        cache_item = {
            "value": value,
            "created_at": datetime.now(),
            "expires_at": (
                datetime.now() + timedelta(seconds=ttl_seconds) if ttl_seconds else None
            ),
        }
        self._memory_cache[key] = cache_item

    def get_cache_item(self, key: str, default: Any = None) -> Any:
        """
        Get item from memory cache

        Args:
            key: Cache key
            default: Default value if not found or expired

        Returns:
            Cached value or default
        """
        if key not in self._memory_cache:
            return default

        cache_item = self._memory_cache[key]

        # Check if expired
        if cache_item["expires_at"] and datetime.now() > cache_item["expires_at"]:
            del self._memory_cache[key]
            return default

        return cache_item["value"]

    def clear_expired_cache(self) -> int:
        """
        Clear expired items from memory cache

        Returns:
            Number of items cleared
        """
        now = datetime.now()
        expired_keys = []

        for key, cache_item in self._memory_cache.items():
            if cache_item["expires_at"] and now > cache_item["expires_at"]:
                expired_keys.append(key)

        for key in expired_keys:
            del self._memory_cache[key]

        return len(expired_keys)

    def clear_memory_cache(self) -> None:
        """Clear all items from memory cache"""
        self._memory_cache.clear()

    # ========================================================================
    # Registry Operations
    # ========================================================================

    def save_registry(self, registry_data: Dict[str, Any]) -> None:
        """
        Save data registry to disk

        Args:
            registry_data: Registry data to save
        """
        try:
            registry_path = Path(self.get_path("REGISTRY_FILE"))
            with open(registry_path, "w", encoding="utf-8") as f:
                json.dump(registry_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved registry to {registry_path}")
        except Exception as e:
            logger.error(f"Failed to save registry: {e}")

    def load_registry(self) -> Dict[str, Any]:
        """
        Load data registry from disk

        Returns:
            Registry data or empty registry if not found
        """
        try:
            registry_path = Path(self.get_path("REGISTRY_FILE"))

            if registry_path.exists():
                with open(registry_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            else:
                # Create empty registry
                empty_registry = {
                    "videos": {},
                    "channels": {},
                    "analysis": {},
                    "created_at": datetime.now().isoformat(),
                    "version": "1.0",
                }
                self.save_registry(empty_registry)
                return empty_registry

        except Exception as e:
            logger.error(f"Failed to load registry: {e}")
            return {}

    # ========================================================================
    # Cleanup Operations
    # ========================================================================

    def cleanup_temp_files(self, older_than_hours: int = 24) -> int:
        """
        Clean up temporary files older than specified hours

        Args:
            older_than_hours: Delete files older than this many hours

        Returns:
            Number of files cleaned
        """
        try:
            temp_dirs = [
                self.get_path("TEMP_DIR"),
                self.get_path("TEMP_DOWNLOADS"),
                self.get_path("TEMP_PROCESSING"),
            ]

            cutoff_time = datetime.now() - timedelta(hours=older_than_hours)
            cleaned_count = 0

            for temp_dir in temp_dirs:
                temp_path = Path(temp_dir)
                if temp_path.exists():
                    for file_path in temp_path.rglob("*"):
                        if file_path.is_file():
                            file_mtime = datetime.fromtimestamp(
                                file_path.stat().st_mtime
                            )
                            if file_mtime < cutoff_time:
                                try:
                                    file_path.unlink()
                                    cleaned_count += 1
                                except Exception as e:
                                    logger.warning(f"Failed to delete {file_path}: {e}")

            logger.info(f"Cleaned up {cleaned_count} temporary files")
            return cleaned_count

        except Exception as e:
            logger.error(f"Failed to cleanup temp files: {e}")
            return 0

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics

        Returns:
            Dictionary with cache statistics
        """
        try:
            cache_root_path = Path(self.cache_root)

            # Calculate total size
            total_size = sum(
                f.stat().st_size for f in cache_root_path.rglob("*") if f.is_file()
            )
            total_size_gb = total_size / (1024**3)

            # Count files
            total_files = len(list(cache_root_path.rglob("*")))

            stats = {
                "cache_root": self.cache_root,
                "total_size_gb": round(total_size_gb, 2),
                "total_files": total_files,
                "memory_cache_items": len(self._memory_cache),
                "last_updated": datetime.now().isoformat(),
                "directories": list(self.app_dirs.keys()),
            }

            return stats

        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {"error": str(e)}

    def get_summary(self) -> Dict[str, Any]:
        """
        Get cache summary information

        Returns:
            Summary dictionary
        """
        stats = self.get_cache_stats()

        return {
            "cache_root": self.cache_root,
            "total_size_gb": stats.get("total_size_gb", 0),
            "total_files": stats.get("total_files", 0),
            "directories": len(self.app_dirs),
            "memory_cache_items": len(self._memory_cache),
        }


# ============================================================================
# Global Singleton Instance
# ============================================================================

_shared_cache: Optional[SharedCache] = None


def get_shared_cache(cache_root: Optional[str] = None) -> SharedCache:
    """
    Get or create shared cache instance (Singleton)

    Args:
        cache_root: Optional cache root directory

    Returns:
        SharedCache instance
    """
    global _shared_cache

    if _shared_cache is None:
        _shared_cache = SharedCache(cache_root)

    return _shared_cache


def reset_cache() -> None:
    """Reset global cache instance (useful for testing)"""
    global _shared_cache
    _shared_cache = None


# ============================================================================
# Main Entry Point (Testing)
# ============================================================================

if __name__ == "__main__":
    """Test shared cache functionality"""

    print("🧪 Testing SharedCache...")
    print("=" * 60)

    # Initialize cache
    cache = get_shared_cache()

    # Print summary
    summary = cache.get_summary()
    print("\n📦 Cache Summary:")
    for key, value in summary.items():
        print(f"  {key}: {value}")

    # Test memory cache
    print("\n🧠 Testing Memory Cache...")
    cache.set_cache_item("test_key", "test_value", ttl_seconds=60)
    cached_value = cache.get_cache_item("test_key")
    print(f"  Cached value: {cached_value}")
    assert cached_value == "test_value", "Cache item retrieval failed"
    print("  ✅ Memory cache works!")

    # Test directory creation
    print("\n📁 Testing Directory Creation...")
    video_path = cache.get_video_cache_path("test_video_123")
    print(f"  Video cache path: {video_path}")
    assert video_path.exists(), "Video cache path not created"
    print("  ✅ Directory creation works!")

    # Test registry
    print("\n📋 Testing Registry...")
    registry = cache.load_registry()
    print(f"  Registry version: {registry.get('version', 'unknown')}")
    print(f"  Registry keys: {list(registry.keys())}")
    print("  ✅ Registry works!")

    # Print cache statistics
    print("\n📊 Cache Statistics:")
    stats = cache.get_cache_stats()
    print(f"  Total size: {stats.get('total_size_gb', 0)} GB")
    print(f"  Total files: {stats.get('total_files', 0)}")
    print(f"  Memory cache items: {stats.get('memory_cache_items', 0)}")

    print("\n" + "=" * 60)
    print("✅ All tests passed!")
