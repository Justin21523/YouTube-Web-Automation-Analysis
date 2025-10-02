"""
Configuration Management for YouTube Web Automation Analysis
Standalone configuration system with environment variable overrides
"""

import os
import yaml
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List
from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# Core Configuration Classes
# ============================================================================


class APIConfig(BaseSettings):
    """API Server Configuration"""

    model_config = SettingsConfigDict(env_prefix="API_")

    host: str = Field(default="0.0.0.0", description="API host")
    port: int = Field(default=8000, description="API port")
    prefix: str = Field(default="/api/v1", description="API prefix")
    debug: bool = Field(default=False, description="Debug mode")
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:8000",
        description="CORS allowed origins (comma-separated)",
    )

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins into list"""
        return [origin.strip() for origin in self.cors_origins.split(",")]


class DatabaseConfig(BaseSettings):
    """Database Configuration"""

    model_config = SettingsConfigDict(env_prefix="DB_")

    url: str = Field(
        default="sqlite:///./youtube_automation.db", description="Database URL"
    )
    echo: bool = Field(default=False, description="Echo SQL queries")
    pool_size: int = Field(default=5, description="Connection pool size")
    max_overflow: int = Field(default=10, description="Max overflow connections")


class CacheConfig(BaseSettings):
    """Cache Configuration"""

    model_config = SettingsConfigDict(env_prefix="CACHE_")

    cache_root: str = Field(
        default="../AI_LLM_projects/ai_warehouse/cache",
        description="Root directory for cache",
    )
    redis_enable: bool = Field(default=False, description="Enable Redis caching")
    redis_url: str = Field(
        default="redis://localhost:6379/1", description="Redis URL for caching"
    )
    auto_cleanup: bool = Field(default=True, description="Enable auto cleanup")
    max_cache_size_gb: int = Field(default=50, description="Max cache size in GB")


class LoggingConfig(BaseSettings):
    """Logging Configuration"""

    model_config = SettingsConfigDict(env_prefix="LOG_")

    level: str = Field(default="INFO", description="Log level")
    format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log format",
    )
    file_path: Optional[str] = Field(
        default="./logs/youtube_automation.log", description="Log file path"
    )


class YouTubeAPISettings(BaseSettings):
    """YouTube API specific settings"""

    model_config = SettingsConfigDict(env_prefix="YOUTUBE_")

    api_key: str = Field(default="", description="YouTube Data API v3 key")
    quota_per_day: int = Field(default=10000, description="Daily API quota limit")
    max_results_per_page: int = Field(
        default=50, description="Max results per API call"
    )
    enable_fallback_scraping: bool = Field(
        default=True, description="Use scraping if API fails"
    )

    @property
    def daily_quota_per_request(self) -> float:
        """Calculate quota units per request for rate limiting"""
        return 100.0


class ScrapingSettings(BaseSettings):
    """Web scraping configuration"""

    model_config = SettingsConfigDict(env_prefix="SCRAPING_")

    use_selenium: bool = Field(
        default=True, description="Use Selenium for dynamic content"
    )
    use_playwright: bool = Field(
        default=False, description="Use Playwright (alternative)"
    )
    headless: bool = Field(default=True, description="Run browser in headless mode")

    # Rate limiting
    request_delay_seconds: float = Field(
        default=2.0, description="Delay between requests"
    )
    max_retries: int = Field(default=3, description="Max retry attempts")
    timeout_seconds: int = Field(default=30, description="Request timeout")

    # Browser settings
    user_agent: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        description="User agent string",
    )


class AnalysisSettings(BaseSettings):
    """Video analysis configuration"""

    model_config = SettingsConfigDict(env_prefix="ANALYSIS_")

    enable_sentiment: bool = Field(
        default=True, description="Enable sentiment analysis"
    )
    enable_topic_modeling: bool = Field(
        default=True, description="Enable topic modeling"
    )
    enable_transcript: bool = Field(
        default=False, description="Download video transcripts"
    )

    # NLP settings
    min_comment_length: int = Field(
        default=10, description="Min comment length for analysis"
    )
    max_comments_per_video: int = Field(
        default=1000, description="Max comments to analyze"
    )


class StorageSettings(BaseSettings):
    """Data storage configuration"""

    model_config = SettingsConfigDict(env_prefix="STORAGE_")

    output_format: str = Field(
        default="json", description="Default output format (json/csv/parquet)"
    )
    enable_compression: bool = Field(default=True, description="Compress output files")
    retention_days: int = Field(default=30, description="Days to keep raw data")


class SecuritySettings(BaseSettings):
    """Security Configuration"""

    model_config = SettingsConfigDict(env_prefix="SECURITY_")

    rate_limit_per_minute: int = Field(default=60, description="Requests per minute")
    rate_limit_per_hour: int = Field(default=1000, description="Requests per hour")
    enable_cors: bool = Field(default=True, description="Enable CORS")


# ============================================================================
# Main Configuration Class
# ============================================================================


class Config:
    """
    Main Application Configuration
    Aggregates all configuration modules with unified access
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize application configuration

        Args:
            config_path: Optional YAML config file path
        """
        self.config_path = config_path or "configs/app.yaml"
        self.yaml_config = self._load_yaml_config()

        # Initialize component configs
        self.api = APIConfig()
        self.database = DatabaseConfig()
        self.cache = CacheConfig()
        self.logging = LoggingConfig()
        self.security = SecuritySettings()

        # YouTube-specific settings
        self.youtube_api = YouTubeAPISettings()
        self.scraping = ScrapingSettings()
        self.analysis = AnalysisSettings()
        self.storage = StorageSettings()

        # Ensure cache directories exist
        self._create_cache_directories()

    def _load_yaml_config(self) -> Dict[str, Any]:
        """Load YAML configuration file"""
        config_file = Path(self.config_path)

        if not config_file.exists():
            logger.warning(f"Config file not found: {config_file}, using defaults")
            return {}

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {}

    def _create_cache_directories(self) -> None:
        """Create necessary cache directories"""
        cache_root = Path(self.cache.cache_root)

        directories = [
            cache_root,
            cache_root / "videos",
            cache_root / "channels",
            cache_root / "analysis",
            cache_root / "models",
            cache_root / "datasets",
            cache_root / "outputs",
            cache_root / "temp",
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def get_output_dir(self, subdir: str = "") -> Path:
        """Get output directory for YouTube data"""
        cache_root = Path(self.cache.cache_root)

        if subdir:
            output_path = cache_root / "outputs" / subdir
        else:
            output_path = cache_root / "outputs"

        output_path.mkdir(parents=True, exist_ok=True)
        return output_path

    def get_cache_dir(self, cache_type: str = "videos") -> Path:
        """Get cache directory for YouTube data"""
        cache_path = Path(self.cache.cache_root) / cache_type
        cache_path.mkdir(parents=True, exist_ok=True)
        return cache_path

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by dot notation key"""
        keys = key.split(".")
        value = self.yaml_config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def to_dict(self) -> Dict[str, Any]:
        """Export full configuration as dictionary"""
        return {
            "api": self.api.model_dump(),
            "database": self.database.model_dump(),
            "cache": self.cache.model_dump(),
            "logging": self.logging.model_dump(),
            "security": self.security.model_dump(),
            "youtube_api": self.youtube_api.model_dump(),
            "scraping": self.scraping.model_dump(),
            "analysis": self.analysis.model_dump(),
            "storage": self.storage.model_dump(),
        }

    def get_summary(self) -> Dict[str, Any]:
        """Get configuration summary"""
        return {
            "api": {
                "host": self.api.host,
                "port": self.api.port,
                "prefix": self.api.prefix,
                "debug": self.api.debug,
            },
            "database": {
                "url": self.database.url,
            },
            "cache": {
                "cache_root": self.cache.cache_root,
                "redis_enabled": self.cache.redis_enable,
            },
            "youtube": {
                "api_key_set": bool(self.youtube_api.api_key),
                "fallback_scraping": self.youtube_api.enable_fallback_scraping,
            },
            "scraping": {
                "use_selenium": self.scraping.use_selenium,
                "headless": self.scraping.headless,
            },
        }


