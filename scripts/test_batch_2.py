#!/usr/bin/env python3
"""Test batch 2: FDA sources (5 sources)."""
import sys
import time
from pathlib import Path

# Add parent directory to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ingestion.fda_faers import try_download_recent as faers_download
from ingestion.fda_purple_book import search_biosimilars as purple_book
from ingestion.fda_breakthrough import scrape_designations as breakthrough
from ingestion.fda_orphan import fetch_orphan_designations as orphan
from ingestion.fda_guidance import search_guidance as fda_guidance


RAW_DIR = ROOT / "data" / "raw"
TIMEOUT = 30


def test_one(name: str, func, *args, **kwargs):
    """Test a single ingestion function with timeout."""
    start = time.time()
    try:
        save_path = RAW_DIR / name
        result = func(*args, save_dir=save_path, **kwargs)
        elapsed = time.time() - start
        print(f"✅ {name}: SUCCESS ({elapsed:.1f}s)")
        if isinstance(result, dict):
            keys = list(result.keys())[:3]
            print(f"   Keys: {keys}")
        return True, None, elapsed
    except Exception as e:
        elapsed = time.time() - start
        print(f"❌ {name}: FAILED ({elapsed:.1f}s) - {str(e)[:100]}")
        return False, str(e), elapsed


def main():
    """Test batch 2 (5 sources)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print("Testing Batch 2: FDA Sources (5 sources)")
    print("=" * 60)
    print()

    results = []
    results.append(test_one("fda_faers", faers_download, attempts=2))
    results.append(test_one("fda_purple_book", purple_book))
    results.append(test_one("fda_breakthrough", breakthrough))
    results.append(test_one("fda_orphan", orphan))
    results.append(test_one("fda_guidance", fda_guidance))

    success_count = sum(1 for ok, _, _ in results if ok)
    total = len(results)
    total_time = sum(elapsed for _, _, elapsed in results)
    print()
    print(f"📊 Batch 2 Results: {success_count}/{total} successful ({total_time:.1f}s total)")
    return success_count == total


if __name__ == "__main__":
    main()
