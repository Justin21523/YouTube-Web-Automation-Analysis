# src/app/database.py
"""
Database Configuration and Session Management
Unified interface for async SQLAlchemy database operations

This module re-exports database components from the infrastructure layer
and provides convenience functions for database initialization.
"""

import asyncio
import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

# Re-export all database components from infrastructure layer
from src.infrastructure.database.connection import (
    Base,
    DatabaseManager,
    db_manager,
    get_session,
    init_database_from_config,
)

logger = logging.getLogger(__name__)

__all__ = [
    "Base",
    "DatabaseManager",
    "db_manager",
    "get_session",
    "init_db",
    "init_db_async",
    "drop_all_tables",
    "reset_database",
]


def init_db() -> None:
    """
    Initialize database (synchronous wrapper)

    Creates all tables defined by models.
    This is a convenience function that wraps the async initialization.
    """
    try:
        # Initialize database manager from config if not already done
        if not db_manager.is_initialized:
            init_database_from_config()

        # Create tables
        asyncio.run(_create_tables())
        logger.info("✅ Database tables created successfully")
    except Exception as e:
        logger.error(f"❌ Failed to create database tables: {e}")
        raise


async def init_db_async() -> None:
    """
    Initialize database (async version)

    Creates all tables defined by models.
    Use this in async contexts like FastAPI lifespan.
    """
    try:
        # Initialize database manager from config if not already done
        if not db_manager.is_initialized:
            init_database_from_config()

        await db_manager.create_tables()
        logger.info("✅ Database tables created successfully")
    except Exception as e:
        logger.error(f"❌ Failed to create database tables: {e}")
        raise


async def _create_tables() -> None:
    """Internal async helper for creating tables"""
    await db_manager.create_tables()


def drop_all_tables() -> None:
    """
    Drop all tables (use with caution!)
    Only use in development/testing
    """
    try:
        asyncio.run(_drop_tables())
        logger.warning("⚠️  All tables dropped")
    except Exception as e:
        logger.error(f"❌ Failed to drop tables: {e}")
        raise


async def _drop_tables() -> None:
    """Internal async helper for dropping tables"""
    await db_manager.drop_tables()


def reset_database() -> None:
    """
    Reset database by dropping and recreating all tables
    Only use in development/testing
    """
    logger.warning("⚠️  Resetting database...")
    drop_all_tables()
    init_db()
    logger.info("✅ Database reset complete")


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for getting async database session

    Usage:
        @app.get("/videos")
        async def get_videos(session: AsyncSession = Depends(get_async_session)):
            ...

    Yields:
        AsyncSession instance
    """
    async for session in get_session():
        yield session


# Test connection on import
if __name__ == "__main__":
    import asyncio

    print("🔧 Testing database connection...")

    async def test_connection():
        try:
            # Initialize
            init_database_from_config()

            # Test with a session
            async with db_manager.session() as session:
                from sqlalchemy import text

                result = await session.execute(text("SELECT 1"))
                assert result.scalar() == 1
            print("✅ Database connection successful!")

            # Initialize tables
            await db_manager.create_tables()
            print("✅ Database tables initialized!")

        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            import traceback

            traceback.print_exc()
        finally:
            await db_manager.close()

    asyncio.run(test_connection())
