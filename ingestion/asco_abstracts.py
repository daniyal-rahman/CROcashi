"""
ASCO (American Society of Clinical Oncology) conference abstracts ingestion.

ASCO abstracts provide:
- Trial results and updates
- Drug efficacy and safety data
- Early termination announcements
- No-show detection (abstracts accepted but not presented)
"""
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import re

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader, asco_abstract_id_extractor


# ASCO meeting abstracts are typically available at:
# https://meetings.asco.org/abstracts-presentations/search
BASE_URL = "https://meetings.asco.org/abstracts-presentations/search"


def fetch_asco_abstracts(
    year: int = 2024,
    limit: int = 50,
    save_dir: Optional[Path] = None,
    load_to_staging: bool = True
) -> Dict[str, Any]:
    """
    Fetch ASCO conference abstracts.
    
    Args:
        year: ASCO meeting year (default: 2024)
        limit: Maximum number of abstracts to fetch
        save_dir: Optional directory to save raw HTML/JSON
        load_to_staging: Whether to load data into staging table (default: True)
        
    Returns:
        Dict with abstract records
    """
    client = HttpClient(requests_per_second=1.0)
    
    # ASCO abstracts are typically accessed via search interface
    # For now, we'll implement a basic HTML scraping approach
    # In production, this could use ASCO's API if available
    
    abstracts = []
    
    try:
        # Try to access ASCO abstract search page
        # Note: ASCO may require authentication or have rate limits
        search_url = f"{BASE_URL}?year={year}"
        resp = client.get(search_url)
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Extract abstract links from search results
        abstract_links = []
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            text = a.get_text(strip=True)
            # Look for abstract links
            if "abstract" in href.lower() or "abstract" in text.lower():
                full_url = href if href.startswith("http") else f"https://meetings.asco.org{href}"
                abstract_links.append({"href": full_url, "text": text[:200]})
        
        # Parse individual abstracts
        for link in abstract_links[:limit]:
            try:
                abstract_data = _parse_asco_abstract(client, link["href"], year)
                if abstract_data:
                    abstracts.append(abstract_data)
            except Exception as e:
                print(f"Error parsing ASCO abstract {link['href']}: {e}")
                continue
        
    except Exception as e:
        print(f"Error fetching ASCO abstracts: {e}")
        # Return empty result rather than failing completely
        abstracts = []
    
    results = {
        "year": year,
        "abstracts_parsed": len(abstracts),
        "abstracts": abstracts,
    }
    
    if save_dir is not None:
        ensure_dir(save_dir)
        import json
        write_text(Path(save_dir) / f"asco_{year}_abstracts.json", json.dumps(results, indent=2, default=str))
    
    # Load to staging if requested
    if load_to_staging and abstracts:
        loader = StagingLoader('asco_abstracts')
        stats = loader.load_records(
            abstracts,
            id_extractor=asco_abstract_id_extractor,
            skip_duplicates=True
        )
        print(f"Staging: {stats['inserted']} inserted, {stats['skipped']} skipped, {stats['errors']} errors")
        results['staging_stats'] = stats
    
    return results


