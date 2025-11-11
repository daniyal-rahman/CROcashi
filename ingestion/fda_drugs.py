from pathlib import Path
from typing import List, Optional, Dict, Any
import csv
import zipfile

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_bytes
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader


PAGE_URL = "https://www.fda.gov/drugs/drug-approvals-and-databases/drugsfda-data-files"


def list_download_links(page_url: str = PAGE_URL) -> List[str]:
    client = HttpClient(requests_per_second=1.0)
    resp = client.get(page_url)
    soup = BeautifulSoup(resp.text, "html.parser")
    links: List[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/media/") or href.startswith("https://www.fda.gov/media/"):
            if any(href.lower().endswith(ext) for ext in (".zip", ".csv", ".xlsx")):
                if href.startswith("/media/"):
                    href = f"https://www.fda.gov{href}"
                links.append(href)
    return links


def download_all(save_dir: Optional[Path] = None) -> List[Path]:
    links = list_download_links()
    out_dir = Path("data/raw/fda_drugs") if save_dir is None else Path(save_dir)
    ensure_dir(out_dir)
    client = HttpClient(requests_per_second=1.0)
    saved: List[Path] = []
    for url in links:
        filename = url.rstrip("/").split("/")[-1]
        out_path = out_dir / filename
        resp = client.get(url)
        write_bytes(out_path, resp.content)
        saved.append(out_path)
    return saved


def parse_csv_file(csv_path: Path) -> List[Dict[str, Any]]:
    """Parse FDA Drugs@FDA CSV file."""
    records = []
    
    try:
        with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
            # Try to detect delimiter
            sample = f.read(1024)
            f.seek(0)
            delimiter = ',' if ',' in sample else '\t'
            
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                # Normalize field names (handle various formats)
                record = {}
                for key, value in row.items():
                    # Normalize key names
                    normalized_key = key.strip().lower().replace(' ', '_').replace('-', '_')
                    record[normalized_key] = value.strip() if value else None
                
                # Map common field variations to standard names
                if 'applno' in record or 'application_number' in record:
                    record['application_number'] = record.get('applno') or record.get('application_number')
                if 'product' in record or 'brand_name' in record:
                    record['brand_name'] = record.get('product') or record.get('brand_name')
                if 'ingredient' in record or 'generic_name' in record:
                    record['generic_name'] = record.get('ingredient') or record.get('generic_name')
                if 'applicant' in record or 'sponsor_name' in record:
                    record['sponsor_name'] = record.get('applicant') or record.get('sponsor_name')
                if 'approval' in record or 'approval_date' in record:
                    record['approval_date'] = record.get('approval') or record.get('approval_date')
                
                records.append(record)
    except Exception as e:
        print(f"Error parsing CSV {csv_path}: {e}")
    
    return records


def parse_zip_file(zip_path: Path) -> List[Dict[str, Any]]:
    """Parse FDA Drugs@FDA ZIP file containing CSV."""
    records = []
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Find CSV files in zip
            csv_files = [f for f in zip_ref.namelist() if f.endswith('.csv')]
            
            for csv_file in csv_files:
                # Extract and parse CSV
                with zip_ref.open(csv_file) as f:
                    # Read into memory
                    content = f.read().decode('utf-8', errors='ignore')
                    
                    # Parse CSV
                    reader = csv.DictReader(content.splitlines())
                    for row in reader:
                        record = {}
                        for key, value in row.items():
                            normalized_key = key.strip().lower().replace(' ', '_').replace('-', '_')
                            record[normalized_key] = value.strip() if value else None
                        
                        # Map field variations
                        if 'applno' in record or 'application_number' in record:
                            record['application_number'] = record.get('applno') or record.get('application_number')
                        if 'product' in record or 'brand_name' in record:
                            record['brand_name'] = record.get('product') or record.get('brand_name')
                        if 'ingredient' in record or 'generic_name' in record:
                            record['generic_name'] = record.get('ingredient') or record.get('generic_name')
                        if 'applicant' in record or 'sponsor_name' in record:
                            record['sponsor_name'] = record.get('applicant') or record.get('sponsor_name')
                        if 'approval' in record or 'approval_date' in record:
                            record['approval_date'] = record.get('approval') or record.get('approval_date')
                        
                        records.append(record)
    except Exception as e:
        print(f"Error parsing ZIP {zip_path}: {e}")
    
    return records


def fda_drugs_id_extractor(record: Dict[str, Any]) -> Optional[str]:
    """Extract application number from FDA drug record."""
    return record.get('application_number') or record.get('applno') or record.get('ApplNo') or ''


def ingest_fda_drugs(
    data_dir: Optional[Path] = None,
    load_to_staging: bool = True
) -> Dict[str, Any]:
    """
    Ingest FDA Drugs@FDA data from downloaded files.
    
    Args:
        data_dir: Directory containing downloaded FDA files (default: data/raw/fda_drugs)
        load_to_staging: Whether to load parsed records to staging table
    
    Returns:
        Dictionary with ingestion statistics
    """
    if data_dir is None:
        data_dir = Path("data/raw/fda_drugs")
    
    if not data_dir.exists():
        print(f"Data directory {data_dir} does not exist. Run download_all() first.")
        return {'error': 'Data directory not found'}
    
    all_records = []
    
    # Process all files in directory
    for file_path in data_dir.glob('*'):
        if file_path.suffix.lower() == '.csv':
            print(f"Parsing CSV: {file_path.name}")
            records = parse_csv_file(file_path)
            all_records.extend(records)
        elif file_path.suffix.lower() == '.zip':
            print(f"Parsing ZIP: {file_path.name}")
            records = parse_zip_file(file_path)
            all_records.extend(records)
    
    print(f"Parsed {len(all_records)} total records")
    
    # Load to staging if requested
    stats = {'parsed': len(all_records), 'inserted': 0, 'skipped': 0, 'errors': 0}
    
    if load_to_staging and all_records:
        loader = StagingLoader('fda_drugs')
        staging_stats = loader.load_records(
            all_records,
            id_extractor=fda_drugs_id_extractor,
            skip_duplicates=True
        )
        stats.update(staging_stats)
        print(f"Staging: {staging_stats['inserted']} inserted, {staging_stats['skipped']} skipped, {staging_stats['errors']} errors")
    
    return stats


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Ingest FDA Drugs@FDA data')
    parser.add_argument('--download', action='store_true', help='Download files first')
    parser.add_argument('--data-dir', type=Path, default=None, help='Data directory path')
    parser.add_argument('--no-staging', action='store_true', help='Skip loading to staging')
    args = parser.parse_args()
    
    if args.download:
        print("Downloading FDA Drugs@FDA files...")
        paths = download_all(save_dir=args.data_dir)
        print(f"Downloaded {len(paths)} files")
    
    print("\nIngesting FDA Drugs@FDA data...")
    stats = ingest_fda_drugs(
        data_dir=args.data_dir,
        load_to_staging=not args.no_staging
    )
    
    if 'error' not in stats:
        print(f"\n✓ Ingested {stats['parsed']} records")
        if not args.no_staging:
            print(f"  - Inserted: {stats['inserted']}")
            print(f"  - Skipped: {stats['skipped']}")
            print(f"  - Errors: {stats['errors']}")


