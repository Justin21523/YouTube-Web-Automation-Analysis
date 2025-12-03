# src/services/base_service.py
"""
Base Service Classes
Foundation classes for the service layer
"""

import logging
from typing import TypeVar, Generic, Optional, Any, Dict, List, Tuple
from abc import ABC, abstractmethod
from sqlalchemy.ext.asyncio import AsyncSession

from .exceptions import ValidationError, ProcessingError


T = TypeVar("T")


class BaseService(ABC):
    """
    Abstract base class for all services

    Provides:
    - Logging setup
    - Cache integration
    - Config access
    - Common validation methods
    - Error handling utilities
    """

    def __init__(self, cache=None, config=None):
        """
        Initialize base service

        Args:
            cache: Optional cache instance
            config: Optional configuration instance
        """
        self._cache = cache
        self._config = config
        self._logger = logging.getLogger(
            f"{self.__class__.__module__}.{self.__class__.__name__}"
        )

    # ========================================================================
    # Abstract Methods
    # ========================================================================

    @abstractmethod
    def get_service_name(self) -> str:
        """Return the service name for logging and metrics"""
        pass

    # ========================================================================
    # Logging Methods
    # ========================================================================

    def log_debug(self, message: str, **kwargs) -> None:
        """Log debug message"""
        self._logger.debug(f"[{self.get_service_name()}] {message}", extra=kwargs)

    def log_info(self, message: str, **kwargs) -> None:
        """Log info message"""
        self._logger.info(f"[{self.get_service_name()}] {message}", extra=kwargs)

    def log_warning(self, message: str, **kwargs) -> None:
        """Log warning message"""
        self._logger.warning(f"[{self.get_service_name()}] {message}", extra=kwargs)

    def log_error(self, message: str, error: Optional[Exception] = None, **kwargs) -> None:
        """Log error message"""
        if error:
            self._logger.error(
                f"[{self.get_service_name()}] {message}: {error}",
                exc_info=error,
                extra=kwargs,
            )
        else:
            self._logger.error(f"[{self.get_service_name()}] {message}", extra=kwargs)

    # ========================================================================
    # Validation Methods
    # ========================================================================

    def validate_required(self, value: Any, field_name: str) -> None:
        """
        Validate that a required field has a value

        Args:
            value: The value to check
            field_name: Name of the field for error message

        Raises:
            ValidationError: If value is None or empty
        """
        if value is None:
            raise ValidationError(f"{field_name} is required", field=field_name)
        if isinstance(value, str) and not value.strip():
            raise ValidationError(f"{field_name} cannot be empty", field=field_name)

    def validate_positive(self, value: int, field_name: str) -> None:
        """
        Validate that a value is positive

        Args:
            value: The value to check
            field_name: Name of the field for error message

        Raises:
            ValidationError: If value is not positive
        """
        if value is None or value <= 0:
            raise ValidationError(
                f"{field_name} must be a positive integer", field=field_name
            )

    def validate_non_negative(self, value: int, field_name: str) -> None:
        """
        Validate that a value is non-negative

        Args:
            value: The value to check
            field_name: Name of the field for error message

        Raises:
            ValidationError: If value is negative
        """
        if value is None or value < 0:
            raise ValidationError(
                f"{field_name} must be non-negative", field=field_name
            )

    def validate_range(
        self, value: int, field_name: str, min_val: int, max_val: int
    ) -> None:
        """
        Validate that a value is within a range

        Args:
            value: The value to check
            field_name: Name of the field for error message
            min_val: Minimum allowed value
            max_val: Maximum allowed value

        Raises:
            ValidationError: If value is out of range
        """
        if value is None or value < min_val or value > max_val:
            raise ValidationError(
                f"{field_name} must be between {min_val} and {max_val}",
                field=field_name,
            )

    def validate_list_not_empty(self, value: List, field_name: str) -> None:
        """
        Validate that a list is not empty

        Args:
            value: The list to check
            field_name: Name of the field for error message

        Raises:
            ValidationError: If list is None or empty
        """
        if not value:
            raise ValidationError(f"{field_name} cannot be empty", field=field_name)

    def validate_string_length(
        self, value: str, field_name: str, min_len: int = 0, max_len: int = 10000
    ) -> None:
        """
        Validate string length

        Args:
            value: String to validate
            field_name: Name of the field for error message
            min_len: Minimum length
            max_len: Maximum length

        Raises:
            ValidationError: If length is out of bounds
        """
        if value is None:
            if min_len > 0:
                raise ValidationError(f"{field_name} is required", field=field_name)
            return

        if len(value) < min_len:
            raise ValidationError(
                f"{field_name} must be at least {min_len} characters",
                field=field_name,
            )

        if len(value) > max_len:
            raise ValidationError(
                f"{field_name} must be at most {max_len} characters",
                field=field_name,
            )

    # ========================================================================
    # Cache Methods
    # ========================================================================

    def get_cache_key(self, *parts: str) -> str:
        """
        Generate a cache key from parts

        Args:
            *parts: Key components

        Returns:
            Formatted cache key
        """
        service_name = self.get_service_name()
        return f"{service_name}:{':'.join(str(p) for p in parts)}"

    def get_from_cache(self, key: str) -> Optional[Any]:
        """
        Get value from cache

        Args:
            key: Cache key

        Returns:
            Cached value or None
        """
        if self._cache is None:
            return None
        try:
            return self._cache.get_cache_item(key)
        except Exception as e:
            self.log_warning(f"Cache get failed: {e}")
            return None

    def set_in_cache(
        self, key: str, value: Any, ttl_seconds: int = 3600
    ) -> bool:
        """
        Set value in cache

        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time to live in seconds

        Returns:
            True if successful
        """
        if self._cache is None:
            return False
        try:
            self._cache.set_cache_item(key, value, ttl_seconds=ttl_seconds)
            return True
        except Exception as e:
            self.log_warning(f"Cache set failed: {e}")
            return False

    def delete_from_cache(self, key: str) -> bool:
        """
        Delete value from cache

        Args:
            key: Cache key

        Returns:
            True if successful
        """
        if self._cache is None:
            return False
        try:
            self._cache.delete_cache_item(key)
            return True
        except Exception as e:
            self.log_warning(f"Cache delete failed: {e}")
            return False

    # ========================================================================
    # Pagination Helpers
    # ========================================================================

    def calculate_pagination(
        self, page: int = 1, page_size: int = 20, max_page_size: int = 100
    ) -> Tuple[int, int]:
        """
        Calculate skip and limit for pagination

        Args:
            page: Page number (1-indexed)
            page_size: Items per page
            max_page_size: Maximum allowed page size

        Returns:
            Tuple of (skip, limit)
        """
        page = max(1, page)
        page_size = min(max(1, page_size), max_page_size)

        skip = (page - 1) * page_size
        return skip, page_size

    # ========================================================================
    # Error Handling
    # ========================================================================

    def handle_error(
        self, error: Exception, operation: str, context: Optional[Dict] = None
    ) -> ProcessingError:
        """
        Handle and wrap an exception

        Args:
            error: Original exception
            operation: Operation that failed
            context: Additional context

        Returns:
            ProcessingError wrapping the original error
        """
        self.log_error(f"Error in {operation}", error=error, **(context or {}))

        if isinstance(error, ProcessingError):
            return error

        return ProcessingError(
            message=str(error),
            operation=operation,
            original_error=error,
        )


