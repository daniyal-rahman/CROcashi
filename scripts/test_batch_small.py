#!/usr/bin/env python3
"""Test ingestion sources in small batches of 5 with timeouts."""
import concurrent.futures
import sys
import time
import traceback
from pathlib import Path

# Add parent directory to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RAW_DIR = ROOT / "data" / "raw"


class TimeoutError(Exception):
    """Raised when a function call exceeds the timeout."""
    pass


def run_with_timeout(func, timeout_seconds=25, *args, **kwargs):
    """Run a function with a timeout using ThreadPoolExecutor (cross-platform)."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        try:
            result = future.result(timeout=timeout_seconds)
            return result
        except concurrent.futures.TimeoutError:
            # Try to cancel if possible
            future.cancel()
            raise TimeoutError(f"Function exceeded {timeout_seconds}s timeout")
        except Exception as e:
            raise


def test_one(name: str, func, timeout=25, *args, **kwargs):
    """Test a single ingestion function with timeout."""
    start_time = time.time()
    try:
        save_path = RAW_DIR / name
        result = run_with_timeout(func, timeout, *args, save_dir=save_path, **kwargs)
        elapsed = time.time() - start_time
        print(f"✅ {name}: SUCCESS ({elapsed:.1f}s)")
        if isinstance(result, dict):
            keys = list(result.keys())[:3]
            print(f"   Keys: {keys}")
        return True, None, elapsed
    except TimeoutError as e:
        elapsed = time.time() - start_time
        print(f"⏱️  {name}: TIMEOUT after {elapsed:.1f}s")
        return False, f"Timeout: {str(e)}", elapsed
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ {name}: FAILED ({elapsed:.1f}s) - {str(e)[:80]}")
        return False, str(e), elapsed


# Define test batches - 5 sources each
BATCHES = [
    # Batch 1: Core clinical trials
    [
        ("clinicaltrials_gov", "ingestion.clinicaltrials_gov", "fetch_studies_sample"),
        ("pubmed", "ingestion.pubmed", "fetch_sample"),
        ("pmc", "ingestion.pmc", "fetch_sample"),
        ("biorxiv", "ingestion.biorxiv", "fetch_recent"),
        ("medrxiv", "ingestion.medrxiv", "fetch_recent"),
    ],
    # Batch 2: FDA regulatory
    [
        ("fda_drugs", "ingestion.fda_drugs", "download_all"),
        ("fda_orange_book", "ingestion.fda_orange_book", "download_all"),
        ("fda_faers", "ingestion.fda_faers", "try_download_recent"),
        ("fda_purple_book", "ingestion.fda_purple_book", "search_biosimilars"),
        ("fda_breakthrough", "ingestion.fda_breakthrough", "scrape_designations"),
    ],
    # Batch 3: More FDA + WHO
    [
        ("fda_orphan", "ingestion.fda_orphan", "fetch_orphan_designations"),
        ("fda_guidance", "ingestion.fda_guidance", "search_guidance"),
        ("fda_warning_letters", "ingestion.fda_warning_letters", "fetch_recent_warnings"),
        ("who_ictrp", "ingestion.who_ictrp", "download_bulk_csv", "https://trialsearch.who.int/Export/WHO-ICTRP-Results.csv"),
        ("who_outbreak_news", "ingestion.who_outbreak_news", "fetch_outbreak_news"),
    ],
    # Batch 4: Scientific databases
    [
        ("europe_pmc", "ingestion.europe_pmc", "search"),
        ("clinvar", "ingestion.clinvar", "fetch_sample"),
        ("chembl", "ingestion.chembl", "get_compounds"),
        ("pubchem", "ingestion.pubchem", "get_compound", "2244"),  # aspirin CID
        ("uniprot", "ingestion.uniprot", "search_proteins"),
    ],
    # Batch 5: More scientific + patents
    [
        ("opentargets", "ingestion.opentargets", "search_targets"),
        ("string_db", "ingestion.string_db", "get_interactions", "BRAF"),
        ("reactome", "ingestion.reactome", "search_pathways"),
        ("biogrid", "ingestion.biogrid", "get_interactions"),
        ("patentsview", "ingestion.patentsview", "search_patents"),
    ],
    # Batch 6: RSS feeds + Reddit
    [
        ("rss_news", "ingestion.rss_news", "fetch_all_feeds"),
        ("reddit_biotech", "ingestion.reddit_biotech", "fetch_recent", 10),
        ("wayback_machine", "ingestion.wayback_machine", "get_snapshots", "fda.gov"),
        ("sec_edgar", "ingestion.sec_edgar", "search_company"),
        ("nih_reporter", "ingestion.nih_reporter", "search_projects"),
    ],
    # Batch 7: Regulatory international + others
    [
        ("ema_trials", "ingestion.ema_trials", "scrape_search_first_page"),
        ("ema_epar", "ingestion.ema_epar", "search_medicines"),
        ("health_canada", "ingestion.health_canada", "search_products"),
        ("mhra_uk", "ingestion.mhra_uk", "search_products"),
        ("nice_uk", "ingestion.nice_uk", "search_guidance"),
    ],
    # Batch 8: Remaining
    [
        ("arxiv", "ingestion.arxiv", "search"),
        ("chemrxiv", "ingestion.chemrxiv", "fetch_recent"),
        ("semantic_scholar", "ingestion.semantic_scholar", "search_papers"),
        ("pubtator", "ingestion.pubtator", "search_annotations"),
        ("orphanet", "ingestion.orphanet", "fetch_rare_diseases"),
    ],
]


def run_batch(batch_num, batch_items):
    """Run a single batch of tests."""
    print(f"\n{'='*60}")
    print(f"BATCH {batch_num}: Testing {len(batch_items)} sources")
    print(f"{'='*60}\n")
    
    results = []
    total_time = 0
    
    for name, module_path, func_name, *args in batch_items:
        try:
            # Dynamic import
            module = __import__(module_path, fromlist=[func_name])
            func = getattr(module, func_name)
        except Exception as e:
            print(f"❌ {name}: IMPORT ERROR - {str(e)[:80]}")
            results.append((name, False, f"Import error: {str(e)}", 0))
            continue
        
        ok, error, elapsed = test_one(name, func, *args)
        results.append((name, ok, error, elapsed))
        total_time += elapsed
        time.sleep(0.5)  # Small delay between tests
    
    print(f"\n📊 Batch {batch_num} Summary:")
    success = sum(1 for _, ok, _, _ in results if ok)
    print(f"   {success}/{len(results)} successful")
    print(f"   Total time: {total_time:.1f}s\n")
    
    return results


def main():
    """Run all batches."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    
    print("Starting ingestion tests in small batches...\n")
    all_results = []
    
    for batch_num, batch in enumerate(BATCHES, 1):
        batch_results = run_batch(batch_num, batch)
        all_results.extend(batch_results)
        
        # Ask if we should continue
        if batch_num < len(BATCHES):
            print(f"Completed batch {batch_num}/{len(BATCHES)}. Ready for next batch...")
            time.sleep(1)
    
    # Final summary
    print(f"\n{'='*60}")
    print("FINAL SUMMARY")
    print(f"{'='*60}")
    total_success = sum(1 for _, ok, _, _ in all_results if ok)
    total_failed = len(all_results) - total_success
    total_time = sum(elapsed for _, _, _, elapsed in all_results)
    
    print(f"\nTotal: {len(all_results)} sources tested")
    print(f"✅ Success: {total_success}")
    print(f"❌ Failed: {total_failed}")
    print(f"⏱️  Total time: {total_time:.1f}s")
    
    if total_failed > 0:
        print(f"\n❌ Failed sources:")
        for name, ok, error, _ in all_results:
            if not ok:
                print(f"   - {name}: {error[:100] if error else 'Unknown error'}")
    
    return total_success == len(all_results)


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(130)

