# Makefile for YouTube-Web-Automation-Analysis
.PHONY: help install setup dev test lint format clean check-config

# Default target
help:
	@echo "YouTube-Web-Automation-Analysis - Available Commands"
	@echo "=================================================="
	@echo "setup          : Initial project setup"
	@echo "install        : Install Python dependencies"
	@echo "dev            : Run development server"
	@echo "test           : Run all tests"
	@echo "test-setup     : Run setup/smoke tests only"
	@echo "lint           : Run code linting"
	@echo "format         : Format code"
	@echo "clean          : Clean cache and temporary files"
	@echo "check-config   : Validate configuration"
	@echo "reset-db       : Reset database (WARNING: deletes all data)"

# Initial setup
setup:
	@echo "🚀 Running initial project setup..."
	@pip install --upgrade pip
	@pip install -r requirements.txt
	@cp .env.example .env || true
	@python -m src.app.config
	@python -m src.app.shared_cache
	@python scripts/setup_db.py
	@echo "✅ Setup complete! Run 'make dev' to start the server."

# Install dependencies
install:
	@echo "📦 Installing dependencies..."
	@pip install --upgrade pip
	@pip install -r requirements.txt
	@echo "✅ Dependencies installed"

# Run development server
dev:
	@echo "🔥 Starting development server..."
	@uvicorn src.app.main:app --reload --host 0.0.0.0 --port 8000

# Run setup tests only
test-setup:
	@echo "🧪 Running setup/smoke tests..."
	@export PYTHONPATH="${PWD}:${PYTHONPATH}" && pytest tests/test_setup.py -v -s

# Run all tests
test:
	@echo "🧪 Running all tests..."
	@export PYTHONPATH="${PWD}:${PYTHONPATH}" && pytest tests/ -v -s

# Check configuration
check-config:
	@echo "🔍 Checking configuration..."
	@python -m src.app.config

# Lint code
lint:
	@echo "🔍 Running linters..."
	@flake8 src/ tests/ --max-line-length=88 --extend-ignore=E203,W503 || true
	@echo "✅ Linting complete"

# Format code
format:
	@echo "✨ Formatting code..."
	@black src/ tests/ scripts/
	@isort src/ tests/ scripts/
	@echo "✅ Formatting complete"

# Clean temporary files
clean:
	@echo "🧹 Cleaning temporary files..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@find . -type f -name "*.pyo" -delete
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@rm -rf htmlcov/ .coverage
	@echo "✅ Cleanup complete"

# Reset database (dangerous!)
reset-db:
	@echo "⚠️  WARNING: This will delete all database data!"
	@echo "Press Ctrl+C to cancel, or wait 5 seconds to continue..."
	@sleep 5
	@python -c "from src.app.database import reset_database; reset_database()"
	@echo "✅ Database reset complete"