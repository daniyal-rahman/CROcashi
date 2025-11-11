from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import re

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader, fda_warning_letter_id_extractor


BASE_URL = "https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/warning-letters"


def fetch_recent_warnings(
    limit: int = 50,
    save_dir: Optional[Path] = None,
    load_to_staging: bool = True
) -> Dict[str, Any]:
    """
    Fetch recent FDA Warning Letters.
    
    Args:
        limit: Maximum number of warning letters to fetch
        save_dir: Optional directory to save raw HTML
        load_to_staging: Whether to load data into staging table (default: True)
        
    Returns:
        Dict with warning letter records
    """
    client = HttpClient(requests_per_second=1.0)
    resp = client.get(BASE_URL)
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    # Extract warning letter links - look for actual letter pages
    links = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        text = a.get_text(strip=True)
        # Look for links that point to actual warning letters
        if ("warning" in text.lower() or "warning" in href.lower()) and \
           ("letter" in href.lower() or "/warning-letters/" in href.lower()):
            full_url = href if href.startswith("http") else f"https://www.fda.gov{href}"
            links.append({"href": full_url, "text": text[:200]})

    # Fetch and parse individual warning letters
    warning_letters = []
    for link in links[:limit]:
        try:
            letter_data = _parse_warning_letter(client, link["href"])
            if letter_data:
                warning_letters.append(letter_data)
        except Exception as e:
            print(f"Error parsing warning letter {link['href']}: {e}")
            continue

    results: Dict[str, Any] = {
        "links_count": len(links),
        "letters_parsed": len(warning_letters),
        "letters": warning_letters,
    }

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "fda_warning_letters.html", html)
        import json
        write_text(Path(save_dir) / "fda_warning_letters.json", json.dumps(results, indent=2, default=str))

    # Load to staging if requested
    if load_to_staging and warning_letters:
        loader = StagingLoader('fda_warning_letters')
        
        def warning_letter_id_extractor(r):
            # Try letter_id first
            letter_id = r.get('letter_id')
            if letter_id and letter_id != 'about-warning-and-close-out-letters':
                return str(letter_id)
            
            # Use full URL if available
            letter_url = r.get('letter_url', '')
            if letter_url and len(letter_url) > 50:
                # Extract unique part from URL
                url_parts = letter_url.rstrip('/').split('/')
                if url_parts and len(url_parts[-1]) > 5:
                    return url_parts[-1]
                return letter_url
            
            # Fallback: hash company + date for uniqueness
            from src.utils.id_generation import generate_hash_id
            company = r.get('company_name', '')
            date = r.get('issue_date', '')
            if company or date:
                return generate_hash_id('FDA-WL', company, date, letter_url)
            return letter_url or ''
        
        stats = loader.load_records(
            warning_letters,
            id_extractor=warning_letter_id_extractor,
            skip_duplicates=True
        )
        print(f"Staging: {stats['inserted']} inserted, {stats['skipped']} skipped, {stats['errors']} errors")
        results['staging_stats'] = stats

    return results


def _parse_warning_letter(client: HttpClient, url: str) -> Optional[Dict[str, Any]]:
    """
    Parse individual warning letter page to extract structured data.
    
    Args:
        client: HTTP client
        url: URL of warning letter page
        
    Returns:
        Dict with parsed warning letter data or None if parsing fails
    """
    try:
        resp = client.get(url)
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Extract company name (usually in first paragraph or heading)
        company_name = None
        issue_date = None
        facility_name = None
        
        # Look for company name in various formats
        # FDA warning letters typically have format: "Company Name" or "Company Name, Inc."
        headings = soup.find_all(['h1', 'h2', 'h3'])
        for heading in headings:
            text = heading.get_text(strip=True)
            if text and len(text) < 200:  # Company names are usually short
                # Check if it looks like a company name
                if any(word in text.lower() for word in ['inc', 'llc', 'corp', 'ltd', 'pharmaceutical', 'biotech']):
                    company_name = text
                    break
        
        # If not found in headings, look in first paragraph
        if not company_name:
            paragraphs = soup.find_all('p')
            for p in paragraphs[:5]:  # Check first 5 paragraphs
                text = p.get_text(strip=True)
                # Look for date pattern (MM/DD/YYYY or Month DD, YYYY)
                date_match = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})|([A-Z][a-z]+ \d{1,2}, \d{4})', text)
                if date_match:
                    issue_date = date_match.group(0)
                    # Company name often appears before the date
                    parts = text.split(date_match.group(0))
                    if parts[0]:
                        potential_name = parts[0].strip().strip('"').strip("'")
                        if potential_name and len(potential_name) < 200:
                            company_name = potential_name
                    break
        
        # Extract full text
        letter_text = soup.get_text(separator=' ', strip=True)
        
        # Extract facility name (often mentioned after "facility" or "site")
        facility_match = re.search(r'facility[:\s]+([^,\n]{0,100})', letter_text, re.IGNORECASE)
        if facility_match:
            facility_name = facility_match.group(1).strip()
        
        # Extract violation types (common GMP violations)
        violation_keywords = [
            'GMP violations', 'data integrity', 'adulteration', 'misbranding',
            'quality control', 'validation', 'documentation', 'contamination'
        ]
        violation_types = []
        for keyword in violation_keywords:
            if keyword.lower() in letter_text.lower():
                violation_types.append(keyword)
        
        # Extract drug/product mentions (basic pattern - can be enhanced)
        # Look for capitalized words that might be drug names
        drug_pattern = r'\b([A-Z][a-z]+(?: [A-Z][a-z]+)*)\b'
        potential_drugs = re.findall(drug_pattern, letter_text[:2000])  # First 2000 chars
        # Filter out common words
        common_words = {'Company', 'Facility', 'FDA', 'United', 'States', 'Food', 'Drug', 'Administration'}
        drugs_mentioned = [d for d in potential_drugs[:10] if d not in common_words and len(d) > 3]
        
        # Generate letter ID from URL or date + company
        from src.utils.id_generation import generate_hash_id, generate_abstract_id
        
        letter_id = url.split('/')[-1] if '/' in url else None
        if not letter_id:
            # Use date + company name hash
            if issue_date and company_name:
                letter_id = generate_hash_id('WL', issue_date.replace('/', '-'), company_name)
            else:
                letter_id = generate_abstract_id('WL', url)
        
        if not company_name:
            # If we can't extract company name, skip this letter
            return None
        
        return {
            'letter_id': letter_id,
            'company_name': company_name,
            'issue_date': issue_date,
            'facility_name': facility_name,
            'violation_types': violation_types,
            'drugs_mentioned': drugs_mentioned[:5],  # Limit to 5
            'letter_url': url,
            'letter_text': letter_text[:50000] if len(letter_text) > 50000 else letter_text,  # Truncate if too long
        }
        
    except Exception as e:
        print(f"Error parsing warning letter {url}: {e}")
        return None


if __name__ == "__main__":
    out = Path("data/raw/fda_warning_letters")
    result = fetch_recent_warnings(limit=20, save_dir=out, load_to_staging=True)
    print(f"Fetched {result.get('letters_parsed', 0)} FDA Warning Letters")

