# src/api/routers/pages_router.py
"""
Page Router - HTML Template Routes
Serves HTML pages for the frontend interface
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

# Setup templates directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(tags=["Pages"])


# ============================================================================
# Dashboard
# ============================================================================

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Dashboard home page"""
    return templates.TemplateResponse(
        "pages/index.html",
        {
            "request": request,
            "title": "Dashboard",
            "active_page": "dashboard"
        }
    )


# ============================================================================
# Video Pages
# ============================================================================

@router.get("/videos", response_class=HTMLResponse)
async def videos_list(request: Request):
    """Video list page"""
    return templates.TemplateResponse(
        "pages/videos/index.html",
        {
            "request": request,
            "title": "Videos",
            "active_page": "videos",
            "breadcrumb": [{"name": "Videos"}]
        }
    )


@router.get("/videos/search", response_class=HTMLResponse)
async def videos_search(request: Request, q: str = ""):
    """Video search page"""
    return templates.TemplateResponse(
        "pages/videos/search.html",
        {
            "request": request,
            "title": "Search Videos",
            "active_page": "search",
            "breadcrumb": [
                {"name": "Videos", "url": "/videos"},
                {"name": "Search"}
            ],
            "initial_query": q
        }
    )


@router.get("/videos/{video_id}", response_class=HTMLResponse)
async def video_detail(request: Request, video_id: str):
    """Video detail page"""
    return templates.TemplateResponse(
        "pages/videos/detail.html",
        {
            "request": request,
            "title": "Video Detail",
            "active_page": "videos",
            "breadcrumb": [
                {"name": "Videos", "url": "/videos"},
                {"name": video_id}
            ],
            "video_id": video_id
        }
    )


# ============================================================================
# Task Pages
# ============================================================================

@router.get("/tasks", response_class=HTMLResponse)
async def tasks_list(request: Request):
    """Task management page"""
    return templates.TemplateResponse(
        "pages/tasks/index.html",
        {
            "request": request,
            "title": "Task Manager",
            "active_page": "tasks",
            "breadcrumb": [{"name": "Tasks"}]
        }
    )


# ============================================================================
# Chat Pages
# ============================================================================

@router.get("/chat", response_class=HTMLResponse)
async def chat_sessions(request: Request):
    """Chat sessions list page"""
    return templates.TemplateResponse(
        "pages/chat/index.html",
        {
            "request": request,
            "title": "AI Chat",
            "active_page": "chat",
            "breadcrumb": [{"name": "AI Chat"}]
        }
    )


@router.get("/chat/{session_id}", response_class=HTMLResponse)
async def chat_session(request: Request, session_id: str):
    """Chat session page"""
    return templates.TemplateResponse(
        "pages/chat/session.html",
        {
            "request": request,
            "title": "Chat Session",
            "active_page": "chat",
            "breadcrumb": [
                {"name": "AI Chat", "url": "/chat"},
                {"name": f"Session {session_id[:8]}..."}
            ],
            "session_id": session_id
        }
    )


# ============================================================================
# Analytics Pages
# ============================================================================

@router.get("/analytics", response_class=HTMLResponse)
async def analytics_dashboard(request: Request):
    """Analytics dashboard page"""
    return templates.TemplateResponse(
        "pages/analytics/index.html",
        {
            "request": request,
            "title": "Analytics",
            "active_page": "analytics",
            "breadcrumb": [{"name": "Analytics"}]
        }
    )


# ============================================================================
# System Pages
# ============================================================================

@router.get("/system/health", response_class=HTMLResponse)
async def system_health(request: Request):
    """System health page"""
    return templates.TemplateResponse(
        "pages/system/health.html",
        {
            "request": request,
            "title": "System Health",
            "active_page": "health",
            "breadcrumb": [
                {"name": "System"},
                {"name": "Health"}
            ]
        }
    )
