"""
Configuration Management for YouTube Web Automation Analysis
Standalone configuration system with environment variable overrides
"""

import os
import yaml
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional, Literal, List
from functools import lru_cache
from pydantic import Field, BaseModel, field_validator
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


class FeaturesConfig(BaseSettings):
    """Feature Flags Configuration"""

    model_config = SettingsConfigDict(env_prefix="FEATURE_")

    enable_caption: bool = Field(default=True, description="Enable caption feature")
    enable_vqa: bool = Field(default=True, description="Enable VQA feature")
    enable_chat: bool = Field(default=True, description="Enable chat feature")
    enable_rag: bool = Field(default=True, description="Enable RAG feature")
    enable_agent: bool = Field(default=True, description="Enable agent feature")
    enable_game: bool = Field(default=True, description="Enable game feature")
    enable_t2i: bool = Field(default=True, description="Enable T2I feature")
    enable_export: bool = Field(default=True, description="Enable export feature")
    enable_training: bool = Field(default=True, description="Enable training feature")
    enable_monitoring: bool = Field(default=True, description="Enable monitoring")

    preload_models: bool = Field(default=False, description="Preload models at startup")


class YouTubeAPISettings(BaseSettings):
    """YouTube API specific settings"""

    model_config = SettingsConfigDict(env_prefix="YOUTUBE_")

    api_key: str = Field(default="", description="YouTube Data API v3 key")
    max_results_per_page: int = Field(
        default=50, description="Max results per API call"
    )
    enable_fallback_scraping: bool = Field(
        default=True, description="Use scraping if API fails"
    )
    # Quota Management
    daily_quota_limit: int = Field(
        default=10000, description="YouTube API daily quota limit"
    )
    quota_warning_threshold: int = Field(
        default=8000, description="Warn when quota usage exceeds this value"
    )

    # Rate Limiting
    requests_per_second: float = Field(
        default=10.0, description="Maximum API requests per second"
    )
    burst_capacity: int = Field(
        default=20, description="Maximum burst request capacity"
    )

    # Request Settings
    max_retries: int = Field(
        default=3, description="Maximum retry attempts for failed requests"
    )
    request_timeout: int = Field(default=30, description="Request timeout in seconds")
    backoff_base: float = Field(
        default=2.0, description="Exponential backoff base multiplier"
    )

    # Search Defaults
    default_search_results: int = Field(
        default=10, description="Default number of search results"
    )
    max_search_results: int = Field(
        default=50, description="Maximum search results per request"
    )
    default_search_order: Literal[
        "date", "rating", "relevance", "title", "viewCount"
    ] = Field(default="relevance", description="Default search result ordering")

    # Comment Fetching
    default_comment_count: int = Field(
        default=100, description="Default number of comments to fetch"
    )
    max_comment_count: int = Field(
        default=1000, description="Maximum comments to fetch per video"
    )
    default_comment_order: Literal["time", "relevance"] = Field(
        default="relevance", description="Default comment ordering"
    )

    # Caching
    enable_response_cache: bool = Field(
        default=True, description="Enable API response caching"
    )
    cache_ttl_seconds: int = Field(
        default=3600, description="Cache TTL in seconds (1 hour default)"
    )

    # Features
    enable_adaptive_rate_limiting: bool = Field(
        default=True, description="Enable adaptive rate limiting based on errors"
    )
    enable_quota_tracking: bool = Field(
        default=True, description="Enable quota usage tracking"
    )

    @property
    def daily_quota_per_request(self) -> float:
        """Calculate quota units per request for rate limiting"""
        return 100.0

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """Validate API key format"""
        if v and len(v) < 20:
            raise ValueError("YouTube API key appears to be invalid (too short)")
        return v

    @field_validator("daily_quota_limit")
    @classmethod
    def validate_quota(cls, v: int) -> int:
        """Validate quota limit"""
        if v < 100:
            raise ValueError("Daily quota limit must be at least 100")
        return v


