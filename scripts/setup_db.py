"""
Database Setup Script
Creates initial database tables and runs migrations
"""

import sys
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.app.database import init_db, engine
from src.app.config import get_config, validate_config, setup_logging


def main():
    """Initialize database and validate configuration"""
    print("=" * 60)
    print("🔧 YouTube Web Automation - Database Setup")
    print("=" * 60)

    # Setup logging
    setup_logging()

    # Validate configuration first
    print("\n🔍 Validating Configuration...")
    validation = validate_config()

    if not validation["valid"]:
        print("\n❌ Configuration validation failed:")
        for error in validation["errors"]:
            print(f"  - {error}")
        sys.exit(1)

    if validation["warnings"]:
        print("\n⚠️  Configuration warnings:")
        for warning in validation["warnings"]:
            print(f"  - {warning}")

    # Get config
    config = get_config()
    print(f"\n📦 Using database: {config.database.url}")

    try:
        # Test connection
        print("\n🔌 Testing database connection...")
        with engine.connect() as conn:
            result = conn.execute("SELECT 1")  # type: ignore
            assert result.fetchone()[0] == 1

        print("✅ Database connection successful")

        # Create tables
        print("\n📊 Creating database tables...")
        init_db()

        print("\n" + "=" * 60)
        print("✅ Database setup complete!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Database setup failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