def _parse_asco_abstract(client: HttpClient, url: str, year: int) -> Optional[Dict[str, Any]]:
    """
    Parse individual ASCO abstract page to extract structured data.
    
    Args:
        client: HTTP client
        url: URL of abstract page
        year: ASCO meeting year
        
    Returns:
        Dict with parsed abstract data or None if parsing fails
    """
    try:
        resp = client.get(url)
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Extract text content
        text = soup.get_text(separator=' ', strip=True)
        
        # Extract abstract ID (usually in URL or page)
        abstract_id = None
        # Try to extract from URL
        url_parts = url.rstrip('/').split('/')
        for part in reversed(url_parts):
            if part and ('abstract' in part.lower() or part.isdigit()):
                abstract_id = part
                break
        
        # If not in URL, look in page
        if not abstract_id:
            id_match = re.search(r'Abstract[:\s#]+(\d+)', text, re.IGNORECASE)
            if id_match:
                abstract_id = id_match.group(1)
        
        from src.utils.id_generation import generate_abstract_id
        
        if not abstract_id:
            abstract_id = generate_abstract_id('ASCO', str(year), url)
        
        # Extract title
        title = None
        headings = soup.find_all(['h1', 'h2', 'h3'])
        for heading in headings:
            text_h = heading.get_text(strip=True)
            if text_h and len(text_h) > 10 and len(text_h) < 500:
                title = text_h
                break
        
        # Extract authors
        authors = []
        author_patterns = [
            r'Authors?[:\s]+([^;\n]{0,500})',
            r'([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
        ]
        
        for pattern in author_patterns:
            matches = re.findall(pattern, text[:2000])
            if matches:
                # Parse author list
                for match in matches:
                    if isinstance(match, str):
                        # Split by common delimiters
                        author_list = re.split(r'[,;]', match)
                        for author in author_list:
                            author = author.strip()
                            if author and len(author) > 3:
                                authors.append(author)
                if authors:
                    break
        
        # Extract presentation type
        presentation_type = None
        type_keywords = {
            'oral': ['oral', 'plenary'],
            'poster': ['poster', 'poster discussion'],
            'late_breaking': ['late breaking', 'late-breaking', 'lb']
        }
        
        text_lower = text.lower()
        for ptype, keywords in type_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                presentation_type = ptype
                break
        
        # Extract presentation date (if available)
        presentation_date = None
        date_patterns = [
            r'Presentation Date[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text[:2000])
            if match:
                try:
                    date_str = match.group(1)
                    # Try to parse
                    for fmt in ['%m/%d/%Y', '%m-%d-%Y', '%Y-%m-%d']:
                        try:
                            presentation_date = datetime.strptime(date_str, fmt).date()
                            break
                        except ValueError:
                            continue
                    if presentation_date:
                        break
                except (IndexError, ValueError):
                    continue
        
        # Extract abstract text (usually in a specific section)
        abstract_text = None
        abstract_sections = soup.find_all(['div', 'section'], class_=re.compile(r'abstract', re.I))
        if abstract_sections:
            abstract_text = abstract_sections[0].get_text(separator=' ', strip=True)
        else:
            # Fallback: use first long paragraph
            paragraphs = soup.find_all('p')
            for p in paragraphs:
                text_p = p.get_text(strip=True)
                if len(text_p) > 200:  # Abstract is usually long
                    abstract_text = text_p
                    break
        
        # Extract NCT IDs from abstract
        nct_ids = []
        nct_pattern = r'NCT\d{8}'
        if abstract_text:
            nct_matches = re.findall(nct_pattern, abstract_text, re.IGNORECASE)
            nct_ids = list(set(nct_matches))  # Remove duplicates
        
        # Extract drug mentions (basic - can be enhanced with NER)
        drugs_mentioned = []
        # Look for capitalized words that might be drug names
        if abstract_text:
            drug_pattern = r'\b([A-Z][a-z]+(?: [A-Z][a-z]+)*)\b'
            potential_drugs = re.findall(drug_pattern, abstract_text[:3000])
            # Filter out common words
            common_words = {'Abstract', 'Background', 'Methods', 'Results', 'Conclusion', 'ASCO', 'Clinical', 'Trial'}
            drugs_mentioned = [d for d in potential_drugs[:10] if d not in common_words and len(d) > 3]
        
        # Extract company affiliations (from author affiliations)
        companies = []
        affiliation_pattern = r'([A-Z][a-zA-Z\s&,\.]+(?:Inc\.?|LLC|Corp\.?|Pharmaceuticals?|Biotech))'
        affiliation_matches = re.findall(affiliation_pattern, text[:3000])
        companies = list(set(affiliation_matches[:5]))  # Limit to 5
        
        # Determine status (accepted, presented, withdrawn)
        status = 'accepted'  # Default
        if 'withdrawn' in text_lower or 'withdrawal' in text_lower:
            status = 'withdrawn'
        elif 'presented' in text_lower or presentation_date:
            status = 'presented'
        
        # Extract session information
        session = None
        session_match = re.search(r'Session[:\s]+([^,\n]{0,100})', text, re.IGNORECASE)
        if session_match:
            session = session_match.group(1).strip()
        
        if not title:
            # If we can't extract title, skip this abstract
            return None
        
        return {
            'abstract_id': f"ASCO-{year}-{abstract_id}",
            'title': title,
            'authors': authors[:20],  # Limit to 20 authors
            'presentation_type': presentation_type,
            'presentation_date': presentation_date.isoformat() if presentation_date else None,
            'abstract_text': abstract_text[:50000] if abstract_text and len(abstract_text) > 50000 else abstract_text,
            'nct_ids': nct_ids,
            'drugs_mentioned': drugs_mentioned[:10],  # Limit to 10
            'companies': companies,
            'conference': f'ASCO {year}',
            'session': session,
            'status': status,
            'abstract_url': url,
        }
        
    except Exception as e:
        print(f"Error parsing ASCO abstract {url}: {e}")
        return None


if __name__ == "__main__":
    out = Path("data/raw/asco_abstracts")
    result = fetch_asco_abstracts(year=2024, limit=20, save_dir=out, load_to_staging=True)
    print(f"Fetched {result.get('abstracts_parsed', 0)} ASCO abstracts")

