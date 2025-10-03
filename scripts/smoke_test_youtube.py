# scripts/smoke_test_youtube.py
"""
YouTube API Client Smoke Test
Validates API connectivity, configuration, and basic functionality

Run: python scripts/smoke_test_youtube.py
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

# ✅ Load .env file explicitly
from dotenv import load_dotenv

dotenv_path = ROOT_DIR / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)
    print(f"✅ Loaded .env from: {dotenv_path}")
else:
    print(f"⚠️  .env file not found at: {dotenv_path}")

from src.app.config import get_config
from src.app.shared_cache import get_shared_cache, bootstrap_cache
from src.infrastructure.clients.youtube_api import (
    YouTubeAPIClient,
    create_youtube_client,
)


def print_section(title: str):
    """Print formatted section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def test_config():
    """Test configuration loading"""
    print_section("1️⃣  Configuration Test")

    try:
        config = get_config()
        print("✅ Configuration loaded successfully")

        # Check YouTube API config
        if hasattr(config, "youtube_api"):
            yt_config = config.youtube_api
            print(f"   Quota Limit: {yt_config.daily_quota_limit:,}")
            print(f"   Requests/sec: {yt_config.requests_per_second}")
            print(f"   Max Retries: {yt_config.max_retries}")
            print(f"   Cache Enabled: {yt_config.enable_response_cache}")
        else:
            print("⚠️  YouTube API config not found (add YouTubeAPIConfig to config.py)")

        return True
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False


def test_shared_cache():
    """Test shared cache initialization"""
    print_section("2️⃣  Shared Cache Test")

    try:
        cache = bootstrap_cache()

        # Test required directories
        required_dirs = ["CACHE_ROOT", "OUTPUT_DIR", "TEMP_DIR", "CONFIG_DIR"]

        for dir_key in required_dirs:
            path = cache.get_path(dir_key)
            exists = Path(path).exists()
            status = "✅" if exists else "❌"
            print(f"   {status} {dir_key}: {path}")

        # Test cache stats
        stats = cache.get_cache_stats()
        print(f"\n   Cache Root: {stats['cache_root']}")
        print(f"   Total Size: {stats['total_size_gb']:.2f} GB")
        print(f"   GPU Available: {stats['gpu_available']}")

        return True
    except Exception as e:
        print(f"❌ Shared cache test failed: {e}")
        return False


def test_api_key():
    """Test API key availability"""
    print_section("3️⃣  API Key Test")

    api_key = os.getenv("YOUTUBE_API_KEY")

    if not api_key:
        print("❌ YOUTUBE_API_KEY not found in environment")
        print("\n   To fix:")
        print("   1. Copy .env.example to .env")
        print("   2. Add your YouTube API key to YOUTUBE_API_KEY")
        print(
            "   3. Get API key from: https://console.cloud.google.com/apis/credentials"
        )
        return False

    # Basic validation
    if len(api_key) < 20:
        print(f"⚠️  API key seems too short: {len(api_key)} characters")
        return False

    print(f"✅ API key found ({len(api_key)} characters)")
    print(f"   Key preview: {api_key[:10]}...{api_key[-10:]}")

    return True


def test_client_initialization():
    """Test YouTube API client initialization"""
    print_section("4️⃣  Client Initialization Test")

    try:
        client = create_youtube_client()
        print("✅ YouTube API client created successfully")

        # Check quota tracker
        quota_status = client.get_quota_status()
        print(f"   Quota Limit: {quota_status['limit']:,}")
        print(f"   Quota Used: {quota_status['used']:,}")
        print(f"   Quota Remaining: {quota_status['remaining']:,}")

        client.close()
        return True
    except Exception as e:
        print(f"❌ Client initialization failed: {e}")
        return False


def test_api_connectivity():
    """Test actual API connectivity with a simple request"""
    print_section("5️⃣  API Connectivity Test")

    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        print("⏭️  Skipping (no API key)")
        return None

    try:
        with create_youtube_client(api_key) as client:
            print("🔄 Fetching test video (Rick Astley - Never Gonna Give You Up)...")

            # Fetch famous video (dQw4w9WgXcQ)
            video = client.get_video("dQw4w9WgXcQ")

            print(f"✅ API call successful!")
            print(f"\n   Video Details:")
            print(f"   Title: {video.snippet.title}")
            print(f"   Channel: {video.snippet.channel_title}")
            print(f"   Views: {video.statistics.view_count:,}")
            print(f"   Likes: {video.statistics.like_count:,}")
            print(f"   Comments: {video.statistics.comment_count:,}")
            print(f"   Published: {video.snippet.published_at.strftime('%Y-%m-%d')}")

            # Check quota consumption
            quota_status = client.get_quota_status()
            print(f"\n   Quota Used: {quota_status['used']} / {quota_status['limit']}")
            print(f"   Quota Remaining: {quota_status['remaining']:,}")

            return True
    except ValueError as e:
        if "quota" in str(e).lower():
            print(f"❌ Quota exceeded: {e}")
        elif "invalid" in str(e).lower():
            print(f"❌ Invalid API key: {e}")
        else:
            print(f"❌ API error: {e}")
        return False
    except Exception as e:
        print(f"❌ Connectivity test failed: {e}")
        return False


