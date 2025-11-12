"""
Script to populate initial source records in the sources table.

Run this after applying the migration to create initial source metadata.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models.sources import Source


def populate_initial_sources():
    """Populate initial source records."""
    
    initial_sources = [
        {
            'source_name': 'clinicaltrials_gov',
            'source_type': 'clinical',
            'reliability_score': 0.95,
            'update_frequency': 'daily',
            'base_url': 'https://clinicaltrials.gov',
            'documentation_url': 'https://clinicaltrials.gov/api',
            'source_metadata': {
                'api_version': 'v2',
                'rate_limit': '1000/hour',
            }
        },
        {
            'source_name': 'fda_drugs',
            'source_type': 'regulatory',
            'reliability_score': 0.98,
            'update_frequency': 'weekly',
            'base_url': 'https://www.fda.gov/drugs',
            'documentation_url': 'https://www.fda.gov/drugs/drug-approvals-and-databases',
            'source_metadata': {
                'data_type': 'approvals',
            }
        },
        {
            'source_name': 'sec_edgar',
            'source_type': 'financial',
            'reliability_score': 0.90,
            'update_frequency': 'daily',
            'base_url': 'https://www.sec.gov/edgar',
            'documentation_url': 'https://www.sec.gov/edgar/searchedgar/companysearch.html',
            'source_metadata': {
                'filing_types': ['8-K', '10-K', '10-Q'],
            }
        },
        {
            'source_name': 'pubmed',
            'source_type': 'literature',
            'reliability_score': 0.95,
            'update_frequency': 'daily',
            'base_url': 'https://pubmed.ncbi.nlm.nih.gov',
            'documentation_url': 'https://www.ncbi.nlm.nih.gov/books/NBK25497/',
            'source_metadata': {
                'api': 'eutils',
            }
        },
        {
            'source_name': 'patentsview',
            'source_type': 'patent',
            'reliability_score': 0.85,
            'update_frequency': 'weekly',
            'base_url': 'https://patentsview.org',
            'documentation_url': 'https://patentsview.org/apis/api-endpoints',
            'source_metadata': {
                'api_version': 'v1',
            }
        },
        {
            'source_name': 'openfda',
            'source_type': 'regulatory',
            'reliability_score': 0.92,
            'update_frequency': 'daily',
            'base_url': 'https://open.fda.gov',
            'documentation_url': 'https://open.fda.gov/apis/',
            'source_metadata': {
                'api_version': 'v1',
            }
        },
    ]
    
    with get_db_session() as session:
        for source_data in initial_sources:
            # Check if source already exists
            existing = session.query(Source).filter(
                Source.source_name == source_data['source_name'],
                Source.deleted_at.is_(None)
            ).first()
            
            if existing:
                print(f"✓ Source '{source_data['source_name']}' already exists, skipping")
                continue
            
            # Create new source
            source = Source(**source_data)
            session.add(source)
            print(f"✓ Created source: {source_data['source_name']}")
        
        session.commit()
        print(f"\n✓ Successfully populated {len(initial_sources)} sources")


if __name__ == '__main__':
    try:
        populate_initial_sources()
    except Exception as e:
        print(f"✗ Error populating sources: {e}")
        sys.exit(1)

