#!/usr/bin/env python3
"""
Map Company Risk Dashboard requirements to relationships and sources.
Connects infrastructure work to product goal.
"""
import sys
from pathlib import Path
import json

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from database.config import get_db_session
from database.models.entities import Company
from database.models.staging import StagingRawData
from database.models.relationships import (
    TrialSponsor, TrialDrug, FilingCompany, FilingDrug
)


def analyze_dashboard_requirements():
    """Analyze what the Company Risk Dashboard needs."""
    print("Analyzing Company Risk Dashboard requirements...")
    
    # Dashboard needs (based on failure analysis platform)
    requirements = {
        'company_risk_signals': {
            'description': 'Signals indicating company risk',
            'relationships_needed': [
                'trial_sponsors',  # Company sponsors trials
                'filing_companies',  # Company has SEC filings
                'filing_drugs',  # Filings mention drugs
            ],
            'sources_needed': [
                'clinicaltrials_gov',  # Trial data
                'sec_edgar',  # Financial filings
                'fda_warning_letters',  # Regulatory issues
                'fda_clinical_hold',  # Program failures
            ]
        },
        'program_failures': {
            'description': 'Failed or terminated programs',
            'relationships_needed': [
                'trial_drugs',  # Trials test drugs
                'trial_sponsors',  # Company sponsors trials
            ],
            'sources_needed': [
                'clinicaltrials_gov',  # Trial status
                'fda_clinical_hold',  # Clinical holds
            ]
        },
        'regulatory_issues': {
            'description': 'Regulatory problems',
            'relationships_needed': [
                'filing_companies',  # Company filings
            ],
            'sources_needed': [
                'fda_warning_letters',  # Warning letters
                'sec_edgar',  # 8-K filings
            ]
        },
        'financial_distress': {
            'description': 'Financial problems',
            'relationships_needed': [
                'filing_companies',  # Company filings
            ],
            'sources_needed': [
                'sec_edgar',  # Financial filings
                'california_warn',  # Layoff notices
                'federal_warn',  # Layoff notices
            ]
        }
    }
    
    return requirements


def check_current_coverage(session, requirements):
    """Check current data coverage for requirements."""
    print("\nChecking current data coverage...")
    
    coverage = {}
    
    for req_name, req_data in requirements.items():
        print(f"\n{req_name}:")
        
        req_coverage = {
            'relationships': {},
            'sources': {}
        }
        
        # Check relationships
        for rel_name in req_data['relationships_needed']:
            count = get_relationship_count(session, rel_name)
            req_coverage['relationships'][rel_name] = count
            status = '✓' if count > 0 else '✗'
            print(f"  {status} {rel_name}: {count}")
        
        # Check sources
        for source_name in req_data['sources_needed']:
            has_data = check_source_has_data(session, source_name)
            req_coverage['sources'][source_name] = has_data
            status = '✓' if has_data else '✗'
            print(f"  {status} {source_name}: {'Has data' if has_data else 'No data'}")
        
        coverage[req_name] = req_coverage
    
    return coverage


def get_relationship_count(session, relationship_name):
    """Get count for a relationship type."""
    relationship_map = {
        'trial_sponsors': TrialSponsor,
        'trial_drugs': 'trial_drugs',  # Will query directly
        'filing_companies': FilingCompany,
        'filing_drugs': FilingDrug,
    }
    
    if relationship_name in relationship_map:
        model = relationship_map[relationship_name]
        if isinstance(model, str):
            # Query directly
            count = session.execute(
                text(f"SELECT COUNT(*) FROM {model} WHERE deleted_at IS NULL")
            ).scalar()
        else:
            count = session.query(model).filter(
                model.deleted_at.is_(None)
            ).count()
        return count or 0
    
    return 0


def check_source_has_data(session, source_name):
    """Check if source has data."""
    # Check staging
    staging_count = session.query(StagingRawData).filter(
        StagingRawData.source_system == source_name,
        StagingRawData.deleted_at.is_(None)
    ).count()
    
    # Check processing logs
    log_count = session.execute(
        text("SELECT COUNT(*) FROM source_processing_log WHERE source_name = :source"),
        {'source': source_name}
    ).scalar()
    
    return staging_count > 0 or log_count > 0


def create_requirements_document(requirements, coverage):
    """Create requirements document."""
    output_file = project_root / 'data' / 'dashboard_requirements.json'
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    doc = {
        'requirements': requirements,
        'coverage': coverage,
        'gaps': identify_gaps(requirements, coverage),
        'priorities': prioritize_gaps(requirements, coverage)
    }
    
    with open(output_file, 'w') as f:
        json.dump(doc, f, indent=2, default=str)
    
    print(f"\n✓ Requirements document created: {output_file}")
    return doc


def identify_gaps(requirements, coverage):
    """Identify gaps in coverage."""
    gaps = {}
    
    for req_name, req_data in requirements.items():
        req_gaps = {
            'missing_relationships': [],
            'missing_sources': []
        }
        
        # Check missing relationships
        for rel_name in req_data['relationships_needed']:
            if coverage[req_name]['relationships'].get(rel_name, 0) == 0:
                req_gaps['missing_relationships'].append(rel_name)
        
        # Check missing sources
        for source_name in req_data['sources_needed']:
            if not coverage[req_name]['sources'].get(source_name, False):
                req_gaps['missing_sources'].append(source_name)
        
        if req_gaps['missing_relationships'] or req_gaps['missing_sources']:
            gaps[req_name] = req_gaps
    
    return gaps


def prioritize_gaps(requirements, coverage):
    """Prioritize gaps by importance."""
    priorities = []
    
    gaps = identify_gaps(requirements, coverage)
    
    for req_name, req_gaps in gaps.items():
        # Calculate priority score
        # Higher score = higher priority
        score = 0
        
        # Missing relationships are critical
        score += len(req_gaps['missing_relationships']) * 10
        
        # Missing sources are important
        score += len(req_gaps['missing_sources']) * 5
        
        # Company risk signals are highest priority
        if req_name == 'company_risk_signals':
            score += 20
        
        priorities.append({
            'requirement': req_name,
            'gaps': req_gaps,
            'priority_score': score
        })
    
    # Sort by priority
    priorities.sort(key=lambda x: x['priority_score'], reverse=True)
    
    return priorities


def main():
    print("=" * 80)
    print("COMPANY RISK DASHBOARD REQUIREMENTS MAPPING")
    print("=" * 80)
    
    with get_db_session() as session:
        # Analyze requirements
        requirements = analyze_dashboard_requirements()
        
        # Check current coverage
        coverage = check_current_coverage(session, requirements)
        
        # Identify gaps
        gaps = identify_gaps(requirements, coverage)
        
        # Prioritize gaps
        priorities = prioritize_gaps(requirements, coverage)
        
        # Create document
        doc = create_requirements_document(requirements, coverage)
        
        # Print summary
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        
        print(f"\nRequirements analyzed: {len(requirements)}")
        print(f"Gaps identified: {len(gaps)}")
        
        print(f"\nPriority gaps:")
        for priority in priorities[:5]:  # Top 5
            print(f"  {priority['requirement']}:")
            print(f"    Missing relationships: {priority['gaps']['missing_relationships']}")
            print(f"    Missing sources: {priority['gaps']['missing_sources']}")
            print(f"    Priority score: {priority['priority_score']}")


if __name__ == '__main__':
    main()

