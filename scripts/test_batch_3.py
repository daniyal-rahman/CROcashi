#!/usr/bin/env python3
"""Test batch 3: Literature & Preprints (5 sources)."""
import sys
import time
from pathlib import Path

# Add parent directory to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ingestion.pubmed import fetch_sample as pubmed_sample
from ingestion.pmc import fetch_sample as pmc_sample
from ingestion.biorxiv import fetch_recent as biorxiv_recent
from ingestion.medrxiv import fetch_recent as medrxiv_recent
from ingestion.arxiv import search as arxiv_search


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
    """Test batch 3 (5 sources)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print("Testing Batch 3: Literature & Preprints (5 sources)")
    print("=" * 60)
    print()

    results = []
    results.append(test_one("pubmed", pubmed_sample, retmax=10))
    results.append(test_one("pmc", pmc_sample, retmax=10))
    results.append(test_one("biorxiv", biorxiv_recent, days=1))
    results.append(test_one("medrxiv", medrxiv_recent, days=1))
    results.append(test_one("arxiv", arxiv_search, max_results=10))

    success_count = sum(1 for ok, _, _ in results if ok)
    total = len(results)
    total_time = sum(elapsed for _, _, elapsed in results)
    print()
    print(f"📊 Batch 3 Results: {success_count}/{total} successful ({total_time:.1f}s total)")
    return success_count == total


if __name__ == "__main__":
    main()