# ============================================================================
# Global Configuration Instance (Singleton)
# ============================================================================

_config: Optional[Config] = None
_config_lock = threading.Lock()


@lru_cache()
def get_config(config_path: Optional[str] = None) -> Config:
    """
    Get or create global configuration instance (Thread-safe singleton)

    Args:
        config_path: Optional path to config file

    Returns:
        Config instance
    """
    global _config

    if _config is None:
        with _config_lock:
            if _config is None:
                _config = Config(config_path)
                logger.info("✅ Configuration initialized")

    return _config


def reload_config(config_path: Optional[str] = None) -> Config:
    """
    Force reload configuration

    Args:
        config_path: Optional new config path

    Returns:
        New Config instance
    """
    global _config

    with _config_lock:
        get_config.cache_clear()  # Clear lru_cache
        _config = Config(config_path)
        logger.info("🔄 Configuration reloaded")

    return _config


def reset_config() -> None:
    """Reset global configuration (mainly for testing)"""
    global _config

    with _config_lock:
        get_config.cache_clear()
        _config = None
        logger.info("🗑️ Configuration reset")


# ============================================================================
# Configuration Validation
# ============================================================================


def validate_config(config: Optional[Config] = None) -> Dict[str, Any]:
    """
    Validate configuration

    Args:
        config: Config instance (uses global if None)

    Returns:
        Validation result with errors and warnings
    """
    if config is None:
        config = get_config()

    errors = []
    warnings = []

    # Check cache root
    cache_root = Path(config.cache.cache_root)
    if not cache_root.exists():
        try:
            cache_root.mkdir(parents=True, exist_ok=True)
            warnings.append(f"Created cache root: {cache_root}")
        except Exception as e:
            errors.append(f"Cannot create cache root: {e}")

    # Check log path
    if config.logging.file_path:
        log_path = Path(config.logging.file_path)
        if not log_path.parent.exists():
            try:
                log_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                errors.append(f"Cannot create log directory: {e}")

    # Check YouTube API key
    if not config.youtube_api.api_key:
        warnings.append("YouTube API key not set - will use scraping fallback")

    # Check scraping settings
    if config.scraping.use_selenium and config.scraping.use_playwright:
        errors.append("Cannot use both Selenium and Playwright - choose one")

    # Check database URL
    if not config.database.url:
        errors.append("Database URL not configured")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


