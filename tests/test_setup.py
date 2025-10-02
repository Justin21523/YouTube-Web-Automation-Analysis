"""
Smoke tests to verify project setup
Tests configuration, cache, and database connectivity
"""

import pytest
import sys
from pathlib import Path

# ← ADD: Fix import path for tests
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import text  # ← ADD this import
from src.app.config import get_config, validate_config, reset_config
from src.app.shared_cache import get_shared_cache, reset_cache
from src.app.database import engine


class TestConfiguration:
    """Test configuration system"""

    def test_config_loads(self):
        """Test that configuration loads correctly"""
        config = get_config()
        assert config is not None
        assert config.api.port == 8000
        print("\n✅ Configuration loads successfully")

    def test_config_validation(self):
        """Test configuration validation"""
        result = validate_config()

        print(f"\n📋 Validation Result:")
        print(f"  Valid: {result['valid']}")

        if result["errors"]:
            print(f"  Errors: {result['errors']}")

        if result["warnings"]:
            print(f"  Warnings: {result['warnings']}")

        # Should have valid structure even with warnings
        assert isinstance(result, dict)
        assert "valid" in result
        assert "errors" in result
        assert "warnings" in result

    def test_config_summary(self):
        """Test configuration summary generation"""
        config = get_config()
        summary = config.get_summary()

        assert "api" in summary
        assert "database" in summary
        assert "cache" in summary
        assert "youtube" in summary
        assert "scraping" in summary

        print("\n📋 Configuration Summary:")
        for key, value in summary.items():
            print(f"  {key}: {value}")

    def test_output_directories(self):
        """Test that output directories are created"""
        config = get_config()

        # Test various output directories
        video_dir = config.get_output_dir("videos")
        assert video_dir.exists()
        print(f"\n📁 Video output: {video_dir}")

        analysis_dir = config.get_output_dir("analysis")
        assert analysis_dir.exists()
        print(f"📁 Analysis output: {analysis_dir}")


class TestSharedCache:
    """Test shared cache system"""

    def test_cache_initialization(self):
        """Test that shared cache initializes"""
        cache = get_shared_cache()
        assert cache is not None
        assert Path(cache.cache_root).exists()
        print(f"\n📦 Cache root: {cache.cache_root}")

    def test_cache_directories(self):
        """Test that cache directories are created"""
        cache = get_shared_cache()

        # Check key directories
        required_dirs = [
            "VIDEOS",
            "CHANNELS",
            "ANALYSIS",
            "OUTPUT_DIR",
            "TEMP_DIR",
        ]

        for dir_key in required_dirs:
            dir_path = Path(cache.get_path(dir_key))
            assert dir_path.exists(), f"Directory {dir_key} not created"

        print(f"\n✅ All {len(required_dirs)} cache directories exist")

    def test_cache_summary(self):
        """Test cache summary generation"""
        cache = get_shared_cache()
        summary = cache.get_summary()

        assert "cache_root" in summary
        assert "total_files" in summary
        assert "directories" in summary

        print("\n📦 Cache Summary:")
        for key, value in summary.items():
            print(f"  {key}: {value}")

    def test_memory_cache(self):
        """Test memory cache operations"""
        cache = get_shared_cache()

        # Set item
        cache.set_cache_item("test_key", "test_value", ttl_seconds=60)

        # Get item
        value = cache.get_cache_item("test_key")
        assert value == "test_value"

        # Clear cache
        cache.clear_memory_cache()
        value = cache.get_cache_item("test_key")
        assert value is None

        print("\n✅ Memory cache operations work")

    def test_video_cache_path(self):
        """Test video-specific cache paths"""
        cache = get_shared_cache()

        video_id = "test_video_123"
        video_path = cache.get_video_cache_path(video_id)

        assert video_path.exists()
        assert video_id in str(video_path)
        print(f"\n📹 Video cache path: {video_path}")

    def test_registry_operations(self):
        """Test registry save/load operations"""
        cache = get_shared_cache()

        # Load registry (will create if not exists)
        registry = cache.load_registry()
        assert isinstance(registry, dict)
        assert "version" in registry

        # Save registry
        test_data = {
            "videos": {"test": "data"},
            "version": "1.0",
        }
        cache.save_registry(test_data)

        # Load again
        loaded = cache.load_registry()
        assert loaded["version"] == "1.0"

        print("\n✅ Registry operations work")


class TestDatabase:
    """Test database connectivity"""

    def test_database_connection(self):
        """Test database connection"""
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            assert result.fetchone()[0] == 1  # type: ignore

        print("\n✅ Database connection successful")

    def test_database_config(self):
        """Test database configuration"""
        config = get_config()

        assert config.database.url is not None
        assert len(config.database.url) > 0

        print(f"\n📊 Database URL: {config.database.url}")


class TestIntegration:
    """Integration tests across components"""

    def test_full_stack(self):
        """Test full stack initialization"""
        # Load config
        config = get_config()
        assert config is not None

        # Initialize cache
        cache = get_shared_cache()
        assert cache is not None

        # Test database
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            assert result.fetchone()[0] == 1  # type: ignore

        print("\n✅ Full stack integration works")

    def test_cache_config_integration(self):
        """Test that cache uses config settings"""
        config = get_config()
        cache = get_shared_cache()

        # Cache root should match config
        assert cache.cache_root == str(Path(config.cache.cache_root).resolve())

        print("\n✅ Cache-Config integration works")


# Cleanup fixtures
@pytest.fixture(autouse=True)
def cleanup_after_test():
    """Reset singletons after each test"""
    yield
    # Tests run here
    # Cleanup happens after
    # Note: We don't reset here to avoid issues, but you can if needed


if __name__ == "__main__":
    # Run tests with pytest
    import sys

    sys.exit(pytest.main([__file__, "-v", "-s"]))
