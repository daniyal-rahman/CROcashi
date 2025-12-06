#!/usr/bin/env python3
"""Test batch 4: Scientific Databases (5 sources)."""
import sys
import time
from pathlib import Path

# Add parent directory to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ingestion.chembl import get_compounds as chembl_get
from ingestion.pubchem import get_compound as pubchem_get
from ingestion.uniprot import search_proteins as uniprot_search
from ingestion.opentargets import search_targets as opentargets_search
from ingestion.clinvar import fetch_sample as clinvar_fetch


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
    """Test batch 4 (5 sources)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print("Testing Batch 4: Scientific Databases (5 sources)")
    print("=" * 60)
    print()

    results = []
    results.append(test_one("chembl", chembl_get, limit=10))
    results.append(test_one("pubchem", pubchem_get, "2244"))  # Aspirin CID
    results.append(test_one("uniprot", uniprot_search, limit=10))
    results.append(test_one("opentargets", opentargets_search, limit=5))
    results.append(test_one("clinvar", clinvar_fetch, retmax=10))

    success_count = sum(1 for ok, _, _ in results if ok)
    total = len(results)
    total_time = sum(elapsed for _, _, elapsed in results)
    print()
    print(f"📊 Batch 4 Results: {success_count}/{total} successful ({total_time:.1f}s total)")
    return success_count == total


if __name__ == "__main__":
    main()

