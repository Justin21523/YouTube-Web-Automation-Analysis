# Makefile - YouTube Web Automation Analysis Project
# Development task automation

.PHONY: help install setup-env test celery-worker celery-beat flower docker-up docker-down

# Colors for output
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[1;33m
NC := \033[0m # No Color

# Default target
help:
	@echo "📋 YouTube Web Automation Analysis - Available Commands"
	@echo ""
	@echo "🔧 Setup & Installation:"
	@echo "  make install          Install Python dependencies"
	@echo "  make install-dev      Install dev dependencies + pre-commit hooks"
	@echo "  make setup-env        Create .env from template"
	@echo ""
	@echo "$(YELLOW)Development:$(NC)"
	@echo "  make dev              - Start FastAPI in dev mode"
	@echo "  make test             - Run all tests"
	@echo "  make lint             - Run linting"
	@echo ""
	@echo "$(YELLOW)Celery - Background Tasks:$(NC)"
	@echo "  make celery-worker    - Start Celery worker"
	@echo "  make celery-beat      - Start Celery Beat scheduler"
	@echo "  make flower           - Start Flower monitoring UI"
	@echo "  make celery-all       - Start worker + beat + flower"
	@echo "  make celery-purge     - Purge all tasks from queue"
	@echo ""
	@echo "$(YELLOW)Docker:$(NC)"
	@echo "  make docker-up        - Start all services (API + Celery + Redis)"
	@echo "  make docker-down      - Stop all services"
	@echo "  make docker-logs      - View all container logs"
	@echo "  make docker-worker    - View Celery worker logs"
	@echo "  make docker-beat      - View Celery Beat logs"
	@echo ""
	@echo "$(YELLOW)Database:$(NC)"
	@echo "  make migrate          - Create new migration"
	@echo "  make upgrade          - Apply migrations"
	@echo "  make downgrade        - Rollback migration"
	@echo ""
	@echo "🧪 Testing:"
	@echo "  make test             Run all unit tests"
	@echo "  make test-unit        Run unit tests only"
	@echo "  make test-integration Run integration tests (requires API key)"
	@echo "  make smoke-test       Run smoke tests for YouTube API"
	@echo "  make test-coverage    Run tests with coverage report"
	@echo ""
	@echo "✅ Code Quality:"
	@echo "  make lint             Run linters (ruff, mypy)"
	@echo "  make format           Auto-format code (black, isort)"
	@echo "  make type-check       Run type checking only"
	@echo ""
	@echo "🗑️  Cleanup:"
	@echo "  make clean            Remove cache and temp files"
	@echo "  make clean-all        Deep clean (includes venv)"

# ============================================================================
# Setup & Installation
# ============================================================================

install:
	@echo "$(GREEN)Installing dependencies...$(NC)"
	pip install -r requirements.txt
	pip install -r requirements-dev.txt
	@echo "$(GREEN)✅ Installation complete$(NC)"

install-dev:
	@echo "📦 Installing dev dependencies..."
	pip install -r requirements-dev.txt
	pre-commit install
	@echo "✅ Pre-commit hooks installed"

setup-env:
	@if [ ! -f .env ]; then \
		echo "📝 Creating .env from template..."; \
		cp .env.example .env; \
		echo "✅ Created .env - Please fill in your API keys"; \
	else \
		echo "⚠️  .env already exists, skipping"; \
	fi

init-db:
	@echo "$(GREEN)Initializing database...$(NC)"
	python -c "from src.app.database import init_db; init_db()"
	@echo "$(GREEN)✅ Database initialized$(NC)"
# ============================================================================
# Development
# ============================================================================

dev:
	@echo "$(GREEN)Starting FastAPI development server...$(NC)"
	uvicorn src.app.main:app --reload --host 0.0.0.0 --port 8000

test:
	@echo "$(GREEN)Running tests...$(NC)"
	pytest tests/ -v --cov=src --cov-report=html

lint:
	@echo "$(GREEN)Running linters...$(NC)"
	black src/ tests/
	flake8 src/ tests/
	mypy src/

# ============================================================================
# Celery Commands
# ============================================================================

celery-worker:
	@echo "$(GREEN)Starting Celery worker...$(NC)"
	celery -A src.infrastructure.tasks.celery_app worker \
		--loglevel=info \
		--concurrency=4 \
		--queues=default,scraping,analysis,priority

celery-beat:
	@echo "$(GREEN)Starting Celery Beat scheduler...$(NC)"
	celery -A src.infrastructure.tasks.celery_app beat \
		--loglevel=info

flower:
	@echo "$(GREEN)Starting Flower monitoring dashboard...$(NC)"
	@echo "$(YELLOW)Access at: http://localhost:5555$(NC)"
	celery -A src.infrastructure.tasks.celery_app flower \
		--port=5555

celery-all:
	@echo "$(GREEN)Starting all Celery services...$(NC)"
	@echo "$(YELLOW)Starting Worker...$(NC)"
	celery -A src.infrastructure.tasks.celery_app worker \
		--loglevel=info \
		--concurrency=4 \
		--detach \
		--pidfile=/tmp/celery_worker.pid \
		--logfile=logs/celery_worker.log
	@echo "$(YELLOW)Starting Beat...$(NC)"
	celery -A src.infrastructure.tasks.celery_app beat \
		--loglevel=info \
		--detach \
		--pidfile=/tmp/celery_beat.pid \
		--logfile=logs/celery_beat.log
	@echo "$(YELLOW)Starting Flower...$(NC)"
	celery -A src.infrastructure.tasks.celery_app flower \
		--port=5555 \
		--detach \
		--pidfile=/tmp/celery_flower.pid \
		--logfile=logs/celery_flower.log
	@echo "$(GREEN)✅ All Celery services started$(NC)"
	@echo "$(YELLOW)Flower: http://localhost:5555$(NC)"

celery-stop:
	@echo "$(YELLOW)Stopping Celery services...$(NC)"
	@if [ -f /tmp/celery_worker.pid ]; then \
		kill $$(cat /tmp/celery_worker.pid); \
		rm /tmp/celery_worker.pid; \
		echo "Worker stopped"; \
	fi
	@if [ -f /tmp/celery_beat.pid ]; then \
		kill $$(cat /tmp/celery_beat.pid); \
		rm /tmp/celery_beat.pid; \
		echo "Beat stopped"; \
	fi
	@if [ -f /tmp/celery_flower.pid ]; then \
		kill $$(cat /tmp/celery_flower.pid); \
		rm /tmp/celery_flower.pid; \
		echo "Flower stopped"; \
	fi
	@echo "$(GREEN)✅ Celery services stopped$(NC)"

celery-purge:
	@echo "$(RED)⚠️  Purging all tasks from queue...$(NC)"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		celery -A src.infrastructure.tasks.celery_app purge -f; \
		echo "$(GREEN)✅ Queue purged$(NC)"; \
	else \
		echo "$(YELLOW)Cancelled$(NC)"; \
	fi

celery-status:
	@echo "$(GREEN)Celery Worker Status:$(NC)"
	celery -A src.infrastructure.tasks.celery_app inspect active
	@echo ""
	@echo "$(GREEN)Scheduled Tasks:$(NC)"
	celery -A src.infrastructure.tasks.celery_app inspect scheduled


# ============================================================================
# Docker Commands
# ============================================================================

docker-up:
	@echo "$(GREEN)Starting all services with Docker Compose...$(NC)"
	docker-compose up -d
	@echo "$(GREEN)✅ Services started$(NC)"
	@echo "$(YELLOW)API: http://localhost:8000$(NC)"
	@echo "$(YELLOW)Flower: http://localhost:5555$(NC)"
	@echo "$(YELLOW)Docs: http://localhost:8000/docs$(NC)"

docker-down:
	@echo "$(YELLOW)Stopping all services...$(NC)"
	docker-compose down
	@echo "$(GREEN)✅ Services stopped$(NC)"

docker-logs:
	@echo "$(GREEN)Viewing all container logs...$(NC)"
	docker-compose logs -f

docker-worker:
	@echo "$(GREEN)Viewing Celery worker logs...$(NC)"
	docker-compose logs -f celery_worker

docker-beat:
	@echo "$(GREEN)Viewing Celery Beat logs...$(NC)"
	docker-compose logs -f celery_beat

docker-api:
	@echo "$(GREEN)Viewing API logs...$(NC)"
	docker-compose logs -f api

docker-flower:
	@echo "$(GREEN)Viewing Flower logs...$(NC)"
	docker-compose logs -f flower

docker-rebuild:
	@echo "$(YELLOW)Rebuilding all containers...$(NC)"
	docker-compose down
	docker-compose build --no-cache
	docker-compose up -d
	@echo "$(GREEN)✅ Containers rebuilt$(NC)"

docker-shell:
	@echo "$(GREEN)Opening shell in API container...$(NC)"
	docker-compose exec api /bin/bash

docker-clean:
	@echo "$(RED)⚠️  Cleaning up Docker resources...$(NC)"
	docker-compose down -v
	docker system prune -f
	@echo "$(GREEN)✅ Cleanup complete$(NC)"

# ============================================================================
# Testing
# ============================================================================

test:
	@echo "🧪 Running all tests..."
	pytest tests/ -v --tb=short

test-unit:
	@echo "🧪 Running unit tests..."
	pytest tests/unit/ -v --tb=short

test-integration:
	@echo "🧪 Running integration tests..."
	pytest tests/integration/ -v --tb=short -m integration

smoke-test:
	@echo "🧪 Running smoke tests..."
	python scripts/smoke_test_youtube.py

test-coverage:
	@echo "📊 Running tests with coverage..."
	pytest tests/ --cov=src --cov-report=html --cov-report=term
	@echo "📊 Coverage report: htmlcov/index.html"

# ============================================================================
# Code Quality
# ============================================================================

lint:
	@echo "🔍 Running linters..."
	ruff check src/ tests/
	mypy src/

format:
	@echo "✨ Formatting code..."
	black src/ tests/ scripts/
	isort src/ tests/ scripts/
	@echo "✅ Code formatted"

type-check:
	@echo "🔍 Type checking..."
	mypy src/ --strict



# ============================================================================
# Database
# ============================================================================

db-init:
	@echo "🗄️  Initializing database..."
	python scripts/setup_db.py

migrate:
	@echo "$(GREEN)Creating new migration...$(NC)"
	@read -p "Migration message: " msg; \
	alembic revision --autogenerate -m "$msg"
	@echo "$(GREEN)✅ Migration created$(NC)"

upgrade:
	@echo "$(GREEN)Applying migrations...$(NC)"
	alembic upgrade head
	@echo "$(GREEN)✅ Migrations applied$(NC)"

downgrade:
	@echo "$(YELLOW)Rolling back one migration...$(NC)"
	alembic downgrade -1
	@echo "$(GREEN)✅ Migration rolled back$(NC)"

migration-status:
	@echo "$(GREEN)Current migration status:$(NC)"
	alembic current
	@echo ""
	@echo "$(GREEN)Migration history:$(NC)"
	alembic history

db-seed:
	@echo "🌱 Seeding database..."
	python scripts/seed_data.py
# Reset database (DEVELOPMENT ONLY)
db-reset:
	@echo "🗑️  Resetting database..."
	rm -f youtube_automation.db
	alembic upgrade head
	@echo "✅ Database reset complete"


# ============================================================================
# Utilities
# ============================================================================

check-env:
	@echo "🔍 Checking environment configuration..."
	@python -c "import os; \
		key = os.getenv('YOUTUBE_API_KEY'); \
		if key: \
			print('✅ YOUTUBE_API_KEY is set'); \
		else: \
			print('❌ YOUTUBE_API_KEY not found in environment'); \
			print('   Run: make setup-env');"

cache-stats:
	@echo "📊 Cache statistics..."
	@python -c "from core.shared_cache import get_shared_cache; \
		cache = get_shared_cache(); \
		stats = cache.get_cache_stats(); \
		print(f'Cache Root: {stats[\"cache_root\"]}'); \
		print(f'Total Size: {stats[\"total_size_gb\"]:.2f} GB'); \
		print(f'GPU Available: {stats[\"gpu_available\"]}');"

info:
	@echo "ℹ️  Project Information"
	@echo "  Python: $$(python --version)"
	@echo "  Pip: $$(pip --version)"
	@echo "  Git: $$(git --version 2>/dev/null || echo 'not installed')"
	@echo "  Docker: $$(docker --version 2>/dev/null || echo 'not installed')"


# ============================================================================
# Quick Start (All-in-One)
# ============================================================================

quickstart:
	@echo "$(GREEN)🚀 Quick Start - YouTube Automation Platform$(NC)"
	@echo ""
	@echo "$(YELLOW)Step 1/5: Setup environment...$(NC)"
	@make setup-env
	@echo ""
	@echo "$(YELLOW)Step 2/5: Install dependencies...$(NC)"
	@make install
	@echo ""
	@echo "$(YELLOW)Step 3/5: Initialize database...$(NC)"
	@make init-db
	@echo ""
	@echo "$(YELLOW)Step 4/5: Start Redis...$(NC)"
	docker run -d -p 6379:6379 --name yt_redis redis:7-alpine
	@echo ""
	@echo "$(YELLOW)Step 5/5: Start services...$(NC)"
	@make celery-all &
	sleep 5
	@make dev &
	@echo ""
	@echo "$(GREEN)✅ Platform ready!$(NC)"
	@echo ""
	@echo "$(YELLOW)Access points:$(NC)"
	@echo "  API: http://localhost:8000/docs"
	@echo "  Flower: http://localhost:5555"
	@echo ""
	@echo "$(YELLOW)Don't forget to set YOUTUBE_API_KEY in .env!$(NC)"

# ============================================================================
# Testing & Quality
# ============================================================================

test-unit:
	@echo "$(GREEN)Running unit tests...$(NC)"
	pytest tests/unit/ -v

test-integration:
	@echo "$(GREEN)Running integration tests...$(NC)"
	pytest tests/integration/ -v

test-celery:
	@echo "$(GREEN)Testing Celery tasks...$(NC)"
	python -m pytest tests/ -k celery -v

coverage:
	@echo "$(GREEN)Generating coverage report...$(NC)"
	pytest tests/ --cov=src --cov-report=html --cov-report=term
	@echo "$(YELLOW)HTML report: htmlcov/index.html$(NC)"

# ============================================================================
# Monitoring & Debugging
# ============================================================================

monitor:
	@echo "$(GREEN)Opening Flower monitoring dashboard...$(NC)"
	@open http://localhost:5555 || xdg-open http://localhost:5555

check-redis:
	@echo "$(GREEN)Checking Redis connection...$(NC)"
	redis-cli ping

check-celery:
	@echo "$(GREEN)Checking Celery worker status...$(NC)"
	celery -A src.infrastructure.tasks.celery_app inspect ping

check-all:
	@echo "$(GREEN)System Health Check$(NC)"
	@echo ""
	@echo "$(YELLOW)1. Redis:$(NC)"
	@make check-redis
	@echo ""
	@echo "$(YELLOW)2. Celery Workers:$(NC)"
	@make check-celery
	@echo ""
	@echo "$(YELLOW)3. Active Tasks:$(NC)"
	@make celery-status

# ============================================================================
# Cleanup
# ============================================================================

clean:
	@echo "$(YELLOW)Cleaning up...$(NC)"
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.coverage" -delete
	rm -rf .pytest_cache htmlcov .mypy_cache
	@echo "$(GREEN)✅ Cleanup complete$(NC)"

clean-all: clean
	@echo "$(RED)Deep cleaning (including cache & data)...$(NC)"
	rm -rf logs/*.log
	rm -rf data/*.db
	@echo "$(GREEN)✅ Deep cleanup complete$(NC)"