class CRUDService(BaseService, Generic[T]):
    """
    Base class for services with standard CRUD operations

    Type Parameters:
        T: The model type this service handles
    """

    def __init__(self, repository, cache=None, config=None):
        """
        Initialize CRUD service

        Args:
            repository: Repository for data access
            cache: Optional cache instance
            config: Optional configuration instance
        """
        super().__init__(cache=cache, config=config)
        self._repository = repository

    @property
    def repository(self):
        """Get the repository"""
        return self._repository

    async def get_by_id(self, db: AsyncSession, id: Any) -> Optional[T]:
        """
        Get entity by ID

        Args:
            db: Database session
            id: Entity ID

        Returns:
            Entity or None
        """
        return await self._repository.get_by_id(db, id)

    async def list(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100,
        **filters,
    ) -> List[T]:
        """
        List entities with pagination and filters

        Args:
            db: Database session
            skip: Number of records to skip
            limit: Maximum records to return
            **filters: Additional filters

        Returns:
            List of entities
        """
        return await self._repository.list(db, skip=skip, limit=limit, **filters)

    async def create(self, db: AsyncSession, data: Dict[str, Any]) -> T:
        """
        Create new entity

        Args:
            db: Database session
            data: Entity data

        Returns:
            Created entity
        """
        return await self._repository.create(db, data)

    async def update(
        self, db: AsyncSession, id: Any, data: Dict[str, Any]
    ) -> Optional[T]:
        """
        Update entity

        Args:
            db: Database session
            id: Entity ID
            data: Update data

        Returns:
            Updated entity or None
        """
        return await self._repository.update(db, id, data)

    async def delete(self, db: AsyncSession, id: Any) -> bool:
        """
        Delete entity

        Args:
            db: Database session
            id: Entity ID

        Returns:
            True if deleted
        """
        return await self._repository.delete(db, id)

    async def count(self, db: AsyncSession, **filters) -> int:
        """
        Count entities

        Args:
            db: Database session
            **filters: Filters to apply

        Returns:
            Count of matching entities
        """
        return await self._repository.count(db, **filters)


# ============================================================================
# Export
# ============================================================================

__all__ = ["BaseService", "CRUDService"]
