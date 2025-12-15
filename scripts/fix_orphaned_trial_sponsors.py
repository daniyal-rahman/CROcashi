#!/usr/bin/env python3
"""
Fix script to backfill missing trial sponsor relationships.

This script finds Phase 2/3 trials that have no sponsor link in trial_sponsors,
extracts sponsor data from staging, and creates the missing relationships.

The main issue is that some trials were processed but their sponsor relationships
weren't created - this breaks the backtesting chain:
Trial Failed → Company → Stock Price Movement
"""
import logging
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import and_, text
from sqlalchemy.orm import Session

from database.config import get_db_session
from database.models import (
    ClinicalTrial, StagingRawData, Company, Institution, TrialSponsor, EntityAlias
)
from src.entity_resolution.entity_resolver import EntityResolver
from src.entity_resolution.types import EntityType, ExtractedEntity, ResolutionStatus
from src.processors.clinicaltrials_processor import ClinicalTrialsProcessor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_orphaned_trials(session: Session, phase_filter: bool = True) -> list:
    """Find trials with no sponsor in trial_sponsors."""
    phase_clause = ""
    if phase_filter:
        phase_clause = "AND ct.phase IN ('PHASE2', 'PHASE3', 'PHASE2/PHASE3', 'Phase 2', 'Phase 3', 'Phase 2/Phase 3')"

    query = text(f"""
        SELECT ct.trial_id, ct.nct_id, ct.phase
        FROM clinical_trials ct
        LEFT JOIN trial_sponsors ts ON ct.trial_id = ts.trial_id
        WHERE ts.trial_id IS NULL
        {phase_clause}
    """)

    result = session.execute(query)
    return [dict(row._mapping) for row in result]


def get_staging_record(session: Session, nct_id: str) -> Optional[StagingRawData]:
    """Get staging record for a trial."""
    return session.query(StagingRawData).filter(
        and_(
            StagingRawData.source_system == 'clinicaltrials_gov',
            StagingRawData.source_record_id == nct_id
        )
    ).first()


