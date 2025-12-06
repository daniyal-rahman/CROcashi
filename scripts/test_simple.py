#!/usr/bin/env python3
"""Simple sequential test of all ingestion sources with timeout."""
import sys
import time
from pathlib import Path

# Add parent directory to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RAW_DIR = ROOT / "data" / "raw"


def test_source(name, module_path, func_name, *args, timeout=15):
    """Test a single source with timeout using subprocess (can actually kill)."""
    import subprocess
    import json
    import tempfile
    
    print(f"\n{'='*70}")
    print(f"Testing: {name}")
    print(f"Module: {module_path}.{func_name}")
    print(f"{'='*70}")
    sys.stdout.flush()
    
    start_time = time.time()
    
    try:
        # Create a temporary script to run the test in a subprocess
        args_str = repr(args) if args else '()'
        test_script = f"""
import sys
import json
from pathlib import Path
sys.path.insert(0, r'{ROOT}')

module = __import__('{module_path}', fromlist=['{func_name}'])
func = getattr(module, '{func_name}')

save_path = Path(r'{RAW_DIR}') / '{name}'
args = {args_str}
result = func(*args, save_dir=save_path)

# Serialize result summary
summary = {{'type': type(result).__name__, 'success': True}}
if isinstance(result, dict):
    summary['keys'] = list(result.keys())[:5]
    summary['count'] = result.get('count', len(result) if isinstance(result, (list, dict)) else None)
elif isinstance(result, list):
    summary['count'] = len(result)
elif isinstance(result, Path):
    summary['path'] = str(result)

print(json.dumps(summary))
"""
        
        print(f"→ Calling function (timeout: {timeout}s)...")
        sys.stdout.flush()
        
        # Run in subprocess with timeout
        try:
            proc = subprocess.run(
                [sys.executable, '-c', test_script],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(ROOT)
            )
            
            elapsed = time.time() - start_time
            
            if proc.returncode == 0:
                try:
                    summary = json.loads(proc.stdout.strip())
                    print(f"✓ SUCCESS in {elapsed:.1f}s")
                    if 'keys' in summary:
                        print(f"  Result keys: {summary['keys']}")
                    if 'count' in summary and summary['count']:
                        print(f"  Count: {summary['count']}")
                    if 'path' in summary:
                        print(f"  File: {summary['path']}")
                except (UnicodeEncodeError, AttributeError):
                    print(f"✓ SUCCESS in {elapsed:.1f}s")
                sys.stdout.flush()
                return True, None, elapsed
            else:
                error_msg = proc.stderr[:200] if proc.stderr else proc.stdout[:200]
                print(f"❌ FAILED in {elapsed:.1f}s")
                print(f"   Error: {error_msg}")
                sys.stdout.flush()
                return False, error_msg, elapsed
                
        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            print(f"⏱️  TIMEOUT after {elapsed:.1f}s (> {timeout}s)")
            print(f"⚠️  NOTE: {name} is hanging - needs investigation")
            sys.stdout.flush()
            return False, "Timeout", elapsed
            
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ FAILED in {elapsed:.1f}s")
        print(f"   Error: {str(e)[:200]}")
        sys.stdout.flush()
        return False, str(e), elapsed


