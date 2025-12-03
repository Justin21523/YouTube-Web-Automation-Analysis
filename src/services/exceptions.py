# src/services/exceptions.py
"""
Service Layer Exceptions
Comprehensive exception hierarchy for business logic errors
"""

from typing import Optional, Dict, Any


# ============================================================================
# Base Exception
# ============================================================================


class ServiceError(Exception):
    """
    Base exception for all service layer errors

    Attributes:
        message: Human-readable error message
        code: Machine-readable error code
        details: Additional error context
    """

    def __init__(
        self,
        message: str,
        code: str = "SERVICE_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API responses"""
        return {
            "error": self.code,
            "message": self.message,
            "details": self.details,
        }

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


# ============================================================================
# Resource Errors
# ============================================================================


class ResourceNotFoundError(ServiceError):
    """Resource does not exist"""

    def __init__(self, resource_type: str, resource_id: str):
        super().__init__(
            message=f"{resource_type} not found: {resource_id}",
            code="RESOURCE_NOT_FOUND",
            details={"resource_type": resource_type, "resource_id": resource_id},
        )
        self.resource_type = resource_type
        self.resource_id = resource_id


class ResourceAlreadyExistsError(ServiceError):
    """Resource already exists"""

    def __init__(self, resource_type: str, resource_id: str):
        super().__init__(
            message=f"{resource_type} already exists: {resource_id}",
            code="RESOURCE_ALREADY_EXISTS",
            details={"resource_type": resource_type, "resource_id": resource_id},
        )
        self.resource_type = resource_type
        self.resource_id = resource_id


class ResourceConflictError(ServiceError):
    """Resource conflict (e.g., concurrent modification)"""

    def __init__(self, message: str, resource_type: str, resource_id: str):
        super().__init__(
            message=message,
            code="RESOURCE_CONFLICT",
            details={"resource_type": resource_type, "resource_id": resource_id},
        )


# ============================================================================
# Validation Errors
# ============================================================================


class ValidationError(ServiceError):
    """Input validation failed"""

    def __init__(self, message: str, field: Optional[str] = None):
        details = {}
        if field:
            details["field"] = field
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            details=details,
        )
        self.field = field


class BusinessRuleViolationError(ServiceError):
    """Business rule was violated"""

    def __init__(self, message: str, rule: str):
        super().__init__(
            message=message,
            code="BUSINESS_RULE_VIOLATION",
            details={"rule": rule},
        )
        self.rule = rule


# ============================================================================
# External Service Errors
# ============================================================================