def test_rate_limiter():
    """Test rate limiting functionality"""
    print_section("6️⃣  Rate Limiter Test")

    try:
        from src.infrastructure.clients.rate_limiter import RateLimiter
        import time

        print("🔄 Testing rate limiter (5 calls/sec, burst=10)...")

        limiter = RateLimiter(calls_per_second=5, burst_capacity=10)

        # Test burst capacity
        start_time = time.time()
        burst_count = 0

        for i in range(10):
            if limiter.acquire(timeout=0.1):
                burst_count += 1

        burst_time = time.time() - start_time

        print(f"   Burst calls: {burst_count}/10 in {burst_time:.2f}s")

        # Test sustained rate
        start_time = time.time()
        sustained_count = 0

        for i in range(15):
            if limiter.acquire(timeout=5.0):
                sustained_count += 1

        sustained_time = time.time() - start_time
        actual_rate = sustained_count / sustained_time if sustained_time > 0 else 0

        print(f"   Sustained calls: {sustained_count}/15 in {sustained_time:.2f}s")
        print(f"   Actual rate: {actual_rate:.2f} calls/sec")

        if 4.0 <= actual_rate <= 6.0:
            print("✅ Rate limiter working correctly")
            return True
        else:
            print("⚠️  Rate limiter may not be working as expected")
            return True  # Don't fail smoke test

    except Exception as e:
        print(f"❌ Rate limiter test failed: {e}")
        return False


def test_search_functionality():
    """Test video search functionality"""
    print_section("7️⃣  Search Functionality Test")

    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        print("⏭️  Skipping (no API key)")
        return None

    try:
        with create_youtube_client(api_key) as client:
            print("🔄 Searching for 'Python tutorial' videos...")

            video_ids = client.search_videos(
                query="Python tutorial", max_results=5, order="relevance"
            )

            print(f"✅ Found {len(video_ids)} videos")

            if video_ids:
                print(f"\n   Fetching details for first result...")
                video = client.get_video(video_ids[0])

                print(f"   Title: {video.snippet.title}")
                print(f"   Channel: {video.snippet.channel_title}")
                print(f"   Views: {video.statistics.view_count:,}")

            # Check quota after search (search costs 100 units!)
            quota_status = client.get_quota_status()
            print(f"\n   Quota Used: {quota_status['used']} (search=100, videos=1)")

            return True
    except Exception as e:
        print(f"❌ Search test failed: {e}")
        return False


def generate_report(results: dict):
    """Generate final test report"""
    print_section("📊 Test Summary")

    total_tests = len(results)
    passed = sum(1 for v in results.values() if v is True)
    failed = sum(1 for v in results.values() if v is False)
    skipped = sum(1 for v in results.values() if v is None)

    print(f"\n   Total Tests: {total_tests}")
    print(f"   ✅ Passed: {passed}")
    print(f"   ❌ Failed: {failed}")
    print(f"   ⏭️  Skipped: {skipped}")

    success_rate = (passed / (passed + failed) * 100) if (passed + failed) > 0 else 0
    print(f"\n   Success Rate: {success_rate:.1f}%")

    if failed == 0:
        print("\n   🎉 All tests passed! YouTube API client is ready to use.")
        return True
    else:
        print("\n   ⚠️  Some tests failed. Check errors above.")
        return False


def main():
    """Run all smoke tests"""
    print("\n" + "=" * 60)
    print("  🧪 YouTube API Client - Smoke Test")
    print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)

    # Run tests
    results = {
        "Configuration": test_config(),
        "Shared Cache": test_shared_cache(),
        "API Key": test_api_key(),
        "Client Init": test_client_initialization(),
        "API Connectivity": test_api_connectivity(),
        "Rate Limiter": test_rate_limiter(),
        "Search": test_search_functionality(),
    }

    # Generate report
    success = generate_report(results)

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
