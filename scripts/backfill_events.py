"""
Backfill script to create Events from existing TrialStatusHistory and RegulatoryEvents.

This script converts historical data to the unified event stream so the dashboard
can display timelines for existing companies.
"""
import logging
import sys
from pathlib import Path
from datetime import date
from typing import List
from uuid import UUID

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models.clinical import ClinicalTrial, TrialStatusHistory
from database.models.clinical import RegulatoryEvent
from database.models.relationships import TrialSponsor
from database.models.relationships import RegulatoryDrugEvent, RegulatoryCompanyEvent
from database.models.sources import Source
from src.services.event_service import EventService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def backfill_trial_events():
    """Backfill events from TrialStatusHistory."""
    logger.info("Starting trial events backfill...")
    
    with get_db_session() as session:
        event_service = EventService(session)
        
        # Get source for clinicaltrials_gov
        source = session.query(Source).filter(
            Source.source_name == 'clinicaltrials_gov'
        ).first()
        source_id = source.source_id if source else None
        
        # Get all trial status history entries
        status_histories = session.query(TrialStatusHistory).filter(
            TrialStatusHistory.deleted_at.is_(None)
        ).order_by(TrialStatusHistory.status_date).all()
        
        logger.info(f"Found {len(status_histories)} status history entries")
        
        events_created = 0
        events_skipped = 0
        
        for history in status_histories:
            try:
                # Check if event already exists
                from database.models.events import Event
                from sqlalchemy import func
                existing = session.query(Event).filter(
                    Event.event_type.like('trial.status.%'),
                    Event.event_date == history.status_date,
                    func.array_position(Event.entities_involved, history.trial_id) != None
                ).first()
                
                if existing:
                    events_skipped += 1
                    continue
                
                # Get trial
                trial = session.query(ClinicalTrial).filter(
                    ClinicalTrial.trial_id == history.trial_id
                ).first()
                
                if not trial:
                    logger.warning(f"Trial {history.trial_id} not found for history {history.history_id}")
                    continue
                
                # Get entities involved (trial + sponsors)
                entities_involved = [history.trial_id]
                sponsors = session.query(TrialSponsor).filter(
                    TrialSponsor.trial_id == history.trial_id,
                    TrialSponsor.entity_type == 'company',
                    TrialSponsor.deleted_at.is_(None)
                ).all()
                for sponsor in sponsors:
                    if sponsor.entity_id not in entities_involved:
                        entities_involved.append(sponsor.entity_id)
                
                # Create event
                event_service.convert_trial_status_to_event(
                    trial_id=history.trial_id,
                    status=history.status,
                    status_date=history.status_date,
                    entities_involved=entities_involved,
                    source_id=source_id
                )
                events_created += 1
                
                if events_created % 100 == 0:
                    session.commit()
                    logger.info(f"Created {events_created} events so far...")
                    
            except Exception as e:
                logger.error(f"Error processing status history {history.history_id}: {e}")
                session.rollback()
                continue
        
        session.commit()
        logger.info(f"Trial events backfill complete: {events_created} created, {events_skipped} skipped")


def backfill_regulatory_events():
    """Backfill events from RegulatoryEvents."""
    logger.info("Starting regulatory events backfill...")
    
    with get_db_session() as session:
        event_service = EventService(session)
        
        # Get source for fda_drugs
        source = session.query(Source).filter(
            Source.source_name == 'fda_drugs'
        ).first()
        source_id = source.source_id if source else None
        
        # Get all regulatory events
        reg_events = session.query(RegulatoryEvent).filter(
            RegulatoryEvent.deleted_at.is_(None)
        ).all()
        
        logger.info(f"Found {len(reg_events)} regulatory events")
        
        events_created = 0
        events_skipped = 0
        
        for reg_event in reg_events:
            try:
                # Check if event already exists
                from database.models.events import Event
                from sqlalchemy import func
                existing = session.query(Event).filter(
                    Event.event_type.like('regulatory.%'),
                    Event.event_date == reg_event.event_date,
                    func.array_position(Event.entities_involved, reg_event.event_id) != None
                ).first()
                
                if existing:
                    events_skipped += 1
                    continue
                
                # Get entities involved (drug + company)
                entities_involved = [reg_event.event_id]
                
                # Get drug
                drug_rel = session.query(RegulatoryDrugEvent).filter(
                    RegulatoryDrugEvent.event_id == reg_event.event_id
                ).first()
                if drug_rel:
                    entities_involved.append(drug_rel.drug_id)
                
                # Get company
                company_rel = session.query(RegulatoryCompanyEvent).filter(
                    RegulatoryCompanyEvent.event_id == reg_event.event_id
                ).first()
                if company_rel:
                    entities_involved.append(company_rel.company_id)
                
                # Convert to unified event
                event_service.convert_regulatory_event_to_event(
                    regulatory_event_id=reg_event.event_id,
                    entities_involved=entities_involved,
                    source_id=source_id
                )
                events_created += 1
                
                if events_created % 50 == 0:
                    session.commit()
                    logger.info(f"Created {events_created} events so far...")
                    
            except Exception as e:
                logger.error(f"Error processing regulatory event {reg_event.event_id}: {e}")
                session.rollback()
                continue
        
        session.commit()
        logger.info(f"Regulatory events backfill complete: {events_created} created, {events_skipped} skipped")


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Event Backfill Script")
    logger.info("=" * 60)
    
    try:
        backfill_trial_events()
        backfill_regulatory_events()
        
        # Final count
        with get_db_session() as session:
            from database.models.events import Event
            total_events = session.query(Event).filter(
                Event.deleted_at.is_(None)
            ).count()
            logger.info(f"Total events in database: {total_events}")
        
        logger.info("=" * 60)
        logger.info("Backfill complete!")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Backfill failed: {e}", exc_info=True)
        raise

