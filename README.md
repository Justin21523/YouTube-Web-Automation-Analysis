# YouTube Web Automation Analysis

> Intelligent YouTube analytics platform with web automation, sentiment analysis, and trend tracking

---

## 📁 Project Structure

```
youtube-web-automation-analysis/
├── src/
│   ├── app/
│   │   └── models/              # SQLAlchemy ORM models
│   │       ├── channel.py       # Channel entity
│   │       ├── video.py         # Video entity with metrics
│   │       ├── comment.py       # Comment with sentiment
│   │       ├── playlist.py      # Playlist entity
│   │       └── analytics.py     # Time-series snapshots
│   └── infrastructure/
│       ├── database/
│       │   └── connection.py    # Async DB manager
│       └── repositories/        # Data access layer
│           ├── base.py          # Generic CRUD operations
│           ├── video_repository.py
│           ├── channel_repository.py
│           ├── comment_repository.py
│           └── analytics_repository.py
├── alembic/                     # Database migrations
├── scripts/
│   └── test_database.py         # Database validation script
├── core/
│   ├── config.py                # ✅ Reused from AI warehouse
│   └── shared_cache.py          # ✅ Reused from AI warehouse
└── docs/
    └── database_schema.md       # Complete schema documentation
```

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Setup Environment

```bash
cp .env.example .env
# Edit .env with your configuration
```

### 3. Initialize Database

```bash
# Create tables and run migrations
make setup-db

# Or manually:
alembic upgrade head
```

### 4. Test Database Setup

```bash
make test-db
```

Expected output:
```
🧪 DATABASE SETUP TEST
==============================
[1/7] Bootstrapping cache...
✅ Cache root: ../ai_warehouse/cache
[2/7] Loading configuration...
✅ Database URL: sqlite+aiosqlite:///./youtube_analytics.db
...
✅ ALL TESTS PASSED!
```

---

## 📊 Database Schema

### Core Entities

- **Channel:** YouTube channels with subscriber tracking
- **Video:** Videos with engagement metrics and processing status
- **Comment:** Comments with sentiment analysis support
- **Playlist:** Video collections
- **VideoAnalytics:** Time-series performance snapshots

See [Database Schema Documentation](docs/database_schema.md) for complete details.

### Entity Relationships

```
Channel (1) ──< (N) Video ──< (N) Comment
              └──< (N) VideoAnalytics
              └──< (N) Playlist
```

---

## 🛠️ Development Commands

```bash
# Database operations
make migrate        # Create new migration
make upgrade        # Apply migrations
make downgrade      # Rollback migration
make test-db        # Run database tests

# Development
make run            # Start dev server
make clean          # Clean cache files
```

---

## 🔌 Repository Usage Examples

### Basic CRUD Operations

```python
from src.infrastructure.database.connection import get_session
from src.infrastructure.repositories import VideoRepository

async with get_session() as session:
    video_repo = VideoRepository(session)

    # Get video by ID
    video = await video_repo.get_by_id("abc123")

    # Search by title
    results = await video_repo.search_by_title("tutorial")

    # Get trending videos
    trending = await video_repo.get_trending(days=7, limit=50)
```

### Advanced Queries

```python
from src.infrastructure.repositories import CommentRepository

async with get_session() as session:
    comment_repo = CommentRepository(session)

    # Get sentiment distribution
    distribution = await comment_repo.get_sentiment_distribution("video_id")
    # Returns: {"positive": 150, "negative": 20, "neutral": 30}

    # Get unanalyzed comments
    comments = await comment_repo.get_unanalyzed(limit=1000)
```

---

## 🎯 Current Status: Phase 1 Complete ✅

**Completed:**
- ✅ Database models with full relationships
- ✅ Alembic migration setup
- ✅ Repository pattern with type-safe operations
- ✅ Integration with existing AppConfig and SharedCache
- ✅ Comprehensive test suite

**Next Phase:**
- 🔄 YouTube Data API client implementation
- 🔄 Web scraping fallback mechanism
- 🔄 Data pipeline and ETL processes

---

## 📝 Git Workflow

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```bash
feat: add new feature
fix: bug fix
docs: documentation updates
chore: maintenance tasks
refactor: code refactoring
test: add tests
```

---

## 🤝 Contributing

1. Follow the existing code structure
2. Write tests for new features
3. Update documentation
4. Use conventional commit messages
5. Ensure migrations are reversible

---

## 📄 License

MIT License - See LICENSE file for details

---

**Project Status:** 🟢 Active Development
**Phase:** 1/10 Complete
**Last Updated:** 2025-10-02