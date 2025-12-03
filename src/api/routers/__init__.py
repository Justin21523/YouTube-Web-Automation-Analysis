# src/api/routers/__init__.py
"""
API Routers
REST API endpoint modules
"""

from .task_router import router as task_router
from .caption_router import router as caption_router
from .vqa_router import router as vqa_router
from .chat_router import router as chat_router
from .rag_router import router as rag_router
from .health_router import router as health_router

__all__ = [
    "task_router",
    "caption_router",
    "vqa_router",
    "chat_router",
    "rag_router",
    "health_router",
]
