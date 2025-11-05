#!/usr/bin/env python3
from pathlib import Path

from ingestion.clinicaltrials_gov import fetch_studies_sample as ctgov_sample
from ingestion.who_ictrp import download_bulk_csv as ictrp_download
from ingestion.ema_trials import scrape_search_first_page as ema_sample
from ingestion.fda_drugs import download_all as drugsfda_download
from ingestion.fda_orange_book import download_all as orange_download
from ingestion.fda_faers import try_download_recent as faers_download
from ingestion.pubmed import fetch_sample as pubmed_sample
from ingestion.pmc import fetch_sample as pmc_sample
from ingestion.biorxiv import fetch_recent as biorxiv_recent


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    print("Running sample ingestions...")

    # ClinicalTrials.gov
    ct = ctgov_sample(save_dir=ROOT / "data/raw/clinicaltrials_gov")
    print(f"ClinicalTrials.gov: {len(ct.get('studies', []))} studies")

    # WHO ICTRP (requires a valid URL; skip if default fails)
    try:
        ictrp_path = ictrp_download("https://trialsearch.who.int/Export/WHO-ICTRP-Results.csv")
        print(f"WHO ICTRP: downloaded {ictrp_path.name}")
    except Exception as e:
        print(f"WHO ICTRP: skipped ({e})")

    # EMA scraper
    ema_rows = ema_sample(save_dir=ROOT / "data/raw/ema_trials")
    print(f"EMA: parsed {len(ema_rows)} rows (first page)")

    # FDA Drugs@FDA and Orange Book
    try:
        drugs_files = drugsfda_download(save_dir=ROOT / "data/raw/fda_drugs")
        print(f"Drugs@FDA: {len(drugs_files)} files")
    except Exception as e:
        print(f"Drugs@FDA: skipped ({e})")

    try:
        orange_files = orange_download(save_dir=ROOT / "data/raw/fda_orange_book")
        print(f"Orange Book: {len(orange_files)} files")
    except Exception as e:
        print(f"Orange Book: skipped ({e})")

    # FAERS recent
    try:
        faers_files = faers_download(save_dir=ROOT / "data/raw/fda_faers")
        print(f"FAERS: {len(faers_files)} files")
    except Exception as e:
        print(f"FAERS: skipped ({e})")

    # PubMed / PMC
    pm = pubmed_sample(save_dir=ROOT / "data/raw/pubmed")
    print(f"PubMed: {len(pm.get('search', {}).get('esearchresult', {}).get('idlist', []))} IDs")

    pc = pmc_sample(save_dir=ROOT / "data/raw/pmc")
    print(f"PMC: {len(pc.get('search', {}).get('esearchresult', {}).get('idlist', []))} IDs")

    # bioRxiv recent
    bx = biorxiv_recent(save_dir=ROOT / "data/raw/biorxiv")
    print(f"bioRxiv: {len(bx.get('collection', []))} records")


if __name__ == "__main__":
    main()


