"""
Services Package
Business logic layer for YouTube Web Automation Analysis
"""

from .base_service import BaseService, CRUDService
from .video_service import VideoService
from .caption_service import CaptionService
from .vqa_service import VQAService
from .chat_service import ChatService
from .rag_service import RAGService
from . import task_tracking_service as TaskTrackingService
from .exceptions import (
    # Base
    ServiceError,

    # Resource Errors
    ResourceNotFoundError,
    ResourceAlreadyExistsError,
    ResourceConflictError,

    # Validation Errors
    ValidationError,
    BusinessRuleViolationError,

    # External Service Errors
    ExternalServiceError,
    YouTubeAPIError,
    RateLimitExceededError,

    # Processing Errors
    ProcessingError,
    AnalysisError,
    ScrapingError,

    # Database Errors
    DatabaseError,
    TransactionError,

    # Permission Errors
    PermissionDeniedError,

    # Configuration Errors
    ConfigurationError,

    # Utility Functions
    is_retryable_error,
    get_retry_delay,
    error_to_http_status,
)

__all__ = [
    # Base Classes
    "BaseService",
    "CRUDService",

    # Services
    "VideoService",
    "CaptionService",
    "VQAService",
    "ChatService",
    "RAGService",
    "TaskTrackingService",

    # Base Exception
    "ServiceError",

    # Resource Errors
    "ResourceNotFoundError",
    "ResourceAlreadyExistsError",
    "ResourceConflictError",

    # Validation Errors
    "ValidationError",
    "BusinessRuleViolationError",

    # External Service Errors
    "ExternalServiceError",
    "YouTubeAPIError",
    "RateLimitExceededError",

    # Processing Errors
    "ProcessingError",
    "AnalysisError",
    "ScrapingError",

    # Database Errors
    "DatabaseError",
    "TransactionError",

    # Permission Errors
    "PermissionDeniedError",

    # Configuration Errors
    "ConfigurationError",

    # Utility Functions
    "is_retryable_error",
    "get_retry_delay",
    "error_to_http_status",
    "BusinessRuleViolationError",

    # External Service Errors
    "ExternalServiceError",
    "YouTubeAPIError",
    "RateLimitExceededError",

    # Processing Errors
    "ProcessingError",
    "AnalysisError",
    "ScrapingError",

    # Database Errors
    "DatabaseError",
    "TransactionError",

    # Permission Errors
    "PermissionDeniedError",

    # Configuration Errors
    "ConfigurationError",

    # Utility Functions
    "is_retryable_error",
    "get_retry_delay",
    "error_to_http_status",
]

# Package metadata
__version__ = "0.1.0"
__author__ = "YouTube Analysis Team"
__description__ = "Service layer for YouTube Web Automation Analysis"