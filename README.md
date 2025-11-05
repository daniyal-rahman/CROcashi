## Ingestion scripts (Phase 1)

This repo contains Python scripts to fetch raw data from high-priority biotech/pharma sources. DB integration will be added later.

### Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run sample ingestions

```bash
python scripts/run_samples.py
```

Outputs are written under `data/raw/{source}/` as JSON, HTML, or downloaded files.

### Run with report

```bash
python scripts/run_with_report.py
```

This writes a consolidated report to `reports/ingestion_report.md` and `reports/ingestion_report.json`, including success/failure reasons.

### Sources covered

- ClinicalTrials.gov API (sample page)
- WHO ICTRP bulk CSV (requires current export URL)
- EMA Clinical Trials search (first page scrape)
- FDA Drugs@FDA data files (link scrape + download)
- FDA Orange Book data files (link scrape + download)
- FDA FAERS quarterly data (attempt recent quarter patterns)
- PubMed E-utilities (ESearch + ESummary)
- PMC E-utilities (ESearch + ESummary)
- bioRxiv API (recent window)
- medRxiv API (recent window)

Notes:
- WHO ICTRP bulk export link can change; update the URL in `ingestion/who_ictrp.py` or pass it when calling `download_bulk_csv`.
- NCBI rate limits: ~3 req/s without an API key, ~10 req/s with a key. These scripts throttle accordingly if you supply a key to the call.