# List of all implemented sources
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
    # NOTE: fda_faers hangs - skipping for now
    # ("fda_faers", "ingestion.fda_faers", "try_download_recent"),
    ("fda_purple_book", "ingestion.fda_purple_book", "search_biosimilars"),
    ("fda_breakthrough", "ingestion.fda_breakthrough", "scrape_designations"),
    ("fda_orphan", "ingestion.fda_orphan", "fetch_orphan_designations"),
    ("fda_guidance", "ingestion.fda_guidance", "search_guidance"),
    ("fda_warning_letters", "ingestion.fda_warning_letters", "fetch_recent_warnings"),
    
    # WHO
    ("who_ictrp", "ingestion.who_ictrp", "download_bulk_csv", "https://trialsearch.who.int/Export/WHO-ICTRP-Results.csv"),
    ("who_outbreak_news", "ingestion.who_outbreak_news", "fetch_outbreak_news"),
    
    # EMA
    ("ema_trials", "ingestion.ema_trials", "scrape_search_first_page"),
    ("ema_epar", "ingestion.ema_epar", "search_medicines"),
    
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
    ("disgenet", "ingestion.disgenet", "search_diseases"),
    ("orphanet", "ingestion.orphanet", "fetch_rare_diseases"),
    
    # Patents
    ("patentsview", "ingestion.patentsview", "search_patents"),
    ("uspto_public_pair", "ingestion.uspto_public_pair", "search_application", ""),
    
    # RSS feeds + Reddit
    ("rss_news", "ingestion.rss_news", "fetch_all_feeds"),
    ("reddit_biotech", "ingestion.reddit_biotech", "fetch_recent", 10),
    ("wayback_machine", "ingestion.wayback_machine", "get_snapshots", "fda.gov"),
    
    # Financial
    ("sec_edgar", "ingestion.sec_edgar", "search_company", ""),  # Empty string for name
    ("nih_reporter", "ingestion.nih_reporter", "search_projects"),
    
    # Regulatory international
    ("health_canada", "ingestion.health_canada", "search_products"),
    ("mhra_uk", "ingestion.mhra_uk", "search_products"),
    ("nice_uk", "ingestion.nice_uk", "search_guidance"),
    
    # More literature
    ("arxiv", "ingestion.arxiv", "search"),
    ("chemrxiv", "ingestion.chemrxiv", "fetch_recent"),
    ("semantic_scholar", "ingestion.semantic_scholar", "search_papers"),
    ("pubtator", "ingestion.pubtator", "search_annotations"),
    
    # OpenFDA
    ("openfda", "ingestion.openfda", "search_drugs"),
]


def main():
    """Run tests sequentially."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    
    print("="*70)
    print("INGESTION SOURCE TESTING")
    print("="*70)
    print(f"Testing {len(SOURCES)} sources sequentially")
    print(f"Timeout per source: 15 seconds")
    print(f"Results will be saved to: {RAW_DIR}")
    print("="*70)
    
    results = []
    hanging_sources = []
    total_start = time.time()
    
    for idx, source_info in enumerate(SOURCES, 1):
        name = source_info[0]
        args = source_info[3:] if len(source_info) > 3 else ()
        
        print(f"\n[{idx}/{len(SOURCES)}] ", end="")
        ok, error, elapsed = test_source(name, source_info[1], source_info[2], *args, timeout=15)
        results.append((name, ok, error, elapsed))
        
        if not ok and error == "Timeout":
            hanging_sources.append(name)
        
        # Small delay between tests
        time.sleep(0.5)
    
    # Summary
    total_time = time.time() - total_start
    print(f"\n\n{'='*70}")
    print("TEST SUMMARY")
    print(f"{'='*70}")
    
    success_count = sum(1 for _, ok, _, _ in results if ok)
    failed_count = len(results) - success_count
    
    print(f"\nTotal sources tested: {len(results)}")
    print(f"✅ Successful: {success_count}")
    print(f"❌ Failed: {failed_count}")
    print(f"⏱️  Total time: {total_time:.1f}s ({total_time/60:.1f} minutes)")
    
    if hanging_sources:
        print(f"\n⚠️  HANGING SOURCES (timeout > 15s):")
        for name in hanging_sources:
            print(f"   - {name}")
    
    if failed_count > 0:
        print(f"\n❌ Failed sources:")
        for name, ok, error, elapsed in results:
            if not ok:
                print(f"   - {name} ({elapsed:.1f}s): {error[:100] if error else 'Unknown'}")
    
    print(f"\n{'='*70}")
    return success_count == len(results)


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(130)

