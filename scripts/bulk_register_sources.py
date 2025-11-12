"""
Bulk source registration script.

Registers all unregistered ingestion scripts as sources in the database.
Sources are registered with is_active=False initially for verification.
"""
import sys
from pathlib import Path
from typing import Dict, Optional, Set

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models.sources import Source


def get_ingestion_scripts() -> Set[str]:
    """Get all ingestion script names from the ingestion directory."""
    ingestion_dir = project_root / 'ingestion'
    scripts = set()
    
    for file in ingestion_dir.glob('*.py'):
        if file.name not in ['__init__.py', 'test_helper.py']:
            script_name = file.stem
            scripts.add(script_name)
    
    return scripts


def get_source_type_from_script(script_name: str) -> Optional[str]:
    """Infer source type from script name or common patterns."""
    script_lower = script_name.lower()
    
    # Regulatory sources
    if any(x in script_lower for x in ['fda_', 'ema_', 'mhra_', 'health_canada', 'tga_', 
                                       'swissmedic', 'cdsco_', 'hsa_', 'mfds_', 'who_', 
                                       'ich_', 'nice_', 'anvisa_']):
        return 'regulatory'
    
    # Employment/WARN sources (map to 'other' since not in allowed types)
    if any(x in script_lower for x in ['warn', 'layoff']):
        return 'other'  # Employment not in allowed types, use 'other'
    
    # Patent sources
    if any(x in script_lower for x in ['patent', 'uspto']):
        return 'patent'
    
    # Literature sources
    if any(x in script_lower for x in ['pubmed', 'pmc', 'arxiv', 'biorxiv', 'medrxiv', 
                                       'chemrxiv', 'pubtator', 'semantic_scholar', 
                                       'europe_pmc']):
        return 'literature'
    
    # Financial sources
    if any(x in script_lower for x in ['sec_', 'alphavantage', 'calcbench', 'openfigi']):
        return 'financial'
    
    # Social sources
    if any(x in script_lower for x in ['reddit', 'youtube', 'google_news', 'rss_news']):
        return 'social'
    
    # Funding sources (map to 'other' since not in allowed types)
    if any(x in script_lower for x in ['nih_', 'nsf_', 'darpa', 'dod_', 'barda', 'sbir']):
        return 'other'  # Funding not in allowed types, use 'other'
    
    # Scientific databases (map to 'other' since not in allowed types)
    if any(x in script_lower for x in ['chembl', 'pubchem', 'uniprot', 'biogrid', 
                                        'string_db', 'opentargets', 'disgenet', 'clinvar', 
                                        'clingen', 'omim', 'orphanet', 'reactome']):
        return 'other'  # Scientific not in allowed types, use 'other'
    
    # Conference sources (map to 'other' since not in allowed types)
    if 'asco' in script_lower or 'conference' in script_lower:
        return 'other'  # Conference not in allowed types, use 'other'
    
    # Clinical sources
    if 'clinicaltrials' in script_lower or 'who_ictrp' in script_lower:
        return 'clinical'
    
    # Employment sources (map to 'other' if not already caught)
    if any(x in script_lower for x in ['employment', 'job']):
        return 'other'
    
    # Scientific/other databases that don't fit other categories
    if any(x in script_lower for x in ['scientific', 'database']):
        return 'other'
    
    # Default
    return 'other'


