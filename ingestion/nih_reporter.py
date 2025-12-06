import json
from pathlib import Path
from typing import Any, Dict, Optional, List

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader


API_BASE = "https://api.reporter.nih.gov/v2"


def search_projects(
    query: str = "biotech",
    limit: int = 50,
    save_dir: Optional[Path] = None,
    load_to_staging: bool = True
) -> Dict[str, Any]:
    """Search NIH RePORTER for projects."""
    client = HttpClient(requests_per_second=2.0)
    payload = {
        "criteria": {
            "text_search": query,
        },
        "offset": 0,
        "limit": limit,
    }
    resp = client.session.post(
        f"{API_BASE}/Projects/Search",
        json=payload,
        headers={"Content-Type": "application/json", **client.default_headers},
        timeout=client.timeout_seconds,
    )
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "nih_reporter_projects.json", resp.text)

    # Extract records from API response
    records = []
    if isinstance(data, dict):
        projects = data.get("results", [])
        if isinstance(projects, list):
            for project in projects:
                if isinstance(project, dict):
                    records.append({
                        'project_number': project.get('project_number', ''),
                        'application_id': project.get('application_id', ''),
                        'organization_name': project.get('organization', {}).get('org_name', '') if isinstance(project.get('organization'), dict) else '',
                        'title': project.get('title', ''),
                        'raw_data': project
                    })
    
    stats = {'parsed': len(records), 'inserted': 0, 'skipped': 0, 'errors': 0}
    
    if load_to_staging and records:
        loader = StagingLoader('nih_reporter')
        
        def nih_id_extractor(r):
            # Try multiple ID fields, fallback to hash-based ID
            project_num = r.get('project_number', '').strip()
            app_id = r.get('application_id', '').strip()
            if project_num:
                return project_num
            elif app_id:
                return app_id
            else:
                # Fallback: generate hash-based ID from available fields
                from src.utils.id_generation import generate_hash_id
                title = r.get('title', '').strip()
                org_name = r.get('organization_name', '').strip()
                raw_data = r.get('raw_data', {})
                
                # Use any available data to generate a unique hash
                if title:
                    return generate_hash_id('NIH', title, org_name)
                elif org_name:
                    return generate_hash_id('NIH', org_name, str(raw_data.get('id', '')))
                elif raw_data:
                    # Last resort: hash the raw data itself
                    raw_str = json.dumps(raw_data, sort_keys=True)
                    return generate_hash_id('NIH', raw_str[:100])
                else:
                    # Absolute last resort: hash empty record position
                    return generate_hash_id('NIH', str(id(r)))
        
        staging_stats = loader.load_records(
            records,
            id_extractor=nih_id_extractor,
            skip_duplicates=True
        )
        stats.update(staging_stats)
        print(f"Staging: {staging_stats['inserted']} inserted, {staging_stats['skipped']} skipped, {staging_stats['errors']} errors")
    
    result = data if isinstance(data, dict) else {'raw_data': data}
    result.update(stats)
    return result


if __name__ == "__main__":
    out = Path("data/raw/nih_reporter")
    result = search_projects(save_dir=out)
    print("Fetched NIH RePORTER projects")

