# src/app/main.py
"""
FastAPI Main Application
YouTube Web Automation Analysis Platform
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
import sys
from pathlib import Path

# Add project root to Python path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))
# Import configuration and cache
from src.app.config import get_config, validate_config, setup_logging
from src.app.shared_cache import get_shared_cache, bootstrap_cache

# Import database manager
from src.app.database import db_manager

# Setup logging
logger = logging.getLogger(__name__)


# ============================================================================
# Application Lifecycle Management
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Application lifespan manager
    Handles startup and shutdown events
    """
    # ========== STARTUP ==========
    logger.info("🚀 Starting YouTube Web Automation Analysis Platform...")

    # 1. Bootstrap shared cache
    logger.info("📦 Bootstrapping shared cache...")
    cache = bootstrap_cache()
    logger.info(f"✅ Cache initialized: {cache.cache_root}")

    # 2. Load and validate configuration
    logger.info("⚙️  Loading configuration...")
    config = get_config()
    setup_logging(config)

    validation_result = validate_config(config)
    if not validation_result["valid"]:
        logger.error("❌ Configuration validation failed!")
        for error in validation_result["errors"]:
            logger.error(f"  - {error}")
        raise RuntimeError("Invalid configuration")

    if validation_result["warnings"]:
        for warning in validation_result["warnings"]:
            logger.warning(f"  ⚠️  {warning}")

    logger.info("✅ Configuration loaded and validated")

    # 3. Initialize database
    logger.info("🗄️  Initializing database...")
    try:
        await db_manager.create_tables()
        logger.info("✅ Database initialized successfully")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise

    # 4. Print startup summary
    _print_startup_summary(config, cache)

    logger.info("✅ Application startup complete!\n")

    yield

    # ========== SHUTDOWN ==========
    logger.info("\n🛑 Shutting down application...")

    # Close database connections
    logger.info("🔌 Closing database connections...")
    await db_manager.close()

    # Cleanup cache
    logger.info("🧹 Cleaning up cache...")
    cache.clear_memory_cache()

    logger.info("✅ Application shutdown complete")


def _print_startup_summary(config, cache) -> None:
    """Print startup summary"""
    summary = f"""
╔══════════════════════════════════════════════════════════════════════╗
║          YouTube Web Automation Analysis Platform                    ║
║                      Status: Ready 🚀                                ║
╚══════════════════════════════════════════════════════════════════════╝

📋 Configuration:
   • Environment: {config.get('app.env', 'development')}
   • Database: {config.database.url.split('/')[-1]}
   • Cache Root: {cache.cache_root}
   • API Host: {config.api.host}:{config.api.port}
   • Debug Mode: {config.api.debug}

🔌 Endpoints:
   • API Docs: http://{config.api.host}:{config.api.port}/docs
   • ReDoc: http://{config.api.host}:{config.api.port}/redoc
   • OpenAPI: http://{config.api.host}:{config.api.port}/openapi.json

🎯 Features Status:
   • Caption: {'✅' if config.features.enable_caption else '❌'}
   • VQA: {'✅' if config.features.enable_vqa else '❌'}
   • Chat: {'✅' if config.features.enable_chat else '❌'}
   • RAG: {'✅' if config.features.enable_rag else '❌'}
   • T2I: {'✅' if config.features.enable_t2i else '❌'}

📊 GPU Info:
   • Available: {cache.get_gpu_info()['cuda_available']}
   • Device Count: {cache.get_gpu_info()['device_count']}

╔══════════════════════════════════════════════════════════════════════╗
║  Press Ctrl+C to stop the server                                     ║
╚══════════════════════════════════════════════════════════════════════╝
    """
    print(summary)


# ============================================================================
# FastAPI Application Instance
# ============================================================================


