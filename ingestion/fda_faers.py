from datetime import date
from pathlib import Path
from typing import List, Optional, Dict, Any
import csv
import zipfile

from ingestion.utils.files import ensure_dir, write_bytes
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader


BASE = "https://fis.fda.gov/content/Exports"


def _quarter_str(d: date) -> str:
    q = (d.month - 1) // 3 + 1
    return f"{d.year}Q{q}"


def _recent_quarters(count: int = 8) -> List[str]:
    quarters: List[str] = []
    today = date.today()
    year = today.year
    quarter = (today.month - 1) // 3 + 1
    for _ in range(count):
        quarters.append(f"{year}Q{quarter}")
        quarter -= 1
        if quarter == 0:
            quarter = 4
            year -= 1
    return quarters


def try_download_recent(save_dir: Optional[Path] = None, attempts: int = 8) -> List[Path]:
    patterns = [
        "FAERS_ascii_{q}.zip",
        "FAERS_{q}.zip",
    ]
    out_dir = Path("data/raw/fda_faers") if save_dir is None else Path(save_dir)
    ensure_dir(out_dir)
    client = HttpClient(requests_per_second=0.5)
    saved: List[Path] = []
    for q in _recent_quarters(attempts):
        for p in patterns:
            url = f"{BASE}/" + p.format(q=q)
            try:
                resp = client.get(url)
                if resp.status_code == 200 and resp.content:
                    out_path = out_dir / url.split("/")[-1]
                    write_bytes(out_path, resp.content)
                    saved.append(out_path)
                    break
            except Exception:
                continue
    return saved


def parse_faers_zip(zip_path: Path, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Parse FAERS ZIP file containing CSV data.
    
    Args:
        zip_path: Path to ZIP file
        limit: Maximum number of records to parse (None = all)
    """
    records = []
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            csv_files = [f for f in zip_ref.namelist() if f.endswith('.csv') or f.endswith('.txt')]
            
            # For small limits, only process 1 file
            max_files = 1 if limit and limit < 1000 else 5
            for csv_file in csv_files[:max_files]:
                if limit and len(records) >= limit:
                    break
                    
                with zip_ref.open(csv_file) as f:
                    content = f.read().decode('utf-8', errors='ignore')
                    
                    reader = csv.DictReader(content.splitlines(), delimiter='$')
                    for row in reader:
                        if limit and len(records) >= limit:
                            break
                            
                        record = {}
                        for key, value in row.items():
                            normalized_key = key.strip().lower().replace(' ', '_').replace('-', '_')
                            record[normalized_key] = value.strip() if value else None
                        
                        # Map common FAERS fields
                        if 'drug' in record:
                            record['drug_name'] = record.get('drug')
                        if 'mfr' in record or 'manufacturer' in record:
                            record['manufacturer_name'] = record.get('mfr') or record.get('manufacturer')
                        if 'event' in record or 'pt' in record:
                            record['adverse_event'] = record.get('event') or record.get('pt')
                        if 'case' in record or 'caseid' in record:
                            record['case_id'] = record.get('case') or record.get('caseid')
                        
                        records.append(record)
    except Exception as e:
        print(f"Error parsing FAERS ZIP {zip_path}: {e}")
    
    return records


def ingest_faers(
    data_dir: Optional[Path] = None,
    load_to_staging: bool = True,
    limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    Ingest FDA FAERS data from downloaded ZIP files.
    
    Args:
        data_dir: Directory containing downloaded FAERS files (default: data/raw/fda_faers)
        load_to_staging: Whether to load parsed records to staging table
        limit: Maximum number of records to process (None = all)
    
    Returns:
        Dictionary with ingestion statistics
    """
    if data_dir is None:
        data_dir = Path("data/raw/fda_faers")
    
    if not data_dir.exists():
        print(f"Data directory {data_dir} does not exist. Run try_download_recent() first.")
        return {'error': 'Data directory not found'}
    
    all_records = []
    
    # Process ZIP files (limit to 1 file for small samples)
    zip_files = sorted(data_dir.glob('*.zip'))
    if limit and limit < 1000:
        # For small samples, only process 1 most recent file
        zip_files = zip_files[:1]
    
    for file_path in zip_files:
        print(f"Parsing ZIP: {file_path.name}")
        records = parse_faers_zip(file_path, limit=limit)
        all_records.extend(records)
        
        # Stop if we've reached the limit
        if limit and len(all_records) >= limit:
            all_records = all_records[:limit]
            break
    
    print(f"Parsed {len(all_records)} total FAERS records")
    
    stats = {'parsed': len(all_records), 'inserted': 0, 'skipped': 0, 'errors': 0}
    
    if load_to_staging and all_records:
        loader = StagingLoader('fda_faers')
        staging_stats = loader.load_records(
            all_records,
            id_extractor=lambda r: r.get('case_id') or r.get('report_id') or '',
            skip_duplicates=True
        )
        stats.update(staging_stats)
        print(f"Staging: {staging_stats['inserted']} inserted, {staging_stats['skipped']} skipped, {staging_stats['errors']} errors")
    
    return stats


if __name__ == "__main__":
    files = try_download_recent()
    print(f"Downloaded {len(files)} FAERS files")


