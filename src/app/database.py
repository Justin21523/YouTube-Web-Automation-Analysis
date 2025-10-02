# src/app/database.py
"""
Database Configuration and Session Management
Uses SQLAlchemy with async support
"""

from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
import logging

from src.app.config import get_config

logger = logging.getLogger(__name__)

config = get_config()

# Create engine
engine = create_engine(
    config.database.url,
    connect_args=(
        {"check_same_thread": False} if "sqlite" in config.database.url else {}
    ),
    echo=config.database.echo,
    pool_size=config.database.pool_size,
    max_overflow=config.database.max_overflow,
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def init_db() -> None:
    """
    Initialize database tables
    Creates all tables defined by models
    """
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Database tables created successfully")
    except Exception as e:
        logger.error(f"❌ Failed to create database tables: {e}")
        raise


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for getting database session

    Usage in FastAPI:
        @app.get("/videos")
        def get_videos(db: Session = Depends(get_db)):
            ...

    Yields:
        Database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def drop_all_tables() -> None:
    """
    Drop all tables (use with caution!)
    Only use in development/testing
    """
    try:
        Base.metadata.drop_all(bind=engine)
        logger.warning("⚠️  All tables dropped")
    except Exception as e:
        logger.error(f"❌ Failed to drop tables: {e}")
        raise


def reset_database() -> None:
    """
    Reset database by dropping and recreating all tables
    Only use in development/testing
    """
    logger.warning("⚠️  Resetting database...")
    drop_all_tables()
    init_db()
    logger.info("✅ Database reset complete")


# Test connection on import
if __name__ == "__main__":
    print("🔧 Testing database connection...")

    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            assert result.fetchone()[0] == 1  # type: ignore
        print("✅ Database connection successful!")

        # Initialize tables
        init_db()
        print("✅ Database tables initialized!")

    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        import traceback

        traceback.print_exc()