def infer_base_url(source_name: str) -> Optional[str]:
    """Infer base URL from source name patterns."""
    name_lower = source_name.lower()
    
    # FDA sources
    if name_lower.startswith('fda_'):
        return 'https://www.fda.gov'
    
    # EMA sources
    if name_lower.startswith('ema_'):
        return 'https://www.ema.europa.eu'
    
    # Patent sources
    if 'patentsview' in name_lower:
        return 'https://patentsview.org'
    if 'uspto' in name_lower:
        return 'https://www.uspto.gov'
    
    # WARN sources
    if 'warn' in name_lower:
        if 'california' in name_lower:
            return 'https://www.edd.ca.gov'
        elif 'federal' in name_lower:
            return 'https://www.dol.gov'
        elif 'illinois' in name_lower:
            return 'https://www.illinois.gov'
        elif 'massachusetts' in name_lower:
            return 'https://www.mass.gov'
        elif 'new_jersey' in name_lower or 'new_jersey' in name_lower:
            return 'https://www.nj.gov'
        elif 'new_york' in name_lower:
            return 'https://www.ny.gov'
        elif 'pennsylvania' in name_lower:
            return 'https://www.pa.gov'
        elif 'texas' in name_lower:
            return 'https://www.texas.gov'
        else:
            return 'https://www.dol.gov'  # Default to federal
    
    # Regulatory agencies
    if 'mhra' in name_lower:
        return 'https://www.gov.uk/government/organisations/medicines-and-healthcare-products-regulatory-agency'
    if 'health_canada' in name_lower:
        return 'https://www.canada.ca/en/health-canada.html'
    if 'tga' in name_lower:
        return 'https://www.tga.gov.au'
    if 'swissmedic' in name_lower:
        return 'https://www.swissmedic.ch'
    if 'cdsco' in name_lower:
        return 'https://cdsco.gov.in'
    if 'hsa' in name_lower and 'singapore' in name_lower:
        return 'https://www.hsa.gov.sg'
    if 'mfds' in name_lower:
        return 'https://www.mfds.go.kr'
    if 'who' in name_lower:
        return 'https://www.who.int'
    if 'ich' in name_lower:
        return 'https://www.ich.org'
    if 'nice' in name_lower:
        return 'https://www.nice.org.uk'
    if 'anvisa' in name_lower:
        return 'https://www.gov.br/anvisa'
    
    # Literature sources
    if 'pubmed' in name_lower:
        return 'https://pubmed.ncbi.nlm.nih.gov'
    if 'pmc' in name_lower:
        return 'https://www.ncbi.nlm.nih.gov/pmc'
    if 'arxiv' in name_lower:
        return 'https://arxiv.org'
    if 'biorxiv' in name_lower:
        return 'https://www.biorxiv.org'
    if 'medrxiv' in name_lower:
        return 'https://www.medrxiv.org'
    if 'chemrxiv' in name_lower:
        return 'https://chemrxiv.org'
    if 'semantic_scholar' in name_lower:
        return 'https://www.semanticscholar.org'
    if 'europe_pmc' in name_lower:
        return 'https://europepmc.org'
    
    # Financial sources
    if 'sec' in name_lower:
        return 'https://www.sec.gov'
    if 'alphavantage' in name_lower:
        return 'https://www.alphavantage.co'
    if 'calcbench' in name_lower:
        return 'https://www.calcbench.com'
    if 'openfigi' in name_lower:
        return 'https://www.openfigi.com'
    
    # Funding sources
    if 'nih' in name_lower:
        return 'https://www.nih.gov'
    if 'nsf' in name_lower:
        return 'https://www.nsf.gov'
    if 'darpa' in name_lower:
        return 'https://www.darpa.mil'
    if 'dod' in name_lower:
        return 'https://www.defense.gov'
    if 'barda' in name_lower:
        return 'https://www.medicalcountermeasures.gov'
    if 'sbir' in name_lower:
        return 'https://www.sbir.gov'
    
    # Scientific databases
    if 'chembl' in name_lower:
        return 'https://www.ebi.ac.uk/chembl'
    if 'pubchem' in name_lower:
        return 'https://pubchem.ncbi.nlm.nih.gov'
    if 'uniprot' in name_lower:
        return 'https://www.uniprot.org'
    if 'biogrid' in name_lower:
        return 'https://thebiogrid.org'
    if 'string_db' in name_lower:
        return 'https://string-db.org'
    if 'opentargets' in name_lower:
        return 'https://www.opentargets.org'
    if 'disgenet' in name_lower:
        return 'https://www.disgenet.org'
    if 'clinvar' in name_lower:
        return 'https://www.ncbi.nlm.nih.gov/clinvar'
    if 'clingen' in name_lower:
        return 'https://www.clinicalgenome.org'
    if 'omim' in name_lower:
        return 'https://www.omim.org'
    if 'orphanet' in name_lower:
        return 'https://www.orpha.net'
    if 'reactome' in name_lower:
        return 'https://reactome.org'
    
    # Conference sources
    if 'asco' in name_lower:
        return 'https://www.asco.org'
    
    # Clinical sources
    if 'clinicaltrials' in name_lower:
        return 'https://clinicaltrials.gov'
    if 'who_ictrp' in name_lower:
        return 'https://www.who.int/clinical-trials-registry-platform'
    
    # Social sources
    if 'reddit' in name_lower:
        return 'https://www.reddit.com'
    if 'youtube' in name_lower:
        return 'https://www.youtube.com'
    if 'google_news' in name_lower:
        return 'https://news.google.com'
    if 'rss_news' in name_lower:
        return None  # Generic RSS
    
    # Other known sources
    if 'openfda' in name_lower:
        return 'https://open.fda.gov'
    if 'seeking_alpha' in name_lower:
        return 'https://seekingalpha.com'
    if 'motley_fool' in name_lower:
        return 'https://www.fool.com'
    if 'xtalks' in name_lower:
        return 'https://xtalks.com'
    if 'biospace' in name_lower:
        return 'https://www.biospace.com'
    if 'fierce' in name_lower:
        return 'https://www.fiercebiotech.com'
    if 'vaers' in name_lower:
        return 'https://vaers.hhs.gov'
    if 'wayback' in name_lower:
        return 'https://web.archive.org'
    
    return None