def create_app() -> FastAPI:
    """
    FastAPI application factory
    Creates and configures the FastAPI application
    """
    config = get_config()

    app = FastAPI(
        title="YouTube Web Automation Analysis",
        description="Intelligent YouTube analytics platform with web automation, sentiment analysis, and trend tracking",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
        debug=config.api.debug,
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.api.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register exception handlers
    _register_exception_handlers(app)

    # Register routers
    _register_routers(app, config)

    # Mount static files
    static_dir = ROOT_DIR / "src" / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
        logger.info("📁 Static files mounted at /static")

    return app


def _register_exception_handlers(app: FastAPI) -> None:
    """Register custom exception handlers"""

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        """Handle HTTP exceptions"""
        logger.error(f"HTTP error: {exc.status_code} - {exc.detail}")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.detail,
                "status_code": exc.status_code,
                "path": str(request.url),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        """Handle validation errors"""
        logger.error(f"Validation error: {exc.errors()}")
        return JSONResponse(
            status_code=422,
            content={
                "error": "Validation Error",
                "details": exc.errors(),
                "body": exc.body,
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle all other exceptions"""
        logger.exception(f"Unhandled exception: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal Server Error",
                "message": str(exc),
                "path": str(request.url),
            },
        )


def _register_routers(app: FastAPI, config) -> None:
    """Register API routers"""

    # Health check endpoint
    @app.get("/health", tags=["System"])
    async def health_check():
        """Health check endpoint"""
        cache = get_shared_cache()
        return {
            "status": "healthy",
            "version": "0.1.0",
            "database": "connected",
            "cache_root": cache.cache_root,
            "gpu_available": cache.get_gpu_info()["cuda_available"],
        }

    # API Root endpoint (JSON info)
    @app.get("/api", tags=["System"])
    async def api_root():
        """API root endpoint with API information"""
        return {
            "message": "YouTube Web Automation Analysis API",
            "version": "0.1.0",
            "docs": "/docs",
            "redoc": "/redoc",
            "health": "/health",
        }

    # System info endpoint
    @app.get("/system/info", tags=["System"])
    async def system_info():
        """Get system information"""
        cache = get_shared_cache()
        config_summary = config.get_summary()

        return {
            "config": config_summary,
            "cache_stats": cache.get_cache_stats(),
            "gpu_info": cache.get_gpu_info(),
        }

    # Database info endpoint
    @app.get("/system/database", tags=["System"])
    async def database_info():
        """Get database information"""
        from src.app.database import get_session
        from src.infrastructure.repositories import (
            ChannelRepository,
            VideoRepository,
            CommentRepository,
        )

        async with db_manager.session() as session:
            channel_repo = ChannelRepository(session)
            video_repo = VideoRepository(session)
            comment_repo = CommentRepository(session)

            return {
                "database_url": config.database.url.split("/")[-1],
                "statistics": {
                    "total_channels": await channel_repo.count(),
                    "total_videos": await video_repo.count(),
                    "total_comments": await comment_repo.count(),
                },
            }

    # Register pages router (HTML templates)
    from src.api.routers.pages_router import router as pages_router
    app.include_router(pages_router)
    logger.info("  🖥️  Pages router registered")

    # Register core API routers
    from src.api.routers.task_router import router as task_router
    from src.api.routers.health_router import router as health_router, set_startup_time

    app.include_router(task_router)
    app.include_router(health_router)

    # Set startup time for health checks
    set_startup_time()
    logger.info("  🏥 Health router registered")

    # Register feature routers based on config
    if config.features.enable_caption:
        from src.api.routers.caption_router import router as caption_router
        app.include_router(caption_router)
        logger.info("  📝 Caption router registered")

    if config.features.enable_vqa:
        from src.api.routers.vqa_router import router as vqa_router
        app.include_router(vqa_router)
        logger.info("  👁️ VQA router registered")

    if config.features.enable_chat:
        from src.api.routers.chat_router import router as chat_router
        app.include_router(chat_router)
        logger.info("  💬 Chat router registered")

    if config.features.enable_rag:
        from src.api.routers.rag_router import router as rag_router
        app.include_router(rag_router)
        logger.info("  🔍 RAG router registered")

    logger.info("✅ API routers registered")


# ============================================================================
# Application Instance
# ============================================================================

app = create_app()


# ============================================================================
# Development Server Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    config = get_config()

    uvicorn.run(
        "src.app.main:app",
        host=config.api.host,
        port=config.api.port,
        reload=config.api.debug,
        log_level=config.logging.level.lower(),
    )
