#!/usr/bin/env python3
"""Test batch 5: News & RSS (5 sources)."""
import sys
import time
from pathlib import Path

# Add parent directory to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ingestion.rss_news import fetch_feed


RAW_DIR = ROOT / "data" / "raw"
TIMEOUT = 30


def test_one(name: str, feed_name: str):
    """Test a single RSS feed."""
    start = time.time()
    try:
        save_path = RAW_DIR / "rss_news"
        result = fetch_feed(feed_name, save_dir=save_path)
        elapsed = time.time() - start
        entries = result.get("entries_count", 0)
        print(f"✅ {name}: SUCCESS ({elapsed:.1f}s) - {entries} entries")
        return True, None, elapsed
    except Exception as e:
        elapsed = time.time() - start
        print(f"❌ {name}: FAILED ({elapsed:.1f}s) - {str(e)[:100]}")
        return False, str(e), elapsed


def main():
    """Test batch 5 (5 RSS feeds)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print("Testing Batch 5: News & RSS Feeds (5 sources)")
    print("=" * 60)
    print()

    feeds = [
        ("endpoints", "endpoints"),
        ("fiercebiotech", "fiercebiotech"),
        ("biopharmadive", "biopharmadive"),
        ("biospace", "biospace"),
        ("stat", "stat"),
    ]

    results = []
    for name, feed_name in feeds:
        results.append(test_one(name, feed_name))

    success_count = sum(1 for ok, _, _ in results if ok)
    total = len(results)
    total_time = sum(elapsed for _, _, elapsed in results)
    print()
    print(f"📊 Batch 5 Results: {success_count}/{total} successful ({total_time:.1f}s total)")
    return success_count == total


if __name__ == "__main__":
    main()