def get_update_frequency(source_name: str, source_type: str) -> str:
    """Infer appropriate update frequency based on source characteristics."""
    name_lower = source_name.lower()
    
    # Real-time or daily sources
    if any(x in name_lower for x in ['sec_', 'pubmed', 'clinicaltrials', 'openfda', 'google_news', 'rss_news']):
        return 'daily'
    
    # Weekly sources (most regulatory)
    if source_type == 'regulatory':
        return 'weekly'
    
    # Monthly for slower-changing sources
    if source_type in ['funding', 'scientific']:
        return 'monthly'
    
    # Default to weekly
    return 'weekly'


def bulk_register_sources(dry_run: bool = False) -> Dict[str, int]:
    """
    Register all unregistered ingestion scripts as sources.
    
    Args:
        dry_run: If True, only report what would be registered without making changes
    
    Returns:
        Dictionary with registration statistics
    """
    stats = {
        'total_scripts': 0,
        'already_registered': 0,
        'new_registrations': 0,
        'errors': 0
    }
    
    # Get all ingestion scripts
    ingestion_scripts = get_ingestion_scripts()
    stats['total_scripts'] = len(ingestion_scripts)
    
    print(f"Found {stats['total_scripts']} ingestion scripts")
    
    with get_db_session() as session:
        # Get already registered sources
        registered_sources = session.query(Source).filter(
            Source.deleted_at.is_(None)
        ).all()
        registered_names = {s.source_name for s in registered_sources}
        
        print(f"Found {len(registered_names)} already registered sources")
        
        # Find unregistered sources
        unregistered = ingestion_scripts - registered_names
        print(f"Found {len(unregistered)} unregistered sources")
        
        if dry_run:
            print("\n=== DRY RUN MODE - No changes will be made ===\n")
        
        # Register each unregistered source
        for source_name in sorted(unregistered):
            try:
                # Check if already exists (shouldn't happen, but double-check)
                existing = session.query(Source).filter(
                    Source.source_name == source_name,
                    Source.deleted_at.is_(None)
                ).first()
                
                if existing:
                    print(f"⚠ {source_name}: Already exists (skipping)")
                    stats['already_registered'] += 1
                    continue
                
                # Infer source type
                source_type = get_source_type_from_script(source_name)
                if not source_type:
                    source_type = 'other'
                
                # Infer base URL
                base_url = infer_base_url(source_name)
                
                # Infer update frequency
                update_frequency = get_update_frequency(source_name, source_type)
                
                # Create source metadata
                source_metadata = {
                    'ingestion_script': source_name,
                    'auto_registered': True,
                }
                if base_url:
                    source_metadata['base_url'] = base_url
                
                # Create source record
                source = Source(
                    source_name=source_name,
                    source_type=source_type,
                    is_active=False,  # Start inactive for verification
                    update_frequency=update_frequency,
                    base_url=base_url,
                    source_metadata=source_metadata
                )
                
                if not dry_run:
                    try:
                        session.add(source)
                        session.flush()  # Flush to get ID, but don't commit yet
                    except Exception as e:
                        session.rollback()
                        print(f"✗ {source_name}: Error during flush - {e}")
                        stats['errors'] += 1
                        continue
                
                print(f"{'[DRY RUN] ' if dry_run else ''}✓ {source_name}: {source_type} ({update_frequency})")
                if base_url:
                    print(f"    URL: {base_url}")
                
                stats['new_registrations'] += 1
                
            except Exception as e:
                print(f"✗ {source_name}: Error - {e}")
                stats['errors'] += 1
        
        if not dry_run:
            session.commit()
            print(f"\n✓ Successfully registered {stats['new_registrations']} new sources")
        else:
            print(f"\n[DRY RUN] Would register {stats['new_registrations']} new sources")
    
    return stats


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Bulk register ingestion scripts as sources')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be registered without making changes')
    args = parser.parse_args()
    
    try:
        stats = bulk_register_sources(dry_run=args.dry_run)
        
        print("\n" + "="*60)
        print("Registration Summary")
        print("="*60)
        print(f"Total scripts: {stats['total_scripts']}")
        print(f"Already registered: {stats['already_registered']}")
        print(f"New registrations: {stats['new_registrations']}")
        print(f"Errors: {stats['errors']}")
        
        if args.dry_run:
            print("\nRun without --dry-run to actually register sources")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

