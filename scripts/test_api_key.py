#!/usr/bin/env python3
"""
Direct YouTube API Key Test
Uses raw HTTP request to test API key without any dependencies
"""

import os
import sys
from pathlib import Path

# Load .env
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from dotenv import load_dotenv

load_dotenv(ROOT_DIR / ".env")

print("=" * 60)
print("  🔑 YouTube API Key Direct Test")
print("=" * 60)

# Get API key
api_key = os.getenv("YOUTUBE_API_KEY")

if not api_key:
    print("\n❌ YOUTUBE_API_KEY not found!")
    print("   Edit .env and add your API key")
    sys.exit(1)

print(f"\n✅ API Key Found")
print(f"   Length: {len(api_key)} characters")
print(f"   Preview: {api_key[:10]}...{api_key[-4:]}")

# Test with httpx
print("\n🔄 Testing API call...")

try:
    import httpx

    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "snippet,statistics",
        "id": "dQw4w9WgXcQ",  # Rick Astley video
        "key": api_key,
    }

    print(f"   URL: {url}")
    print(f"   Video ID: dQw4w9WgXcQ")

    response = httpx.get(url, params=params, timeout=30.0)

    print(f"\n📊 Response:")
    print(f"   Status Code: {response.status_code}")

    if response.status_code == 200:
        data = response.json()

        if "items" in data and len(data["items"]) > 0:
            video = data["items"][0]
            snippet = video["snippet"]
            stats = video["statistics"]

            print(f"\n✅ API Call Successful!")
            print(f"\n   📺 Video Details:")
            print(f"   Title: {snippet['title']}")
            print(f"   Channel: {snippet['channelTitle']}")
            print(f"   Views: {int(stats['viewCount']):,}")
            print(f"   Likes: {int(stats['likeCount']):,}")

            print(f"\n✅ Your API key is working correctly!")
            print(f"   You can now run: python scripts/minimal_smoke_test.py")
        else:
            print(f"\n⚠️  API returned no items")
            print(f"   Response: {data}")

    elif response.status_code == 403:
        error_data = response.json()
        print(f"\n❌ API Error 403: Access Denied")
        print(f"   Reason: {error_data.get('error', {}).get('message', 'Unknown')}")

        if "API_KEY_SERVICE_BLOCKED" in str(error_data):
            print(f"\n   🔧 Your API key has service restrictions!")
            print(f"\n   To fix:")
            print(f"   1. Go to: https://console.cloud.google.com/apis/credentials")
            print(f"   2. Click on your API key")
            print(f"   3. Scroll to 'API restrictions'")
            print(f"   4. Select 'Restrict key'")
            print(f"   5. Check 'YouTube Data API v3' ✅")
            print(f"   6. Click 'Save'")
            print(f"   7. Wait 2-5 minutes for changes to apply")
            print(f"   8. Run this test again")

        elif "PERMISSION_DENIED" in str(error_data):
            print(f"\n   🔧 API not enabled!")
            print(f"\n   To fix:")
            print(f"   1. Go to: https://console.cloud.google.com/apis/library")
            print(f"   2. Search for 'YouTube Data API v3'")
            print(f"   3. Click 'Enable'")
            print(f"   4. Wait 1-2 minutes")
            print(f"   5. Run this test again")

        print(f"\n   Full error:")
        import json

        print(json.dumps(error_data, indent=2))

    elif response.status_code == 400:
        print(f"\n❌ API Error 400: Bad Request")
        print(f"   Your API key format might be incorrect")
        print(f"   Response: {response.text}")

    else:
        print(f"\n❌ Unexpected status code")
        print(f"   Response: {response.text}")

except ImportError:
    print(f"\n❌ httpx not installed")
    print(f"   Run: pip install httpx")
    sys.exit(1)

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