def extract_sponsor_from_raw(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract sponsor info from raw ClinicalTrials.gov data."""
    protocol = raw_data.get('protocolSection', {})
    sponsor_module = protocol.get('sponsorCollaboratorsModule', {})
    lead_sponsor = sponsor_module.get('leadSponsor', {})

    return {
        'name': lead_sponsor.get('name', ''),
        'class': lead_sponsor.get('class', '').lower()
    }


def resolve_sponsor_entity(
    session: Session,
    resolver: EntityResolver,
    sponsor_name: str,
    sponsor_class: str,
    nct_id: str
) -> Optional[tuple]:
    """
    Resolve sponsor to a company or institution entity.

    Returns: (entity_id, entity_type) or None
    """
    if not sponsor_name:
        return None

    # Determine entity type
    is_industry = sponsor_class in ['industry', 'company']
    entity_type = EntityType.COMPANY if is_industry else EntityType.INSTITUTION

    # Create extracted entity for resolution
    extracted = ExtractedEntity(
        entity_type=entity_type,
        name=sponsor_name,
        identifiers={},
        context={'sponsor_class': sponsor_class, 'role': 'lead_sponsor'},
        source_name='clinicaltrials_gov',
        source_identifier=nct_id
    )

    # Try to resolve
    resolution = resolver.resolve(extracted)

    if resolution.status in [ResolutionStatus.EXACT_MATCH, ResolutionStatus.HIGH_CONFIDENCE]:
        return (resolution.entity_id, entity_type)

    # For NEEDS_REVIEW and NO_MATCH - create new entity
    # We create new entities even for NEEDS_REVIEW because:
    # 1. We need sponsor links for backtesting
    # 2. Fuzzy matches can be merged later via entity resolution review
    if resolution.status in [ResolutionStatus.NO_MATCH, ResolutionStatus.NEEDS_REVIEW]:
        if is_industry:
            # Create new company
            new_company = Company(
                company_id=uuid4(),
                name=sponsor_name,
                data_sources={'clinicaltrials_gov': {'first_seen': datetime.now().isoformat()}}
            )
            session.add(new_company)
            session.flush()

            # Create alias
            alias = EntityAlias(
                alias_id=uuid4(),
                entity_type='company',
                entity_id=new_company.company_id,
                alias_text=sponsor_name,
                alias_type='original_name',
                source='clinicaltrials_gov',
                confidence_score=1.0
            )
            session.add(alias)

            logger.info(f"Created new company: {sponsor_name}")
            return (new_company.company_id, entity_type)
        else:
            # Create new institution
            # Map sponsor_class to valid institution_type
            institution_type_map = {
                'other': 'research_institute',
                'nih': 'government',
                'other_gov': 'government',
                'fed': 'government',
                'network': 'cooperative_group',
            }
            inst_type = institution_type_map.get(sponsor_class, 'research_institute')

            new_institution = Institution(
                institution_id=uuid4(),
                name=sponsor_name,
                institution_type=inst_type
            )
            session.add(new_institution)
            session.flush()

            # Create alias
            alias = EntityAlias(
                alias_id=uuid4(),
                entity_type='institution',
                entity_id=new_institution.institution_id,
                alias_text=sponsor_name,
                alias_type='original_name',
                source='clinicaltrials_gov',
                confidence_score=1.0
            )
            session.add(alias)

            logger.info(f"Created new institution: {sponsor_name}")
            return (new_institution.institution_id, entity_type)

    return None


def create_trial_sponsor_relationship(
    session: Session,
    trial_id,
    entity_id,
    entity_type: EntityType
) -> bool:
    """Create a trial_sponsor relationship."""
    try:
        trial_sponsor = TrialSponsor(
            trial_id=trial_id,
            entity_id=entity_id,
            entity_type='company' if entity_type == EntityType.COMPANY else 'institution',
            sponsor_role='lead_sponsor',
            is_regulatory_sponsor=True,
            is_financial_sponsor=True,
            data_sources={'clinicaltrials_gov': {'first_seen': datetime.now().isoformat()}}
        )
        session.add(trial_sponsor)
        return True
    except Exception as e:
        logger.error(f"Error creating trial_sponsor: {e}")
        return False


def fix_orphaned_sponsors(dry_run: bool = True, limit: Optional[int] = None):
    """Main function to fix orphaned trial sponsors."""
    logger.info(f"Starting fix_orphaned_sponsors (dry_run={dry_run}, limit={limit})")

    stats = {
        'orphaned_found': 0,
        'staging_found': 0,
        'sponsor_extracted': 0,
        'resolved_company': 0,
        'resolved_institution': 0,
        'relationships_created': 0,
        'errors': 0
    }

    with get_db_session() as session:
        # Get orphaned trials
        orphaned = get_orphaned_trials(session)
        stats['orphaned_found'] = len(orphaned)
        logger.info(f"Found {len(orphaned)} orphaned Phase 2/3 trials")

        if limit:
            orphaned = orphaned[:limit]

        # Initialize resolver
        resolver = EntityResolver(session)

        for trial in orphaned:
            nct_id = trial['nct_id']
            trial_id = trial['trial_id']

            # Get staging record
            staging = get_staging_record(session, nct_id)
            if not staging:
                logger.warning(f"No staging record for {nct_id}")
                continue

            stats['staging_found'] += 1

            # Extract sponsor
            sponsor_info = extract_sponsor_from_raw(staging.raw_data)
            if not sponsor_info['name']:
                logger.warning(f"No sponsor name in staging for {nct_id}")
                continue

            stats['sponsor_extracted'] += 1
            logger.info(f"Processing {nct_id}: sponsor={sponsor_info['name']} ({sponsor_info['class']})")

            # Resolve sponsor entity
            result = resolve_sponsor_entity(
                session, resolver,
                sponsor_info['name'],
                sponsor_info['class'],
                nct_id
            )

            if not result:
                logger.warning(f"Could not resolve sponsor for {nct_id}")
                stats['errors'] += 1
                continue

            entity_id, entity_type = result

            if entity_type == EntityType.COMPANY:
                stats['resolved_company'] += 1
            else:
                stats['resolved_institution'] += 1

            # Create relationship
            if not dry_run:
                if create_trial_sponsor_relationship(session, trial_id, entity_id, entity_type):
                    stats['relationships_created'] += 1
                else:
                    stats['errors'] += 1
            else:
                stats['relationships_created'] += 1  # Would be created
                logger.info(f"  [DRY RUN] Would create trial_sponsor: {nct_id} -> {sponsor_info['name']}")

        if not dry_run:
            session.commit()
            logger.info("Changes committed to database")

    # Print summary
    logger.info("\n" + "="*60)
    logger.info("SUMMARY")
    logger.info("="*60)
    for key, value in stats.items():
        logger.info(f"  {key}: {value}")

    return stats


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Fix orphaned trial sponsors')
    parser.add_argument('--dry-run', action='store_true', default=True,
                        help='Simulate without making changes (default: True)')
    parser.add_argument('--execute', action='store_true',
                        help='Actually make changes to the database')
    parser.add_argument('--limit', type=int, default=None,
                        help='Limit number of trials to process')

    args = parser.parse_args()

    dry_run = not args.execute

    fix_orphaned_sponsors(dry_run=dry_run, limit=args.limit)
