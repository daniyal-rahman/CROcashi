"""
Backfill script to create Events for trials with failed status but no corresponding event.

This fixes the mismatch where we have 79 failed trials but only 31 failure events.
Creates events for trials that were imported with failed status but never had a status change event.
"""
import logging
import sys
from pathlib import Path
from datetime import date, datetime
from typing import List
from uuid import UUID

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models.clinical import ClinicalTrial
from database.models.events import Event
from database.models.relationships import TrialSponsor
from database.models.sources import Source
from src.services.event_service import EventService
from sqlalchemy import func

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def backfill_missing_failure_events():
    """
    Create events for trials with failed status but no corresponding failure event.
    
    This handles the case where trials were imported with status='terminated' 
    but never had a status change event created.
    """
    logger.info("Starting backfill of missing failure events...")
    
    with get_db_session() as session:
        event_service = EventService(session)
        
        # Get source for clinicaltrials_gov
        source = session.query(Source).filter(
            Source.source_name == 'clinicaltrials_gov'
        ).first()
        source_id = source.source_id if source else None
        
        # Find all trials with failed status
        failed_statuses = ['terminated', 'withdrawn', 'suspended']
        failed_trials = session.query(ClinicalTrial).filter(
            ClinicalTrial.status.in_(failed_statuses),
            ClinicalTrial.deleted_at.is_(None)
        ).all()
        
        logger.info(f"Found {len(failed_trials)} trials with failed status")
        
        events_created = 0
        events_skipped = 0
        events_failed = 0
        
        # Status to event type mapping
        status_to_event_type = {
            'terminated': 'trial.status.terminated',
            'withdrawn': 'trial.status.withdrawn',
            'suspended': 'trial.status.suspended'
        }
        
        for trial in failed_trials:
            try:
                # Check if failure event already exists for this trial
                # Look for events with matching event type and trial ID in entities_involved
                event_type = status_to_event_type.get(trial.status.lower())
                if not event_type:
                    logger.warning(f"Unknown failed status: {trial.status} for trial {trial.nct_id}")
                    events_failed += 1
                    continue
                
                # Check if event already exists
                existing = session.query(Event).filter(
                    Event.event_type == event_type,
                    func.array_position(Event.entities_involved, trial.trial_id) != None,
                    Event.deleted_at.is_(None)
                ).first()
                
                if existing:
                    events_skipped += 1
                    continue
                
                # Get entities involved (trial + sponsor companies)
                entities_involved = [trial.trial_id]
                sponsors = session.query(TrialSponsor).filter(
                    TrialSponsor.trial_id == trial.trial_id,
                    TrialSponsor.entity_type == 'company',
                    TrialSponsor.deleted_at.is_(None)
                ).all()
                for sponsor in sponsors:
                    if sponsor.entity_id not in entities_involved:
                        entities_involved.append(sponsor.entity_id)
                
                # Determine event date
                # Prefer status_verified_date, then completion_date, then last_updated, fallback to today
                event_date = None
                if trial.status_verified_date:
                    event_date = trial.status_verified_date
                elif trial.completion_date:
                    event_date = trial.completion_date
                elif trial.last_updated:
                    if isinstance(trial.last_updated, datetime):
                        event_date = trial.last_updated.date()
                    else:
                        event_date = trial.last_updated
                else:
                    # Fallback to today (approximate, but better than missing)
                    event_date = date.today()
                    logger.warning(
                        f"Trial {trial.nct_id} has no date info, using today as event_date"
                    )
                
                # Create event using EventService
                event_service.create_event(
                    event_type=event_type,
                    event_date=event_date,
                    entities_involved=entities_involved,
                    event_data={
                        'trial_id': str(trial.trial_id),
                        'nct_id': trial.nct_id,
                        'status': trial.status,
                        'backfilled': True,  # Mark as backfilled for transparency
                        'note': 'Created from trial status (no status change event existed)'
                    },
                    source_id=source_id,
                    confidence_score=0.9  # High confidence since it's from trial status
                )
                
                events_created += 1
                
                if events_created % 50 == 0:
                    session.commit()
                    logger.info(f"Created {events_created} events so far...")
                    
            except Exception as e:
                logger.error(f"Error processing trial {trial.nct_id}: {e}", exc_info=True)
                session.rollback()
                events_failed += 1
                continue
        
        # Final commit
        session.commit()
        
        logger.info("=" * 60)
        logger.info("Backfill complete!")
        logger.info(f"  Events created: {events_created}")
        logger.info(f"  Events skipped (already exist): {events_skipped}")
        logger.info(f"  Events failed: {events_failed}")
        logger.info(f"  Total trials processed: {len(failed_trials)}")
        logger.info("=" * 60)
        
        # Verify the fix
        total_failure_events = session.query(func.count(Event.event_id)).filter(
            Event.event_type.in_(list(status_to_event_type.values())),
            Event.deleted_at.is_(None)
        ).scalar()
        
        logger.info(f"\nVerification:")
        logger.info(f"  Failed trials: {len(failed_trials)}")
        logger.info(f"  Failure events: {total_failure_events}")
        
        if total_failure_events >= len(failed_trials):
            logger.info("  ✅ Match! All failed trials now have events.")
        else:
            logger.warning(
                f"  ⚠️  Still {len(failed_trials) - total_failure_events} trials without events"
            )


if __name__ == "__main__":
    try:
        backfill_missing_failure_events()
    except Exception as e:
        logger.error(f"Backfill failed: {e}", exc_info=True)
        sys.exit(1)