class ExternalServiceError(ServiceError):
    """Error communicating with external service"""

    def __init__(
        self,
        message: str,
        service_name: str,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(
            message=message,
            code="EXTERNAL_SERVICE_ERROR",
            details={
                "service_name": service_name,
                "original_error": str(original_error) if original_error else None,
            },
        )
        self.service_name = service_name
        self.original_error = original_error


class YouTubeAPIError(ExternalServiceError):
    """YouTube API specific error"""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(
            message=message,
            service_name="YouTube API",
            original_error=original_error,
        )
        self.code = "YOUTUBE_API_ERROR"
        self.status_code = status_code
        if status_code:
            self.details["status_code"] = status_code


class RateLimitExceededError(ExternalServiceError):
    """Rate limit exceeded"""

    def __init__(
        self,
        service_name: str,
        retry_after: Optional[int] = None,
    ):
        super().__init__(
            message=f"Rate limit exceeded for {service_name}",
            service_name=service_name,
        )
        self.code = "RATE_LIMIT_EXCEEDED"
        self.retry_after = retry_after
        if retry_after:
            self.details["retry_after_seconds"] = retry_after


# ============================================================================
# Processing Errors
# ============================================================================


class ProcessingError(ServiceError):
    """Error during data processing"""

    def __init__(
        self,
        message: str,
        operation: str,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(
            message=message,
            code="PROCESSING_ERROR",
            details={
                "operation": operation,
                "original_error": str(original_error) if original_error else None,
            },
        )
        self.operation = operation
        self.original_error = original_error


class AnalysisError(ProcessingError):
    """Error during analysis operation"""

    def __init__(
        self,
        message: str,
        analysis_type: str,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(
            message=message,
            operation=f"analysis:{analysis_type}",
            original_error=original_error,
        )
        self.code = "ANALYSIS_ERROR"
        self.analysis_type = analysis_type
        self.details["analysis_type"] = analysis_type


class ScrapingError(ProcessingError):
    """Error during web scraping"""

    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(
            message=message,
            operation="scraping",
            original_error=original_error,
        )
        self.code = "SCRAPING_ERROR"
        self.url = url
        if url:
            self.details["url"] = url


# ============================================================================
# Database Errors
# ============================================================================


class DatabaseError(ServiceError):
    """Database operation failed"""

    def __init__(
        self,
        message: str,
        operation: str,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(
            message=message,
            code="DATABASE_ERROR",
            details={
                "operation": operation,
                "original_error": str(original_error) if original_error else None,
            },
        )
        self.operation = operation
        self.original_error = original_error


class TransactionError(DatabaseError):
    """Database transaction failed"""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(
            message=message,
            operation="transaction",
            original_error=original_error,
        )
        self.code = "TRANSACTION_ERROR"


# ============================================================================
# Permission Errors
# ============================================================================


class PermissionDeniedError(ServiceError):
    """Permission denied for operation"""

    def __init__(
        self,
        message: str = "Permission denied",
        resource: Optional[str] = None,
        action: Optional[str] = None,
    ):
        details = {}
        if resource:
            details["resource"] = resource
        if action:
            details["action"] = action
        super().__init__(
            message=message,
            code="PERMISSION_DENIED",
            details=details,
        )


# ============================================================================
# Configuration Errors
# ============================================================================


class ConfigurationError(ServiceError):
    """Configuration error"""

    def __init__(self, message: str, config_key: Optional[str] = None):
        details = {}
        if config_key:
            details["config_key"] = config_key
        super().__init__(
            message=message,
            code="CONFIGURATION_ERROR",
            details=details,
        )


# ============================================================================
# Utility Functions
# ============================================================================


def is_retryable_error(error: Exception) -> bool:
    """
    Check if an error is retryable

    Args:
        error: Exception to check

    Returns:
        True if the error is retryable
    """
    retryable_types = (
        RateLimitExceededError,
        TransactionError,
    )

    if isinstance(error, retryable_types):
        return True

    # Check for specific external service errors
    if isinstance(error, ExternalServiceError):
        return True

    # Check for specific database errors
    if isinstance(error, DatabaseError):
        return error.operation != "validation"

    return False


def get_retry_delay(error: Exception, attempt: int = 1) -> int:
    """
    Get retry delay in seconds based on error type

    Args:
        error: The exception
        attempt: Current attempt number (for exponential backoff)

    Returns:
        Delay in seconds before retry
    """
    base_delay = 1

    if isinstance(error, RateLimitExceededError) and error.retry_after:
        return error.retry_after

    if isinstance(error, RateLimitExceededError):
        base_delay = 60  # Default 60 seconds for rate limits

    if isinstance(error, ExternalServiceError):
        base_delay = 5

    if isinstance(error, TransactionError):
        base_delay = 1

    # Exponential backoff with jitter
    import random
    delay = base_delay * (2 ** (attempt - 1))
    jitter = random.uniform(0, delay * 0.1)

    return min(int(delay + jitter), 300)  # Max 5 minutes


def error_to_http_status(error: ServiceError) -> int:
    """
    Map service error to HTTP status code

    Args:
        error: Service error

    Returns:
        HTTP status code
    """
    status_map = {
        "RESOURCE_NOT_FOUND": 404,
        "RESOURCE_ALREADY_EXISTS": 409,
        "RESOURCE_CONFLICT": 409,
        "VALIDATION_ERROR": 400,
        "BUSINESS_RULE_VIOLATION": 422,
        "EXTERNAL_SERVICE_ERROR": 502,
        "YOUTUBE_API_ERROR": 502,
        "RATE_LIMIT_EXCEEDED": 429,
        "PROCESSING_ERROR": 500,
        "ANALYSIS_ERROR": 500,
        "SCRAPING_ERROR": 500,
        "DATABASE_ERROR": 500,
        "TRANSACTION_ERROR": 500,
        "PERMISSION_DENIED": 403,
        "CONFIGURATION_ERROR": 500,
        "SERVICE_ERROR": 500,
    }

    return status_map.get(error.code, 500)


# ============================================================================
# Export
# ============================================================================

__all__ = [
    # Base
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
]