class ScrapingSettings(BaseSettings):
    """Web scraping configuration"""

    model_config = SettingsConfigDict(env_prefix="SCRAPING_")

    enabled: bool = Field(default=True, description="Enable web scraping fallback")
    use_selenium: bool = Field(
        default=True, description="Use Selenium for dynamic content"
    )
    use_playwright: bool = Field(
        default=False, description="Use Playwright (alternative)"
    )
    # Browser Settings
    browser_type: Literal["chromium", "firefox", "webkit"] = Field(
        default="chromium", description="Playwright browser type"
    )
    headless: bool = Field(default=True, description="Run browser in headless mode")
    user_agent: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        description="User agent string",
    )

    # Rate limiting
    request_delay_seconds: float = Field(
        default=2.0, description="Delay between requests"
    )
    max_retries: int = Field(default=3, description="Max retry attempts")
    timeout_seconds: int = Field(default=30, description="Request timeout")
    delay_min: float = Field(
        default=2.0, description="Min delay between requests (seconds)"
    )
    delay_max: float = Field(
        default=5.0, description="Max delay between requests (seconds)"
    )

    # Performance
    max_concurrent_browsers: int = Field(
        default=3, description="Maximum concurrent browser instances"
    )
    page_timeout: int = Field(
        default=30000, description="Page load timeout in milliseconds"
    )
    navigation_timeout: int = Field(
        default=30000, description="Navigation timeout in milliseconds"
    )

    # Anti-Detection
    use_stealth_mode: bool = Field(
        default=True, description="Enable stealth mode to avoid bot detection"
    )
    randomize_user_agent: bool = Field(
        default=True, description="Randomize user agent strings"
    )
    enable_cookies: bool = Field(default=True, description="Enable cookie persistence")

    # Rate Limiting
    requests_per_minute: int = Field(
        default=30, description="Maximum scraping requests per minute"
    )
    min_delay_seconds: float = Field(
        default=1.0, description="Minimum delay between requests"
    )
    max_delay_seconds: float = Field(
        default=3.0, description="Maximum delay between requests"
    )

    # Retry Logic
    max_retries: int = Field(
        default=3, description="Maximum retry attempts for failed scrapes"
    )
    retry_delay_seconds: float = Field(
        default=5.0, description="Delay between retry attempts"
    )

    # Proxy Settings (Optional)
    enable_proxy: bool = Field(default=False, description="Enable proxy rotation")
    proxy_list: str = Field(
        default="", description="Comma-separated list of proxy URLs"
    )

    # Caching
    cache_html: bool = Field(
        default=True, description="Cache scraped HTML for debugging"
    )
    cache_screenshots: bool = Field(
        default=False, description="Save screenshots of scraped pages"
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
    language_detection: bool = Field(
        default=True, description="Enable language detection"
    )
    batch_size: int = Field(default=32, description="Batch size for analysis")

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
    auto_backup: bool = Field(default=True, description="Enable automatic backups")
    backup_interval_hours: int = Field(
        default=24, description="Backup interval (hours)"
    )


class SecuritySettings(BaseSettings):
    """Security Configuration"""

    model_config = SettingsConfigDict(env_prefix="SECURITY_")

    rate_limit_per_minute: int = Field(default=60, description="Requests per minute")
    rate_limit_per_hour: int = Field(default=1000, description="Requests per hour")
    enable_cors: bool = Field(default=True, description="Enable CORS")


class CeleryConfig(BaseSettings):
    """Celery Task Queue Configuration"""

    model_config = SettingsConfigDict(env_prefix="CELERY_")

    # Broker Settings
    broker_url: str = Field(
        default="redis://localhost:6379/0",
        description="Celery message broker URL (Redis or RabbitMQ)",
    )
    result_backend: str = Field(
        default="redis://localhost:6379/0",
        description="Task result storage backend URL",
    )

    # Task Serialization
    task_serializer: str = Field(
        default="json", description="Task serialization format"
    )
    result_serializer: str = Field(
        default="json", description="Result serialization format"
    )
    accept_content: List[str] = Field(
        default=["json"], description="Accepted content types"
    )

    # Worker Settings
    worker_concurrency: int = Field(
        default=4, description="Number of concurrent worker processes"
    )
    worker_prefetch_multiplier: int = Field(
        default=4, description="Tasks to prefetch per worker"
    )
    worker_max_tasks_per_child: int = Field(
        default=1000,
        description="Max tasks before worker restart (memory leak prevention)",
    )

    # Task Execution Settings
    task_track_started: bool = Field(
        default=True, description="Track when tasks start executing"
    )
    task_time_limit: int = Field(
        default=3600, description="Hard task timeout in seconds (1 hour)"
    )
    task_soft_time_limit: int = Field(
        default=1800, description="Soft task timeout in seconds (30 min)"
    )
    task_acks_late: bool = Field(
        default=True, description="Acknowledge tasks after completion (safer)"
    )
    task_reject_on_worker_lost: bool = Field(
        default=True, description="Reject tasks if worker dies"
    )

    # Retry Settings
    task_max_retries: int = Field(
        default=3, description="Maximum retry attempts for failed tasks"
    )
    task_default_retry_delay: int = Field(
        default=60, description="Default delay between retries (seconds)"
    )
    task_retry_backoff: bool = Field(
        default=True, description="Use exponential backoff for retries"
    )
    task_retry_backoff_max: int = Field(
        default=600, description="Maximum retry delay (seconds)"
    )

    # Queue Settings
    task_default_queue: str = Field(
        default="default", description="Default task queue name"
    )
    task_queues: List[str] = Field(
        default=["default", "scraping", "analysis", "priority"],
        description="Available task queues",
    )
    task_routes: dict = Field(
        default={
            "tasks.scraping.*": {"queue": "scraping"},
            "tasks.analysis.*": {"queue": "analysis"},
            "tasks.priority.*": {"queue": "priority"},
        },
        description="Task routing configuration",
    )

    # Rate Limiting
    task_default_rate_limit: str = Field(
        default="10/m", description="Default rate limit for tasks (10 per minute)"
    )
    worker_disable_rate_limits: bool = Field(
        default=False, description="Disable rate limiting for workers"
    )

    # Result Backend Settings
    result_expires: int = Field(
        default=86400, description="Task result expiration time (24 hours)"
    )
    result_persistent: bool = Field(default=True, description="Persist task results")

    # Monitoring
    enable_flower: bool = Field(
        default=True, description="Enable Flower monitoring dashboard"
    )
    flower_port: int = Field(default=5555, description="Flower dashboard port")
    flower_basic_auth: str = Field(
        default="", description="Flower basic auth (format: username:password)"
    )

    # Beat Scheduler Settings
    beat_scheduler: str = Field(
        default="celery.beat:PersistentScheduler",
        description="Celery Beat scheduler class",
    )
    beat_schedule_filename: str = Field(
        default="celerybeat-schedule", description="Beat schedule database filename"
    )
    beat_max_loop_interval: int = Field(
        default=5, description="Maximum beat loop interval (seconds)"
    )

    # Logging
    worker_hijack_root_logger: bool = Field(
        default=False, description="Don't hijack root logger"
    )
    worker_log_format: str = Field(
        default="[%(asctime)s: %(levelname)s/%(processName)s] %(message)s",
        description="Worker log format",
    )

    # Task Priority Settings
    task_inherit_parent_priority: bool = Field(
        default=True, description="Child tasks inherit parent priority"
    )

    # Performance Optimization
    worker_prefetch_multiplier: int = Field(
        default=4, description="How many messages to prefetch"
    )
    task_compression: Literal["gzip", "bzip2", ""] = Field(
        default="", description="Task compression algorithm"
    )

    # Error Handling
    task_send_error_emails: bool = Field(
        default=False, description="Send emails on task errors"
    )
    task_error_whitelist: List[str] = Field(
        default=[], description="Errors to ignore in task execution"
    )


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
        self.celery = CeleryConfig()

        # YouTube-specific settings
        self.features = FeaturesConfig()
        self.youtube_api = YouTubeAPISettings()
        self.scraping = ScrapingSettings()
        self.analysis = AnalysisSettings()
        self.storage = StorageSettings()

        # Internal cache
        self._yaml_cache: Dict[str, Any] = {}

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
            "app": self.yaml_config.get("app", {}),
            "features": {
                "caption": self.features.enable_caption,
                "vqa": self.features.enable_vqa,
                "chat": self.features.enable_chat,
                "rag": self.features.enable_rag,
                "agent": self.features.enable_agent,
                "game": self.features.enable_game,
                "t2i": self.features.enable_t2i,
                "export": self.features.enable_export,
                "training": self.features.enable_training,
                "monitoring": self.features.enable_monitoring,
            },
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
            "youtube_api": {
                "enabled": bool(self.youtube_api.api_key),
                "quota_limit": self.youtube_api.daily_quota_limit,
                "requests_per_second": self.youtube_api.requests_per_second,
                "cache_enabled": self.youtube_api.enable_response_cache,
                "api_key_set": bool(self.youtube_api.api_key),
                "fallback_scraping": self.youtube_api.enable_fallback_scraping,
            },
            "scraping": {
                "use_selenium": self.scraping.use_selenium,
                "enabled": self.scraping.enabled,
                "browser_type": self.scraping.browser_type,
                "headless": self.scraping.headless,
                "max_browsers": self.scraping.max_concurrent_browsers,
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