# ============================================================================
# Convenience Functions
# ============================================================================


def get_db_settings() -> DatabaseConfig:
    """Get database settings (shortcut)"""
    return get_config().database


def get_youtube_settings() -> YouTubeAPISettings:
    """Get YouTube API settings (shortcut)"""
    return get_config().youtube_api


def get_scraping_settings() -> ScrapingSettings:
    """Get scraping settings (shortcut)"""
    return get_config().scraping


def setup_logging(config: Optional[Config] = None) -> None:
    """
    Setup logging based on configuration

    Args:
        config: Config instance (uses global if None)
    """
    import logging.handlers

    if config is None:
        config = get_config()

    # Set log level
    log_level = getattr(logging, config.logging.level.upper(), logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(config.logging.format))
    root_logger.addHandler(console_handler)

    # File handler (if specified)
    if config.logging.file_path:
        log_path = Path(config.logging.file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_path,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(logging.Formatter(config.logging.format))
        root_logger.addHandler(file_handler)

    logger.info(f"📝 Logging configured: level={config.logging.level}")


# ============================================================================
# Main Entry Point (Testing)
# ============================================================================

if __name__ == "__main__":
    """Test configuration loading and validation"""

    print("🔧 Testing Configuration System...")
    print("=" * 60)

    # Load configuration
    config = get_config()

    # Print summary
    import json

    print("\n📋 Configuration Summary:")
    print(json.dumps(config.get_summary(), indent=2))

    # Validate configuration
    print("\n🔍 Validating Configuration...")
    validation_result = validate_config(config)

    if validation_result["errors"]:
        print("\n❌ Validation Errors:")
        for error in validation_result["errors"]:
            print(f"  - {error}")

    if validation_result["warnings"]:
        print("\n⚠️  Configuration Warnings:")
        for warning in validation_result["warnings"]:
            print(f"  - {warning}")

    if validation_result["valid"]:
        print("\n✅ Configuration is valid!")

    print("=" * 60)
