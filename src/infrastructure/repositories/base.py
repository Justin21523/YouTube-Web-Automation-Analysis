# src/infrastructure/repositories/base.py
"""
Base Repository Pattern
Provides generic CRUD operations for all entities
"""

from typing import Generic, TypeVar, Type, List, Optional, Dict, Any, Protocol, cast
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import DeclarativeMeta, InstrumentedAttribute
import logging

logger = logging.getLogger(__name__)

# Generic type for models
ModelType = TypeVar("ModelType", bound=DeclarativeMeta)

# ------------------------------------------------------------------------
# Typing helpers (minimal, to satisfy Pylance without changing behavior)
# ------------------------------------------------------------------------


class HasId(Protocol):
    id: Any  # all our ORM models expose an "id" column


class BaseRepository(Generic[ModelType]):
    """
    Abstract Repository with generic CRUD operations

    Usage:
        class VideoRepository(BaseRepository[Video]):
            def __init__(self, session: AsyncSession):
                super().__init__(session, Video)
    """

    def __init__(self, session: AsyncSession, model: Type[ModelType]):
        """
        Initialize repository

        Args:
            session: Database session
            model: SQLAlchemy model class
        """
        self.session = session
        self.model = model

    # internal: get the mapped "id" column with a cast so type checker is happy
    def _id_col(self) -> InstrumentedAttribute:
        return cast(InstrumentedAttribute, getattr(self.model, "id"))

    # ========================================================================
    # CREATE Operations
    # ========================================================================

    async def create(self, **kwargs) -> ModelType:
        """
        Create new entity

        Args:
            **kwargs: Model attributes

        Returns:
            Created model instance
        """
        try:
            # The call is correct at runtime; we just silence the type checker.
            instance: ModelType = cast(Any, self.model)(**kwargs)  # type: ignore[call-arg]
            self.session.add(instance)
            await self.session.commit()
            await self.session.refresh(instance)
            logger.info(f"✅ Created {self.model.__name__}: {kwargs.get('id', 'N/A')}")
            return instance
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Failed to create {self.model.__name__}: {e}")
            raise

    async def bulk_create(self, items: List[Dict[str, Any]]) -> List[ModelType]:
        """
        Create multiple entities in bulk

        Args:
            items: List of dictionaries with model attributes

        Returns:
            List of created model instances
        """
        try:
            instances: List[ModelType] = [cast(Any, self.model)(**item) for item in items]  # type: ignore[call-arg]
            # AsyncSession.add_all exists; cast only to keep Pylance quiet.
            self.session.add_all(cast(List[Any], instances))
            await self.session.commit()

            for instance in instances:
                await self.session.refresh(instance)

            logger.info(
                f"✅ Bulk created {len(instances)} {self.model.__name__} records"
            )
            return instances
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Failed to bulk create {self.model.__name__}: {e}")
            raise

    # ========================================================================
    # READ Operations
    # ========================================================================

    async def get_by_id(self, id: str) -> Optional[ModelType]:
        """
        Get entity by ID

        Args:
            id: Entity ID

        Returns:
            Model instance or None
        """
        try:
            result = await self.session.get(self.model, id)
            return cast(Optional[ModelType], result)
        except Exception as e:
            logger.error(f"❌ Failed to get {self.model.__name__} by ID: {e}")
            raise

    async def get_all(
        self, skip: int = 0, limit: int = 100, order_by: Optional[str] = None
    ) -> List[ModelType]:
        """
        Get all entities with pagination

        Args:
            skip: Number of records to skip
            limit: Maximum number of records
            order_by: Column to order by (default: id)

        Returns:
            List of model instances
        """
        try:
            query = select(self.model).offset(skip).limit(limit)

            # Add ordering if a valid column name is provided
            if order_by and hasattr(self.model, order_by):
                query = query.order_by(getattr(self.model, order_by).desc())

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to get all {self.model.__name__}: {e}")
            raise

    async def count(self, **filters) -> int:
        """
        Count entities matching filters

        Args:
            **filters: Filter conditions

        Returns:
            Count of matching records
        """
        try:
            query = select(func.count()).select_from(self.model)
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.where(getattr(self.model, key) == value)

            result = await self.session.execute(query)
            # 防止 None：scalar_one_or_none() 可能回 None，統一轉成 int
            total = result.scalar_one_or_none()
            return int(total or 0)
        except Exception as e:
            logger.error(f"❌ Failed to count {self.model.__name__}: {e}")
            raise

    async def exists(self, id: str) -> bool:
        """
        Check if entity exists

        Args:
            id: Entity ID

        Returns:
            True if exists, False otherwise
        """
        try:
            stmt = (
                select(func.count())
                .select_from(self.model)
                .where(
                    self._id_col() == id
                )  # 以 _id_col() 取得對應欄位，解決 Pylance 的 id 型別問題
            )
            result = await self.session.execute(stmt)
            count_val = result.scalar_one_or_none()
            return int(count_val or 0) > 0  # 防止 None，再做比較
        except Exception as e:
            logger.error(f"❌ Failed to check existence: {e}")
            raise

    # ========================================================================
    # UPDATE Operations
    # ========================================================================

    async def update(self, id: str, **kwargs) -> Optional[ModelType]:
        """
        Update entity by ID

        Args:
            id: Entity ID
            **kwargs: Fields to update

        Returns:
            Updated model instance or None
        """
        try:
            stmt = update(self.model).where(self._id_col() == id).values(**kwargs)
            await self.session.execute(stmt)
            await self.session.commit()
            updated = await self.get_by_id(id)
            if updated:
                await self.session.refresh(updated)
            logger.info(f"✅ Updated {self.model.__name__}: {id}")
            return updated
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Failed to update {self.model.__name__}: {e}")
            raise

    async def bulk_update(self, ids: List[Any], **kwargs) -> int:
        """
        Bulk update entities by IDs
        """
        try:
            stmt = update(self.model).where(self._id_col().in_(ids)).values(**kwargs)
            result = await self.session.execute(stmt)
            await self.session.commit()
            updated_count = int(result.rowcount or 0)
            logger.info(
                f"✅ Bulk updated {updated_count} {self.model.__name__} records"
            )
            return updated_count
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Failed to bulk update {self.model.__name__}: {e}")
            raise

    # ========================================================================
    # DELETE Operations
    # ========================================================================

    async def delete(self, id: str) -> bool:
        """
        Delete entity by ID

        Args:
            id: Entity ID

        Returns:
            True if deleted, False if not found
        """
        try:
            result = await self.session.execute(
                delete(self.model).where(self._id_col() == id)
            )
            await self.session.commit()

            deleted = result.rowcount > 0
            if deleted:
                logger.info(f"✅ Deleted {self.model.__name__}: {id}")
            else:
                logger.warning(f"⚠️ {self.model.__name__} not found for deletion: {id}")

            return deleted
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Failed to delete {self.model.__name__}: {e}")
            raise

    async def delete_many(self, ids: List[str]) -> int:
        """
        Delete multiple entities by IDs

        Args:
            ids: List of entity IDs

        Returns:
            Number of deleted records
        """
        try:
            result = await self.session.execute(
                delete(self.model).where(self._id_col().in_(ids))
            )
            await self.session.commit()

            deleted_count = result.rowcount
            logger.info(f"✅ Deleted {deleted_count} {self.model.__name__} records")
            return deleted_count
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Failed to delete many {self.model.__name__}: {e}")
            raise

    async def find_one(self, **filters) -> Optional[ModelType]:
        """
        Find one entity by filters
        """
        try:
            query = select(self.model)
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.where(getattr(self.model, key) == value)

            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"❌ Failed to find one {self.model.__name__}: {e}")
            raise

    # ========================================================================
    # Advanced Query Helpers
    # ========================================================================

    async def find_by(self, **filters) -> List[ModelType]:
        """
        Find entities by filters

        Args:
            **filters: Field-value pairs to filter by

        Returns:
            List of matching model instances
        """
        try:
            query = select(self.model)

            # Apply filters
            for key, value in filters.items():
                if hasattr(self.model, key):
                    if value is None:
                        query = query.where(getattr(self.model, key).is_(None))
                    else:
                        query = query.where(getattr(self.model, key) == value)

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"❌ Failed to find {self.model.__name__}: {e}")
            raise

    async def find_one_by(self, **filters) -> Optional[ModelType]:
        """
        Find single entity by filters

        Args:
            **filters: Field-value pairs to filter by

        Returns:
            First matching model instance or None
        """
        try:
            query = select(self.model)

            # Apply filters
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.where(getattr(self.model, key) == value)

            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"❌ Failed to find one {self.model.__name__}: {e}")
            raise


# ============================================================================
# Convenience Type Aliases
# ============================================================================

Repository = BaseRepository
