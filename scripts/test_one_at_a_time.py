#!/usr/bin/env python3
"""Test ingestion sources one at a time with timeout."""
import concurrent.futures
import sys
import threading
import time
from pathlib import Path

# Add parent directory to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RAW_DIR = ROOT / "data" / "raw"


class TimeoutError(Exception):
    """Raised when a function call exceeds the timeout."""
    pass


def run_with_timeout(func, timeout_seconds=20, *args, **kwargs):
    """Run a function with a timeout using ThreadPoolExecutor."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        try:
            result = future.result(timeout=timeout_seconds)
            return result
        except concurrent.futures.TimeoutError:
            # Note: ThreadPoolExecutor can't actually kill threads, but we can detect timeout
            raise TimeoutError(f"Function exceeded {timeout_seconds}s timeout - may still be running")
        except Exception as e:
            raise


def test_one(name: str, module_path: str, func_name: str, timeout=20, *args, **kwargs):
    """Test a single ingestion function with timeout."""
    print(f"\n{'='*60}")
    print(f"Testing: {name} (timeout: {timeout}s)")
    print(f"{'='*60}")
    sys.stdout.flush()
    
    start_time = time.time()
    try:
        # Dynamic import
        module = __import__(module_path, fromlist=[func_name])
        func = getattr(module, func_name)
        
        save_path = RAW_DIR / name
        print(f"   Starting...", end="", flush=True)
        
        # Run with timeout
        result = run_with_timeout(func, timeout, *args, save_dir=save_path, **kwargs)
        
        elapsed = time.time() - start_time
        print(f"\r   ✅ {name}: SUCCESS ({elapsed:.1f}s)")
        if isinstance(result, dict):
            keys = list(result.keys())[:3]
            print(f"      Keys: {keys}")
        return True, None, elapsed
        
    except TimeoutError as e:
        elapsed = time.time() - start_time
        print(f"\r   ⏱️  {name}: TIMEOUT after {elapsed:.1f}s")
        print(f"      ⚠️  Process may still be running - check manually")
        return False, f"Timeout: {str(e)}", elapsed
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\r   ❌ {name}: FAILED ({elapsed:.1f}s)")
        print(f"      Error: {str(e)[:150]}")
        return False, str(e), elapsed


# Define all sources to test
SOURCES = [
    # Core clinical trials
    ("clinicaltrials_gov", "ingestion.clinicaltrials_gov", "fetch_studies_sample"),
    ("pubmed", "ingestion.pubmed", "fetch_sample"),
    ("pmc", "ingestion.pmc", "fetch_sample"),
    ("biorxiv", "ingestion.biorxiv", "fetch_recent"),
    ("medrxiv", "ingestion.medrxiv", "fetch_recent"),
    
    # FDA regulatory
    ("fda_drugs", "ingestion.fda_drugs", "download_all"),
    ("fda_orange_book", "ingestion.fda_orange_book", "download_all"),
    ("fda_faers", "ingestion.fda_faers", "try_download_recent"),
    ("fda_purple_book", "ingestion.fda_purple_book", "search_biosimilars"),
    ("fda_breakthrough", "ingestion.fda_breakthrough", "scrape_designations"),
    ("fda_orphan", "ingestion.fda_orphan", "fetch_orphan_designations"),
    ("fda_guidance", "ingestion.fda_guidance", "search_guidance"),
    ("fda_warning_letters", "ingestion.fda_warning_letters", "fetch_recent_warnings"),
    
    # WHO
    ("who_ictrp", "ingestion.who_ictrp", "download_bulk_csv", "https://trialsearch.who.int/Export/WHO-ICTRP-Results.csv"),
    ("who_outbreak_news", "ingestion.who_outbreak_news", "fetch_outbreak_news"),
    
    # Scientific databases
    ("europe_pmc", "ingestion.europe_pmc", "search"),
    ("clinvar", "ingestion.clinvar", "fetch_sample"),
    ("chembl", "ingestion.chembl", "get_compounds"),
    ("pubchem", "ingestion.pubchem", "get_compound", "2244"),
    ("uniprot", "ingestion.uniprot", "search_proteins"),
    ("opentargets", "ingestion.opentargets", "search_targets"),
    ("string_db", "ingestion.string_db", "get_interactions", "BRAF"),
    ("reactome", "ingestion.reactome", "search_pathways"),
    ("biogrid", "ingestion.biogrid", "get_interactions"),
    
    # Patents
    ("patentsview", "ingestion.patentsview", "search_patents"),
    
    # RSS feeds + Reddit
    ("rss_news", "ingestion.rss_news", "fetch_all_feeds"),
    ("reddit_biotech", "ingestion.reddit_biotech", "fetch_recent", 10),
    ("wayback_machine", "ingestion.wayback_machine", "get_snapshots", "fda.gov"),
    
    # Financial
    ("sec_edgar", "ingestion.sec_edgar", "search_company"),
    ("nih_reporter", "ingestion.nih_reporter", "search_projects"),
    
    # Regulatory international
    ("ema_trials", "ingestion.ema_trials", "scrape_search_first_page"),
    ("ema_epar", "ingestion.ema_epar", "search_medicines"),
    ("health_canada", "ingestion.health_canada", "search_products"),
    ("mhra_uk", "ingestion.mhra_uk", "search_products"),
    ("nice_uk", "ingestion.nice_uk", "search_guidance"),
    
    # More literature
    ("arxiv", "ingestion.arxiv", "search"),
    ("chemrxiv", "ingestion.chemrxiv", "fetch_recent"),
    ("semantic_scholar", "ingestion.semantic_scholar", "search_papers"),
    ("pubtator", "ingestion.pubtator", "search_annotations"),
    ("orphanet", "ingestion.orphanet", "fetch_rare_diseases"),
]


def main():
    """Test all sources one at a time."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    
    print("="*60)
    print("Testing ingestion sources ONE AT A TIME")
    print("="*60)
    print(f"Total sources to test: {len(SOURCES)}\n")
    
    results = []
    total_start = time.time()
    
    for idx, source_tuple in enumerate(SOURCES, 1):
        name = source_tuple[0]
        args = source_tuple[3:] if len(source_tuple) > 3 else ()
        
        print(f"\n[{idx}/{len(SOURCES)}] ", end="", flush=True)
        ok, error, elapsed = test_one(name, source_tuple[1], source_tuple[2], *args)
        results.append((name, ok, error, elapsed))
        
        # Small delay between tests
        time.sleep(0.3)
    
    # Final summary
    total_time = time.time() - total_start
    print(f"\n\n{'='*60}")
    print("FINAL SUMMARY")
    print(f"{'='*60}")
    
    success_count = sum(1 for _, ok, _, _ in results if ok)
    failed_count = len(results) - success_count
    
    print(f"\nTotal: {len(results)} sources")
    print(f"✅ Success: {success_count}")
    print(f"❌ Failed: {failed_count}")
    print(f"⏱️  Total time: {total_time:.1f}s ({total_time/60:.1f}m)")
    
    if failed_count > 0:
        print(f"\n❌ Failed sources:")
        for name, ok, error, elapsed in results:
            if not ok:
                print(f"   - {name} ({elapsed:.1f}s): {error[:100] if error else 'Unknown'}")
    
    return success_count == len(results)


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(130)

