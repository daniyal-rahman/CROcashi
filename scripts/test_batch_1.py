#!/usr/bin/env python3
"""Test batch 1: Core clinical trial sources (5 sources)."""
import sys
import time
from pathlib import Path

# Add parent directory to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ingestion.clinicaltrials_gov import fetch_studies_sample as ctgov_sample
from ingestion.who_ictrp import download_bulk_csv as ictrp_download
from ingestion.ema_trials import scrape_search_first_page as ema_sample
from ingestion.fda_drugs import download_all as drugsfda_download
from ingestion.fda_orange_book import download_all as orange_download


RAW_DIR = ROOT / "data" / "raw"
TIMEOUT = 30  # seconds per source


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
        elif isinstance(result, list):
            print(f"   Items: {len(result)}")
        return True, None, elapsed
    except Exception as e:
        elapsed = time.time() - start
        print(f"❌ {name}: FAILED ({elapsed:.1f}s) - {str(e)[:100]}")
        return False, str(e), elapsed


def main():
    """Test batch 1 (5 sources)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print("Testing Batch 1: Core Clinical Trial Sources (5 sources)")
    print("=" * 60)
    print()

    results = []
    results.append(test_one("clinicaltrials_gov", ctgov_sample, page_size=10))
    results.append(test_one("who_ictrp", ictrp_download, "https://trialsearch.who.int/Export/WHO-ICTRP-Results.csv"))
    results.append(test_one("ema_trials", ema_sample))
    results.append(test_one("fda_drugs", drugsfda_download))
    results.append(test_one("fda_orange_book", orange_download))

    success_count = sum(1 for ok, _, _ in results if ok)
    total = len(results)
    total_time = sum(elapsed for _, _, elapsed in results)
    print()
    print(f"📊 Batch 1 Results: {success_count}/{total} successful ({total_time:.1f}s total)")
    return success_count == total


if __name__ == "__main__":
    main()

