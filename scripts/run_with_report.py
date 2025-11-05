#!/usr/bin/env python3
import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from ingestion.clinicaltrials_gov import fetch_studies_sample as ctgov_sample
from ingestion.who_ictrp import download_bulk_csv as ictrp_download
from ingestion.ema_trials import scrape_search_first_page as ema_sample
from ingestion.fda_drugs import download_all as drugsfda_download
from ingestion.fda_orange_book import download_all as orange_download
from ingestion.fda_faers import try_download_recent as faers_download
from ingestion.pubmed import fetch_sample as pubmed_sample
from ingestion.pmc import fetch_sample as pmc_sample
from ingestion.biorxiv import fetch_recent as biorxiv_recent
from ingestion.medrxiv import fetch_recent as medrxiv_recent


ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"
RAW_DIR = ROOT / "data" / "raw"


def record_result(results: List[Dict[str, Any]], name: str, ok: bool, detail: str, extra: Dict[str, Any] | None = None) -> None:
    entry: Dict[str, Any] = {
        "source": name,
        "success": ok,
        "detail": detail,
    }
    if extra:
        entry.update(extra)
    results.append(entry)


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    results: List[Dict[str, Any]] = []
    started = datetime.utcnow().isoformat() + "Z"

    # ClinicalTrials.gov
    try:
        data = ctgov_sample(save_dir=RAW_DIR / "clinicaltrials_gov")
        n = len(data.get("studies", [])) if isinstance(data, dict) else 0
        record_result(results, "clinicaltrials_gov", True, f"Fetched {n} studies", {"count": n})
    except Exception:
        record_result(results, "clinicaltrials_gov", False, traceback.format_exc())

    # WHO ICTRP
    try:
        path = ictrp_download("https://trialsearch.who.int/Export/WHO-ICTRP-Results.csv", save_dir=RAW_DIR / "who_ictrp")
        record_result(results, "who_ictrp", True, f"Downloaded {path.name}")
    except Exception:
        record_result(results, "who_ictrp", False, traceback.format_exc())

    # EMA
    try:
        rows = ema_sample(save_dir=RAW_DIR / "ema_trials")
        record_result(results, "ema_trials", True, f"Parsed {len(rows)} rows", {"count": len(rows)})
    except Exception:
        record_result(results, "ema_trials", False, traceback.format_exc())

    # Drugs@FDA
    try:
        files = drugsfda_download(save_dir=RAW_DIR / "fda_drugs")
        record_result(results, "fda_drugs", True, f"Downloaded {len(files)} files", {"count": len(files)})
    except Exception:
        record_result(results, "fda_drugs", False, traceback.format_exc())

    # Orange Book
    try:
        files = orange_download(save_dir=RAW_DIR / "fda_orange_book")
        record_result(results, "fda_orange_book", True, f"Downloaded {len(files)} files", {"count": len(files)})
    except Exception:
        record_result(results, "fda_orange_book", False, traceback.format_exc())

    # FAERS
    try:
        files = faers_download(save_dir=RAW_DIR / "fda_faers")
        record_result(results, "fda_faers", True, f"Downloaded {len(files)} files", {"count": len(files)})
    except Exception:
        record_result(results, "fda_faers", False, traceback.format_exc())

    # PubMed
    try:
        data = pubmed_sample(save_dir=RAW_DIR / "pubmed")
        n = len(data.get("search", {}).get("esearchresult", {}).get("idlist", []))
        record_result(results, "pubmed", True, f"Fetched {n} IDs", {"count": n})
    except Exception:
        record_result(results, "pubmed", False, traceback.format_exc())

    # PMC
    try:
        data = pmc_sample(save_dir=RAW_DIR / "pmc")
        n = len(data.get("search", {}).get("esearchresult", {}).get("idlist", []))
        record_result(results, "pmc", True, f"Fetched {n} IDs", {"count": n})
    except Exception:
        record_result(results, "pmc", False, traceback.format_exc())

    # bioRxiv
    try:
        data = biorxiv_recent(save_dir=RAW_DIR / "biorxiv")
        n = len(data.get("collection", []))
        record_result(results, "biorxiv", True, f"Fetched {n} records", {"count": n})
    except Exception:
        record_result(results, "biorxiv", False, traceback.format_exc())

    # medRxiv
    try:
        data = medrxiv_recent(save_dir=RAW_DIR / "medrxiv")
        n = len(data.get("collection", []))
        record_result(results, "medrxiv", True, f"Fetched {n} records", {"count": n})
    except Exception:
        record_result(results, "medrxiv", False, traceback.format_exc())

    # Write JSON and Markdown reports
    report_obj = {
        "started": started,
        "finished": datetime.utcnow().isoformat() + "Z",
        "results": results,
    }
    (REPORTS_DIR / "ingestion_report.json").write_text(json.dumps(report_obj, indent=2), encoding="utf-8")

    # Markdown summary
    lines = [
        f"# Ingestion Report",
        "",
        f"Started: {report_obj['started']}",
        f"Finished: {report_obj['finished']}",
        "",
        "| Source | Success | Detail | Count |",
        "|---|:---:|---|---:",
    ]
    for r in results:
        count = r.get("count")
        lines.append(f"| {r['source']} | {'✅' if r['success'] else '❌'} | {str(r['detail']).splitlines()[0]} | {count if count is not None else ''} |")
    (REPORTS_DIR / "ingestion_report.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"Report written to {REPORTS_DIR / 'ingestion_report.md'} and JSON sidecar")


if __name__ == "__main__":
    main()


