# src/infrastructure/database/connection.py
"""
Async Database Connection Management
Provides SQLAlchemy async engine and session management
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
import logging

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy import event

logger = logging.getLogger(__name__)

# Base class for all ORM models
Base = declarative_base()


class DatabaseManager:
    """
    Async Database Manager
    Handles engine creation, session management, and lifecycle
    """

    def __init__(self):
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker[AsyncSession]] = None
        self._initialized: bool = False

    @property
    def engine(self) -> AsyncEngine:
        """Get the async engine (raises if not initialized)"""
        if self._engine is None:
            raise RuntimeError("Database not initialized. Call init() first.")
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Get the session factory (raises if not initialized)"""
        if self._session_factory is None:
            raise RuntimeError("Database not initialized. Call init() first.")
        return self._session_factory

    @property
    def is_initialized(self) -> bool:
        """Check if database is initialized"""
        return self._initialized

    def init(
        self,
        database_url: str,
        echo: bool = False,
        pool_size: int = 5,
        max_overflow: int = 10,
    ) -> None:
        """
        Initialize the database connection

        Args:
            database_url: Database connection URL
            echo: Echo SQL queries to log
            pool_size: Connection pool size
            max_overflow: Maximum overflow connections
        """
        if self._initialized:
            logger.warning("Database already initialized, skipping re-initialization")
            return

        # Convert sync URL to async URL if needed
        async_url = self._convert_to_async_url(database_url)

        # Create engine with appropriate settings
        engine_kwargs = {
            "echo": echo,
        }

        # SQLite-specific settings
        if "sqlite" in async_url:
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        else:
            # PostgreSQL/MySQL settings
            engine_kwargs["pool_size"] = pool_size
            engine_kwargs["max_overflow"] = max_overflow
            engine_kwargs["pool_pre_ping"] = True

        self._engine = create_async_engine(async_url, **engine_kwargs)

        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )

        self._initialized = True
        logger.info(f"Database initialized with URL: {self._mask_url(async_url)}")

    def _convert_to_async_url(self, url: str) -> str:
        """Convert sync database URL to async URL"""
        if url.startswith("sqlite:///"):
            return url.replace("sqlite:///", "sqlite+aiosqlite:///")
        elif url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://")
        elif url.startswith("mysql://"):
            return url.replace("mysql://", "mysql+aiomysql://")
        return url

    def _mask_url(self, url: str) -> str:
        """Mask sensitive parts of database URL for logging"""
        import re
        return re.sub(r"://[^:]+:[^@]+@", "://***:***@", url)

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Context manager for database sessions

        Usage:
            async with db_manager.session() as session:
                result = await session.execute(query)
        """
        if not self._initialized:
            raise RuntimeError("Database not initialized. Call init() first.")

        session = self._session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def create_tables(self) -> None:
        """Create all tables defined in Base.metadata"""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")

    async def drop_tables(self) -> None:
        """Drop all tables (use with caution!)"""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        logger.warning("All database tables dropped")

    async def close(self) -> None:
        """Close database connections"""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            self._initialized = False
            logger.info("Database connections closed")


# Global database manager instance
db_manager = DatabaseManager()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for getting async database session

    Usage:
        @app.get("/videos")
        async def get_videos(session: AsyncSession = Depends(get_session)):
            ...
    """
    async with db_manager.session() as session:
        yield session


def init_database_from_config() -> None:
    """
    Initialize database using application configuration

    This is a convenience function that loads config and initializes the database.
    Typically called during application startup.
    """
    from src.app.config import get_config

    config = get_config()

    db_manager.init(
        database_url=config.database.url,
        echo=config.database.echo,
        pool_size=config.database.pool_size,
        max_overflow=config.database.max_overflow,
    )
