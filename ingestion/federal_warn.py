from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import re

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader


BASE_URL = "https://www.dol.gov/agencies/eta/layoffs/warn"


def _parse_warn_notice(client: HttpClient, url: str) -> Optional[Dict[str, Any]]:
    """
    Parse individual WARN notice page to extract structured data.
    
    Args:
        client: HTTP client
        url: URL of WARN notice page
        
    Returns:
        Dict with parsed WARN notice data or None if parsing fails
    """
    try:
        resp = client.get(url)
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Extract text content
        text = soup.get_text(separator=' ', strip=True)
        
        # Extract company name
        company_name = None
        headings = soup.find_all(['h1', 'h2', 'h3'])
        for heading in headings:
            text_h = heading.get_text(strip=True)
            if text_h and len(text_h) < 200:
                company_name = text_h
                break
        
        if not company_name:
            company_pattern = r'([A-Z][a-zA-Z\s&,\.]+(?:Inc\.?|LLC|Corp\.?|Ltd\.?|Pharmaceuticals?|Biotech))'
            match = re.search(company_pattern, text[:1000])
            if match:
                company_name = match.group(1).strip()
        
        # Extract dates
        notice_date = None
        effective_date = None
        
        date_patterns = [
            r'Notice Date[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
            r'Date[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
        ]
        
        for pattern in date_patterns:
            matches = re.findall(pattern, text[:2000])
            if matches:
                try:
                    notice_date = matches[0]
                    if len(matches) > 1:
                        effective_date = matches[1]
                    break
                except (IndexError, ValueError):
                    continue
        
        # Extract number of employees
        employees_affected = None
        employee_patterns = [
            r'(\d+)\s+employees?',
            r'(\d+)\s+workers?',
            r'layoff[:\s]+(\d+)',
        ]
        
        for pattern in employee_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    employees_affected = int(match.group(1))
                    break
                except (ValueError, IndexError):
                    continue
        
        # Extract location
        location = None
        location_patterns = [
            r'Location[:\s]+([^,\n]{0,100})',
            r'([A-Z][a-z]+,\s*[A-Z]{2})',
        ]
        
        for pattern in location_patterns:
            match = re.search(pattern, text)
            if match:
                location = match.group(1).strip()
                break
        
        # Extract facility name
        facility_name = None
        facility_match = re.search(r'Facility[:\s]+([^,\n]{0,100})', text, re.IGNORECASE)
        if facility_match:
            facility_name = facility_match.group(1).strip()
        
        # Extract reason
        reason = None
        reason_keywords = ['restructuring', 'closure', 'relocation', 'downsizing', 'economic']
        for keyword in reason_keywords:
            if keyword in text.lower():
                reason = keyword
                break
        
        if not company_name:
            return None
        
        # Generate notice ID
        from src.utils.id_generation import generate_hash_id, generate_abstract_id
        
        notice_id = url.split('/')[-1] if '/' in url else None
        if not notice_id:
            if notice_date and company_name:
                notice_id = generate_hash_id('FED-WARN', notice_date.replace('/', '-'), company_name)
            else:
                notice_id = generate_abstract_id('FED-WARN', url)
        
        return {
            'notice_id': notice_id,
            'company_name': company_name,
            'notice_date': notice_date,
            'effective_date': effective_date,
            'employees_affected': employees_affected,
            'location': location,
            'facility_name': facility_name,
            'reason': reason,
            'notice_url': url,
            'notice_text': text[:50000] if len(text) > 50000 else text,
        }
        
    except Exception as e:
        print(f"Error parsing WARN notice {url}: {e}")
        return None


def fetch_recent_warn_notices(
    limit: int = 50,
    save_dir: Optional[Path] = None,
    load_to_staging: bool = True
) -> Dict[str, Any]:
    """
    Fetch recent Federal WARN notices.
    
    Args:
        limit: Maximum number of notices to fetch
        save_dir: Optional directory to save raw HTML
        load_to_staging: Whether to load data into staging table (default: True)
    
    Returns:
        Dict with WARN notice records
    """
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    
    try:
        resp = client.get(BASE_URL)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        
        # Find WARN notice links
        warn_notices = []
        links_found = []
        
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a.get("href", "")
            if "warn" in text.lower() or "warn" in href.lower() or "layoff" in text.lower():
                full_url = href if href.startswith("http") else f"https://www.dol.gov{href}"
                links_found.append({"text": text[:200], "href": full_url})
        
        # Parse individual notice pages
        for link in links_found[:limit]:
            try:
                notice_data = _parse_warn_notice(client, link["href"])
                if notice_data:
                    warn_notices.append(notice_data)
            except Exception as e:
                print(f"Error parsing WARN notice {link['href']}: {e}")
                continue
        
        result = {
            "links_found": len(links_found),
            "notices_parsed": len(warn_notices),
            "notices": warn_notices,
        }
        
        if save_dir is not None:
            ensure_dir(save_dir)
            write_text(Path(save_dir) / "federal_warn.html", html)
            import json
            write_text(Path(save_dir) / "federal_warn.json", json.dumps(result, indent=2, default=str))
        
        # Load to staging if requested
        if load_to_staging and warn_notices:
            loader = StagingLoader('federal_warn')
            stats = loader.load_records(
                warn_notices,
                id_extractor=lambda r: r.get('notice_id') or r.get('notice_url', ''),
                skip_duplicates=True
            )
            print(f"Staging: {stats['inserted']} inserted, {stats['skipped']} skipped, {stats['errors']} errors")
            result['staging_stats'] = stats
        
        return result
    except Exception as e:
        return {
            "notices_parsed": 0,
            "error": str(e),
        }


if __name__ == "__main__":
    out = Path("data/raw/federal_warn")
    result = fetch_recent_warn_notices(save_dir=out)
    print(f"Fetched {result.get('notices_found', 0)} WARN notices")

