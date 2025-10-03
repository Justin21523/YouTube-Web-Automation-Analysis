# Makefile - YouTube Web Automation Analysis Project
# Development task automation

.PHONY: help install test smoke-test lint format clean docker-up docker-down

# Default target
help:
	@echo "📋 YouTube Web Automation Analysis - Available Commands"
	@echo ""
	@echo "🔧 Setup & Installation:"
	@echo "  make install          Install Python dependencies"
	@echo "  make install-dev      Install dev dependencies + pre-commit hooks"
	@echo "  make setup-env        Create .env from template"
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
	@echo "🚀 Development:"
	@echo "  make run-api          Start FastAPI server"
	@echo "  make run-frontend     Start React dev server"
	@echo "  make run-all          Start both backend + frontend"
	@echo ""
	@echo "🐳 Docker:"
	@echo "  make docker-build     Build Docker images"
	@echo "  make docker-up        Start all services"
	@echo "  make docker-down      Stop all services"
	@echo "  make docker-logs      View service logs"
	@echo ""
	@echo "🗑️  Cleanup:"
	@echo "  make clean            Remove cache and temp files"
	@echo "  make clean-all        Deep clean (includes venv)"

# ============================================================================
# Setup & Installation
# ============================================================================

install:
	@echo "📦 Installing dependencies..."
	pip install -r requirements.txt

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
# Development
# ============================================================================

run-api:
	@echo "🚀 Starting FastAPI server..."
	uvicorn src.app.main:app --reload --host 0.0.0.0 --port 8000

run-frontend:
	@echo "🚀 Starting React dev server..."
	cd frontend && npm run dev

run-all:
	@echo "🚀 Starting all services..."
	@make -j2 run-api run-frontend

# ============================================================================
# Docker
# ============================================================================

docker-build:
	@echo "🐳 Building Docker images..."
	docker-compose build

docker-up:
	@echo "🐳 Starting Docker services..."
	docker-compose up -d
	@echo "✅ Services started:"
	@echo "   API: http://localhost:8000"
	@echo "   Frontend: http://localhost:3000"

docker-down:
	@echo "🐳 Stopping Docker services..."
	docker-compose down

docker-logs:
	@echo "📜 Viewing service logs..."
	docker-compose logs -f

docker-rebuild:
	@echo "🐳 Rebuilding and restarting services..."
	docker-compose down
	docker-compose build --no-cache
	docker-compose up -d

# ============================================================================
# Database
# ============================================================================

db-init:
	@echo "🗄️  Initializing database..."
	python scripts/setup_db.py

db-migrate:
	@echo "🗄️  Running migrations..."
	alembic upgrade head

db-seed:
	@echo "🌱 Seeding database..."
	python scripts/seed_data.py

db-reset:
	@echo "⚠️  Resetting database..."
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		rm -f youtube_analysis.db; \
		make db-init; \
		echo "✅ Database reset complete"; \
	fi

# ============================================================================
# Cleanup
# ============================================================================

clean:
	@echo "🗑️  Cleaning cache and temp files..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.coverage" -delete
	rm -rf htmlcov/ .coverage
	@echo "✅ Cleaned cache files"

clean-all: clean
	@echo "🗑️  Deep cleaning..."
	rm -rf venv/ node_modules/
	@echo "✅ Deep clean complete"

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