from pathlib import Path
from typing import Optional, Dict, Any, List
import csv

from ingestion.utils.files import ensure_dir, write_bytes
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader


def download_bulk_csv(
    download_url: str,
    save_dir: Optional[Path] = None,
    requests_per_second: float = 1.0,
) -> Path:
    client = HttpClient(requests_per_second=requests_per_second)
    resp = client.get(download_url)
    filename = download_url.split("/")[-1] or "ictrp.csv"
    out_dir = Path("data/raw/who_ictrp") if save_dir is None else Path(save_dir)
    ensure_dir(out_dir)
    out_path = out_dir / filename
    write_bytes(out_path, resp.content)
    return out_path


def parse_ictrp_csv(csv_path: Path) -> List[Dict[str, Any]]:
    """Parse WHO ICTRP CSV file."""
    records = []
    
    try:
        with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Normalize field names
                record = {}
                for key, value in row.items():
                    normalized_key = key.strip().lower().replace(' ', '_').replace('-', '_')
                    record[normalized_key] = value.strip() if value else None
                
                records.append(record)
    except Exception as e:
        print(f"Error parsing WHO ICTRP CSV {csv_path}: {e}")
    
    return records


def ingest_ictrp(
    csv_path: Optional[Path] = None,
    download_url: str = "https://trialsearch.who.int/Export/WHO-ICTRP-Results.csv",
    load_to_staging: bool = True
) -> Dict[str, Any]:
    """
    Ingest WHO ICTRP data from CSV file.
    
    Args:
        csv_path: Path to CSV file (if None, will download)
        download_url: URL to download CSV from
        load_to_staging: Whether to load parsed records to staging table
    
    Returns:
        Dictionary with ingestion statistics
    """
    if csv_path is None:
        csv_path = download_bulk_csv(download_url)
    
    if not csv_path.exists():
        return {'error': 'CSV file not found'}
    
    records = parse_ictrp_csv(csv_path)
    print(f"Parsed {len(records)} WHO ICTRP records")
    
    stats = {'parsed': len(records), 'inserted': 0, 'skipped': 0, 'errors': 0}
    
    if load_to_staging and records:
        loader = StagingLoader('who_ictrp')
        staging_stats = loader.load_records(
            records,
            id_extractor=lambda r: r.get('trial_id') or r.get('trial_number') or r.get('id', ''),
            skip_duplicates=True
        )
        stats.update(staging_stats)
        print(f"Staging: {staging_stats['inserted']} inserted, {staging_stats['skipped']} skipped, {staging_stats['errors']} errors")
    
    return stats


if __name__ == "__main__":
    # Provide the actual WHO ICTRP bulk CSV URL here when known
    # Example placeholder (must be replaced with the current official link):
    url = "https://trialsearch.who.int/Export/WHO-ICTRP-Results.csv"
    try:
        path = download_bulk_csv(url)
        print(f"Downloaded WHO ICTRP to {path}")
    except Exception as e:
        print(f"WHO ICTRP download failed: {e}")


